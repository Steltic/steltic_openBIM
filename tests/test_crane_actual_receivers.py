import copy
from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.fixture(scope='module')
def case():
    p=evidence('hr33')['package'];before=copy.deepcopy(p);s=scenario('hr33')
    m=build_model(p,dict(design_scenario=dict(id='hr33',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    assert p==before
    return m,p


def test_crane_seats_own_one_actual_girder_end_and_four_source_bolts(case):
    model,p=case;lookup={m['id']:m for m in model['members']}
    cs=[c for c in model['connections'] if c.get('parameters',{}).get('actual_crane_joint')=='seat']
    assert len(cs)==40
    assert set(Counter(c['member_ids'][0] for c in cs).values())=={2}
    for c in cs:
        scene=build_scene(model,p,c);parts={v['id']:v for v in scene['parts']}
        assert parts['BEARING']['bounds'][2][1]==pytest.approx(parts['RUNWAY']['bounds'][2][0])
        bolts=scene['fasteners'][0];assert len(bolts['points'])==4 and bolts['diameter']==.875
        assert lookup[c['member_ids'][1]]['kind']=='crane_bracket'
        for q in bolts['points']:
            for name in bolts['connects']:assert contact(parts[name],bolts,q),(c['id'],name,q)


def test_tie_uses_actual_column_and_cap_with_source_vertical_plate_and_no_plate_weld(case):
    model,p=case
    cs=[c for c in model['connections'] if c.get('parameters',{}).get('actual_crane_joint')=='tie']
    assert len(cs)==40
    for c in cs:
        scene=build_scene(model,p,c);parts={v['id']:v for v in scene['parts']};bounds=parts['TIE']['bounds']
        assert [v[1]-v[0] for v in bounds]==pytest.approx([.375,24,8])
        assert all('TIE' not in w['connects'] for w in scene['welds'])
        assert len(scene['fasteners'])==2
        for f in scene['fasteners']:
            assert len(f['points'])==2 and f['diameter']==.75
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)


def test_clip_bolts_meet_actual_cap_and_rail_remains_floating(case):
    model,p=case
    cs=[c for c in model['connections'] if c.get('parameters',{}).get('actual_crane_joint')=='rail_clip']
    assert len(cs)==280
    for c in (cs[0],cs[13],cs[140],cs[-1]):
        scene=build_scene(model,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)
        assert all(i['kind']=='floating_rail_clip' for i in scene['interfaces'])


def test_bracket_geometry_does_not_claim_source_nine_inch_check_verifies_larger_lever(case):
    m,_=case;changes=[c for c in m['changes'] if c['kind']=='crane_actual_bracket_receiver']
    assert len(changes)==22 and all(c['adopted_reaction_lever_in']>c['source_reaction_lever_in'] for c in changes)
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_crane_joint')=='bracket']
    assert all(c['engineering_status']=='source_condition_mismatch_proposed_fit_not_verified' for c in cs)
