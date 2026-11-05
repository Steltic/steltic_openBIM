import copy
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.affinity import rotate,translate
from steltic_openbim.review_z_sections import folded
from steltic_openbim.pilots.geometry import strips


class Catalog:
    def __init__(self):self.profiles={}
    def custom(self,label,family,dimensions,**extra):
        self.profiles[label]=dict(id=label,family=family,dimensions=dimensions,**extra)
        return label


@pytest.mark.parametrize('t1,t2',[(.0566,.0566),(.0713,.0713),(.0713,.1017),(.1017,.0713),(.1017,.1017),(.1242,.1242)])
def test_actual_nested_sections_have_touching_webs_and_no_interpenetrating_steel(t1,t2):
    b=Catalog();sections=[]
    for j,t in enumerate((t1,t2)):
        pid=b.custom('SOURCE'+str(j),'z',dict(d=10,b=3,t=t,lip=.625),lip_angle_deg=50)
        before=copy.deepcopy(b.profiles[pid]);actual=folded(b,pid)
        assert b.profiles[pid]==before
        assert b.profiles[actual]['source_profile_id']==pid
        sections.append(unary_union([Polygon(p) for p in strips(b.profiles[actual],b.profiles)]))
    moved=translate(rotate(sections[1],180,origin=(0,0)),xoff=(t1+t2)/2,yoff=-max(t1,t2))
    assert sections[0].intersection(moved).area<1e-8
    assert sections[0].distance(moved)<1e-8
