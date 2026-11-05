from collections import Counter
import math
import pytest
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from steltic_openbim.review_cfs_occurrences import axis
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs5')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs5',answers_sha256=fingerprint(scenario('cfs5')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_six_source_drag_types_have_all_levels_and_actual_chord_terminals(actual):
    m,p=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    straps=[v for v in m['members'] if v['kind']=='collector' and v['id'].startswith('DRAG-')]
    assert len(straps)==330
    assert {r for v in straps for r in v['design_record_ids']}=={r['id'] for r in p['design_records'] if r['table']=='collectors'}
    assert Counter(v['level'] for v in straps)=={k:55 for k in range(1,7)}
    ends=[c for c in m['connections'] if c['detail_ref']['id']=='review_cfs5_drag_end']
    assert len(ends)==528
    for c in ends:
        ms=[members[mid] for mid in c['member_ids']]
        assert ms[7]['id']==ms[8]['id'].rsplit('-CH',1)[0]+'-TT'
        assert ms[8]['kind']=='chord' and ms[7]['kind']=='top_track'
        assert profiles[ms[1]['profile_id']]['dimensions']==dict(width=8,thickness=.1017)
        assert len(c['parameters']['points_relative'])==8
        assert len(c['parameters']['track_points'])==6
        assert len(c['parameters']['chord_points'])==6


def test_every_new_drag_fastener_contacts_its_declared_actual_plies(actual):
    m,p=actual;seen=Counter()
    for c in m['connections']:
        if c['detail_ref']['id'] not in ('review_cfs5_drag_screws','review_cfs5_drag_end'):continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']};seen[scene['family']]+=1
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(c['id'],f['id'],target,q)
        if scene['family']=='review_cfs5_drag_end':
            assert sum(f['count'] for f in scene['fasteners'] if f['id'].startswith('STRAP'))==8
            assert next(f for f in scene['fasteners'] if f['id']=='TRACK')['count']==6
    assert seen['review_cfs5_drag_end']==528 and seen['review_cfs5_drag_screws']>2000


def test_drag_return_ties_and_track_legs_have_no_overlapping_steel(actual):
    m,p=actual
    for c in m['connections']:
        if c['detail_ref']['id']!='review_cfs5_drag_end':continue
        scene=build_scene(m,p,c);parts=[v for v in scene['parts'] if v['id'].startswith('M')]
        for z in (-4,-.75):
            sections={v['id']:unary_union([Polygon(poly) for poly in section_polygons(v,2,z)]) for v in parts}
            for i,one in enumerate(parts):
                for two in parts[i+1:]:
                    assert sections[one['id']].intersection(sections[two['id']]).area<1e-6,(c['id'],z,one['id'],two['id'])


def test_every_drag_return_weld_lies_on_both_actual_plate_surfaces(actual):
    m,p=actual
    def on_surface(part,q):
        for face in part['faces']:
            normal=min(range(3),key=lambda i:max(v[i] for v in face)-min(v[i] for v in face))
            if max(v[normal] for v in face)-min(v[normal] for v in face)>1e-7 or abs(q[normal]-face[0][normal])>1e-6:continue
            axes=[i for i in range(3) if i!=normal]
            if Polygon([[v[i] for i in axes] for v in face]).buffer(1e-7).covers(Point([q[i] for i in axes])):return True
        return False
    for c in m['connections']:
        if c['detail_ref']['id']!='review_cfs5_drag_end':continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for w in scene['welds']:
            for fraction in (.25,.5,.75):
                q=[a+(d-a)*fraction for a,d in zip(w['a'],w['b'])]
                for label in w['connects']:assert on_surface(parts[label],q),(c['id'],w['id'],label,q)


def test_source_blocks_keep_sections_counts_and_maximum_screw_spacing(actual):
    m,p=actual;members={v['id']:v for v in m['members']};count=0
    for c in m['connections']:
        par=c.get('parameters',{})
        if par.get('source_collector_block'):
            assert members[c['member_ids'][0]]['profile_id']=='1000S200-68'
            scene=build_scene(m,p,c)
            assert [f['count'] for f in scene['fasteners']]==[6,6]
            parts={v['id']:v for v in scene['parts']}
            for f in scene['fasteners']:
                for q in f['points']:
                    for target in f['connects']:assert contact(parts[target],f,q),(c['id'],target)
            count+=1
        if par.get('purpose')=='four_per_block':
            pts=par['points_relative'];assert len(pts)==4
            assert all(.57<=math.dist(a,d)<=3.00001 for a,d in zip(pts,pts[1:]))
    assert count>2000


def test_every_crossing_pack_has_actual_fixings_and_no_invented_capacity(actual):
    m,p=actual;members={v['id']:v for v in m['members']};attached=set()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_cfs5_drag_screws':continue
        for layers in c['parameters']['fixing_layers']:
            assert 0<layers['rebate']<c['parameters']['subfloor_thickness']
            attached.update(c['member_ids'][i] for i in layers['member_indices'])
    packs=[v for v in members.values() if v['kind']=='collector_packing']
    assert packs and all(v['id'] in attached and v['basis']=='A' for v in packs)
    straps=[v for v in members.values() if v['kind']=='collector' and v['id'].startswith('DRAG-')]
    assert all(v['basis']=='A' and 'capacity' in v['source_selection'] for v in straps)
