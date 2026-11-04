import copy
import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_track_corners import apply
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons


def contact(part,f,q):
    axis=max(range(3),key=lambda i:abs(f['axis'][i]));other=[i for i in range(3) if i!=axis]
    point=Point([q[i] for i in other])
    for step in range(1,40):
        at=q[axis]+f['axis'][axis]*f['grip']*step/40
        if any(Polygon(poly).buffer(1e-7).covers(point) for poly in section_polygons(part,axis,at)):return True
    return False


@pytest.mark.parametrize('turn',[-1,1])
@pytest.mark.parametrize('up',[-1,1])
@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('braced',[False,True])
def test_tracks_cut_clear_and_each_corner_screw_contacts_both_sheets(turn,up,reverse,braced):
    b=object.__new__(CaseModel);b.key='cfs-test';b.members=[];b.connections=[];b.used_records=set();b.changes=[];b.notes=[]
    b.profiles={'T':dict(id='T',family='channel',dimensions=dict(d=6.1757,b=1.5,t=.0566,lip=0))}
    for index,(name,end) in enumerate([('Z' if braced else 'A',[60,0,0]),('B',[0,60*turn,0])]):
        axes=[[0,0,0],end]
        if reverse:axes.reverse()
        kind=('bottom_track' if up>0 else 'top_track') if braced and index==0 else 'ordinary_track'
        m=b.member(name,'T',kind,*axes,local_y=[0,0,up])
        m['end_offsets']=[[0,0,up*.025],[0,0,up*.025]]
    first=copy.deepcopy(b.members[0])
    apply(b);assert len(b.connections)==1
    assert b.members[0]==first
    assert all(q[2]==up*.025 for q in b.members[1]['end_offsets'])
    before=copy.deepcopy((b.members,b.connections,b.changes));apply(b)
    assert (b.members,b.connections,b.changes)==before
    model=dict(pilot=b.key,members=b.members,profiles=list(b.profiles.values()))
    scene=build_scene(model,dict(design_records=[]),b.connections[0]);parts={p['id']:p for p in scene['parts']}
    aa,bb=[parts[name]['bounds'] for name in ('TRACK1','TRACK2')]
    assert min(min(a[1],d[1])-max(a[0],d[0]) for a,d in zip(aa,bb))<-.12
    assert len(scene['fasteners'])==2
    for f in scene['fasteners']:
        for q in f['points']:
            for mid in f['connects']:assert contact(parts[mid],f,q),(turn,up,reverse,f['id'],mid,q)
