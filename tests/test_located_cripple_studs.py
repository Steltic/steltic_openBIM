import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs_occurrences import bind
from steltic_openbim.assembly_templates import build_scene


def test_cripple_stud_binds_actual_sill_instead_of_invented_track():
    p=evidence('cfs1')['package'];m=build_model(p,dict(design_scenario=dict(id='cfs1',answers_sha256=fingerprint(scenario('cfs1')['answers']))))
    bind(m)
    assert not any(s['id']=='ORD-0-336.0-3-0-S21-0' for s in m['members'])
    c=next(c for c in m['connections'] if c['id']=='ORD-0-336.0-3-0-S22-0:1')
    selected=c['parameters']['physical_stud_support'];lookup={s['id']:s for s in m['members']}
    assert lookup[selected['member_id']]['kind']=='opening_sill'
    scene=build_scene(m,p,c)
    assert {s['id'] for s in scene['parts'] if s.get('member')}=={'STUD','OPENING'}
    stud=next(s['member'] for s in scene['parts'] if s['id']=='STUD')
    assert max(q[2] for q in stud['axis'])==pytest.approx(0)
    assert all(s['basis']=='A' for s in scene['fasteners'])
