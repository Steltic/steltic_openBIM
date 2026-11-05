import math
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cases import evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs6_chord_floors import apply
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('direction',[0,1])
def test_scheduled_chord_pack_interrupts_both_real_joists_and_clips_every_cut_end(direction):
    source=evidence('cfs6');spec=scenario('cfs6')
    b=CaseModel('cfs6',source['package'],dict(design_scenario=dict(id='cfs6',answers_sha256=fingerprint(spec['answers']))),source)
    b.endpoint_links=[];b.levels=[(0,'Base',0),(1,'L1',120),(2,'Roof',240)]
    # XSB's actual row is independent of this rotated contact fixture.
    xy=lambda x,y,z:[x,y,z] if direction==0 else [y,x,z]
    for sign in (-1,1):
        local=xy(0,-sign,0)
        j=b.member('J'+str(sign),'1000S250-68','joist',xy(0,sign*3.96435,112.78125),xy(168,sign*3.96435,112.78125),1,'S',
                   local_y=local,parallel_wall_line='XSB',parallel_wall_axis_in=0)
        b.ends(j,'review_cfs_joist')
    for key,z,level,sign in (('LT',107.69635,1,-1),('UT',120.0283,2,1)):
        b.member(key,'600T150-54','top_track' if sign<0 else 'bottom_track',xy(0,0,z),xy(168,0,z),level,local_y=[0,0,sign])
    above=b.member('XSB-L2-B1-CH0','2X600S200-54','chord',xy(59,0,120.1),xy(59,0,220),2,local_y=xy(1,0,0))
    apply(b)
    blocks=[m for m in b.members if m['kind']=='chord_squash_pack'];assert len(blocks)==1
    block=blocks[0];assert math.dist(*block['axis'])==pytest.approx(10)
    selected=b.profiles[block['profile_id']]['components']
    assert sorted(c['profile_id'] for c in selected)==['600S200-54','600S200-68','600S200-68','600S200-68']
    assert above['profile_id']=='2X600S200-54' # Floor row, not a copied upper chord.
    joists=[m for m in b.members if m['kind']=='joist'];assert len(joists)==4
    assert all(m['source_unsplit_axis']==[xy(0,m['axis'][0][1-direction],112.78125),xy(168,m['axis'][0][1-direction],112.78125)] for m in joists)
    clips=[c for c in b.connections if c['detail_ref']['id']=='review_chord_floor_clip'];assert len(clips)==4
    ids={m['id'] for m in b.members};assert all(set(c['member_ids'])<=ids for c in b.connections)
    model=dict(pilot='cfs6',members=b.members,profiles=list(b.profiles.values()),connections=b.connections)
    for c in clips:
        scene=build_scene(model,source['package'],c);parts={p['id']:p for p in scene['parts']}
        assert [len(f['points']) for f in scene['fasteners']]==[4,4]
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(direction,c['id'],name,q)
    assert len([r for r in b.endpoint_links if r['connection_id'] in {c['id'] for c in clips}])==4
