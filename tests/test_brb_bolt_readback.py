import numpy as np
import pytest

from steltic_openbim.brb_bolt_readback import measure_layout
from steltic_openbim.hr_brace_fit import fit_brb_rows
from steltic_openbim.hr_detail_selections import with_bolt_pattern
from test_ifc_assembly_verification import cuboid,cylinder,export_readback


PATTERN=dict(longitudinal_stations=4,transverse_lines=2,longitudinal_pitch_in=3.5,
             loaded_end_distance_in=2.,block_shear_path_length_in=12.5,transverse_shear_plane_spacing_in=14.)


@pytest.mark.parametrize('change',['none','rotate','gauge','pitch','edge','duplicate'])
def test_actual_brb_group_has_the_selected_axial_path(tmp_path,change):
    plate=cuboid([-3.,-9.,-.5],[12.5 if change!='edge' else 12.2,9.,.5])
    parts={'GUSSET':plate}
    for i in range(4):
        for j in range(2):
            u,v=i*(3.4 if change=='pitch' else 3.5),(j-.5)*(13. if change=='gauge' else 14.)
            if change=='rotate':u,v=v,u
            if change=='duplicate' and i==3 and j==1:v=-v
            bolt=cylinder(.5,-1.,1.)
            bolt.vertices+=np.array([u,v,0.])
            parts[f'B{i}{j}']=bolt
    shapes=export_readback(tmp_path,parts)
    info,issues=measure_layout(shapes.pop('GUSSET'),shapes.values(),[1.,0,0],PATTERN)
    assert bool(issues)==(change!='none'),(info,issues)
    if change=='none':assert info['block_shear_paths_in']==pytest.approx([12.5,12.5])


def test_source_oriented_pattern_cannot_rotate_at_a_crowded_end():
    selected=with_bolt_pattern(dict(count=8,diameter=1.,rows=2,pitch=3.5),
                              {('brb_bolt_pattern',key):value for key,value in PATTERN.items()})
    _,layout=fit_brb_rows(selected,[.8,0.,.6],5.,7.)
    assert [layout[k] for k in ('along_count','across_count','along_pitch','across_pitch')]==[4,2,3.5,14.]
