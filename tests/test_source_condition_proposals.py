import copy
import pytest
from steltic_openbim.review_cases import evidence, scenario, build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_assemblies import build_scene


def model(key):
    package=evidence(key)['package'];before=copy.deepcopy(package)
    result=build_model(package,dict(design_scenario=dict(id=key,
        answers_sha256=fingerprint(scenario(key)['answers']))))
    assert package==before
    return package,result


@pytest.fixture(scope='module')
def hr14():return model('hr14')


@pytest.fixture(scope='module')
def hr9():return model('hr9')


def test_boundary_corner_keeps_actual_brace_and_column_without_fictitious_beam(hr14):
    package,m=hr14;c=next(c for c in m['connections'] if c['id']=='hr:element:610:0')
    assert len(c['member_ids'])==2
    assert c['parameters']['unsupported_base_corner']['opposite_beam_id']=='hr:element:831'
    assert c['engineering_status']=='source_condition_mismatch_proposed_fit_not_verified'
    s=build_scene(m,package,c);parts={p['id']:p for p in s['parts']}
    assert 'BEAM' not in parts
    assert parts['SEAT']['basis']=='A'
    assert {'SEAT-STIFF-1','SEAT-STIFF1'}<=set(parts)
    assert s['source_record_ids']==c['design_record_ids']
    assert any('saved capacity checks do not verify' in note for note in s['notes'])
    welds={w['id']:w for w in s['welds']}
    assert welds['WGB']['connects']==['SEAT','GUSSET']
    assert welds['WGB']['size']==pytest.approx(.5625)
    assert welds['WGC']['size']==pytest.approx(.5625)


def test_perpendicular_splice_retains_sections_and_roll_with_explicit_plate_gap(hr9):
    package,m=hr9;c=next(c for c in m['connections'] if c['id']=='hr:element:332:splice')
    members={v['id']:v for v in m['members']};upper,lower=[members[i] for i in c['member_ids']]
    assert (upper['profile_id'],lower['profile_id'])==('W14X48','W14X550')
    assert upper['local_y']==[0,1,0] and lower['local_y']==[1,0,0]
    assert upper['end_offsets'][0][2]==.75 and lower['end_offsets'][1][2]==-.75
    assert c['design_record_ids']==[]
    assert c['source_context_records']==['connections/conn-gravity_col-W14X48']
    assert c['source_record_applicability'][0]['applies'] is False
    s=build_scene(m,package,c);parts={p['id']:p for p in s['parts']}
    assert parts['TRANSFER']['bounds']==[[-11,11],[-11,11],[-.75,.75]]
    assert parts['UPPER']['bounds'][2][0]==pytest.approx(.75)
    assert parts['LOWER']['bounds'][2][1]==pytest.approx(-.75)
    assert len(s['welds'])==6 and all(w['basis']=='A' for w in s['welds'])
    assert s['source_context']['record_ids']==c['source_context_records']
    assert any('separate design check' in note for note in s['notes'])


def test_proposals_do_not_reclassify_other_source_connections(hr9,hr14):
    for _,m in (hr9,hr14):
        proposals=[c for c in m['connections'] if c.get('engineering_status')==
                   'source_condition_mismatch_proposed_fit_not_verified']
        assert len(proposals)==1
