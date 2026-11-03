import json
import numpy as np
from test_ifc import drawing_source
from steltic_openbim.drawing_workflow import initial_state,write_json
from steltic_openbim.ifc_export import export_drawing
from steltic_openbim.ifc_handoff import grids
from steltic_openbim.ifc_import import build_review,metadata,open_model


def test_cfs_layout_datums_survive_without_any_member_level_labels(tmp_path):
    folder,package,_=drawing_source(tmp_path);package['module']='CFS'
    package['layout_evidence']['levels_in']=[0,144]
    for member in package['physical']['members']:member.pop('level',None)
    write_json(folder/'source.json',package);write_json(folder/'state.json',initial_state(package,1))
    path=tmp_path/'cfs.ifc';export_drawing(folder,path)
    assert [s['elevation_m'] for s in metadata(open_model(path))['storeys']]==[0,3.6576]


def test_rotated_source_grid_names_datums_and_fingerprint_survive(tmp_path):
    folder,package,_=drawing_source(tmp_path);package['module']='CFS'
    reference=dict(basis='Architectural reference, not inferred column centrelines',source_ifc_sha256='a'*64,
        levels=[dict(level=0,name='Ground',elevation_in=0),dict(level=1,name='Platform',elevation_in=144)],
        grids=[dict(id='A',label='A',direction='U',points_in=[[0,0,0],[120,120,0]]),
               dict(id='1',label='1',direction='V',points_in=[[0,120,0],[120,0,0]])])
    package['reference_system']=reference;package['require_connection_parts']=True
    write_json(folder/'source.json',package);write_json(folder/'state.json',initial_state(package,1))
    path=tmp_path/'source-reference.ifc';report=export_drawing(folder,path);assert not report['schema_errors']
    model=open_model(path);axes=grids(model,1.)
    assert [a['label'] for a in axes]==['A','1']
    assert np.allclose(axes[0]['points_m'],[[0,0,0],[3.048,3.048,0]])
    assert [s['name'] for s in metadata(model)['storeys']]==['Ground','Platform']
    import ifcopenshell.util.element
    properties=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert json.loads(properties['ReferenceSystem'])==reference
    assert properties['RequireConnectionParts'] is True
    review=build_review(path,dict(units='auto'))
    beam=next(o for o in review['objects'] if o['ifc_class']=='IfcBeam')
    assert np.allclose(beam['bounds_m'],[[0,3.048],[-.0508,.0508],[-.1016,.1016]])
