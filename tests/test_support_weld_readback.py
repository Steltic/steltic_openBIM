import numpy as np
import pytest
from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.support_weld_readback import both_faces,selected_support_sides


def stock():
    vertices=np.array([[x,y,z] for z in (0.,.5) for x,y in ((0.,0.),(5.,0.),(5.,3.),(0.,3.))])
    return Mesh(vertices,((3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)))


@pytest.mark.parametrize('change',['none','segmented','center','same_side','missing','partial','offset','repeat','gap'])
def test_two_separate_selected_fillet_runs_on_actual_faces(change):
    p=stock()
    def run(a,b,z,y=0.):return np.asarray([[a,y,z],[b,y,z]])
    paths=[('left',run(0,5,0)),('right',run(0,5,.5))]
    if change=='segmented':paths[1:]=[('a',run(0,2,.5)),('b',run(2,5,.5))]
    if change=='center':paths=[('single',run(0,5,.25))]
    if change=='same_side':paths[-1]=('other',run(0,5,0))
    if change=='missing':paths.pop()
    if change=='partial':paths[-1]=('right',run(0,4.5,.5))
    if change=='offset':paths[-1]=('right',run(0,5,.5,.25))
    if change=='repeat':paths[1:]=[('a',run(0,2,.5)),('b',run(1,4,.5))]
    if change=='gap':paths[1:]=[('a',run(0,2,.5)),('b',run(2.25,5.25,.5))]
    facts,issues=both_faces(p,paths,5.)
    assert bool(issues)==(change not in ('none','segmented')),issues
    if not issues:assert facts['face_lengths_in']==[5.,5.]


def test_groove_is_not_an_explicit_two_sided_fillet():
    plate=stock()
    p={'WGB':dict(id='WGB',kind='weld',connects=['BASE','GUSSET'],parameters=dict(weld_type='CJP'))}
    lines={'WGB':np.array([[0.,0,0],[5.,0,0]])}
    inputs=(p,{'GUSSET':plate},np.eye(4),lines)
    assert selected_support_sides(*inputs,{}, {'GUSSET'})==([],[])
    _,errors=selected_support_sides(*inputs,{('gusset_base_weld','faces'):[2]}, {'GUSSET'})
    assert errors
