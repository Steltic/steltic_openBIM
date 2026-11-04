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


def test_transfer_collectors_use_the_explicit_saved_line_checks_when_csv_axial_is_zero():
    p,m=building('hr12');members={v['id']:v for v in m['members']}
    expected={r['id'] for r in p['design_records'] if r['id'].startswith('members/collector-L9-')}
    located={r for v in m['members'] for r in v.get('design_record_ids',[])}
    assert expected<=located
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('collector') and members[c['member_ids'][0]]['level']==9]
    assert cs and any('connections/collector-irregularity-lines' in c['design_record_ids'] for c in cs)
    for c in cs:
        beam=members[c['member_ids'][0]]
        if 'members/collector-L9-GridF-W24X62' in beam['design_record_ids']:assert max(q[0] for q in beam['axis'])<=336
    assert all('connections/diaphragm-chords-L9' not in c['design_record_ids'] for c in m['connections'] if c['detail_ref']['id']=='review_deck_studs')


def test_top_and_bottom_rockers_keep_beam_datum_and_clear_the_actual_post():
    p,m=building('hr9');members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']};seen=set()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_rocker':continue
        upper=c['parameters']['inverted'];post,beam=[members[mid] for mid in c['member_ids'][:2]]
        key=(upper,post['profile_id'],beam['profile_id'])
        if key in seen:continue
        seen.add(key);scene=build_scene(m,p,c);depth=profiles[beam['profile_id']]['dimensions']['d']
        hbe=next(v['member'] for v in scene['parts'] if v['id']=='HBE')
        assert all(v[2]==pytest.approx(-depth/2) for v in hbe['axis'])
        end=1 if upper else 0;expected=-depth-10 if upper else 10
        assert post['end_offsets'][end][2]==pytest.approx(expected)
        local=next(v['member'] for v in scene['parts'] if v['id']=='POST')
        assert (max(v[2] for v in local['axis']) if upper else min(v[2] for v in local['axis']))==pytest.approx(expected)
    assert {k[0] for k in seen}=={False,True}


def test_transfer_chord_keeps_both_analysis_components_and_receives_actual_infill_and_brace():
    p,m=building('hr20');members={v['id']:v for v in m['members']};cs={v['id']:v for v in m['connections']}
    assert 'hr:element:1094' not in members
    chord=members['hr:element:1093']
    assert set(chord['analysis_ids'])=={'hr:element:1093','hr:element:1094'}
    assert {v['source_member_id'] for v in chord['analysis_design_evidence']}==set(chord['analysis_ids'])
    assert chord['analysis_component_roles']=={'hr:element:1093':'axial','hr:element:1094':'flexural'}
    c=cs['INF-FLOOR-9-840.0:1'];assert chord['id'] in c['member_ids']
    scene=build_scene(m,p,c);support=next(q['member'] for q in scene['parts'] if q['id']=='M1')
    assert support['profile_id']=='W14X665' and all(q[2]==pytest.approx(0) for q in support['axis'])
    c=cs['hr:element:1021:0'];assert 'hr:element:431' in c['member_ids'] and 'hr:element:430' not in c['member_ids']
    scene=build_scene(m,p,c);support=next(q['member'] for q in scene['parts'] if q['id']=='BEAM')
    assert support['profile_id']=='W14X665' and all(q[2]==pytest.approx(0) for q in support['axis'])


def test_embedded_transfer_building_bases_keep_selected_erection_anchors():
    p,m=building('hr20');seen=set()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_base':continue
        if not any(r in ('connections/conn-base-lateral_col-W14X808','connections/conn-base-lateral_col-W14X873') for r in c['design_record_ids']):continue
        seen.update(c['design_record_ids']);scene=build_scene(m,p,c)
        f=next(v for v in scene['fasteners'] if v['id']=='ERECTION-ANCHORS')
        assert f['diameter']==1.5 and f['count']==4
        assert 'F1554-36' in next(v['description'] for v in scene['parts'] if v['id']=='ERECTION-ANCHORS')
        plate=next(v for v in scene['parts'] if v['id']=='P1')
        for point in f['points']:
            assert min(plate['bounds'][i][1]-abs(point[i]) for i in (0,1))==pytest.approx(2.66)
    assert len(seen)==2
