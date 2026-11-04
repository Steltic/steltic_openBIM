from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene


def test_collinear_floor_joint_uses_real_members_on_both_sides():
    profiles=[dict(id='T',family='channel',dimensions=dict(d=6.2,b=1.25,t=.1,lip=0)),
              dict(id='J',family='channel',dimensions=dict(d=10,b=2,t=.07,lip=.625))]
    members=[]
    for side in (-1,1):
        ends=sorted((0,side*24))
        for tag,z,kind,pid,ly in (('L',0,'top_track','T',[0,0,-1]),('U',12,'bottom_track','T',[0,0,1]),('J',5,'joist','J',[0,1,0])):
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
