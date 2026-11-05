import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint


@pytest.fixture(scope='module')
def model():
    p=evidence('hr9')['package']
    return build_model(p,dict(design_scenario=dict(id='hr9',answers_sha256=fingerprint(scenario('hr9')['answers']))))


def test_final_collector_selections_override_only_their_actual_source_lines(model):
    selected=[m for m in model['members'] if m.get('source_collector_line')]
    assert len(selected)==156
    assert {m['profile_id'] for m in selected}=={'W24X68'}
    assert {m['source_collector_line'] for m in selected}=={'X-B','X-D','Y-3','Y-4','Y-5'}
    assert {m['analysis_profile_id'] for m in selected if 'analysis_profile_id' in m}=={'W24X55','W16X31'}
    for m in selected:
        assert 'members/collector-'+m['source_collector_line'] in m['design_record_ids']
    transfer=[m for m in model['members'] if m['kind'] in ('beam','moment_beam') and m['level']==12 and all(q[1]==336 and 672<=q[0]<=1344 for q in m['axis']) and m['axis'][0]!=m['axis'][1]]
    assert len(transfer)==4 and {m['profile_id'] for m in transfer}=={'W24X146'}


def test_no_field_splice_record_is_retained_on_its_one_piece_post(model):
    for pid in ('W14X211','W14X283'):
        posts=[m for m in model['members'] if m['kind']=='rocking_post' and m['profile_id']==pid]
        assert posts
        assert all('connections/conn-lateral_col-'+pid in m['design_record_ids'] for m in posts)
    dispositions=model['record_dispositions']
    assert {d['record_id'] for d in dispositions}=={'connections/conn-lateral_col-'+p for p in ('BOX34X34X2.5','BOX38X38X4','W14X193')}
    assert all(d['status']=='not_applicable' and d['evidence_member_ids'] for d in dispositions)
