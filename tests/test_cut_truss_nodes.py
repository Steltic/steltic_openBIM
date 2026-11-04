import copy,math
import pytest
from steltic_openbim.review_floor_openings import bind
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.connection_details import prepare
from test_floor_opening_contact import contact


def model():
    profiles=[dict(id='CH',family='channel',dimensions=dict(d=2.5,b=1.625,t=.0713,lip=.375)),
        dict(id='WEB',family='channel',dimensions=dict(d=2.5,b=1.375,t=.0451,lip=.375)),
        dict(id='H',family='channel',dimensions=dict(d=12,b=2.5,t=.1017,lip=.625)),
        dict(id='PAIR',family='built_up',dimensions={},components=[dict(profile_id='H',offset=[-.11335,0],rotation_deg=180),dict(profile_id='H',offset=[.11335,0],rotation_deg=0)])]
    members=[]
    for name,kind,pid,aa,bb in [
        ('B1','truss_chord','CH',[-9.333333333,0,0],[0,0,0]),
        ('W1','truss_web','WEB',[-9.333333333,0,9.333333333*9.5/(68/3)],[0,0,0]),
        ('B2','truss_chord','CH',[0,0,0],[68/3,0,0]),
        ('W2','truss_web','WEB',[0,0,0],[68/3,0,9.5]),
        ('H','opening_header','PAIR',[-9.333333333,-20,4.75],[-9.333333333,20,4.75])]:
        members.append(dict(id=name,kind=kind,profile_id=pid,axis=[aa,bb],end_offsets=[[0,0,0],[0,0,0]],local_y=[-1,0,0] if name=='H' else [0,1,0],basis='A',level=1))
    connections=[dict(id='NODE',point=[0,0,0],member_ids=['B1','W1','B2','W2'],detail_ref=dict(id='review_truss_node'),design_record_ids=[],parameters={},parts=[])]
    for m in members[:2]:connections.append(dict(id='CUT-'+m['id'],point=m['axis'][0],member_ids=[m['id']],detail_ref=dict(id='test_floor_opening'),design_record_ids=[],parameters={},parts=[]))
    return dict(pilot='cfs-fixture',profiles=profiles,members=members,connections=connections,member_schedule=[])


@pytest.mark.parametrize('reverse',[False,True])
def test_sloping_opening_cut_preserves_web_workline_and_all_screws_hit_real_members(reverse):
    m=model();web=m['members'][1];before=copy.deepcopy(web['axis'])
    if reverse:web['axis'].reverse();web['local_y']=[0,-1,0]
    bind(m)
    a,b=web['axis'];physical=[[v+off for v,off in zip(q,o)] for q,o in zip(web['axis'],web['end_offsets'])]
    original=[bb-aa for aa,bb in zip(a,b)];actual=[bb-aa for aa,bb in zip(*physical)]
    ratio=actual[0]/original[0]
    assert actual==pytest.approx([v*ratio for v in original])
    assert web['axis']==(before[::-1] if reverse else before)
    for c in m['connections']:
        scene=build_scene(m,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        if c['id']=='NODE':
            from steltic_openbim.assembly_scene import section_polygons
            assert any(p.get('member') and section_polygons(p,scene['section_axis'],scene['section_at']) for p in scene['parts'])
            assert all(p['member']['source_member_index']==i for i,p in enumerate(p for p in scene['parts'] if p.get('member')))
            assert any('short cut-end proposal' in note and 'capacity verification' in note for note in scene['notes'])
            assert any(len(f['points'])<6 for f in scene['fasteners'])


def test_cut_end_node_does_not_share_a_longer_node_template():
    m=model()
    other=copy.deepcopy(m['members'][:4])
    for v in other:
        v['id']='LONG-'+v['id']
        for q in v['axis']:q[1]+=60
        if v['id']=='LONG-B1':v['axis'][0][0]=-68/3
        if v['id']=='LONG-W1':v['axis'][0][0]=-68/3;v['axis'][0][2]=9.5
    m['members']+=other
    m['connections'].append(dict(id='LONG-NODE',point=[0,60,0],member_ids=[v['id'] for v in other],detail_ref=dict(id='review_truss_node'),design_record_ids=[],parameters={},parts=[]))
    prepare(m,dict(design_records=[]))
    nodes=[c for c in m['connections'] if c['detail_ref']['id']=='review_truss_node']
    assert len({c['assembly_id'] for c in nodes})==2


def test_section_through_concave_cap_keeps_two_legs_without_filling_the_gap():
    from shapely.geometry import Point,Polygon
    from steltic_openbim.assembly_scene import Assembly,section_polygons
    assembly=Assembly('Concave cap',{})
    part=assembly.polygon('U',[[x,0,z] for x,z in [(0,0),(4,0),(4,4),(3,4),(3,1),(1,1),(1,4),(0,4)]],1)
    polygons=[Polygon(p) for p in section_polygons(part,2,2)]
    assert all(p.is_valid for p in polygons)
    assert any(p.covers(Point(.5,.5)) for p in polygons)
    assert any(p.covers(Point(3.5,.5)) for p in polygons)
    assert not any(p.covers(Point(2,.5)) for p in polygons)
