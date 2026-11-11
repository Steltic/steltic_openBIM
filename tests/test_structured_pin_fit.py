import numpy as np
import pytest
from shapely.geometry import box
from shapely.ops import unary_union
from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.stack_moving_head import allocate_ends,rectangular_layers
from steltic_openbim.stack_section_readback import check_head_contact,check_plate_sections


def mesh(layers):
    rings=rectangular_layers(layers,lambda s,d,y:[s,y,d]);vertices=[];indices={};faces=[]
    for ring in rings:
        face=[]
        for xyz in ring:
            pt=tuple(xyz)
            if pt not in indices:indices[pt]=len(vertices);vertices.append(pt)
            face.append(indices[pt])
        faces.append(face)
    return Mesh(np.array(vertices),tuple(faces))


def billet(x0,x1,y0,y1,z0,z1):
    return mesh([(x0,x1,box(y0,z0,y1,z1),1.,1.)])


def test_machined_end_and_taper_are_closed():
    split=box(-3,-4,3,4).difference(box(-.5,-6,.5,6))
    shape=mesh([(0,1,split,1.,1.),(1,3,box(-3,-4,3,4),.25,.5)])
    assert shape.closed
    sec=shape.section([1,0,0],.5,([0,1,0],[0,0,1]))
    assert sec.geom_type=='MultiPolygon'
    assert sec.area==pytest.approx(40.)
    sec=shape.section([1,0,0],2.,([0,1,0],[0,0,1]))
    assert sec.area==pytest.approx(6*.625*8*.75)


@pytest.mark.parametrize(('gap','height','valid'),[(0.,3.,True),(.2,3.,False),(-.1,3.,False),(0.,2.,False)])
def test_full_tongue_to_head_contact(gap,height,valid):
    a=billet(1,6,0,1,-3,3);b=billet(6+gap,7+gap,-1,2,-height,height)
    _,errors=check_head_contact(a,b,[1,0,0])
    assert (not errors)==valid


@pytest.mark.parametrize(('damage','expected'),[
    ('clean',None),('short','selected_pin_end_extension_differs'),('narrow','selected_eye_breadth_at_pin_differs'),
    ('whitmore','selected_whitmore_width_not_contained_by_primary'),('intrusion','actual_moving_head_or_core_intersects_stationary_pin_steel'),
    ('casing','actual_stationary_pin_steel_intersects_swept_casing'),('receiver','selected_moving_tongue_intrudes_receiving_member')])
def test_measured_pin_footprints_and_movement(damage,expected):
    axis=np.array([1.,0.,0.]);parts={'PIN':dict(id='PIN',kind='pin',parameters={'axis':[0,1,0],'point':[0,0,0]})}
    rows=[dict(role='primary',connected_to='host'),dict(role='clevis',connected_to='brace_end')]
    for key in rows:
        role=key['role'];parts[role]=dict(id=role,kind='plate',parameters={'source_stack_role':role})
    source=dict(selected_stack=rows,primary_width_at_pin_in=6.,pin_hole_diameter_in=2.,extension_in=7.)
    req=8 if damage=='whitmore' else 6
    receiver={'ufm_for_one_primary_leaf':dict(whitmore_clear_station_in=-4.,whitmore_effective_width_in=req)}
    tip=7.5 if damage=='short' else 8.;half=2.5 if damage=='narrow' else 3.
    shapes=dict(PIN=billet(-.5,.5,-1,2,-.5,.5),primary=billet(-12,tip,-.5,.5,-half,half),
                clevis=billet(-8,6,1,2,-3,3),**{'END-CAP':billet(6,7,-2,2,-4,4) if damage=='intrusion' else billet(6,7,1,2,-3.5,3.5),
                'CORE-END':billet(7,11,1,2,-1,1)})
    # A separate real core and hollow square casing; moving the casing closer
    # puts its upper wall through the stationary primary only in the corruption.
    inside=2.5 if damage=='casing' else 4.
    shell=box(-5,-5,5,5).difference(box(-4,-inside,4,inside))
    casing=mesh([(11,31,unary_union([shell,box(-.6,-.8,.6,.8)]),1.,1.)])
    hosts={'COLUMN':billet(-12,-7,-4,4,-8,8)} if damage=='receiver' else {}
    _,issues,_=check_plate_sections(source,receiver,parts,shapes,axis,casing,4.,hosts)
    if expected is None:assert not issues
    else:assert expected in {i['code'] for i in issues}


def test_end_fit_preserves_both_workline_stations_and_full_yield_length():
    m={'axis':[[0,0,0],[100,0,0]],'supplier_core':dict(reported_elongation_in=2.,yielding_length_in=60.)}
    p=dict(pin_hole_diameter_in=2.,extension_in=4.)
    ends=[(str(v),p,{'ufm_for_one_primary_leaf':{'minimum_pin_station_in':v}}) for v in (13.,16.)]
    allocation=allocate_ends(m,ends)
    trims=[a['front_in']+a['thickness_in']+a['casing_gap_in'] for a in allocation.values()]
    assert sum(trims)==pytest.approx(39.5)
    assert trims[1]-trims[0]==pytest.approx(3.)
    assert all(a['casing_gap_in']>2. for a in allocation.values())
