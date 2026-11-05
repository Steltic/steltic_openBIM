import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_rod_actual_receivers import contact


def test_five_source_door_headers_connect_to_actual_frame_column_webs():
    package=evidence('cfs17')['package'];s=scenario('cfs17')
    model=build_model(package,dict(design_scenario=dict(id='cfs17',answers_sha256=fingerprint(s['answers']))))
    members={m['id']:m for m in model['members']}
    connections=[c for c in model['connections'] if c.get('parameters',{}).get('actual_cfs_door_header')]
    assert len(connections)==10
    for c in connections:
        header,column=[members[mid] for mid in c['member_ids']]
        assert header['profile_id']=='HSS4X4X1/8' and column['kind']=='column'
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        bolts=next(f for f in scene['fasteners'] if f['id']=='HEADER-BOLTS')
        assert len(bolts['points'])==2 and bolts['diameter']==.5
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(c['id'],f['id'],target,q)
    openings=[o for o in model['openings'] if o['id'].startswith('OH-')]
    assert len(openings)==5 and all(o['width_ft']==pytest.approx(10.4) for o in openings)
