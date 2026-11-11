import numpy as np
import pytest
from shapely.geometry import MultiPoint,Polygon

from steltic_openbim.gusset_outline_readback import measure_outline
from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.slotted_gusset_outline import fitted_outline,width_station


def prism(outline,t):
    n=len(outline)
    points=np.asarray([[x,y,z] for y in (-t/2,t/2) for x,z in outline])
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return Mesh(points,tuple(faces))


@pytest.mark.parametrize('change',['none','spike','unneeded_stock','narrow','off_center','omitted_support'])
def test_actual_free_gusset_contour_and_located_whitmore_section(change):
    t=.5
    axis=[1.,0,0]
    start=[3.,0,0]
    support=[[0.,0,-3.],[0.,0,3.]]
    paths=[np.array([[3.,y,z],[7.,y,z]]) for y in (-.25,.25) for z in (-1.,1.)]
    outline=fitted_outline(support,paths,start,axis,t,4.)
    if change=='spike':
        outline=list(MultiPoint([*outline,(5.,9.)]).convex_hull.exterior.coords)[:-1]
    elif change=='unneeded_stock':outline=[(0,-3),(8,-3),(8,3),(0,3)]
    elif change=='narrow':outline=[(0,-1),(8,-1),(8,1),(0,1)]
    elif change=='off_center':outline=[(0,-.5),(8,-.5),(8,4.5),(0,4.5)]
    arm=dict(member='B',axis=axis,paths=paths,width=4.,fitted=True)
    if change=='omitted_support':
        with pytest.raises(ValueError,match='finite support'):measure_outline(prism(outline,t),[arm],[])
        return
    result,issues=measure_outline(prism(outline,t),[arm],support)
    assert bool(issues)==(change!='none'),issues
    if change=='none':
        assert result['unsupported_area_in2']==pytest.approx(0.)
        assert min(result['transfer_sections'][0]['available_sides_in'])>=2.
    if change in ('narrow','off_center'):
        assert any('Whitmore' in v['detail'] for v in issues)


def test_selected_width_and_limit_planes_survive_rotation():
    axis=np.asarray([.6,0.,.8]);across=np.asarray([-.8,0.,.6])
    limits=[(0,1,4.),(1,1,2.)]
    station=width_station(axis,10.,limits)
    assert station==pytest.approx((4+4)/.6)
    start=axis*station
    supports=[[4.,0,2.],[4.,0,12.],[11.,0,2.]]
    runs=[np.array([start+v*across,start+v*across+6*axis]) for v in (-2.,2.)]
    outline=fitted_outline(supports,runs,start,axis,.5,10.,limits)
    assert all(x>=4.-1e-8 and z>=2.-1e-8 for x,z in outline)
    assert Polygon(outline).is_valid
    arm=dict(member='B',axis=axis,paths=runs,width=10.,fitted=True)
    _,issues=measure_outline(prism(outline,.5),[arm],supports)
    assert not issues


def test_allowed_shared_plate_includes_the_attachment_regions_of_both_real_arms():
    support=[[0.,0.,-2.],[0.,0.,2.]]
    arms=[];envelopes=[]
    for sign in (-1,1):
        axis=np.asarray([.8,0.,sign*.6]);cross=np.asarray([-sign*.6,0.,.8])
        start=axis*3.
        runs=[np.array([start+v*cross,start+v*cross+4*axis]) for v in (-1.,1.)]
        arms.append(dict(member=str(sign),axis=axis,paths=runs,width=None,fitted=True))
        envelopes.append(Polygon(fitted_outline(support,runs,start,axis,.5,None)))
    outline=envelopes[0].union(envelopes[1])
    assert outline.geom_type=='Polygon'
    actual=prism(list(outline.exterior.coords)[:-1],.5)
    _,issues=measure_outline(actual,arms,support)
    assert not issues
    _,missing=measure_outline(actual,arms[:1],support)
    assert any('free contour' in d['detail'] for d in missing)
