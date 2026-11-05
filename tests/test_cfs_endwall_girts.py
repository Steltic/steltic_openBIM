import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_rod_actual_receivers import contact


@pytest.mark.parametrize('key',['cfs17','cfs19','cfs30'])
def test_endwall_girt_clips_bind_actual_columns_posts_and_opening_jambs(key):
    package=evidence(key)['package'];s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    members={m['id']:m for m in model['members']};seen=set();kinds=set()
    for c in model['connections']:
        if not c.get('parameters',{}).get('actual_cfs_endwall_girt'):continue
        m,h=[members[mid] for mid in c['member_ids']];kinds.add(h['kind']);par=c['parameters']['actual_cfs_endwall_girt']
        shape=(m['profile_id'],h['profile_id'],tuple(h['local_y']),par['side'])
        if shape in seen:continue
        seen.add(shape);scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        assert parts['GIRT']['member']['source_member_index']==0
        assert parts['RECEIVER']['member']['source_member_index']==1
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(key,c['id'],f['id'],target,q)
    assert kinds=={'column','endwall_post','opening_jamb'}
    assert len(seen)>=6
