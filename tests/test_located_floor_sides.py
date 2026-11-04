from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
import pytest
from test_floor_opening_contact import contact


@pytest.mark.parametrize('kind',['joist','truss_chord'])
def test_floor_track_uses_framing_over_the_actual_run_instead_of_the_closest_outside_station(kind):
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='C',family='channel',dimensions=dict(d=2.5 if kind=='truss_chord' else 10,b=1.625,t=.0713,lip=.375))]
    members=[dict(id='TRACK',kind='top_track',profile_id='T',axis=[[0,0,0],[64,0,0]],local_y=[0,0,-1],end_offsets=[[0,0,0]]*2,level=1)]
    for name,x in [('OUT',-3),('IN',20)]:
        for edge,z in ([('B',1.3),('T',14)] if kind=='truss_chord' else [('B',5.05)]):
            members.append(dict(id='TRUSS-'+name+'-'+edge,kind=kind,profile_id='C',axis=[[x,0,z],[x,32,z]],local_y=[1,0,0],end_offsets=[[0,0,0]]*2,level=1))
    c=dict(id='joint',point=[0,0,0],member_ids=['TRACK'],detail_ref=dict(id='review_cfs_floor'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c])
    bind(model)
    ids='truss_ids' if kind=='truss_chord' else 'joist_ids'
    assert set(c['parameters']['physical_floor_stack'][ids])==({'TRUSS-IN-B','TRUSS-IN-T'} if kind=='truss_chord' else {'TRUSS-IN-B'})
    scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    assert scene['fasteners']
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(f['id'],name,q)


@pytest.mark.parametrize('mirror',[-1,1])
def test_cut_track_end_uses_a_declared_return_clip_instead_of_a_screw_in_space(mirror):
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.07,lip=.625))]
    members=[]
    for tag,z,kind,ly in [('L',0,'top_track',[0,0,-1]),('U',12,'bottom_track',[0,0,1])]:
        members.append(dict(id=tag,kind=kind,profile_id='T',axis=[[0,0,z],[-mirror*24,0,z]],local_y=ly,end_offsets=[[0,0,0]]*2,level=1))
    members.append(dict(id='JOIST',kind='joist',profile_id='J',axis=[[0,0,5.1],[0,32,5.1]],local_y=[mirror,0,0],end_offsets=[[0,0,0]]*2,level=1))
    c=dict(id='joint',point=[0,0,0],member_ids=['L'],detail_ref=dict(id='review_cfs_floor'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c])
    before=[m['axis'][:] for m in members]
    bind(model);scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    assert [m['axis'] for m in members]==before
    assert len([p for p in scene['parts'] if p['id'].startswith('END-') and p['id'].endswith(('-WEB','-FOOT'))])==4
    assert not any(f['id'].startswith(('LOWER-S','UPPER-S')) for f in scene['fasteners'])
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(mirror,f['id'],name,q)
    assert any('capacity verification' in note and 'return clip' in note for note in scene['notes'])


def test_collinear_floor_joint_uses_real_members_on_both_sides():
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.07,lip=.625))]
    members=[]
    for side in (-1,1):
        ends=sorted((0,side*24))
        for tag,z,kind,pid,ly in (('L',0,'top_track','T',[0,0,-1]),('U',12,'bottom_track','T',[0,0,1]),('J',5.05,'joist','J',[0,1,0])):
            members.append(dict(id=tag+str(side),kind=kind,profile_id=pid,axis=[[x,0,z] for x in ends],local_y=ly,end_offsets=[[0,0,0]]*2,level=1))
    c=dict(id='joint',point=[0,0,0],member_ids=['L1'],detail_ref=dict(id='review_cfs_floor'),design_record_ids=[],parameters={})
    m=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c])
    bind(m)
    data=c['parameters']['physical_floor_stack']
    assert set(data['joist_ids'])=={'J-1','J1'}
    assert set(data['track_ids'])=={'L-1','L1','U-1','U1'}
    scene=build_scene(m,dict(design_records=[]),c)
    screws=[q for q in scene['fasteners'] if q['id'].startswith('RIM-')]
    assert len(screws)==4
    for group in screws:
        xs=[q[0] for q in group['points']]
        assert all(x<0 for x in xs) or all(x>0 for x in xs)
        parts={p['id']:p for p in scene['parts']}
        for q in group['points']:
            for name in group['connects']:assert contact(parts[name],group,q)


@pytest.mark.parametrize('mirror',[-1,1])
def test_built_up_trimmer_fasteners_act_on_each_real_channel_web(mirror):
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.1,lip=.625)),
              dict(id='PAIR',family='built_up',dimensions={},components=[
                  dict(profile_id='J',offset=[-.1125,0],rotation_deg=180),
                  dict(profile_id='J',offset=[.1125,0],rotation_deg=0)])]
    members=[dict(id='TRACK',kind='top_track',profile_id='T',axis=[[0,0,0],[-mirror*24,0,0]],
                  local_y=[0,0,-1],end_offsets=[[0,0,0]]*2,level=1),
             dict(id='TRIMMER',kind='opening_trimmer',profile_id='PAIR',axis=[[0,0,5.1],[0,32,5.1]],
                  local_y=[mirror,0,0],end_offsets=[[0,0,0]]*2,level=1)]
    c=dict(id='joint',point=[0,0,0],member_ids=['TRACK'],detail_ref=dict(id='review_cfs_floor'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c])
    bind(model);scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    assert len([p for p in scene['parts'] if p['id'].startswith('STIFF') and p['kind']=='member'])==2
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(mirror,f['id'],name,q)


