from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Point

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.hr_joist_nodes import separate_bearing_ends
from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.review_hr_seats import roof


def test_shallow_endpost_keeps_six_screws_per_ply_and_distinct_node_plates():
    from shapely.geometry import Polygon
    from steltic_openbim.hr_joist_nodes import screw_stations,gussets
    profiles={'channel':dict(id='channel',family='channel',dimensions=dict(d=2.5,b=1.375,t=.055,lip=.375))}
    post=dict(id='post',profile_id='channel',axis=[[0,0,0],[0,0,16]],end_offsets=[[0,0,0],[0,0,0]])
    chord=dict(id='chord',profile_id='channel',axis=[[0,0,0],[30,0,0]],end_offsets=[[0,0,0],[0,0,0]])
    outlines=[]
    for elevation,sign in ((0.,1),(16.,-1)):
        ends=[(1,[0.,0.,sign],post),(2,[1.,0.,0.],chord)]
        layouts={i:screw_stations(v,[[.7071,0.,sign*.7071]],m,16,5)[:2] for i,v,m in ends}
        a=Assembly('node',profiles);gussets(a,profiles,ends,layouts)
        plate=next(p for p in a.parts if p['kind']=='plate')
        outline=Polygon([(v[0],v[2]+elevation) for v in plate['polygon']])
        for fastener in a.fasteners:
            assert len(fastener['points'])==6
            assert all(outline.buffer(-.49).covers(Point(q[0],q[2]+elevation)) for q in fastener['points'])
        outlines.append(outline)
    assert outlines[0].distance(outlines[1])>.0625


@pytest.mark.parametrize('reverse',[False,True])
def test_clockwise_and_counterclockwise_plate_rings_both_bound_positive_material(reverse):
    a=Assembly('plate',{});ring=[[0,0,0],[3,0,0],[3,0,2],[0,0,2]]
    p=a.polygon('P',ring[::-1] if reverse else ring,.75)
    total=sum(float(np.dot(face[0],np.cross(face[i],face[i+1])))/6
              for face in p['faces'] for i in range(1,len(face)-1))
    assert total==pytest.approx(4.5)


def mesh(part):
    vertices=[];faces=[]
    for polygon in part['faces']:
        faces.append(tuple(range(len(vertices),len(vertices)+len(polygon))))
        vertices.extend(polygon)
    return Mesh(np.asarray(vertices),tuple(faces))


def test_independent_joists_fit_inside_opposite_flange_tips_and_still_bear():
    profiles={'C':dict(id='C',family='channel',dimensions=dict(d=6,b=2,t=.1,lip=.5)),
              'W':dict(id='W',family='i',dimensions=dict(d=16,bf=12,tw=.5,tf=1))}
    members=[];connections=[]
    def member(name,kind,profile,axis,y):
        m=dict(id=name,kind=kind,profile_id=profile,axis=axis,local_y=y,end_offsets=[[0,0,0],[0,0,0]])
        members.append(m)
        return m
    host=member('girder','girder','W',[[0,-20,6],[0,20,6]],[1,0,0])
    for side in (-1,1):
        suffix=str(side)
        post=member('post'+suffix,'truss_web','C',[[0,0,0],[0,0,20]],[0,1,0])
        for z in (0,20):
            chord=member(f'chord{side}-{z}','truss_chord','C',[[0,0,z],[60*side,0,z]],[0,1,0])
            node=dict(id=f'node{side}-{z}',point=[0,0,z],parameters={},member_ids=[chord['id'],post['id']],
                      detail_ref={'id':'review_truss_node'},assembly_id='NODE')
            connections.append(node)
            if z==0:
                connections.append(dict(id='seat'+suffix,point=[0,0,0],parameters={},
                                        member_ids=[chord['id'],post['id'],host['id']],detail_ref={'id':'review_roof_seat'}))
    scene=dict(id='NODE',parts=[dict(kind='plate',faces=[[[-4,0,0],[4,0,0],[4,0,4],[-4,0,4]]])])
    model=dict(pilot='hr-any',profiles=list(profiles.values()),members=members,connections=connections,connection_assemblies=[scene])
    original=[deepcopy(m['axis']) for m in members]
    separate_bearing_ends(model)
    separate_bearing_ends(model)
    assert [m['axis'] for m in members]==original
    lookup={m['id']:m for m in members}
    for side in (-1,1):
        post=lookup['post'+str(side)]
        assert post['end_offsets']==[[side*10.0625,0,0]]*2
        seat=next(c for c in connections if c['id']=='seat'+str(side))
        assembly=Assembly('Independent seat',profiles)
        roof(SimpleNamespace(a=assembly,p=profiles,model=model,c=seat,params=seat['parameters'],
                             ms=[lookup[mid] for mid in seat['member_ids']]))
        parts={p['id']:p for p in assembly.parts}
        plane=([0,1,0],[0,0,1])
        girder=mesh(parts['SUPPORT']).section([1,0,0],2.5,plane)
        riser=mesh(parts['RISER']).section([1,0,0],2.5,plane)
        assert girder.intersection(riser).area<1e-4
        assert girder.distance(riser)<1e-5
        weld=next(w for w in assembly.welds if w['id']=='CHORD-SEAT')
        assert abs(weld['b'][1]-weld['a'][1])==pytest.approx(4)
        for part in (parts['CHORD'],parts['SEAT']):
            faces=part['faces']
            for q in (weld['a'],weld['b']):
                on_face=[f for f in faces if all(abs(p[2]-q[2])<1e-5 for p in f)]
                from shapely.geometry import Polygon
                assert min(Polygon([(p[0],p[1]) for p in f]).distance(Point(*q[:2])) for f in on_face)<1e-5
