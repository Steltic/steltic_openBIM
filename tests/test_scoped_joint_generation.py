import math
from types import SimpleNamespace

import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.connection_cuts import drill_receivers
from steltic_openbim.flat_bar_crossings import plate_scene
from steltic_openbim.hr_pin_stack import make_stack,stack_positions
from steltic_openbim.pilots.model import unit


def test_selected_nine_ply_pin_and_two_independent_host_attachments():
    rows=[]
    for role,thickness,host in [('clevis_outer_left',2,'brace_end'),('cheek_left_1',1.3125,'primary_gusset_1'),
        ('primary_gusset_1',1.25,'host'),('cheek_right_1',1.3125,'primary_gusset_1'),('clevis_central',4,'brace_end'),
        ('cheek_left_2',1.3125,'primary_gusset_2'),('primary_gusset_2',1.25,'host'),('cheek_right_2',1.3125,'primary_gusset_2'),
        ('clevis_outer_right',2,'brace_end')]:
        rows.append(dict(role=role,thickness_in=thickness,material='ASTM A572 Grade 50',connected_to=host))
    source=dict(selected_stack=rows,pin_diameter_in=4,pin_hole_diameter_in=4.0625,pin_material='ASTM A434 Grade 4140 Class BD',
                grip_in=16.,clearance_between_moving_groups_in=.0625,receiving_leaves=2,cheek_side_in=11.,
                cheek_weld_leg_in=.75,cheek_weld_perimeter_in=44.,primary_width_at_pin_in=22.,extension_in=12.)
    profile=dict(id='BRB',family='rhs',dimensions=dict(h=10.,b=10.,t=.5))
    a=Assembly('Located BRB stack',{'BRB':profile})
    a.polygon('GUSSET',[[4,-.625,0],[4,-.625,20],[22,-.625,0]],1.25)
    a.weld('WGC',[4,0,0],[4,0,20],['COLUMN','GUSSET'],.5)
    a.weld('WGB',[4,0,0],[22,0,0],['BASE','GUSSET'],.625)
    ctx=SimpleNamespace(a=a,pid='BRB',package={'source_handoff':{'records':{'R':{'data':{'pin_stack':source}}}}})
    make_stack(ctx,('R',source),unit([1,0,1]),12,10,10)
    pin=next(p for p in a.parts if p['id']=='PIN')
    assert pin['grip']==16 and len(pin['connects'])==9
    assert len([p for p in a.parts if p.get('holes') and p['holes'][0]['diameter_in']==4.0625])==9
    assert len([w for w in a.welds if w.get('attachment_role')=='cheek_perimeter_fillet'])==16
    assert len([w for w in a.welds if 'COLUMN' in w['connects']])==4
    assert len([w for w in a.welds if 'BASE' in w['connects']])==4
    with pytest.raises(ValueError,match='sum'):stack_positions(dict(source,grip_in=15))


def test_plated_crossing_uses_opposite_bar_faces_and_four_selected_edge_welds():
    profiles={'FLAT':dict(id='FLAT',family='flat',dimensions={'width':1.75,'thickness':.75})}
    rows=[]
    for i,side in enumerate((-1,1)):
        v=unit([2.,0.,float(side)])
        rows.append(dict(role=f'BAR{i+1}',pid='FLAT',ray=v,width_axis=[-v[2],0,v[0]],width=1.75,thickness=.75,
                         face_sign=side,centre=[0.,side*.75,0.]))
    plate=dict(length_in=8,width_in=8,thickness_in=.75,material='ASTM A572 Grade 50')
    weld=dict(count_per_bar=2,size_in=.375,length_in=5,run='longitudinal',material='E70XX')
    s=plate_scene(rows,profiles,plate,weld)
    assert len(s['welds'])==4
    assert all(w['connects'][1]=='CROSSING-PLATE' and math.dist(w['a'],w['b'])==pytest.approx(5.) for w in s['welds'])
    assert sorted(w['a'][1] for w in s['welds'])==[-.375,-.375,.375,.375]
    rows[1]['centre'][1]+=.1
    with pytest.raises(ValueError,match='does not meet'):plate_scene(rows,profiles,plate,weld)


def test_kicker_bolt_perforates_both_real_tube_walls_and_its_plate():
    p=dict(id='TUBE',family='rhs',dimensions=dict(h=3.,b=3.,t=.25))
    a=Assembly('Kicker',{'TUBE':p})
    m=a.member('KICKER','TUBE',[0,0,0],[12,0,0])
    g=a.box('GUSSET',[0,1.5,-1.5],[10,.375,3])
    f=a.fastener('KB',[[2.,1.875,0.],[5.,1.875,0.]],[0,-1,0],.75,3.375,['KICKER','GUSSET'],'Two bolts')
    original=len(m['faces']);drill_receivers(a,f,.8125)
    assert len(g['holes'])==2 and len(m['member']['through_bores'])==2
    assert len(m['faces'])>original
    # Four perforated wall faces have independent rings at each shaft.
    for y in (-1.5,-1.25,1.25,1.5):
        ring={(round(q[0],6),round(q[2],6)) for face in m['faces'] for q in face if abs(q[1]-y)<1e-7
              and abs(math.hypot(q[0]-2.,q[2])-.40625)<1e-6}
        assert len(ring)==32
