import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.pilots.geometry import member_faces
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact
from steltic_openbim.review_cfs_occurrences import bind


@pytest.mark.parametrize('key,floor_finish,height,prefix',[
    ('cfs10',1+23/32,132,'OFF-'),('cfs18',1.5+23/32,120,'MEZZ-')])
def test_source_floor_and_roof_stacks_share_exact_bearing_datums(key,floor_finish,height,prefix):
    package=evidence(key)['package'];before=fingerprint(package);s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(package)==before
    profiles={p['id']:p for p in model['profiles']}
    for level,finish in ((1,floor_finish),(2,19/32)):
        panel=next(p for p in model['panels'] if p['id']=='WING-FLOOR-'+str(level))
        assert panel['thickness_in']==pytest.approx(finish)
        assert panel['thickness_direction']=='negative_global_z'
        joists=[m for m in model['members'] if m['id'].startswith('WING-J-'+str(level)+'-')]
        tracks=[m for m in model['members'] if m['id'].startswith(prefix) and m['id'].endswith(str(level)+'TT')]
        assert joists and len(tracks)==4
        tops=[];bottoms=[]
        for joist in joists:
            points=[q for face in member_faces(joist,profiles) for q in face]
            tops.append(max(q[2] for q in points));bottoms.append(min(q[2] for q in points))
        assert tops==pytest.approx([level*height-finish]*len(joists))
        for track in tracks:
            bearing=[m for m in model['members'] if m['id'].startswith(track['id']+'-COLLECTOR')] if key=='cfs18' else [track]
            assert bearing
            for ply in bearing:
                top=max(q[2] for face in member_faces(ply,profiles) for q in face)
                assert top==pytest.approx(bottoms[0])
        east=2382 if key=='cfs18' else 2168
        assert any(j['axis'][0][0]==east for j in joists)
    lookup={m['id']:m for m in model['members']}
    for c in model['connections']:
        if c['detail_ref']['id']=='cfs_stud' and c['id'].endswith(':0'):
            m=lookup[c['member_ids'][0]]
            if m['id'].startswith(prefix+'S1-ST-'):
                assert c['point']==m['axis'][0]


@pytest.mark.parametrize('key',('cfs10','cfs18'))
def test_main_hall_ground_tracks_are_not_drawn_as_intermediate_floors(key):
    package=evidence(key)['package'];s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    bind(model);lookup={m['id']:m for m in model['members']};count=0
    for c in model['connections']:
        if c['detail_ref']['id'] not in ('review_cfs_sill','review_sbmf_track_anchor') or abs(c['point'][2])>.01 or lookup[c['member_ids'][0]]['level']!=3:continue
        scene=build_scene(model,package,c)
        assert {p['id'] for p in scene['parts'] if p.get('member')}=={'TRACK'}
        assert any(p['kind']=='concrete' for p in scene['parts'])
        count+=1
    assert count


@pytest.mark.parametrize('key',('cfs10','cfs18'))
def test_all_sbmf_wall_straps_attach_to_actual_chord_flange(key):
    package=evidence(key)['package'];s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    count=0
    for c in model['connections']:
        if not c.get('parameters',{}).get('physical_strap_end'):continue
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        assert len(c['member_ids'])==2
        assert next(m for m in model['members'] if m['id']==c['member_ids'][1])['kind']=='chord'
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        count+=1
    assert count>100
