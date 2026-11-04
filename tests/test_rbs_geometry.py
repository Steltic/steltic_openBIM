"""Do not mirror the remote connection into a short single-end detail extract."""
import copy
import pytest
from steltic_openbim.pilots.geometry import member_faces

CATALOG={'W':dict(id='W',family='i',dimensions=dict(d=20,bf=10,tw=.5,tf=1))}
MEMBER=dict(id='beam',profile_id='W',axis=[[0,0,0],[40,0,0]],end_offsets=[[0,0,0],[0,0,0]],local_y=[0,1,0])


def edge_minima(rbs,z):
    member=dict(MEMBER,rbs=rbs)
    points={tuple(round(v,7) for v in p) for face in member_faces(member,CATALOG) for p in face if abs(p[2]-z)<1e-6 and p[1]>1}
    edge={x:y for x,y,_ in points}
    stations=sorted(edge)
    return [x for a,x,b in zip(stations,stations[1:],stations[2:]) if edge[x]<edge[a]-1e-6 and edge[x]<edge[b]-1e-6]


@pytest.mark.parametrize('z',[-10,10])
def test_single_connection_has_one_reduction_on_each_flange(z):
    assert edge_minima(dict(a_in=6,b_in=12,c_in=2,ends=[0]),z)==[12]
    assert edge_minima(dict(a_in=6,b_in=12,c_in=2,ends=[1]),z)==[28]


def test_full_beam_retains_both_selected_end_reductions():
    assert edge_minima(dict(a_in=6,b_in=12,c_in=2),10)==[12,28]


def test_different_end_dimensions_and_no_input_mutation():
    rbs=dict(cuts=[dict(end=0,a_in=4,b_in=8,c_in=1),dict(end=1,a_in=6,b_in=12,c_in=2)])
    original=copy.deepcopy(rbs)
    assert edge_minima(rbs,10)==[8,28]
    assert rbs==original
