import copy
import math

import numpy as np
import pytest

from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.pin_stack_readback import verify_pin_stack


def extrusion(radius,low,high,hole=None):
    ring=np.array([(math.cos(t),math.sin(t)) for t in np.linspace(0,2*math.pi,32,endpoint=False)])
    boundary=radius*ring if hole is None else radius*ring/np.max(np.abs(ring),axis=1)[:,None]
    def level(xy,z):return np.column_stack((xy,np.full(len(ring),z)))
    n=len(ring);vertices=[level(boundary,low),level(boundary,high)];faces=[]
    for i in range(n):
        j=(i+1)%n;faces.append((i,j,n+j,n+i))
    if hole is None:faces.extend((tuple(reversed(range(n))),tuple(range(n,2*n))))
    else:
        vertices.extend((level(hole*ring,low),level(hole*ring,high)))
        for i in range(n):
            j=(i+1)%n
            faces.extend(((2*n+i,3*n+i,3*n+j,2*n+j),(i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)))
    return Mesh(np.vstack(vertices),tuple(faces))


def fixture():
    roles=['clevis_outer_left','cheek_left_1','primary_gusset_1','cheek_right_1','clevis_outer_right']
    rows=[dict(role=r,thickness_in=1.,material='ASTM A572 Grade 50',connected_to='brace_end' if 'clevis' in r else 'host' if 'primary' in r else 'primary_gusset_1') for r in roles]
    source=dict(pin_diameter_in=2.,pin_hole_diameter_in=2.0625,grip_in=5.125,selected_stack=rows,
                pin_material='ASTM A434 Grade 4140 Class BD',cheek_weld_leg_in=.5,cheek_side_in=8.,
                cheek_weld_perimeter_in=32.,clearance_between_moving_groups_in=.0625)
    parts={'PIN':dict(kind='pin',parameters={'point':[0,0,0],'axis':[0,0,1]},connects=roles)}
    meshes={'PIN':extrusion(1,0,5.125)};materials={'PIN':source['pin_material']};curves=[];z=0.
    for i,ply in enumerate(rows):
        role=ply['role'];parts[role]=dict(kind='plate',parameters=dict(source_stack_role=role,source_stack_index=i,source_record_id='R'))
        if i and ('clevis' in role)!=('clevis' in roles[i-1]):z+=.0625
        meshes[role]=extrusion(4,z,z+1,hole=1.03125);materials[role]=ply['material']
        if 'cheek' in role:
            corners=[[-4,-4,z],[-4,4,z],[4,4,z],[4,-4,z]]
            for j,(a,b) in enumerate(zip(corners,corners[1:]+corners[:1])):
                line=[a,b];curves.append(np.asarray(line))
                parts[role+str(j)]=dict(kind='weld',connects=[role,'primary_gusset_1'],parameters={'size_in':.5},geometry={'points':line})
        z+=1
    return source,parts,meshes,materials,curves


@pytest.mark.parametrize('damage',[None,'wrong_ply_grade','wrong_pin_grade','missing_clearance','hole','order','missing_weld','weld_size'])
def test_ordered_pin_stack_detects_source_and_geometry_errors(damage):
    source,parts,meshes,materials,curves=fixture()
    if damage=='wrong_ply_grade':materials['primary_gusset_1']='ASTM A36'
    if damage=='wrong_pin_grade':materials['PIN']='ASTM A434 Grade 4140 Class BC'
    if damage=='missing_clearance':
        mesh=meshes['cheek_left_1'];meshes['cheek_left_1']=Mesh(mesh.vertices-[0,0,.0625],mesh.faces)
    if damage=='hole':meshes['cheek_right_1']=extrusion(4,3.0625,4.0625,hole=1.5)
    if damage=='order':source['selected_stack'][1:3]=reversed(source['selected_stack'][1:3])
    if damage=='missing_weld':curves.pop()
    if damage=='weld_size':parts['cheek_left_10']['parameters']['size_in']=.25
    counts,issues=verify_pin_stack('R',source,parts,meshes,materials,curves,np.eye(4))
    assert counts['actual_ordered_pin_bearing_plies']==5
    if damage is None:assert issues==[]
    else:assert issues
