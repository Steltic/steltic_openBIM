import math
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cases import evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs6_floor_framing import apply,bearing_receivers
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def fixture(along,flange,station=8):
    source=evidence('cfs6');spec=scenario('cfs6')
    b=CaseModel('cfs6',source['package'],dict(design_scenario=dict(id='cfs6',answers_sha256=fingerprint(spec['answers']))),source)
    b.levels=[(0,'Base',0),(1,'L1',120),(2,'Roof',240)]
    positions=(0,168,336) if along==0 else (1080,1248,1416)
    def xy(v,w,z):return [v,w,z] if along==0 else [w,v,z]
    for i,(lo,hi) in enumerate(zip(positions,positions[1:])):
        ly=[0.,0.,0.];ly[1-along]=flange
        m=b.member('J'+str(i),'1000S250-68','joist',xy(lo,station,112.78),xy(hi,station,112.78),1,local_y=ly)
        b.ends(m,'review_cfs_joist')
    for i,v in enumerate(positions):
        for level,z,sign in ((1,107.75,-1),(2,120,1)):
            lo=0 if station==0 else -40
            m=b.member(f'T{i}-{level}','600T150-54','top_track' if sign<0 else 'bottom_track',xy(v,lo,z),xy(v,40,z),level,local_y=[0,0,sign])
            for offset in m['end_offsets']:offset[2]=sign*.0566/2
    apply(b)
    return b,source['package']


@pytest.mark.parametrize('along',[0,1])
@pytest.mark.parametrize('flange',[-1,1])
def test_source_rim_and_tight_squash_blocks_have_real_steel_contact(along,flange):
    b,package=fixture(along,flange);bearing_receivers(b,b.levels)
    model=dict(pilot='cfs6',members=b.members,profiles=list(b.profiles.values()),connections=b.connections)
    blocks=[m for m in b.members if m['kind']=='squash_block']
    assert len(blocks)==4
    for block in blocks:
        assert math.dist(*block['axis'])==pytest.approx(10-2*.0713)
        assert block['source_nominal_length_in']==9.86
        assert block['profile_id'] in ('600S162-54','600S162-68')
    assert not any(c['id'] in ('J0:0','J0:1','J1:0','J1:1') for c in b.connections)
    for c in b.connections:
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(along,flange,c['id'],f['id'],name,q)


def test_source_bearing_uses_track_after_the_actual_corner_cut():
    b,package=fixture(0,1,station=0)
    for m in b.members:
        if m['kind']=='bottom_track':m['end_offsets'][0][1]=3.25
    bearing_receivers(b,b.levels)
    blocks=[c for c in b.connections if c['detail_ref']['id']=='review_source_floor_block']
    assert blocks and all('upper_track_index' not in c['parameters'] for c in blocks)
    # These edge joists still have their rim and lower steel support; no upper
    # wall or screws are invented where its real cut track is absent.
    assert all('lower_track_index' in c['parameters'] and 'rim_index' in c['parameters'] for c in blocks)
