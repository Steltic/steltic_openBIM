from steltic_openbim.connection_details import prepare


def test_floor_extract_uses_the_final_opening_face_cut_not_the_uncut_joist():
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.5,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.1,lip=.625))]
    members=[]
    for name,kind,pid,axis,ly in [
        ('TRACK','top_track','T',[[-24,0,0],[24,0,0]],[0,0,-1]),
        ('JOIST','joist','J',[[0,0,5.1],[0,24,5.1]],[1,0,0]),
        ('HEADER','opening_header','J',[[-24,24,5.1],[24,24,5.1]],[0,1,0])]:
        members.append(dict(id=name,kind=kind,profile_id=pid,axis=axis,local_y=ly,end_offsets=[[0,0,0],[0,0,0]],level=1,basis='A'))
    cs=[dict(id='BEARING',point=[0,0,5.1],member_ids=['JOIST'],detail_ref=dict(id='review_cfs_joist'),design_record_ids=[],parameters={},parts=[]),
        dict(id='CUT',point=[0,24,5.1],member_ids=['JOIST','HEADER'],detail_ref=dict(id='test_floor_opening'),design_record_ids=[],parameters={},parts=[])]
    model=dict(pilot='cfs-fixture',profiles=profiles,members=members,connections=cs,member_schedule=[])
    prepare(model,dict(design_records=[]))
    joist=members[1];actual_end=joist['axis'][1][1]+joist['end_offsets'][1][1]
    assert actual_end<24
    floor=next(c for c in model['connections'] if c['id']=='BEARING')
    receiver=next(r for r in floor['parameters']['physical_floor_stack']['receivers'] if r['member_id']=='JOIST')
    assert max(q[1] for q in receiver['axis'])==actual_end
    assert len([r for r in model['changes'] if r['kind']=='opening_clip_actual_receiver'])==1
