import numpy as np

from steltic_openbim.joint_mesh_readback import Mesh, matches_flat_extrusion


def test_flat_cap_size_position_and_all_six_surfaces():
    points=np.array([[x,y,z] for x in (0.,12.) for y in (-5.,5.) for z in (-.375,.375)])
    faces=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
    mesh=Mesh(points,faces)
    geom={'axis':[1,0,0],'local_y':[0,1,0],'origin':[0,0,0],'length':12.}
    dims={'width':10.,'thickness':.75}
    assert matches_flat_extrusion(mesh,geom,dims)
    assert not matches_flat_extrusion(mesh,dict(geom,length=11.75),dims)
    assert not matches_flat_extrusion(mesh,dict(geom,origin=[.2,0,0]),dims)
    assert not matches_flat_extrusion(mesh,geom,dict(dims,width=10.5))
    assert not matches_flat_extrusion(Mesh(points,faces[:-1]),geom,dims)
    damaged=points.copy();damaged[-1]-=[.3,.3,.15]
    assert not matches_flat_extrusion(Mesh(damaged,faces),geom,dims)
