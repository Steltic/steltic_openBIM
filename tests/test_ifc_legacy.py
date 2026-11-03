import json
import copy
import numpy as np
import pytest

from steltic_openbim.ifc_export import export_drawing,opening_boundary
from steltic_openbim.ifc_import import build_review
from steltic_openbim.drawing_workflow import write_json
from test_ifc import drawing_source


@pytest.mark.parametrize('plane,expected',[
    ('xy',[[12,24,36],[60,24,36],[60,84,36],[12,84,36]]),
    ('xz',[[12,24,36],[60,24,36],[60,24,96],[12,24,96]]),
    ('yz',[[12,24,36],[12,72,36],[12,72,96],[12,24,96]]),
])
def test_legacy_opening_plane_units_roundtrip(tmp_path,plane,expected):
    folder,package,state=drawing_source(tmp_path)
    opening=dict(id='legacy-opening',plane=plane,x_ft=1,y_ft=2,z_ft=3,width_ft=4,height_ft=5,level=1)
    physical=dict(package['physical'],openings=[opening])
    write_json(folder/'design_model.json',physical)
    before=(folder/'design_model.json').read_bytes()
    report=export_drawing(folder,tmp_path/'return.ifc')
    assert report['counts']['opening_references']==1
    review=build_review(tmp_path/'return.ifc',{'units':'auto'})
    obj=next(o for o in review['objects'] if o['name']=='legacy-opening')
    points=np.asarray([p for line in obj['lines'] for p in line])
    assert np.allclose(points.min(axis=0),np.asarray(expected).min(axis=0)*.0254)
    assert np.allclose(points.max(axis=0),np.asarray(expected).max(axis=0)*.0254)
    assert 'HostSourceId' not in obj['properties']['Steltic_Coordination']
    assert (folder/'design_model.json').read_bytes()==before


def test_explicit_polygon_takes_precedence_and_invalid_legacy_data_is_rejected():
    polygon=[[0,0,0],[1,0,0],[0,1,0]]
    assert opening_boundary(dict(vertices=polygon,plane='bad'))==polygon
    for change in ({'width_ft':0},{'height_ft':float('nan')},{'plane':'ab'},{'z_ft':None}):
        with pytest.raises(ValueError):
            opening_boundary(dict(id='O',plane='xy',x_ft=0,y_ft=0,z_ft=0,width_ft=1,height_ft=1) | change)


def test_source_grid_and_datums_survive_without_moving_members(tmp_path):
    from steltic_openbim.drawing_workflow import initial_state
    from steltic_openbim.ifc_handoff import grids
    from steltic_openbim.ifc_import import open_model,metadata
    folder,package,_=drawing_source(tmp_path)
    package['layout_evidence'].update(grid_x_in=[0,120],grid_y_in=[0,240],levels_in=[0,144,288])
    write_json(folder/'source.json',package);write_json(folder/'state.json',initial_state(package,1))
    out=tmp_path/'grids.ifc';report=export_drawing(folder,out);model=open_model(out)
    axes=grids(model,1.)
    assert len(axes)==4
    assert np.allclose(axes[1]['points_m'],[[3.048,0,0],[3.048,6.096,0]])
    assert sorted(s['elevation_m'] for s in metadata(model)['storeys'])==pytest.approx([0,3.6576,7.3152])
    review=build_review(out,{'units':'auto'})
    beam=next(o for o in review['objects'] if o['ifc_class']=='IfcBeam')
    assert np.allclose(beam['bounds_m'],[[0,3.048],[-.0508,.0508],[-.1016,.1016]])


def test_repeated_geometry_and_properties_are_shared_without_moving_occurrences(tmp_path):
    import ifcopenshell
    import ifcopenshell.util.element as element_util
    folder,package,_=drawing_source(tmp_path)
    physical=copy.deepcopy(package['physical']);first=physical['members'][0]
    second=copy.deepcopy(first);second['id']='translated';second['axis']=[[x+120,y+180,z+36] for x,y,z in first['axis']]
    physical['members'].append(second);write_json(folder/'design_model.json',physical)
    path=tmp_path/'instances.ifc';report=export_drawing(folder,path)
    assert report['mesh_templates']==2  # shared beam plus the fixture's base plate
    model=ifcopenshell.open(str(path));assert len(model.by_type('IfcRepresentationMap'))==2
    products=model.by_type('IfcBeam');assert len(products)==2
    assert products[0].Representation.Representations[0].Items[0].MappingSource==products[1].Representation.Representations[0].Items[0].MappingSource
    props=[element_util.get_psets(p)['Steltic_Coordination'] for p in products]
    assert {p['SourceId'] for p in props}=={first['id'],'translated'}
    shared=[p for p in model.by_type('IfcPropertySingleValue') if p.Name=='SourceModelSHA256']
    # One shared value on member property sets; the project has its own record.
    assert len(shared)==2
    review=build_review(path,{'units':'auto'})
    boxes={o['properties']['Steltic_Coordination']['SourceId']:np.asarray(o['bounds_m']) for o in review['objects'] if o['ifc_class']=='IfcBeam'}
    assert np.allclose(boxes['translated']-boxes[first['id']],np.asarray([[120,120],[180,180],[36,36]])*.0254)
