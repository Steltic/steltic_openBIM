import copy,math
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_hr_strut_bracing import apply,ends
from steltic_openbim.review_assemblies import build_scene
from test_floor_opening_contact import contact


def model(sign):
    b=object.__new__(CaseModel);b.key='hr30';b.members=[];b.connections=[];b.profiles={};b.used_records=set();b.changes=[]
    rid='connections/conn-strut-bracing-Y';b.records={rid:dict(id=rid,data=dict(components='HSS3X3X1/4 at 45 deg to HSS4X4X1/4 struts spanning 10 ft'))}
    for label,x in (('SOURCE',0),('ADJACENT',sign*120)):
        m=b.member(label,'W21X55','beam' if label=='SOURCE' else 'infill',[x,0,180],[x,480,180],1,'S')
        m['end_offsets']=[[0,0,-b.depth(m['profile_id'])/2]]*2
    s=b.member('SOURCE-ST0','HSS4X4X1/4','lateral_strut',[0,120,178],[sign*120,120,178],1,'S')
    k=b.member('SOURCE-KICK0','HSS3X3X1/4','flange_brace',[0,120,159.2],[sign*18.8,120,178],1,'S')
    b.ends(s,'review_angle_clip',[rid]);b.ends(k,'review_angle_clip',[rid]);return b


@pytest.mark.parametrize('sign',[-1,1])
def test_actual_two_beams_and_source_hss_are_bound_to_both_end_details(sign):
    b=model(sign);before=copy.deepcopy({m['id']:m['axis'] for m in b.members});apply(b)
    assert len(b.connections)==1 and len(b.endpoint_links)==4
    c=b.connections[0]
    assert c['member_ids']==['SOURCE','ADJACENT','SOURCE-ST0','SOURCE-KICK0']
    assert before=={m['id']:m['axis'] for m in b.members}
    beam,other,s,k=b.members
    assert s['profile_id']=='HSS4X4X1/4' and math.dist(*s['axis'])==120
    low,high=ends(k);assert abs(high[0]-low[0])==pytest.approx(high[2]-low[2])
    assert low[1]==high[1]==120.5
    package=dict(design_records=list(b.records.values()))
    scene=build_scene(dict(pilot='hr30',members=b.members,profiles=list(b.profiles.values())),package,c)
    parts={p['id']:p for p in scene['parts']}
    assert {k:parts[k]['member']['source_member_index'] for k in ('BEAM','ADJACENT','STRUT','KICKER')}=={'BEAM':0,'ADJACENT':1,'STRUT':2,'KICKER':3}
    assert len(scene['fasteners'])==4 and all(f['basis']=='A' and len(f['points'])==2 for f in scene['fasteners'])
    for f in scene['fasteners']:
        for pt in f['points']:
            for name in f['connects']:assert contact(parts[name],f,pt),(sign,f['id'],name,pt)
    assert max(q[2] for face in parts['ENDPLATE0']['faces'] for q in face)<=-b.profiles['W21X55']['dimensions']['tf']-.24999
    assert all(w['basis']=='A' for w in scene['welds'])


def test_missing_adjacent_beam_cannot_be_replaced_by_a_generic_receiver():
    b=model(1);b.members[:]=[m for m in b.members if m['id']!='ADJACENT']
    with pytest.raises(ValueError,match='No actual ten-foot adjacent beam'):apply(b)


def test_source_strut_checks_bind_only_the_actual_braced_bays_and_level_scope():
    from types import SimpleNamespace
    from steltic_openbim.review_design_bindings import apply as bind
    records={f'members/strut-{d}-{scope}-W21X68':dict(table='members',data=dict(inputs=dict(section='W21X68',role='collector')))
             for d in ('X','Y') for scope in ('floor','roof')}
    members=[]
    for level in (1,6):
        for label,xy in (('X',[[720,0],[1080,0]]),('Y',[[0,480],[0,960]]),('OTHER',[[360,0],[720,0]])):
            members.append(dict(id=f'{label}-{level}',profile_id='W21X68',kind='beam',level=level,
                                axis=[p+[level*100] for p in xy],design_record_ids=[]))
    b=SimpleNamespace(key='hr30',members=members,records=records,used_records=set(),
                      config=dict(SX=360,SY=480,XBAYS=[[2,0]],YBAYS=[[0,1]]))
    bind(b)
    for m in members:
        direction=m['id'].split('-')[0];scope='roof' if m['level']==6 else 'floor'
        assert m['design_record_ids']==([] if direction=='OTHER' else [f'members/strut-{direction}-{scope}-W21X68'])
    assert b.used_records==set(records)
