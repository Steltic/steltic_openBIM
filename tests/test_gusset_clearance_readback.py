import numpy as np
import pytest
from types import SimpleNamespace

from steltic_openbim.gusset_clearance_readback import measure_fold_line,selected_clearances
from steltic_openbim.joint_mesh_readback import Mesh


def plate():
    points=np.array([[x,y,z] for z in (0,.5) for x,y in ((0,0),(8,0),(8,8),(0,8))])
    faces=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    return Mesh(points,faces)


@pytest.mark.parametrize('case,start,expected,passes',[
    ('corner',7.,1.,True),('corner',6.4,.4,False),('base',5.8,-.2,False),
    ('apex',5.,1.,True),('apex',4.,0.,False),('beam_only',5.,1.,True)])
def test_actual_cap_to_foremost_restrained_edge(case,start,expected,passes):
    u=np.array([.8,.6,0.])
    origin=np.array([30.,15.,120.])
    actual=SimpleNamespace(vertices=origin+np.array([start*u,(start+20)*u]))
    endpoints={'BEAM':[origin,origin+np.array([5.,0.,0.])]}
    if case in ('corner','base'):
        endpoints['COLUMN']=[origin,origin+np.array([0.,10.,0.])]
    facts=measure_fold_line(actual,u,origin,endpoints,.5,2)
    assert facts['clearance_in']==pytest.approx(expected)
    assert (facts['clearance_in']+1e-6>=facts['required_in'])==passes


@pytest.mark.parametrize('change',['none','short','missing','no_selection','scope'])
def test_real_attachment_roles_and_two_selected_end_bindings(change):
    # At a beam-only corner, a nearby column and the brace-slot weld do not
    # restrain the free gusset edge. An actual column weld does restrain it.
    base=plate()
    members={'b':{'axis':[[0.,0,0],[20.,0,0]]},'host':{},'free_col':{}}
    inst={'bindings':{'BRACE':'b','BEAM':'host','COLUMN':'free_col'}}
    parts={'GUSSET':{'kind':'plate'},'WB':{'kind':'weld','connects':['BRACE','GUSSET']},
           'WGB':{'kind':'weld','connects':['GUSSET','BEAM']}}
    lines={'WB':np.array([[4.,0,0],[9.,0,0]]),'WGB':np.array([[0.,0,0],[3.,0,0]])}
    if change=='scope':
        parts['WGC']={'kind':'weld','connects':['GUSSET','COLUMN']}
        lines['WGC']=np.array([[0.,0,0],[5.,0,0]])
    if change=='missing':del lines['WGB']
    cap=3.5 if change=='short' else 4.
    rb=SimpleNamespace(member=lambda mid:SimpleNamespace(vertices=np.array([[cap,-.2,0],[cap,.2,0],[20.,0,0]])))
    fields={} if change=='no_selection' else {('brace_end_clearance','depths'):[2.]}
    measured,issues=selected_clearances(members,{'BRACE':'b'},{'b':fields},parts,(inst,np.eye(4)),
                                         {'GUSSET':base},lines,rb,[])
    assert bool(issues)==(change in ('short','missing','scope')),issues
    assert len(measured)==int(change not in ('no_selection','missing'))
