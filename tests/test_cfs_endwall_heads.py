import copy,math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_rod_actual_receivers import contact


@pytest.mark.parametrize('key', ['cfs17','cfs19','cfs30'])
def test_wind_post_clips_contact_actual_post_and_sloping_outer_roof_flange(key):
    package=evidence(key)['package'];before=copy.deepcopy(package);s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    assert package==before
    connections=[c for c in model['connections'] if c.get('parameters',{}).get('actual_cfs_endwall_head')]
    assert len(connections)=={'cfs17':10,'cfs19':6,'cfs30':8}[key]
    members={m['id']:m for m in model['members']}
    for c in connections:
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        assert {p['member']['source_member_index'] for p in scene['parts'] if p.get('member')}==set(range(len(c['member_ids'])))
        for side in (-1,1):
            assert sum(len(f['points']) for f in scene['fasteners'] if f['id'].startswith('CLIP'+str(side)+'-FOOT'))==2
            post_bolts=next(f for f in scene['fasteners'] if f['id']=='CLIP'+str(side)+'-POST')
            assert len(post_bolts['points'])==2 and post_bolts['diameter']==.5
            assert post_bolts['slot']['travel_in']==1
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:
                    assert contact(parts[target],f,q),(key,c['id'],f['id'],target,q)
        assert any(r['member_id']==c['member_ids'][0] and r['connection_id']==c['id'] and r['end']=='end'
                   for r in model['connection_endpoint_links'])
    if key in ('cfs17','cfs19'):
        assert any(len(c['member_ids'])==3 for c in connections), 'Apex head must retain both actual roof slopes'
