from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def test_extra_corridor_joist_is_declared_on_the_actual_off_grid_wall_axis():
    p=evidence('cfs2')['package'];s=scenario('cfs2')
    m=build_model(p,dict(design_scenario=dict(id='cfs2',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    change=next(c for c in m['changes'] if c['kind']=='adopted_corridor_wall_joist' and c['station_in']==204 and c['level']==1)
    member=next(v for v in m['members'] if v['id']==change['member_id'])
    assert [q[:2] for q in member['axis']]==[[204,372],[204,444]]
    assert member['profile_id']=='1200S162-68' and change['basis'].startswith('A:')
    assert 'capacity remain separately required' in change['basis']
    cid='ORD-1-204-1-0-0-T-0';c=next(c for c in m['connections'] if c['id']==cid);m['connections']=[c];bind(m)
    assert change['member_id'] in c['parameters']['physical_floor_stack']['joist_ids']
    scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(f['id'],name,q)
