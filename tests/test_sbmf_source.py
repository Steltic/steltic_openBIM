from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint


@pytest.mark.parametrize('key,count',(('cfs10',162),('cfs18',306)))
def test_each_saved_analysis_element_maps_once_to_its_actual_frame(key,count):
    p=evidence(key)['package'];before=fingerprint(p);s=scenario(key)
    m=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(p)==before
    claimed=Counter(a for v in m['members'] for a in v.get('analysis_ids',[]))
    assert len(claimed)==count and set(claimed.values())=={1}
    assert set(claimed)=={v['id'] for v in p['analysis']['elements']}
    for v in m['members']:
        if v.get('analysis_ids'):
            frame=int(v['id'].split('-')[1])+1
            assert all(a.startswith(f'cfs:frame:{frame}:') for a in v['analysis_ids'])
    conns={c['id']:c for c in m['connections']}
    for link in m['connection_endpoint_links']:
        assert link['member_id'] in conns[link['connection_id']]['member_ids']
