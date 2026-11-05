from types import SimpleNamespace
from steltic_openbim.review_cfs6_endpoint_links import apply


def test_endpoint_references_require_nearby_hardware_bound_to_the_same_member():
    m=dict(id='J',kind='joist',axis=[[0,0,0],[100,0,0]],end_offsets=[[0,0,0],[0,0,0]])
    def c(id,mid,x):return dict(id=id,member_ids=[mid],point=[x,0,0],detail_ref=dict(id='review_source_floor_block'))
    b=SimpleNamespace(key='cfs6',members=[m],connections=[c('near','J',4),c('remote','J',50),c('wrong','OTHER',100)],endpoint_links=[])
    apply(b)
    assert [(r['member_id'],r['end'],r['connection_id']) for r in b.endpoint_links]==[('J','start','near')]
    apply(b);assert len(b.endpoint_links)==1


def test_late_bound_receiver_and_offset_joist_joint_are_linked():
    from steltic_openbim.review_cfs6_endpoint_links import bind
    track=dict(id='T',kind='ordinary_track',axis=[[0,0,0],[50,0,0]],end_offsets=[[0,0,0],[0,0,0]])
    joist=dict(id='J',kind='joist',axis=[[0,10,0],[10,10,0]],end_offsets=[[0,0,0],[0,0,0]])
    model=dict(pilot='cfs6',members=[track,joist],connections=[
        dict(id='stud',member_ids=['STUD','T'],point=[8,0,0],detail_ref=dict(id='cfs_stud')),
        dict(id='joist',member_ids=['J','HOST'],point=[.001,10,0],detail_ref=dict(id='review_cfs_joist'))])
    bind(model)
    assert {(r['member_id'],r['end'],r['connection_id']) for r in model['connection_endpoint_links']}=={
        ('T','start','stud'),('J','start','joist')}
