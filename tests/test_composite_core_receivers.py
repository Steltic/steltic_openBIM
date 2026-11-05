import copy,math
import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from steltic_openbim.pilots.geometry import strips


@pytest.fixture(scope='module')
def case():
    p=evidence('hr27')['package'];before=copy.deepcopy(p);s=scenario('hr27')
    m=build_model(p,dict(design_scenario=dict(id='hr27',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    assert p==before
    return m,p


def test_coupling_boxes_retain_two_side_webs_and_exact_source_embedments(case):
    m,p=case;profiles={x['id']:x for x in m['profiles']};members={x['id']:x for x in m['members']}
    connections=[c for c in m['connections'] if c.get('parameters',{}).get('purpose')=='coupling']
    assert len(connections)==160
    assert {c['parameters']['embedment'] for c in connections}=={24,30,36,42,54}
    for c in connections:
        beam=members[c['member_ids'][0]];shape=profiles[beam['profile_id']]
        assert shape['family']=='built_up' and len(shape['components'])==4
        s=strips(shape,profiles)
        assert sum(Polygon(poly).covers(Point([8.99,0])) for poly in s)==1
        assert sum(Polygon(poly).covers(Point([-8.99,0])) for poly in s)==1
        assert not any(Polygon(poly).covers(Point([0,0])) for poly in s)
        wall=members[c['member_ids'][1]];closure=members[c['member_ids'][2]]
        assert wall['kind']=='composite_wall' and closure['kind']=='wall_closure'
        assert len(wall['slots'])==2 and len(closure['slots'])==1


def test_all_source_tier_ties_and_base_stud_counts_are_located(case):
    m,p=case;members={x['id']:x for x in m['members']};totals={}
    for c in m['connections']:
        par=c.get('parameters',{})
        if par.get('purpose')=='ties':
            wall=members[c['member_ids'][0]]
            assert par['tie_pitch']==(12 if wall['level']<=15 else 10)
            xs=par['tie_stations'];assert xs
            assert all(abs(b-a-par['tie_pitch'])<1e-7 for a,b in zip(xs,xs[1:]))
        if par.get('purpose')=='base':
            group=members[c['member_ids'][0]]['core_group']
            totals[group]=totals.get(group,0)+12*sum(x['stud_columns'] for x in par['face_rows'])
    assert totals==dict(SW=1920,NE=1920,SE=1488,NW=1488)
    assert len([x for x in m['members'] if x['kind']=='wall_closure'])==160


def test_core_welds_touch_both_actual_workpieces(case):
    m,p=case;seen=set();failures=[]
    for c in m['connections']:
        par=c.get('parameters',{})
        if not par.get('actual_composite_core'):continue
        # Cover every source thickness, direction, embedment and physical end.
        key=(par['purpose'],par['direction'],par['plate_thickness'],par.get('embedment'),par.get('end'),par.get('upper_thickness'),par.get('sx'),par.get('sy'))
        if key in seen:continue
        seen.add(key);scene=build_scene(m,p,c);parts={x['id']:x for x in scene['parts']}
        welds=scene['welds']
        if par['purpose'] in ('ties','base','diaphragm'):welds=welds[:2]+welds[len(welds)//2:len(welds)//2+2]+welds[-2:]
        for w in welds:
            delta=[b-a for a,b in zip(w['a'],w['b'])];axis=max(range(3),key=lambda i:abs(delta[i]));other=[i for i in range(3) if i!=axis]
            for fraction in (.05,.5,.95):
                q=[a+(b-a)*fraction for a,b in zip(w['a'],w['b'])]
                for name in w['connects']:
                    distance=min((Polygon(poly).distance(Point([q[i] for i in other])) for poly in section_polygons(parts[name],axis,q[axis])),default=1e6)
                    if distance>1e-5:failures.append((c['id'],w['id'],name,round(distance,6),q))
    assert not failures,failures[:30]
