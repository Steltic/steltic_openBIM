import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.review_assemblies import build_scene
from steltic_openbim.drawing_workflow import fingerprint


@pytest.fixture(scope='module')
def cfs19():
    p=evidence('cfs19')['package']
    return p,build_model(p,dict(design_scenario=dict(id='cfs19',answers_sha256=fingerprint(scenario('cfs19')['answers']))))


def test_six_ply_column_is_not_reused_as_a_nonexistent_track(cfs19):
    package,model=cfs19
    c=next(c for c in model['connections'] if c['id']=='SIDE-X-0-0-False:0')
    scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
    assert 'TRACK' not in parts
    assert parts['RECEIVER']['profile_id']=='6X1400S300-118'
    assert parts['RECEIVER']['member']['axis']==[[0,0,0],[0,0,42]]
    assert sum(f['count'] for f in scene['fasteners'] if f['id']=='FS')==19
    assert sum(f['count'] for f in scene['fasteners'] if f['id'].startswith('FP'))==12
    assert all(f['basis']=='A' for f in scene['fasteners'] if f['id'].startswith('FP'))
    assert c['member_ids']==['SIDE-X-0-0-False','F1-C0']
    assert parts['COLLECTOR']['basis']=='A'


def test_crossing_straps_remain_continuous_and_have_clear_separate_planes(cfs19):
    _,model=cfs19;members={m['id']:m for m in model['members']}
    first=members['SIDE-X-0-0-False'];second=members['SIDE-X-0-0-True']
    profiles={p['id']:p for p in model['profiles']};t=profiles[first['profile_id']]['dimensions']['thickness']
    distance=abs(first['end_offsets'][0][0]-second['end_offsets'][0][0])
    assert distance-t==pytest.approx(.0625)
    assert first['axis']==[[0,0,0],[0,240,264]]
    assert len([m for m in model['members'] if m['id']==first['id']])==1
    assert first['local_y'][0]==pytest.approx(0)


def test_roof_strap_uses_its_actual_pitched_rafter_on_both_sides_of_ridge(cfs19):
    package,model=cfs19;members={m['id']:m for m in model['members']}
    for c in model['connections']:
        if not c['id'].startswith('ROOF-X-'):continue
        assert c['parameters']['physical_strap_end']
        assert members[c['parameters']['receiver_member_id']]['kind']=='rafter'
        scene=build_scene(model,package,c)
        assert not any(p['id']=='TRACK' for p in scene['parts'])
