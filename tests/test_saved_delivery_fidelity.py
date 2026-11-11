import json
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path

import pytest
from shapely.geometry import Point,Polygon
from shapely.ops import unary_union

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.connection_cuts import drill_joined_plates
from steltic_openbim.hr_brace_fit import bolted_brb_end,fit_brb_rows,fit_detail_slot,reinforcement
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


def test_large_source_bolt_group_fits_both_ends_of_the_short_hr23_brace():
    import math
    length=math.hypot(150,192)
    selected=dict(count=44,rows=2,pitch=3.5,diameter=1.125,material='A490-X')
    consumed=0.
    for axis,support,column in (([150/length,0.,192/length],0.,29.),
                                ([150/length,0.,-192/length],27.6*length/192,None)):
        start,layout=fit_brb_rows(selected,axis,support,column)
        a=Assembly('Source BRB',{})
        casing,_,groups=bolted_brb_end(a,selected,axis,start,1.5,support,layout)
        assert layout['row_axis']=='longitudinal'
        assert layout['along_count']==2 and layout['along_pitch']==3.5
        assert layout['across_count']==22 and len(groups[0]['points'])==44
        assert groups[0]['connects']==['SPLICE0','GUSSET','SPLICE1']
        consumed+=math.dist(casing,[0.,0.,0.])
    assert length-consumed>50.


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


def test_real_hub_reopens_corrupted_pdf_and_preserves_failure_certificate(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    from steltic_openbim.drawing_workflow import DrawingStore,initial_state
    package=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    drawings=DrawingStore(tmp_path/'jobs')
    drawings.publish('FutureHRJob',package,initial_state(package,1))
    folder,state=drawings.current('FutureHRJob')
    altered=Canvas(str(folder/'drawings.pdf'));altered.drawString(72,72,'Changed drawing');altered.save()
    store=IFCStore(drawings)
    with pytest.raises(ValueError,match='verification failed'):
        store.export('FutureHRJob',dict(source='steltic',revision=state['revision'],
                     source_sha256=state['source_model_sha256'],final=True))
    export,=(drawings.project('FutureHRJob')/'ifc'/'exports').iterdir()
    assert (export/'model.ifc').read_bytes().startswith(b'ISO-10303-21')
    certificate=json.loads((export/'delivery_certificate.json').read_bytes())
    assert not certificate['passed']
    assert not certificate['checks']['pdf_readback']['passed']
    assert 'Drawing PDF digest differs from drawing manifest' in certificate['checks']['source_bindings']['findings']
    assert 'Original HR job evidence is unavailable for this Hub revision' in certificate['checks']['source_bindings']['findings']


def test_source_consistency_checks_hr_result_and_both_live_digests(tmp_path):
    from steltic_openbim.delivery_verification import original_consistency_findings
    from steltic_openbim.saved_delivery import digest_file
    design=tmp_path/'design';design.mkdir();cfg=tmp_path/'cfg.py';calc=design/'calc_package.json'
    cfg.write_bytes(b'height = 2\n');calc.write_bytes(b'{}')
    result=dict(result='PASS',n_issues=0,issues=[],cfg_sha256=digest_file(cfg),calc_package_sha256=digest_file(calc))
    path=design/'consistency_result.json';path.write_text(json.dumps(result))
    assert not original_consistency_findings(tmp_path)
    path.write_text(json.dumps(dict(result,result='FAIL',n_issues=1,issues=['Incomplete member record'])))
    assert 'Original HR consistency evidence is incomplete or failed' in original_consistency_findings(tmp_path)
    path.write_text(json.dumps(result));cfg.write_bytes(b'height = 3\n');calc.write_bytes(b'{"revision":2}')
    assert len(original_consistency_findings(tmp_path))==2


def test_cfs_and_standalone_ifc_store_exports_keep_their_normal_paths(tmp_path):
    from test_ifc import fixture_ifc
    from steltic_openbim.drawing_workflow import DrawingStore,initial_state
    drawings=DrawingStore(tmp_path/'jobs');store=IFCStore(drawings)
    cfs=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    cfs['module']='CFS';drawings.publish('CFSJob',cfs,initial_state(cfs,1))
    _,state=drawings.current('CFSJob')
    out=store.export('CFSJob',dict(source='steltic',source_sha256=state['source_model_sha256'],revision=1,final=True))
    assert out['counts']['members']==1 and 'delivery_certificate' not in out
    f=tmp_path/'incoming.ifc';fixture_ifc(f);initial=store.upload('Independent',f.name,f.read_bytes())
    state=store.build('Independent',dict(revision=initial['revision'],source_sha256=initial['source_sha256'],
                                         options={'scope':'all','units':'auto'}))
    out=store.export('Independent',dict(source='ifc_import',revision=state['revision'],
                                        source_sha256=state['source_sha256'],final=True))
    assert not out['schema_errors'] and 'delivery_certificate' not in out
