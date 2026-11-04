import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_supplements import floor_openings


def test_open_web_opening_frame_uses_actual_chord_height_and_whole_support_span():
    b=object.__new__(CaseModel);b.key='cfs2';b.members=[];b.connections=[];b.panels=[];b.openings=[];b.walls=[];b.used_records=set();b.notes=[];b.changes=[]
    b.profiles={'CH':dict(id='CH',family='channel',dimensions=dict(d=2.5,b=1.625,t=.0713,lip=.375)),
        '1200S250-97':dict(id='1200S250-97',family='channel',dimensions=dict(d=12,b=2.5,t=.1017,lip=.625))}
    b.pack('1200S250-97',2,label='2X1200S250-97')
    for level in (1,2):b.panel('F'+str(level),'floor',[[0,0,300*level],[204,0,300*level],[204,360,300*level],[0,360,300*level]],3.5,level,'A')
    for kind,z in [('T',295.25),('B',285.75)]:
        for i in range(4):
            m=b.member('OW-1-96-0-'+kind+str(i),'CH','truss_chord',[i*51,96,z],[(i+1)*51,96,z],1,'S')
            b.ends(m,'review_truss_node')
    floor_openings(b)
    frame=[m for m in b.members if m['id'].startswith('STAIR-1-1-FRAME')]
    assert len(frame)==4
    # 3.5in source finish, 12in full truss depth; the 12in header contains both
    # actual 2.5in chords. The former .75in finish datum missed the bottom one.
    for m in frame:
        assert m['axis'][0][2]==pytest.approx(290.5)
    trimmers=[m for m in frame if m['kind']=='opening_trimmer']
    assert len(trimmers)==2
    assert all([m['axis'][0][0],m['axis'][1][0]]==[0,204] for m in trimmers)
    assert all(c['detail_ref']['id']=='review_cfs_joist' for c in b.connections if c['member_ids'][0] in {m['id'] for m in trimmers})


def test_opening_at_existing_truss_node_attaches_surviving_chord_to_header():
    b=object.__new__(CaseModel);b.key='cfs2';b.members=[];b.connections=[];b.panels=[];b.openings=[];b.walls=[];b.used_records=set();b.notes=[];b.changes=[];b.profiles={}
    for k in (1,2):b.panel('F'+str(k),'floor',[[0,0,300*k],[204,0,300*k],[204,360,300*k],[0,360,300*k]],3.5,k,'A')
    for i in range(3):b.member('OW-1-96-0-B'+str(i),'250S162-68','truss_chord',[i*68,96,285.75],[(i+1)*68,96,285.75],1,'S')
    web=b.member('OW-1-96-0-W1','250S137-43','truss_web',[68,96,285.75],[136,96,295.25],1,'S')
    b.connection('NODE-68','review_truss_node',[68,96,285.75],['OW-1-96-0-B0','OW-1-96-0-B1',web])
    floor_openings(b)
    c=next(c for c in b.connections if c['id']=='NODE-68')
    assert c['member_ids']==['OW-1-96-0-B0']
    assert c['detail_ref']['id']=='test_floor_opening'
    assert any(r['kind']=='opening_panel_point_attachment' for r in b.changes)


def test_top_occupied_floor_keeps_its_opening_when_roof_has_its_own_kind():
    b=object.__new__(CaseModel);b.key='cfs7';b.members=[];b.connections=[];b.panels=[];b.openings=[];b.walls=[];b.used_records=set();b.notes=[];b.changes=[];b.profiles={}
    b.levels=[(0,'BASE',0),(1,'FLOOR',132),(2,'ROOF',246)]
    b.panel('F1','floor',[[0,0,130.5],[204,0,130.5],[204,360,130.5],[0,360,130.5]],23/32,1,'S')
    b.panel('R2','roof',[[0,0,246],[204,0,246],[204,360,246],[0,360,246]],19/32,2,'S')
    floor_openings(b)
    assert any(o['kind']=='stair' and o['level']==1 for o in b.openings)
    assert not any(o['level']==2 for o in b.openings)
