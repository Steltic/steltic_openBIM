import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_assemblies import build_scene


@pytest.fixture(scope='module')
def building():
    p=evidence('cfs1')['package']
    m=build_model(p,dict(design_scenario=dict(id='cfs1',answers_sha256=fingerprint(scenario('cfs1')['answers']))))
    return p,m,{v['id']:v for v in m['members']}


def test_actual_rods_reach_their_drawn_foundation_plate_and_floor_couplers(building):
    package,m,members=building
    foundations=[c for c in m['connections'] if c['detail_ref']['id']=='review_rod_foundation']
    couplers=[c for c in m['connections'] if c['detail_ref']['id']=='review_rod_coupler']
    assert foundations and couplers
    for c in foundations:
        rod=next(members[mid] for mid in c['member_ids'] if members[mid]['kind']=='hold_down_rod')
        assert rod['axis'][0][2]==pytest.approx(c['point'][2]-c['parameters']['embedment'])
        assert c['source_context_records'] and not c['design_record_ids']
    for c in couplers:
        lower,upper=[members[mid] for mid in c['member_ids']]
        assert math.dist(lower['axis'][1],upper['axis'][0])==pytest.approx(.125)
        assert lower['level']+1==upper['level']
        scene=build_scene(m,package,c)
        assert [p['member']['profile_id'] for p in scene['parts'][:2]]==[lower['profile_id'],upper['profile_id']]
        assert all(w['kind']=='THREADED' for w in scene['welds'])
    assert len([v for v in m['connection_endpoint_links'] if 'coupler' in v['connection_id']])==2*len(couplers)


def test_hold_down_has_no_floating_duplicate_coupler(building):
    package,m,_=building
    c=next(c for c in m['connections'] if c['detail_ref']['id']=='review_cfs_hold_down')
    scene=build_scene(m,package,c)
    assert not any(p['id']=='COUPLER' for p in scene['parts'])
    assert any(p['id']=='NUT' for p in scene['parts'])
