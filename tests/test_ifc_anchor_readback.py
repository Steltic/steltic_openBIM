import numpy as np
import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.connection_cuts import drill_plate
from steltic_openbim.ifc_anchor_readback import anchor_bores
from steltic_openbim.joint_mesh_readback import Mesh


def mesh(faces):
    coordinates={}
    rings=[]
    for face in faces:
        ids=[]
        for point in face:
            key=tuple(np.round(point,8))
            ids.append(coordinates.setdefault(key,len(coordinates)))
        rings.append(tuple(ids))
    return Mesh(np.array(list(coordinates)),tuple(rings))


@pytest.mark.parametrize('change',['none','filled','half_size','off_center','oversize','missing_rod','unrelated_hole'])
def test_selected_bore_in_actual_plate_section(change):
    a=Assembly('base',{})
    plate=a.box('P1',[-6.,-4.,0.],[12.,8.,1.25])
    points=[[-3.,0.,0.],[3.,0.,0.]]
    if change=='missing_rod':points=points[:1]
    if change!='filled':
        holes=[p[:] for p in points]
        if change=='off_center':holes[0][0]+=.125
        if change=='unrelated_hole':holes[0][1]=2.5
        drill_plate(plate,holes,[0,0,1],{'half_size':.90625,'oversize':2.}.get(change,1.8125),'HR')
    shafts={str(i):mesh(a.cylinder(str(i),[x,0.,-1.],[0.,0.,1.],1.,4.)['faces']) for i,x in enumerate((-3.,3.))}
    actual,findings=anchor_bores(mesh(plate['faces']),shafts,1.8125)
    assert bool(findings)==(change!='none'),findings
    if change=='none':
        assert len(actual)==2
        for row in actual.values():assert row['diameter_range_in']==pytest.approx([1.8125,1.8125])
