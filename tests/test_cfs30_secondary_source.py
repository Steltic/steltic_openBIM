from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint


def test_cold_storage_uses_its_distinct_source_purlin_and_girt_laps_and_girt_depth():
    source=evidence('cfs30');s=scenario('cfs30')
    model=build_model(source['package'],dict(design_scenario=dict(id='cfs30',answers_sha256=fingerprint(s['answers']))))
    schedules={r['id']:r for r in source['calc']['schedules']}
    assert 'lapped 18 in. each side' in schedules['sched-purlin']['note']
    assert '600Z250-54' in schedules['sched-girt']['note'] and 'lapped 15 in.' in schedules['sched-girt']['note']
    purlins=[m for m in model['members'] if m['kind']=='purlin' and not m.get('full_length_nested')]
    girts=[m for m in model['members'] if m['kind']=='girt' and m['id'].startswith('G-')]
    assert purlins and girts
    assert {m['lap_in'] for m in purlins}=={18}
    assert {m['profile_id'] for m in girts}=={'600Z250-54'}
    span=source['configuration']['cfg']['spacing_ft']*12
    interior_p=next(m for m in purlins if m['id']=='P-0-2')
    interior_g=next(m for m in girts if m['id']=='G-0-2-30')
    assert interior_p['axis'][1][1]-interior_p['axis'][0][1]==span+36
    assert interior_g['axis'][1][1]-interior_g['axis'][0][1]==span+30
