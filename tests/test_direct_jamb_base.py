import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('height',[0,120])
def test_jamb_without_track_uses_explicit_proposed_slab_anchors_only_at_ground(height):
    b=object.__new__(CaseModel);b.key='cfs7';b.members=[];b.connections=[];b.profiles={};b.used_records=set()
    m=b.member('J','2X600S162-54','opening_jamb',[0,0,height],[0,0,height+92],1,'A',local_y=[0,1,0])
    b.ends(m,'test_wall_opening')
    model=dict(pilot='cfs7',members=b.members,connections=b.connections,profiles=list(b.profiles.values()))
    bind(model);c=model['connections'][0]
    assert bool(c.get('parameters',{}).get('direct_jamb_base'))==(height==0)
    assert not model['connections'][1].get('parameters',{}).get('direct_jamb_base')
    if height:return
    s=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in s['parts']}
    assert {p['member']['profile_id'] for p in s['parts'] if p.get('member')}=={m['profile_id']}
    for f in s['fasteners']:
        assert f['basis']=='A'
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(f['id'],name,q)
    assert any('No bottom track' in n and 'unverified' in n for n in s['notes'])


@pytest.mark.parametrize('kind',['ordinary_track','bottom_track'])
def test_upper_jamb_can_extend_the_actual_adjacent_track_beneath_its_foot(kind):
    b=object.__new__(CaseModel);b.key='cfs7';b.members=[];b.connections=[];b.profiles={};b.used_records=set()
    jamb=b.member('J','2X600S162-54','opening_jamb',[0,3,132],[0,3,224],2,'A',local_y=[0,1,0])
    track=b.member('T','600T150-54',kind,[0,6,132],[0,78,132],2,'A',local_y=[0,0,1]);b.ends(jamb,'test_wall_opening')
    model=dict(pilot='cfs7',members=b.members,connections=b.connections,profiles=list(b.profiles.values()))
    bind(model);c=model['connections'][0]
    assert c['parameters']['physical_jamb_base']['track']['member_id']=='T'
    assert track['end_offsets'][0][1]<-3
    assert track['axis']==[[0,6,132],[0,78,132]]
    scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(f['id'],name,q)
    assert len(model['changes'])==1
    bind(model);assert len(model['changes'])==1
