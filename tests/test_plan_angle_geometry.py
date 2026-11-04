import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.pilots.model import add,sub,dot,cross,unit
from steltic_openbim.pilots.geometry import strips


@pytest.fixture(scope='module')
def platform():
    p=evidence('hr35')['package']
    m=build_model(p,dict(design_scenario=dict(id='hr35',answers_sha256=fingerprint(scenario('hr35')['answers']))))
    return p,m


def test_crossing_bolt_passes_through_both_real_angle_legs_without_cutting(platform):
    from shapely.geometry import Point,Polygon
    p,m=platform;profiles={v['id']:v for v in m['profiles']}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_angle_crossing':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']};bolt=s['fasteners'][0]
        assert bolt['diameter']==.75 and len(bolt['points'])==1 and bolt['grip']==pytest.approx(.875)
        for label in ('ANGLE0','ANGLE1'):
            part=parts[label];member=part['member'];u=unit(sub(*member['axis'][::-1]));y=member['local_y'];z=cross(u,y)
            # At the horizontal leg's mid-thickness the vertical bolt lies in steel.
            q=[0,0,-.125 if label=='ANGLE0' else .5];delta=sub(q,member['axis'][0])
            section=Point(dot(delta,y),dot(delta,z))
            assert any(Polygon(poly).buffer(1e-7).contains(section) for poly in strips(profiles[part['profile_id']],profiles)),(c['id'],label)
            assert not member.get('slots')
        assert parts['ANGLE0']['bounds'][2][1]<=0.00001
        assert parts['ANGLE1']['bounds'][2][0]>=.37499


def test_plan_bolt_patterns_hit_actual_angle_leg_and_plate(platform):
    from shapely.geometry import Point,Polygon
    p,m=platform;profiles={v['id']:v for v in m['profiles']}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_plan_angle':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']};angle=parts['ANGLE']['member'];u=unit(sub(*angle['axis'][::-1]));y=angle['local_y'];z=cross(u,y)
        assert len(s['fasteners'][0]['points'])==c['parameters']['count']
        outline=Polygon([q[:2] for q in parts['PLATE']['polygon']])
        for q in s['fasteners'][0]['points']:
            assert outline.contains(Point(q[:2])),c['id']
            thickness=profiles[parts['ANGLE']['profile_id']]['dimensions']['t']
            q=list(q);q[2]=-.5*thickness if dot(z,[0,0,1])<0 else .375+.5*thickness
            d=sub(q,angle['axis'][0]);assert 1.49999<=dot(d,u)<=math.dist(*angle['axis'])-1.49999,c['id']
            assert any(Polygon(poly).buffer(1e-7).contains(Point(dot(d,y),dot(d,z))) for poly in strips(profiles[parts['ANGLE']['profile_id']],profiles)),c['id']


def test_equipment_records_and_all_supplier_leg_ends_are_preserved(platform):
    p,m=platform
    expected={r['id'] for r in p['design_records'] if r['table']=='members' and any(v in r['id'] for v in ('vessel-','skid-','diaphragm-plan-'))}
    assert expected <= {rid for member in m['members'] for rid in member['design_record_ids']}
    links={(r['member_id'],r['end']) for r in m['connection_endpoint_links']}
    legs=[member for member in m['members'] if member['kind']=='equipment_leg']
    assert len(legs)==14 and all((leg['id'],end) in links for leg in legs for end in ('start','end'))


def test_leg_point_gussets_clear_supplier_feet_and_foot_bolts_hit_real_flanges(platform):
    from shapely.geometry import Polygon,box
    p,m=platform
    for c in m['connections']:
        if c.get('parameters',{}).get('supplier_foot_point'):
            scene=build_scene(m,p,c);parts={q['id']:q for q in scene['parts']}
            plate=Polygon([q[:2] for q in parts['PLATE']['polygon']]);bb=parts['SUPPLIER-FOOT']['bounds']
            assert plate.distance(box(bb[0][0],bb[1][0],bb[0][1],bb[1][1]))>=.4999,c['id']
            assert parts['SUPPLIER-FOOT']['representation_role']=='context_only'
        elif c['detail_ref']['id']=='review_equipment_foot':
            scene=build_scene(m,p,c);parts={q['id']:q for q in scene['parts']};beam=parts['BEAM']['bounds']
            assert len(scene['welds'])==4
            for q in scene['fasteners'][0]['points']:
                assert beam[1][0]+.99999<=q[1]<=beam[1][1]-.99999,c['id']


def test_outer_tower_chord_uses_source_extension_width_and_unused_check_is_explicit():
    p=evidence('hr34b')['package'];m=build_model(p,dict(design_scenario=dict(id='hr34b',answers_sha256=fingerprint(scenario('hr34b')['answers']))))
    chords=[q for q in m['members'] if 'members/chord-L2-Grid9-W24X76' in q['design_record_ids']]
    assert len(chords)==3 and all(q['axis'][0][0]==q['axis'][1][0]==1521 for q in chords)
    unused=next(q for q in m['record_dispositions'] if q['record_id']=='members/floor-W27X84-Y-lines')
    assert unused['status']=='not_applicable' and len(unused['evidence_member_ids'])==4
    assert not any('members/floor-W27X84-Y-lines' in q['design_record_ids'] for q in m['members'])
