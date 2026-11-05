import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.assembly_scene import Assembly,section_polygons


@pytest.mark.parametrize('offset',[[0,0,0],[100.1,-1000.3,279.7]])
def test_web_punch_does_not_cut_the_continuous_channel_flange_in_section(offset):
    profiles={'C':dict(id='C',family='channel',dimensions=dict(d=6,b=1.625,t=.0566,lip=.5))}
    a=Assembly('punched stud',profiles)
    part=a.member('STUD','C',[0,0,-6],[0,0,6],y=[1,0,0],slots=[dict(start_in=5.125,end_in=6.875,width_in=.75,centre_in=0,section_axis=1)])
    a.translate(offset)
    flange=section_polygons(part,1,2.99+offset[1])
    assert flange and all(Polygon(poly).is_valid for poly in flange)
    assert any(Polygon(poly).covers(Point([.75+offset[0],offset[2]])) for poly in flange)
    web=section_polygons(part,0,offset[0])
    assert not any(Polygon(poly).buffer(1e-8).covers(Point([offset[1],offset[2]])) for poly in web)
    assert any(Polygon(poly).covers(Point([1+offset[1],offset[2]])) for poly in web)
