import numpy as np
import pytest
from shapely.geometry import box

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.base_tongue_readback import measure_solid
from test_brb_core_readback import as_mesh
from test_ifc_assembly_verification import export_readback


@pytest.mark.parametrize('change',['none','rectangle','wrong_side','narrow','short','overwide_stock','open'])
def test_integral_tongue_is_measured_on_the_written_solid(tmp_path,change):
    base=box(-16.,-15.,16.,15. if change!='overwide_stock' else 15.25)
    end=29.5 if change=='short' else 30.;half=5.5 if change=='narrow' else 6.
    tongue=box(16.,-half,end,half) if change!='wrong_side' else box(-end,-half,-16.,half)
    contour=base if change=='rectangle' else base.union(tongue)
    a=Assembly('Integral sole',{})
    p=a.polygon('P1',[[x,y,0.] for x,y in list(contour.exterior.coords)[:-1]],2.75,normal=[0.,0.,1.])
    faces=p['faces'][1:] if change=='open' else p['faces']
    mesh=export_readback(tmp_path,{'P1':as_mesh(faces)})['P1']
    select=[dict(axis=0,sign=1,width_in=12.,length_in=14.)]
    facts,errors=measure_solid(mesh,30.,32.,select)
    assert bool(errors)==(change!='none'),(facts,errors)
    if change=='none':
        assert facts['sections'][0]['tongues'][0]['measured_projection_in']==pytest.approx(14.)
