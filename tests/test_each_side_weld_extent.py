import numpy as np

from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.weld_extent_readback import actual_inner_slot_tip,each_side_extents


def test_unchanged_total_weld_length_detects_off_center_curve_at_actual_slot_end():
    faces=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
    points=[];all_faces=[]
    for x0,x1,y0,y1 in [(0,4,-1,-.3),(0,4,.3,1),(4,10,-1,1)]:
        base=len(points)
        points.extend((x,y,z) for x in (x0,x1) for y in (y0,y1) for z in (-1.,1.))
        all_faces.extend(tuple(base+i for i in face) for face in faces)
    mesh=Mesh(np.array(points),tuple(all_faces))
    slot=dict(start_in=0,end_in=3.5,centre_in=0,width_in=.6,section_axis=0)
    tip=actual_inner_slot_tip(mesh,slot)
    assert tip==4.0
    assert each_side_extents([[[2,0,1],[6,0,1]]],[0,0,0],[1,0,0],tip)==(2.0,2.0)
    assert each_side_extents([[[2.5,0,1],[6.5,0,1]]],[0,0,0],[1,0,0],tip)==(1.5,2.5)
