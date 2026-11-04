import math
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_wall_straps import apply
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('rotate',[False,True])
@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('falling',[False,True])
def test_source_wall_strap_groups_contact_actual_plies_at_both_ends(rotate,side,falling):
    b=object.__new__(CaseModel);b.key='cfs5';b.members=[];b.connections=[];b.profiles={};b.used_records=set();b.changes=[]
    def pt(x,y,z):return [-y,x,z] if rotate else [x,y,z]
    prefix='LINE-L1-B1-'
    for j,x in enumerate((3,141)):
        b.member(prefix+'CH'+str(j),'2X600S200-97','chord',pt(x,0,.1),pt(x,0,107.9),1,'S',local_y=pt(1,0,0))
    for label,z,sign in [('BT',0,1),('TT',108,-1)]:b.member(prefix+label,'600T125-97','bottom_track' if sign>0 else 'top_track',pt(0,0,z),pt(144,0,z),1,'S',local_y=[0,0,sign])
    pid=b.custom('STRAP','flat',dict(width=3,thickness=.0566))
    m=b.member(prefix+'X-1-0',pid,'strap',pt(0,side*3,108 if falling else 0),pt(144,side*3,0 if falling else 108),1,'S')
    b.ends(m,'review_cfs_strap',['connections/end'],parameters=dict(story=1))
    apply(b)
    model=dict(pilot='cfs5',members=b.members,profiles=list(b.profiles.values()))
    package=dict(design_records=[dict(id='connections/end',data=dict(selection='9 No. 12 strap-end screws'))])
    for c in b.connections:
        s=build_scene(model,package,c);parts={p['id']:p for p in s['parts']}
        assert parts['CHORD']['member']['axis'][1][2]>parts['CHORD']['member']['axis'][0][2]
        assert s['front_depth_sign']==-1
        assert len(next(f for f in s['fasteners'] if f['id']=='FS')['points'])==9
        assert sum(len(f['points']) for f in s['fasteners'] if f['id'].startswith('CHORD-S'))==5
        assert sum(len(f['points']) for f in s['fasteners'] if f['id'].startswith('TRACK-S'))==6
        assert 'CHORD-PACK' in parts
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(rotate,side,falling,c['id'],f['id'],name,q)
    assert len(b.changes)==1 and all(math.dist(o,[0,0,0])>3 for o in m['end_offsets'])
