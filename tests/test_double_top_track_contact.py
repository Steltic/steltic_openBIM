import copy
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_double_top_tracks import apply
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('rotate',[False,True])
@pytest.mark.parametrize('mil,count',[(54,24),(68,16)])
def test_source_double_tracks_and_splice_screws_touch_every_real_ply(rotate,mil,count):
    b=object.__new__(CaseModel);b.key='cfs6';b.members=[];b.connections=[];b.profiles={};b.used_records=set();b.changes=[];b.notes=[]
    line='P30' if rotate else 'XN';rid='collectors/collector-Y-P30' if rotate else 'collectors/collector-X-XN'
    source=dict(id=rid,data=dict(selection=f'2 x 600T200-54 top track, splices with {count} No. 10 screws each side',
        design_note=f'level 1 2 x 600T200-{mil} (example); level 4 2 x 600T200-54 (governing)'))
    b.records={rid:source};b.walls=[dict(line=line,direction='Y' if rotate else 'X',level=1,runs=[dict(position_in=0)])]
    def q(x,y,z):return [y,x,z] if rotate else [x,y,z]
    for j,(lo,hi) in enumerate(((0,54),(60,120))):
        t=b.member('TRACK'+str(j),'600T150-54','top_track',q(lo,0,100),q(hi,0,100),1,local_y=[0,0,-1]);t['end_offsets']=[[0,0,-.0283],[0,0,-.0283]]
    before=copy.deepcopy(source);apply(b)
    assert b.records[rid]==before
    assert len([m for m in b.members if m['profile_id']==f'600T200-{mil}'])==2
    assert len([m for m in b.members if m['profile_id']==f'600T200-{mil}-OUTER-FIT'])==2
    model=dict(pilot='cfs6',members=b.members,profiles=list(b.profiles.values()))
    package=dict(design_records=[source])
    for c in b.connections:
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        if c['parameters']['purpose']=='splice':assert sum(f['count'] for f in scene['fasteners'])==2*count
        for f in scene['fasteners']:
            for point in f['points']:
                for name in f['connects']:assert contact(parts[name],f,point),(rotate,mil,c['id'],f['id'],name,point)
