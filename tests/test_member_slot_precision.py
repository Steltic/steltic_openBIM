"""Sloped, translated HSS end slots retain solid geometry at roundoff limits."""
import copy
import math

import pytest

from steltic_openbim.pilots.geometry import member_faces
from steltic_openbim.pilots.model import add, sub, length, unit, cross


PROFILES={'HSS':dict(family='rhs',dimensions=dict(h=7,b=7,t=.465))}
MEMBER=dict(profile_id='HSS',axis=[[1800,900,180],[1800,750,258]],
            end_offsets=[[0,0,0],[0,7.7460851492405025,-4.0279642776050615]],
            local_y=[1,0,0])


def volume(faces,origin):
    total=0.
    for face in faces:
        points=[sub(p,origin) for p in face]
        for b,c in zip(points[1:],points[2:]):
            total+=sum(x*y for x,y in zip(points[0],cross(b,c)))/6
    return abs(total)


@pytest.mark.parametrize('rounding',[-1,0,1])
def test_rounded_end_slot_preserves_extent_and_removed_material(rounding):
    member=copy.deepcopy(MEMBER)
    a,b=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]
    extent=length(sub(b,a)); end=extent
    if rounding:end=math.nextafter(extent,math.inf if rounding>0 else -math.inf)
    member['slots']=[dict(section_axis=0,centre_in=0,width_in=.625,
                          start_in=extent-13.5,end_in=end)]
    original=copy.deepcopy(member)
    faces=member_faces(member,PROFILES)
    d=unit(sub(b,a))
    stations=[sum(x*y for x,y in zip(sub(p,a),d)) for face in faces for p in face]
    assert min(stations)==pytest.approx(0,abs=1e-10)
    assert max(stations)==pytest.approx(extent,abs=1e-10)
    area=7*7-(7-2*.465)**2
    removed=13.5*.625*2*.465
    assert volume(faces,a)==pytest.approx(area*extent-removed,abs=1e-8)
    # Every face still has a nonzero normal, including the end slot surfaces.
    for face in faces:
        assert length(cross(sub(face[1],face[0]),sub(face[2],face[0])))>1e-10
    assert member==original


def test_small_but_resolvable_end_ligament_is_retained():
    member=copy.deepcopy(MEMBER)
    a,b=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]
    extent=length(sub(b,a)); gap=1e-5
    member['slots']=[dict(section_axis=0,centre_in=0,width_in=.625,
                          start_in=extent-13.5,end_in=extent-gap)]
    faces=member_faces(member,PROFILES)
    d=unit(sub(b,a))
    stations=[sum(x*y for x,y in zip(sub(p,a),d)) for face in faces for p in face]
    assert any(abs(s-(extent-gap))<1e-10 for s in stations)
    area=7*7-(7-2*.465)**2
    assert volume(faces,a)==pytest.approx(area*extent-(13.5-gap)*.625*2*.465,abs=1e-8)
