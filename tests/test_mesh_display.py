import copy
import pytest
from steltic_openbim.mesh_display import display_faces,normal
from steltic_openbim.pilots.geometry import member_faces,extrude,rect
from steltic_openbim.pilots.model import dot,cross


def volume(faces):
    return sum(dot(f[0],cross(a,b))/6 for f in faces for a,b in zip(f[1:],f[2:]))


def test_rbs_display_preserves_geometry_without_internal_station_caps():
    catalog={'W':dict(id='W',family='i',dimensions=dict(d=20,bf=10,tw=.5,tf=1))}
    member=dict(profile_id='W',axis=[[0,0,0],[40,0,0]],end_offsets=[[0,0,0],[0,0,0]],local_y=[0,1,0],rbs=dict(a_in=6,b_in=12,c_in=2,ends=[0]))
    source=member_faces(member,catalog);original=copy.deepcopy(source);shown=display_faces(source)
    assert volume(shown)==pytest.approx(volume(source))
    assert source==original and len(shown)<len(source)/3
    for f in shown:
        if abs(normal(f)[0])>.999999:
            assert f[0][0] in (0,40)
    # The real reduction remains on both top and bottom flange edges.
    assert any(abs(p[0]-12)<1e-8 and abs(abs(p[1])-3)<1e-8 for f in shown for p in f)


def test_hollow_section_end_opening_is_never_filled():
    strips=[rect(-2,-2,2,-1),rect(-2,1,2,2),rect(-2,-1,-1,1),rect(1,-1,2,1)]
    source=[f for poly in strips for f in extrude(poly,[0,0,0],[0,0,10],[1,0,0])]
    shown=display_faces(source)
    assert volume(shown)==pytest.approx(volume(source))
    for f in shown:
        if abs(normal(f)[2])>.99999:
            assert not (min(p[0] for p in f)<0<max(p[0] for p in f) and min(p[1] for p in f)<0<max(p[1] for p in f))