def test_truss_seat_cannot_be_replaced_by_a_nearby_floor_trimmer():
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='C',family='channel',dimensions=dict(d=2.5,b=1.625,t=.0713,lip=.375)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.07,lip=.625))]
    members=[dict(id='TRACK',kind='top_track',profile_id='T',axis=[[-32,0,0],[32,0,0]],local_y=[0,0,-1],end_offsets=[[0,0,0]]*2,level=1)]
    for name,z in [('B',1.3),('T',14)]:
        members.append(dict(id='TRUSS-'+name,kind='truss_chord',profile_id='C',axis=[[0,0,z],[0,32,z]],local_y=[1,0,0],end_offsets=[[0,0,0]]*2,level=1))
    members.append(dict(id='TRIMMER',kind='opening_trimmer',profile_id='J',axis=[[16,0,5.1],[16,32,5.1]],local_y=[1,0,0],end_offsets=[[0,0,0]]*2,level=1))
    c=dict(id='seat',point=[0,0,1.3],member_ids=['TRUSS-B'],detail_ref=dict(id='review_roof_seat'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c]);bind(model)
    data=c['parameters']['physical_floor_stack']
    assert data['joist_ids']==[] and set(data['truss_ids'])=={'TRUSS-B','TRUSS-T'}
    scene=build_scene(model,dict(design_records=[]),c)
    assert scene['fasteners'] and all(p.get('member',{}).get('profile_id')!='J' for p in scene['parts'])


def test_floor_receiver_is_over_both_track_tiers_when_one_tier_has_an_offset_end():
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.07,lip=.625))]
    members=[]
    for tag,z,lo,ly in [('LOW',0,0,[0,0,-1]),('UP',12,-20,[0,0,1])]:
        members.append(dict(id=tag,kind='top_track' if tag=='LOW' else 'bottom_track',profile_id='T',
                            axis=[[lo,0,z],[32,0,z]],local_y=ly,end_offsets=[[0,0,0]]*2,level=1))
    for tag,x in [('OUT',-4.5),('IN',11.5)]:
        members.append(dict(id=tag,kind='joist',profile_id='J',axis=[[x,0,5.1],[x,32,5.1]],local_y=[1,0,0],end_offsets=[[0,0,0]]*2,level=1))
    c=dict(id='floor',point=[0,0,0],member_ids=['LOW'],detail_ref=dict(id='review_cfs_floor'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c]);bind(model)
    assert c['parameters']['physical_floor_stack']['joist_ids']==['IN']


@pytest.mark.parametrize('case,cid',[('cfs13','NB-L4-B1-TT'),('cfs14','M-L4-B1-TT')])
def test_delegated_six_inch_roof_chord_bears_above_track_instead_of_through_it(case,cid):
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    package=evidence(case)['package'];spec=scenario(case)
    model=build_model(package,dict(design_scenario=dict(id=case,source_sha256=spec['source_sha256'],answers_sha256=fingerprint(spec['answers']))))
    c=next(c for c in model['connections'] if c['id']==cid);model['connections']=[c];bind(model)
    scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
    assert scene['fasteners'] and any(i['kind']=='compression_bearing' for i in scene['interfaces'])
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(case,f['id'],name,q)
    assert any(r['kind']=='delegated_roof_chord_bearing_datum' for r in model['changes'])


@pytest.mark.parametrize('reverse',[False,True])
def test_corner_joist_bears_on_the_actual_parallel_track_after_perpendicular_cutback(reverse):
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.07,lip=.625))]
    members=[dict(id='PAR',kind='top_track',profile_id='T',axis=[[0,0,0],[24,0,0]],local_y=[0,0,-1],end_offsets=[[0,0,0]]*2,level=1),
             dict(id='CUT',kind='top_track',profile_id='T',axis=[[0,6,0],[0,24,0]],local_y=[0,0,-1],end_offsets=[[0,0,0]]*2,level=1),
             dict(id='JOIST',kind='joist',profile_id='J',axis=[[0,0,5.05],[24,0,5.05]],local_y=[0,1,0],end_offsets=[[0,0,0]]*2,level=1)]
    if reverse:members[-1].update(axis=members[-1]['axis'][::-1],local_y=[0,-1,0])
    c=dict(id='joint',point=[0,0,5.05],member_ids=['JOIST'],detail_ref=dict(id='review_cfs_joist'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c])
    bind(model);data=c['parameters']['physical_floor_stack']
    assert data['track_ids']==['PAR'] and data['joist_ids']==['JOIST']
    assert 'CUT' not in c['member_ids']
    scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    assert len(scene['fasteners'])==1
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(reverse,f['id'],name,q)
