import copy,math
import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from steltic_openbim.review_rod_receivers import ends


@pytest.fixture(scope='module')
def case():
    p=evidence('hr31')['package'];before=copy.deepcopy(p);s=scenario('hr31')
    m=build_model(p,dict(design_scenario=dict(id='hr31',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    assert p==before
    return m,p


def contact(part,fastener,origin):
    axis=max(range(3),key=lambda i:abs(fastener['axis'][i]));other=[i for i in range(3) if i!=axis]
    for step in range(1,40):
        q=[origin[i]+fastener['axis'][i]*fastener['grip']*step/40 for i in range(3)]
        if any(Polygon(poly).buffer(1e-7).covers(Point([q[i] for i in other])) for poly in section_polygons(part,axis,q[axis])):return True
    return False


def test_source_pin_passes_through_real_gusset_and_both_forged_jaws(case):
    m,p=case;cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_rod_end')]
    assert len(cs)==52
    for c in cs:
        a=build_scene(m,p,c);parts={v['id']:v for v in a['parts']};pin=a['fasteners'][0]
        assert pin['diameter']==1.25 and len(pin['points'])==1
        assert parts['ROD']['member']['source_member_index']==0 and parts['HOST']['member']['source_member_index']==1
        for name in pin['connects']:assert contact(parts[name],pin,pin['points'][0]),(c['id'],name)
        for w in a['welds']:
            delta=[b-a for a,b in zip(w['a'],w['b'])];axis=max(range(3),key=lambda i:abs(delta[i]));other=[i for i in range(3) if i!=axis]
            q=[(a+b)/2 for a,b in zip(w['a'],w['b'])]
            for name in w['connects']:
                distance=min((Polygon(poly).distance(Point([q[i] for i in other])) for poly in section_polygons(parts[name],axis,q[axis])),default=1e6)
                assert distance<1e-5,(c['id'],w['id'],name,distance)


def test_turnbuckles_have_separate_rods_and_crossed_adjusters_are_staggered(case):
    m,p=case;lookup={v['id']:v for v in m['members']}
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_rod_adjuster')];assert len(cs)==26
    for c in cs:
        left,right=[lookup[mid] for mid in c['member_ids']]
        assert math.dist(ends(left)[1],ends(right)[0])==pytest.approx(4)
        a=build_scene(m,p,c);body=next(v for v in a['parts'] if v['id']=='BODY')
        assert body['representation_role']=='assembly_component'
    changes=[v for v in m['changes'] if v['kind']=='actual_crossed_rod_and_adjuster']
    assert {v['plane_offset_in'] for v in changes}=={-.75,.75}
    assert {v['turnbuckle_fraction'] for v in changes}=={.4,.6}


def test_analysis_segments_of_each_gable_column_have_one_physical_roll(case):
    m,_=case;stacks={}
    for member in m['members']:
        if member['kind']=='column' and member['profile_id']=='W24X84':stacks.setdefault(tuple(member['axis'][0][:2]),set()).add(tuple(member['local_y']))
    assert all(len(rolls)==1 for rolls in stacks.values())
