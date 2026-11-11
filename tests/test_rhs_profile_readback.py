import numpy as np

from steltic_openbim.joint_mesh_readback import Mesh, matches_rhs_extrusion


def test_rhs_open_bore_through_length_and_wall_dimensions():
    geom={'axis':[1,0,0],'local_y':[0,1,0],'origin':[0,0,0],'length':12.}
    dims={'b':4.,'h':3.,'t':.25}
    unit_faces=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
    def walls(filled=False):
        regions=[(-2,-1.75,-1.5,1.5),(1.75,2,-1.5,1.5),(-1.75,1.75,-1.5,-1.25),(-1.75,1.75,1.25,1.5)]
        if filled:regions=[(-2,2,-1.5,1.5)]
        points=[];faces=[]
        for yl,yh,zl,zh in regions:
            offset=len(points)
            points.extend((x,y,z) for x in (0,12) for y in (yl,yh) for z in (zl,zh))
            faces.extend(tuple(offset+i for i in face) for face in unit_faces)
        return Mesh(np.array(points,dtype=float),tuple(faces))
    hollow=walls()
    assert matches_rhs_extrusion(hollow,geom,dims)
    assert not matches_rhs_extrusion(walls(True),geom,dims)
    assert not matches_rhs_extrusion(hollow,geom,dict(dims,t=.3))
    assert not matches_rhs_extrusion(hollow,dict(geom,origin=[0,.1,0]),dims)
    assert not matches_rhs_extrusion(Mesh(hollow.vertices,hollow.faces[:-1]),geom,dims)
