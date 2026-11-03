import copy
import numpy as np
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from steltic_openbim.drawing_workflow import write_json
from steltic_openbim.ifc_export import export_drawing
from steltic_openbim.ifc_handoff import top_surfaces
from steltic_openbim.ifc_import import build_review
from test_ifc import drawing_source


def export_panel(tmp_path,panel,openings):
    folder,package,_=drawing_source(tmp_path)
    physical=copy.deepcopy(package['physical'])
    physical.update(panels=[panel],openings=openings)
    write_json(folder/'design_model.json',physical)
    before=(folder/'design_model.json').read_bytes()
    path=tmp_path/'panel.ifc';report=export_drawing(folder,path)
    assert not report['schema_errors']
    assert (folder/'design_model.json').read_bytes()==before
    review=build_review(path,{'units':'auto'})
    assert review['counts']['unrendered']==0
    return report,{o['name']:o for o in review['objects']}


def test_sloped_reversed_sheet_retains_real_hole_on_reimport(tmp_path):
    panel=dict(id='roof',kind='roof',vertices=[[0,240,120],[240,240,180],[240,0,180],[0,0,120]])
    hole=dict(id='skylight',host_id='roof',vertices=[[60,60,135],[120,60,150],[120,120,150],[60,120,135]])
    report,objects=export_panel(tmp_path,panel,[hole])
    assert report['counts']['panel_opening_cuts']==1
    surface=top_surfaces(objects['roof'])
    assert len(surface)==1 and len(surface[0]['holes_m'])==1
    polygon=Polygon([p[:2] for p in surface[0]['boundary_m']],[[p[:2] for p in h] for h in surface[0]['holes_m']])
    assert polygon.area==pytest.approx((240*240-60*60)*.0254**2,abs=1e-5)
    for p in surface[0]['boundary_m']+surface[0]['holes_m'][0]:
        assert p[2]==pytest.approx(120*.0254+p[0]/4,abs=1e-6)
    assert objects['skylight']['properties']['Steltic_Coordination']['OpeningCutInHost'] is True


def test_door_at_wall_edge_is_a_notch_not_a_filled_panel(tmp_path):
    panel=dict(id='wall',kind='wall',vertices=[[0,0,0],[240,0,0],[240,0,120],[0,0,120]])
    opening=dict(id='door',host_id='wall',vertices=[[48,0,0],[84,0,0],[84,0,84],[48,0,84]])
    report,objects=export_panel(tmp_path,panel,[opening]);obj=objects['wall']
    union=unary_union([Polygon([[obj['vertices'][i][k] for k in (0,2)] for i in f]) for f in obj['faces']])
    expected=Polygon([(0,0),(240,0),(240,120),(0,120)]).difference(Polygon([(48,0),(84,0),(84,84),(48,84)]))
    from shapely.affinity import scale
    assert union.symmetric_difference(scale(expected,xfact=.0254,yfact=.0254,origin=(0,0))).area<1e-8
    assert report['counts']['panel_opening_cuts']==1


def test_unhosted_offset_and_outside_openings_are_not_guessed_cuts(tmp_path):
    panel=dict(id='floor',kind='floor',vertices=[[0,0,0],[240,0,0],[240,240,0],[0,240,0]])
    base=dict(id='offset',host_id='floor',vertices=[[24,24,1],[48,24,1],[48,48,1],[24,48,1]])
    outside=dict(id='outside',host_id='floor',vertices=[[230,24,0],[260,24,0],[260,48,0],[230,48,0]])
    unhosted=dict(id='unhosted',vertices=[[24,24,0],[48,24,0],[48,48,0],[24,48,0]])
    report,objects=export_panel(tmp_path,panel,[base,outside,unhosted])
    assert report['counts']['panel_opening_cuts']==0
    assert {w['id'] for w in report['warnings']}=={'offset','outside'}
    assert top_surfaces(objects['floor'])[0]['holes_m']==[]
    assert all(objects[k]['properties']['Steltic_Coordination']['OpeningCutInHost'] is False for k in ('offset','outside','unhosted'))


def test_closed_solid_bottom_is_not_promoted_to_top_surface():
    obj=dict(vertices=[[0,0,0],[2,0,0],[2,2,0],[0,2,0],[0,0,1],[2,0,1],[2,2,1],[0,2,1]],
             faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4]])
    surfaces=top_surfaces(obj)
    assert len(surfaces)==1
    assert {p[2] for p in surfaces[0]['boundary_m']}=={1}
