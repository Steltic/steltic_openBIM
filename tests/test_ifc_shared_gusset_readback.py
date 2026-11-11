import numpy as np
import pytest

from steltic_openbim.ifc_shared_gusset_readback import PlacedGusset,check_shared_gussets
from steltic_openbim.joint_mesh_readback import Mesh


def square():
    coords=np.array([[x,y,z] for z in (0.,.75) for x,y in ((0.,0.),(4.,0.),(4.,4.),(0.,4.))])
    faces=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
    return Mesh(coords,faces)


@pytest.mark.parametrize('placement,volume',[
    ('identical',12.),('overlap',6.),('touching',0.),('disjoint',0.),('crossed',2.25)])
def test_separate_placed_occurrences_common_material(placement,volume):
    mesh=square()
    matrix=np.eye(4)
    if placement=='overlap':matrix[0,3]=2.
    if placement=='touching':matrix[2,3]=.75
    if placement=='disjoint':matrix[0,3]=5.
    if placement=='crossed':
        matrix[:3,:3]=[[1.,0,0],[0,0,-1.],[0,1.,0]]
        matrix[:3,3]=[0.,2.,-1.]
    stock=[PlacedGusset('left','C1','GUSSET',mesh,np.eye(4)),PlacedGusset('right','C2','GUSSET',mesh,matrix)]
    metrics,findings=check_shared_gussets(stock,[])
    assert metrics['actual_gusset_occurrences']==2
    assert bool(findings)==bool(volume),findings
    if volume:assert findings[0]['volume_in3']==pytest.approx(volume,abs=1e-5)


@pytest.mark.parametrize('owner,extra,passes',[('first',False,True),('unknown',False,False),('first',True,False)])
def test_shared_plate_has_one_real_owner(owner,extra,passes):
    mesh=square();stock=[PlacedGusset('first','C1','GUSSET',mesh,np.eye(4))]
    if extra:
        matrix=np.eye(4);matrix[0,3]=8.
        stock.append(PlacedGusset('second','C1','GUSSET',mesh,matrix))
    uses=[dict(id='second',parameters=dict(shared_constituents=[
        dict(role='GUSSET',owner_connection_id=owner,owner_part_id='GUSSET')]))]
    metrics,issues=check_shared_gussets(stock,uses)
    assert metrics['shared_gusset_references']==1
    assert bool(issues)==(not passes),issues
