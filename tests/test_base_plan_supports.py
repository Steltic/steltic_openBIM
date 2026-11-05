from steltic_openbim.review_pdf import base_members,is_base_connection


def test_differential_embedment_does_not_remove_shallow_column_bases_from_plan():
    members=[];connections=[]
    for index,base in enumerate((-156,-114,0,24)):
        mid=str(index)
        members.append(dict(id=mid,axis=[[index*240,0,base],[index*240,0,168]],end_offsets=[[0,0,0],[0,0,0]],kind='column',level=1))
        connections.append(dict(id='B'+mid,member_ids=[mid],point=[index*240,0,base],detail_ref=dict(id='review_base')))
    members.append(dict(id='UPPER',axis=[[0,0,168],[0,0,336]],end_offsets=[[0,0,0],[0,0,0]],kind='column',level=2))
    model=dict(members=members,connections=connections,levels=[(0,'BASE',0)],bounds=[(0,720),(0,240),(-156,336)])
    assert {m['id'] for m in base_members(model)}=={'0','1','2','3'}


def test_hr9_plan_keeps_every_actual_foundation_column_and_embedded_piece():
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    s=scenario('hr9');p=evidence('hr9')['package']
    m=build_model(p,dict(design_scenario=dict(id='hr9',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    required={mid for c in m['connections'] if c['detail_ref']['id']=='review_base' for mid in c['member_ids']}
    shown={v['id'] for v in base_members(m)}
    assert required and required<=shown
    assert len([v for v in base_members(m) if v['kind']=='column'])>=27
    lookup={v['id']:v for v in m['members']}
    calls=[c for c in m['connections'] if is_base_connection(c,lookup)]
    assert calls and all(c['detail_ref']['id'] in ('review_base','review_plate_base') for c in calls)
