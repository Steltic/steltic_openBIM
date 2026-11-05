import math
import pytest
from shapely.geometry import Polygon
from steltic_openbim.review_cases import evidence, scenario, build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module',params=('cfs10','cfs18'))
def actual(request):
    key=request.param; package=evidence(key)['package']; before=fingerprint(package)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(scenario(key)['answers']))))
    assert fingerprint(package)==before
    return model,package


def test_hold_down_bolts_reach_both_real_webs_and_offset_rod_clears_chord(actual):
    model,package=actual; count=0
    for c in model['connections']:
        if c['detail_ref']['id']!='review_sbmf_hold_down':continue
        scene=build_scene(model,package,c); parts={p['id']:p for p in scene['parts']}
        f=scene['fasteners'][0]
        assert f['count']==4 and f['diameter']==.75
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)
        for z in (f['points'][0][2],f['points'][-1][2]):
            chord=[Polygon(p) for p in section_polygons(parts['CHORD'],2,z)]
            rod=[Polygon(p) for p in section_polygons(parts['ROD'],2,z)]
            assert all(a.intersection(b).area<1e-8 for a in chord for b in rod),c['id']
        assert parts['CHORD']['member']['source_member_index']==0
        assert parts['ROD']['member']['source_member_index']==1
        count+=1
    assert count==40


def test_cast_anchors_are_short_and_story_couplers_follow_offset_rods(actual):
    model,_=actual; lookup={m['id']:m for m in model['members']}; counts=0
    for c in model['connections']:
        if c['detail_ref']['id']=='review_sbmf_hold_down' and c['parameters']['continuous']:
            rod=lookup[c['member_ids'][1]]
            assert [q[2] for q in rod['axis']]==[-12,2.5]
        if c['detail_ref']['id']=='review_rod_coupler':
            lower,upper=[lookup[mid] for mid in c['member_ids']]
            assert lower['axis'][1][:2]==upper['axis'][0][:2]==c['point'][:2]
            assert math.dist(lower['axis'][1],upper['axis'][0])==pytest.approx(.125)
            counts+=1
    assert counts==16
