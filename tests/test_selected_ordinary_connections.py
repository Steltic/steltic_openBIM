from types import SimpleNamespace
from copy import deepcopy
import math
import pytest
from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.selected_beam_hinge import draw,bind_cuts
from steltic_openbim.selected_column_splice import selected,cjp_paths


PROFILES={'W14':{'id':'W14','family':'i','dimensions':{'d':14.,'bf':10.,'tw':.45,'tf':.75}},
          'W24':{'id':'W24','family':'i','dimensions':{'d':24.,'bf':12.,'tw':.6,'tf':1.}}}
SPLICE=('milled ends in bearing; web plates 2 PL 3/8 x 10.5 in (A572 Gr 50) with 2 x 7/8 in A325-N bolts per side in one vertical line at 3 in (double shear); '
        'flange plates PL 1/2 x 10 in (A572 Gr 50) with 4 bolts per flange per side in two lines at g = 5.5 in; standard holes 15/16 in, edge distances at least 1.75 in')
PIN='4 in dia. pin (AISI 4140 Q&T, Fy 105 / Fu 125 ksi) in double shear; knife plate 2 in at the hole, width 15 in, extension 7 in, pin hole 4-1/16 = d + 1/16 in; two clevis plates 1.25 in welded to the beam end (1/2 in fillets); 1 in clear gap at the flanges'


def test_splice_stock_actual_bores_and_selected_three_axis_stations():
    a=Assembly('splice',PROFILES);ctx=SimpleNamespace(a=a,p=PROFILES,ms=[{'profile_id':'W14'}]*2,text=SPLICE)
    assert selected(ctx);parts={p['id']:p for p in a.parts}
    assert parts['WP0']['bounds'][0]==[-5.25,5.25]
    assert {p[0] for p in parts['FW0']['points']}=={0.};assert sorted(p[2] for p in parts['FW0']['points'])==[-4.75,-1.75]
    assert {p[1] for p in parts['F00']['points']}=={-2.75,2.75}
    assert {h['diameter_in'] for h in parts['FP0']['holes']}=={.9375};assert len(parts['M1']['member']['through_bores'])==10
    assert parts['M1']['member']['axis'][-1]==parts['M2']['member']['axis'][0]


def test_splice_rejects_infeasible_flange_edge():
    ctx=SimpleNamespace(a=Assembly('splice',PROFILES),p=PROFILES,ms=[{'profile_id':'W14'}]*2,text=SPLICE.replace('g = 5.5','g = 9.5'))
    with pytest.raises(ValueError,match='gauge'):selected(ctx)


def test_cjp_three_contacts_follow_web_and_both_flanges():
    a=Assembly('CJP',PROFILES);a.member('M2','W14',[0,0,.0625],[0,0,30]);a.weld('SPLICE',[-7,-5,0],[7,5,0],['M1','M2'],kind='CJP')
    cjp_paths(SimpleNamespace(a=a,p=PROFILES,pid='W14',text='CJP groove welds of both flanges and the web; milled ends'))
    assert [(w['a'],w['b']) for w in a.welds]==[([-6.25,0,0],[6.25,0,0]),([-6.625,-5,0],[-6.625,5,0]),([6.625,-5,0],[6.625,5,0])]
    assert a.parts[0]['member']['axis'][0][2]==0


def pin_context(text=PIN):
    a=Assembly('pin',PROFILES);c={'id':'j','design_record_ids':['pin'],'parameters':{}};row={'components':text,'checks':[
        {'limit_state':'pin in double shear','Ru_kip':400.},{'limit_state':'M=P/2 (t/4 + gap + tclevis/2)','Mu_kipin':275.},
        {'limit_state':'clevis plates to beam web/flanges, 1/2 in fillets, total length 82 in'}]}
    return SimpleNamespace(a=a,c=c,p=PROFILES,pid='W24',n=lambda pattern,default:default,package={'design_records':[{'id':'pin','data':row}]})


def test_pin_stack_profile_welds_and_actual_member_interruption():
    c=pin_context();assert draw(c,7.);p={q['id']:q for q in c.a.parts};knife=p['KNIFE'];point=p['PIN']['points'][0];hole=knife['holes'][0]['diameter_in'];bb=knife['bounds']
    assert (bb[2][1]-bb[2][0],bb[1][1]-bb[1][0],hole)==(15.,2.,4.0625);assert bb[0][1]-point[0]-hole/2==7
    assert p['PIN']['diameter']==4 and p['PIN']['grip']==5
    welds=[w for w in c.a.welds if w['id'].startswith('WC')];assert len(welds)==4 and {w['size'] for w in welds}=={.5}
    assert sum(math.dist(w['a'],w['b']) for w in welds)==82
    assert len({tuple(w['a']) for w in welds})==4
    frame={'bindings':{'M3':'B'},'origin':[0,0,0],'x_axis':[1,0,0],'y_axis':[0,1,0]};m={'id':'B','axis':[[0,0,0],[144,0,0]],'end_offsets':[[0,0,-12]]*2,'local_y':[0,1,0],'profile_id':'W24'}
    bind_cuts(c.c,frame,{'B':m});assert [(s['start_in'],s['end_in']) for s in m['slots']]==[(0,7),(17.9375,50.5)]
    from steltic_openbim.pilots.geometry import member_solids
    solids=member_solids(m,PROFILES);xs=[(min(q[0] for f in so for q in f),max(q[0] for f in so for q in f)) for so in solids]
    assert xs and all(any(lo>=a-1e-7 and hi<=b+1e-7 for a,b in ((7,17.9375),(50.5,144))) for lo,hi in xs)


@pytest.mark.parametrize('text',[PIN.replace('4-1/16','3-15/16'),PIN.replace('width 15','width 27')])
def test_reject_inconsistent_pin_bore_or_unfit_width(text):
    with pytest.raises(ValueError,match='footprint'):draw(pin_context(text),7.)
