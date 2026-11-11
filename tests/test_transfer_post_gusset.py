import math

import numpy as np
import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.transfer_post_plate import post_plate
from steltic_openbim.transfer_post_readback import measure
from test_brb_core_readback import as_mesh
from test_ifc_assembly_verification import export_readback


@pytest.mark.parametrize('change',['none','thin','steeper','narrow','excess_arm_stock','missing_corner_blend'])
def test_machined_post_spread_is_measured_from_real_step(tmp_path,change):
    angle=30.;depth=21.6
    source=dict(thickness_in=4.,arm_thickness_in=1.5,fan_angle_deg=angle,
        outside_taper_run_per_rise=4.,weld_root_width_in=depth,
        joint_side_fan_width_in=depth+152*math.tan(math.radians(angle)),blend_radius_in=1.,
        material='ASTM A572 Grade 50')
    made=dict(source)
    if change=='thin':made['thickness_in']=3.
    if change=='steeper':made['outside_taper_run_per_rise']=2.
    if change=='narrow':
        made['weld_root_width_in']-=6.
        made['joint_side_fan_width_in']-=6.
    if change=='excess_arm_stock':made['arm_thickness_in']=2.
    if change=='missing_corner_blend':made['blend_radius_in']=.1
    weld=dict(start_in=22.,length_in=76.)
    a=Assembly('Post fan',{})
    plate=post_plate(a,'G1',[(-90.,-45.),(98.,-45.),(100.,50.),(14.,100.),(-15.,100.),(-70.,60.)],
                     8.85,1.,[0.,0.,1.],made,weld)
    mesh=export_readback(tmp_path,{'fan':as_mesh(plate['faces'])})['fan']
    actual,errors=measure(mesh,np.zeros(3),[0.,1.,0.],[0.,0.,1.],source,weld)
    assert bool(errors)==(change!='none')
    if not errors:
        assert actual['joint_side_fan_span_in']==pytest.approx(source['joint_side_fan_width_in'])
        assert actual['minimum_taper_run_per_rise']==pytest.approx(4.,abs=.0001)
