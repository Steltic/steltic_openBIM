import copy
from steltic_openbim.review_cases import build_model,evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint


def test_every_cfs7_source_segment_and_layout_row_has_verified_occurrences():
    p=evidence('cfs7')['package'];before=copy.deepcopy(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs7',answers_sha256=fingerprint(scenario('cfs7')['answers']))))
    selected={r['id'] for r in p['design_records'] if r['table'] in ('segment_framing','braced_wall_layout')}
    assert len(selected)==36
    linked={r for v in m['members'] for r in v['design_record_ids']}
    assert selected<=linked,selected-linked
    assert not [v for v in m['changes'] if v['kind']=='source_wall_schedule_unbound' and v['record_id'] in selected]
    assert p==before
    for line in ('YN7','YS5'):
        walls=[w for w in m['wall_layouts'] if w['line']==line]
        assert len(walls)==6
        assert all(sorted(round(r['end_in']-r['start_in']) for r in w['runs'])==[120,168,168] for w in walls)
