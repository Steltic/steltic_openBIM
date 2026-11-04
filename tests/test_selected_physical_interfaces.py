import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene


def building(key):
    p=evidence(key)['package']
    return p,build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(scenario(key)['answers']))))


def test_heavier_embedded_box_is_an_actual_piece_not_only_a_drawing_substitute():
    p,m=building('hr9');members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    cases=[c for c in m['connections'] if c['detail_ref']['id']=='review_base' and any(mid.endswith(':embedded') for mid in c['member_ids'])]
    assert cases
    for c in cases:
        shaft,embedded=[members[mid] for mid in c['member_ids'][:2]]
        assert embedded['axis'][1]==shaft['axis'][0]
        assert profiles[embedded['profile_id']]['dimensions']['t']>profiles[shaft['profile_id']]['dimensions']['t']
        scene=build_scene(m,p,c);drawn={v['profile_id'] for v in scene['parts'] if v.get('member')}
        assert {shaft['profile_id'],embedded['profile_id']}<=drawn


def test_workshop_column_splices_follow_the_workshop_floor_not_odd_global_levels():
    _,m=building('hr13')
    cs=[c for c in m['connections'] if 'connections/conn-lateral_col-W14X68' in c['design_record_ids']]
    assert len(cs)==8
    assert {c['point'][2] for c in cs}=={288}


def test_tmd_support_design_and_every_supplier_leg_end_have_actual_receivers():
    p,m=building('hr26');members={v['id']:v for v in m['members']};cs={c['id']:c for c in m['connections']}
    beams=[v for v in m['members'] if v['id'].startswith('TMD-SUPPORT-')]
    assert len(beams)==2 and all('members/tmd-support-W24X68' in v['design_record_ids'] for v in beams)
    links={(v['member_id'],v['end']):v['connection_id'] for v in m['connection_endpoint_links']}
    for leg in [v for v in m['members'] if v['kind']=='equipment_leg' and v['id'].startswith('TMD-')]:
        for end in ('start','end'):
            c=cs[links[leg['id'],end]];assert leg['id'] in c['member_ids']
            scene=build_scene(m,p,c);assert len([v for v in scene['parts'] if v.get('member')])==2
            assert all(v['basis']=='A' for v in scene['fasteners'])


def test_pg_pickup_uses_the_actual_whole_girder_once_and_keeps_fabrication_specification():
    p,m=building('hr19');c=next(c for c in m['connections'] if c['detail_ref']['id']=='review_pg_pickup');scene=build_scene(m,p,c)
    receivers=[v for v in scene['parts'] if v.get('member')]
    assert len(receivers)==2 and any(v['profile_id']=='PG84X1108' for v in receivers)
    assert not {'PG-TOP','PG-BOTTOM','PG-WEB'} & {v['id'] for v in scene['parts']}
    assert any('5/16 in flange-to-web fillets' in note for note in scene['notes'])


def test_plain_and_boxed_columns_cannot_share_a_splice_receiver_variant():
    from steltic_openbim.connection_details import prepare
    p,m=building('hr12');prepare(m,p);members={v['id']:v for v in m['members']};scenes={s['id']:s for s in m['connection_assemblies']}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_splice':continue
        expected=2*sum(bool(members[mid].get('boxing_thickness_in')) for mid in c['member_ids'] if members[mid]['kind']=='column')
        actual=sum(v['id'].startswith('BOX') and bool(v.get('member')) for v in scenes[c['assembly_id']]['parts'])
        assert actual==expected,c['id']


def test_clipping_a_bearing_cylinder_produces_closed_faces_without_zero_edges():
    import math
    from steltic_openbim.assembly_scene import Assembly,clip_part
    a=Assembly('Bearing',{});p=a.cylinder('C',[0,0,0],[0,1,0],24,24)
    clip_part(p,[0,0,1],6.25)
    assert all(math.dist(v,w)>1e-7 for f in p['faces'] for v,w in zip(f,f[1:]+f[:1]))
    assert any(all(v[2]==pytest.approx(6.25) for v in f) for f in p['faces'])


def test_skew_plate_cut_through_an_existing_edge_keeps_a_closed_cap():
    from collections import Counter
    from steltic_openbim.assembly_scene import Assembly,clip_part
    a=Assembly('Skew',{});p=a.box('PLATE',[0,.125,-12],[5,.25,9])
    clip_part(p,[1,-1,0],-.125)
    point=lambda v:tuple(round(x,7) for x in v)
    edges=Counter(tuple(sorted((point(v),point(w)))) for face in p['faces'] for v,w in zip(face,face[1:]+face[:1]))
    assert set(edges.values())=={2}
    assert any(len(f)==4 and all(v[0]-v[1]==pytest.approx(-.125) for v in f) for f in p['faces'])


def test_mirrored_chamfer_corners_have_compatible_upright_receiver_directions():
    from steltic_openbim.connection_details import prepare
    from steltic_openbim.pilots.model import sub,unit,dot,cross
    p,m=building('hr12');prepare(m,p);members={v['id']:v for v in m['members']};scenes={s['id']:s for s in m['connection_assemblies']}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_chamfer':continue
        beam=members[c['member_ids'][0]];column=next(members[mid] for mid in c['member_ids'] if members[mid]['kind']=='column')
        ray=unit(sub(max(beam['axis'],key=lambda q:sum((q[i]-c['point'][i])**2 for i in range(3))),c['point']))
        cy=column['local_y'];cx=cross(cy,[0,0,1]);local=[dot(ray,v) for v in (cx,cy)]
        drawn=next(q['member'] for q in scenes[c['assembly_id']]['parts'] if q['id']=='BEAM')
        direction=unit(sub(*drawn['axis'][::-1]))
        assert direction[:2]==pytest.approx(local)
        assert all(q[2]<0 for q in drawn['axis']), 'Beam centroid remains below top of steel at every corner'
