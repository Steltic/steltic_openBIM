import json
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path

import pytest
from shapely.geometry import Point,Polygon
from shapely.ops import unary_union

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.connection_cuts import drill_joined_plates
from steltic_openbim.hr_brace_fit import bolted_brb_end,fit_detail_slot,reinforcement
from steltic_openbim.hr_detail_selections import selected_fields,pin_selection
from steltic_openbim.ifc_store import IFCStore
from steltic_openbim.pilots.geometry import member_faces
from steltic_openbim.review_assemblies import hull
from steltic_openbim.terminal_planes import apply_planes


def test_every_selected_brb_bolt_has_a_real_bore_in_the_gusset_and_both_covers():
    a=Assembly('Source BRB',{})
    selection=dict(count=8,rows=2,pitch=3.5,diameter=1.125,material='A490-X')
    _,outline,groups=bolted_brb_end(a,selection,[1.,0.,0.],8.,1.,0.)
    a.polygon('GUSSET',[[x,-.5,z] for x,z in hull(outline)],1.)
    assert len(groups)==1
    group=groups[0]
    assert group['count']==8 and group['connects']==['SPLICE0','GUSSET','SPLICE1']
    drill_joined_plates(a,group,1.1875,'selected group and fitted diametral clearance')
    for plate in (p for p in a.parts if p['id'] in group['connects']):
        assert len(plate['holes'])==8
        low=plate['bounds'][1][0]
        cap=unary_union([Polygon([(q[0],q[2]) for q in face])
                         for face in plate['faces'] if all(abs(q[1]-low)<1e-8 for q in face)])
        assert all(not cap.covers(Point(point[0],point[2])) for point in group['points'])
        assert len(cap.interiors)==8


def test_actual_hss_slot_uses_selected_width_independent_of_end_relief():
    profile=dict(id='h',family='rhs',dimensions=dict(b=6.,h=6.,t=.25))
    a=Assembly('Actual slot',{'h':profile})
    brace=a.member('BRACE','h',[0,0,0],[30,0,0])
    a.polygon('GUSSET',[[-2,-.375,-4],[10,-.375,-4],[10,-.375,4],[-2,-.375,4]],.75)
    fit_detail_slot(a,.875)
    slot=brace['member']['slots'][0]
    assert slot['width_in']==.875 and slot['end_in']==pytest.approx(10.0625)
    # At the open terminal cap the slot is a real void through both HSS walls.
    cap=unary_union([Polygon([(q[1],q[2]) for q in f]) for f in brace['faces']
                     if all(abs(q[0])<1e-8 for q in f)])
    assert not cap.covers(Point(0,2.9)) and cap.covers(Point(.5,2.9))


def test_reinforcement_edges_fit_the_actual_faceted_chs_not_a_rectangular_envelope():
    profile=dict(id='c',family='chs',dimensions=dict(d=5.563,t=.25))
    a=Assembly('Reinforced CHS',{'c':profile})
    for side in (-1,1):
        _,edges=reinforcement(a,'REINF'+str(side),profile,[0,0,0],[1,0,0],side,2.,.25,9.)
        import math
        tube=Polygon([(5.563/2*math.cos(i*math.pi/16),5.563/2*math.sin(i*math.pi/16)) for i in range(32)])
        assert all(tube.boundary.distance(Point(q[1],q[2]))<1e-8 for q in edges)
        assert abs(edges[0][1])<5.563/2


def test_miter_changes_actual_steel_without_replacing_the_source_workline():
    profile=dict(id='h',family='rhs',dimensions=dict(b=2.,h=2.,t=.25))
    member=dict(id='w',axis=[[0.,0.,0.],[10.,0.,0.]],local_y=[0.,1.,0.],
                end_offsets=[[0.,0.,0.],[0.,0.,0.]],profile_id='h')
    apply_planes(member,[dict(normal=[1.,0.,1.],offset_in=2.,end=0)])
    verts=[p for f in member_faces(member,{'h':profile}) for p in f]
    assert member['axis'][0]==[0,0,0] and member['end_offsets'][0]==[2,0,0]
    assert min(p[0]+p[2] for p in verts)==pytest.approx(2.)
    assert min(p[0] for p in verts)==pytest.approx(1.)


def test_conflicting_selected_pin_cannot_fall_back_to_prose():
    c={'id':'joint'};rows=[]
    for i,diam in enumerate([4,5]):
        rows.append(dict(role='pin',field='diameter_in',value=diam,source={'pointer':f'/records/{i}'}))
    package={'source_handoff':{'records':{'r':{'fields':rows}},'occurrences':{'joint':{
        'applications':[{'record_id':'r','selected':[0,1]}]}}}}
    ctx=SimpleNamespace(c=c,selected=selected_fields(package,c),text='pin 4 in dia. (AISI 4140 Q&T)')
    with pytest.raises(ValueError,match='Competing selected pin.diameter_in'):pin_selection(ctx)
    package['source_handoff']['occurrences']['joint']['overrides']=[dict(record_id='r',field_index=1,value=4)]
    assert selected_fields(package,c).get(('pin','diameter_in'))==4


def test_hub_keeps_bad_hr_artifacts_provisional_and_blocks_final(tmp_path,monkeypatch):
    drawing=tmp_path/'drawing';drawing.mkdir()
    (drawing/'source.json').write_text(json.dumps({'module':'HR'}))
    state={'source_model_sha256':'h','revision':3}
    drawings=SimpleNamespace(current=lambda p:(drawing,state),project=lambda p:tmp_path,lock=lambda p:nullcontext())
    store=IFCStore(drawings)
    def worker(action,source,output,*args):
        report={'passed':False,'findings':[{'check':'physical brace fit'}]} if action=='verify_delivery' else {}
        Path(output).write_text(json.dumps(report))
        return report
    monkeypatch.setattr('steltic_openbim.ifc_store.worker',worker)
    opts=dict(source='steltic',revision=3,source_sha256='h')
    result=store.export('test',opts)
    assert result['delivery_status']=='provisional' and result['verification_findings']
    assert (tmp_path/'ifc'/'exports'/result['key']/'delivery_certificate.json').is_file()
    with pytest.raises(ValueError,match='verification failed'):store.export('test',dict(opts,final=True))
