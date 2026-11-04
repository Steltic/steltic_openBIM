import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.review_floor_openings import bind as opening_bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('case,cid,station,level',[
    ('cfs3','ORD-0-348.0-1-0-0-T-0',348,1),
    ('cfs12','X15-L8-B1-TT',180,8)])
def test_parallel_wall_off_regular_grid_has_declared_framing_and_actual_sheet_contact(case,cid,station,level):
    p=evidence(case)['package'];s=scenario(case)
    m=build_model(p,dict(design_scenario=dict(id=case,source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    change=next(v for v in m['changes'] if v['kind']=='adopted_parallel_wall_framing' and v['station_in']==station and v['level']==level)
    assert change['basis'].startswith('A:') and 'capacity' in change['basis']
    assert cid in change['source_wall_member_ids']
    added=[v for v in m['members'] if v['id'].startswith(change['member_prefix'])]
    assert added and all(q[1]==station for v in added for q in v['axis'])
    # Keep the adjacent regular grid too; the added member is not a relocation.
    prefix=f'OW-{level}-336-' if case=='cfs3' else f'J-{level}-168-'
    assert any(v['id'].startswith(prefix) for v in m['members'])
    opening_bind(m);c=next(v for v in m['connections'] if v['id']==cid);m['connections']=[c];bind(m)
    assert 'physical_floor_stack' in c['parameters']
    scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
    assert scene['fasteners']
    for f in scene['fasteners']:
        for q in f['points']:
            for joined in f['connects']:assert contact(parts[joined],f,q),(case,f['id'],joined,q)
