import pytest
from shapely.geometry import Polygon
from steltic_openbim.design_pdf import wall_plan_sections


@pytest.mark.parametrize('along',[0,1])
def test_vertical_core_wall_plan_retains_full_length_thickness_and_hollow_centre(along):
    profiles={'FACE':dict(family='flat',dimensions=dict(width=120,thickness=.5)),
        'WALL':dict(family='built_up',dimensions={},components=[
            dict(profile_id='FACE',offset=[0,-8.75],rotation_deg=0),
            dict(profile_id='FACE',offset=[0,8.75],rotation_deg=0)])}
    member=dict(kind='composite_wall',profile_id='WALL',axis=[[1000,200,0],[1000,200,144]],
        local_y=[1,0,0] if along==0 else [0,1,0],end_offsets=[[0,0,-72],[0,0,6.25]])
    sections=wall_plan_sections(member,profiles);points=[q for poly in sections for q in poly]
    assert max(q[along] for q in points)-min(q[along] for q in points)==pytest.approx(120)
    assert max(q[1-along] for q in points)-min(q[1-along] for q in points)==pytest.approx(18)
    assert len(sections)==2
    assert sum(Polygon([q[:2] for q in poly]).area for poly in sections)==pytest.approx(120)
