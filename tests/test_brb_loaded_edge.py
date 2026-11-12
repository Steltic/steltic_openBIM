import math

import pytest
from shapely.geometry import LineString, Polygon

from steltic_openbim.brb_loaded_edge import fit_loaded_edge


@pytest.mark.parametrize('angle', [0.,.8,-.8])
def test_tongue_ends_on_both_bolt_paths_and_keeps_all_support_steel(angle):
    u,v=math.cos(angle),math.sin(angle)
    def point(s,t):
        return (s*u-t*v,s*v+t*u)
    def weld(a,b):
        x,z=point(*a);xx,zz=point(*b)
        return dict(a=[x,0.,z],b=[xx,0.,zz],connects=['BEAM','GUSSET'])
    gross=[point(*p) for p in [(0,-16),(25,-16),(31,-13),(31,16),(0,16)]]
    tongue=[point(s,t) for s in (5,17) for t in (-9,9)]
    supported=weld((0,16),(31,16))
    pts=fit_loaded_edge(gross,tongue,[u,0.,v],[supported])
    shape=Polygon(pts)
    for t in (-7.,7.):
        assert shape.intersection(LineString([point(15,t),point(40,t)])).length==pytest.approx(2.)
    assert shape.buffer(1.e-7).covers(LineString([point(0,16),point(31,16)]))
    assert shape.buffer(1.e-7).covers(Polygon([point(5,-9),point(17,-9),point(17,9),point(5,9)]))
    with pytest.raises(ValueError,match='weld crosses'):
        fit_loaded_edge(gross,tongue,[u,0.,v],[weld((10,0),(23,2))])
