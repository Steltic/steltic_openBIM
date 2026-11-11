import numpy as np
import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.brb_core_readback import core_sections, meets_axial_core, moving_head_clearance
from steltic_openbim.brb_supplier_core import extension, prepare, source_requirements, write_cores
from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.pilots.geometry import member_faces
from test_ifc_assembly_verification import export_readback


def as_mesh(faces):
    ring={};vertices=[];polygons=[]
    for face in faces:
        ids=[]
        for p in face:
            point=tuple(p)
            if point not in ring:
                ring[point]=len(vertices);vertices.append(p)
            ids.append(ring[point])
        polygons.append(tuple(ids))
    return Mesh(np.array(vertices),tuple(polygons))


@pytest.mark.parametrize('change',('none','short','missing','oversize','eccentric','end_gap','hits_shell'))
def test_yielding_core_is_measured_separately_from_casing(tmp_path,change):
    record={'id':'members/brace-BRB6','data':dict(design_note='steel core Asc = 6 in2 (ASTM A36, Fysc 38-46 ksi)',
            checks=[dict(limit_state='over the yielding length 60 in (0.60 Lwp, Lwp = 100 in)')])}
    connection={'id':'conn','member_ids':['test'],'design_record_ids':['connections/end'],'detail_ref':{'id':'review_brb'}}
    profile=dict(id='BRB6',family='rhs',dimensions=dict(h=10,b=10,t=.375),core_area_in2=6.)
    m=dict(id='test',kind='brace',profile_id='BRB6',axis=[[0.,0.,0.],[100.,0.,0.]],local_y=[0,1,0],
           end_offsets=[[15.,0,0],[-35. if change=='short' else -15.,0,0]],design_record_ids=[record['id']])
    model=dict(profiles=[profile],members=[m],connections=[connection])
    package=dict(physical={'materials':[],'members':[dict(m)]},design_records=[record,
                 {'id':'connections/end','data':{'components':'BRB end bolted between two splice plates'}}])
    prepare(package,model);write_cores(package,model)
    if change=='missing':m['section_plies']=[]
    if change in ('oversize','eccentric'):
        for _,points in m['section_plies'][0]['sections']:
            for p in points:
                if change=='oversize':p[0]*=1.05
                else:p[0]+=4.8
    m['axis']=[[0.,0.,0.],[100.,0.,0.]]
    core=m['supplier_core'];assembly=Assembly('Supplier end',{'BRB6':profile})
    tip=15.+(-.3 if change=='end_gap' else 0.)
    extension(assembly,[1.,0.,0.],6.,tip,8.,1.,core)
    projected=as_mesh(assembly.parts[0]['faces'])
    if change=='hits_shell':projected.vertices[:,1]*=10.
    rb=export_readback(tmp_path,{'BRACE':as_mesh(member_faces(m,{'BRB6':profile})),'PROJECTION':projected},reader=True)
    brace=rb.member('BRACE');offset=np.eye(4);offset[0,3]=-15.
    facts,errors=core_sections(brace.transformed(offset),6.,60.)
    contact,issues=meets_axial_core(brace,rb.member('PROJECTION'),[1,0,0],6.)
    assert bool(errors or issues)==(change!='none'),(errors,issues)
    if change=='none':
        assert facts['measured_yielding_intervals_in'][0]==pytest.approx([5.,65.])
        assert contact['casing_clearance_in']>0.


def test_hr_controls_survive_suppression_of_generated_core_metadata():
    record=dict(id='members/diagonal',data=dict(design_note='BRB27.0: Asc = 27 in2, A36 core',
                checks=[dict(limit_state='brace elongation 3.61 in against yielding length 237 in (0.60 Lwp)')]))
    member=dict(id='physical-diagonal',design_record_ids=[record['id']])
    selected=dict(record_id=record['id'],fields=[dict(role='brb_core',field=k,value=v)
                  for k,v in [('area_in2',27),('material','ASTM A36'),('yielding_length_workpoint_ratio',.60)]])
    handoff={'member_selections':{member['id']:selected}}
    assert source_requirements([member],handoff,[record])[member['id']]['reported_elongation_in']==3.61
    selected['fields'][0]['value']=26.
    with pytest.raises(ValueError,match='disagrees'):
        source_requirements([member],handoff,[record])


@pytest.mark.parametrize(('gap','valid'),[(3.86,True),(3.60,False),(0.,False),(-1.,False)])
def test_moving_head_separation_is_measured_on_actual_step(tmp_path,gap,valid):
    assembly=Assembly('clearance',{})
    for pid,lo,hi in [('BRACE',10.,40.),('END-CAP',9.-gap,10.-gap)]:
        pts=[[lo,-2.,-2.],[lo,2.,-2.],[lo,2.,2.],[lo,-2.,2.]]
        assembly.polygon(pid,pts,hi-lo,normal=[1.,0,0])
    rb=export_readback(tmp_path,{p['id']:as_mesh(p['faces']) for p in assembly.parts},reader=True)
    errors=[]
    facts=moving_head_clearance({k:rb.member(k) for k in ('BRACE','END-CAP')},[1.,0,0],3.61,errors)
    assert facts['measured_head_clearance_in']==pytest.approx(gap)
    assert bool(errors)!=valid
