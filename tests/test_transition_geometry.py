import pytest
from steltic_openbim.review_transition_geometry import loft
from steltic_openbim.bim_contract import geometry_errors


def volume(faces):
    result=0
    for f in faces:
        for b,c in zip(f[1:-1],f[2:]):
            a=f[0]
            result+=sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6
    return result


@pytest.mark.parametrize('family,dimensions,area',[
    ('i',dict(d=20,bf=12,tf=1,tw=.5),33),
    ('rhs',dict(h=20,b=16,t=1),68)])
def test_transition_is_manifold_and_does_not_fill_the_section_void(family,dimensions,area):
    lower=dict(family=family,dimensions=dimensions)
    upper=dict(family=family,dimensions={k:v*.8 for k,v in dimensions.items()})
    faces=loft(lower,upper,10)
    assert geometry_errors(dict(type='mesh',faces=faces),{})==[]
    assert volume(faces)==pytest.approx(area*10*(1+.8+.8**2)/3)
