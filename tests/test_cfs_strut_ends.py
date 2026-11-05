import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_rod_actual_receivers import contact


@pytest.mark.parametrize('key',['cfs17','cfs19','cfs30'])
def test_every_strut_clip_uses_actual_receiver_and_contacts_all_declared_parts(key):
    package=evidence(key)['package'];s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    members={m['id']:m for m in model['members']};seen=set();struts=set()
    for c in model['connections']:
        par=c.get('parameters',{}).get('actual_cfs_strut_end')
        if not par:continue
        m,h=[members[mid] for mid in c['member_ids']];struts.add(m['id'])
        assert m['end_offsets'][par['end']][1]*par['into']>0
        shape=(m['profile_id'],h['profile_id'],par['into'],par['clip_side'])
        if shape in seen:continue
        seen.add(shape);scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        assert parts['STRUT']['member']['source_member_index']==0
        assert parts['RAFTER']['member']['source_member_index']==1
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(key,c['id'],f['id'],target,q)
    assert struts=={m['id'] for m in model['members'] if m['kind']=='eave_strut'}
    assert len(seen)>=4
