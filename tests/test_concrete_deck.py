import math
from collections import defaultdict
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from test_floor_opening_contact import contact


@pytest.fixture(scope='module')
def actual():
    package=evidence('cfs4')['package'];before=fingerprint(package);s=scenario('cfs4')
    model=build_model(package,dict(design_scenario=dict(id='cfs4',answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(package)==before
    return model,package


def test_all_source_collector_lines_have_located_blocking_and_thin_deck_fixings(actual):
    m,p=actual;members={x['id']:x for x in m['members']};by_block=defaultdict(list)
    sources={r['id'] for r in p['design_records'] if r['table']=='collectors'}
    seen=defaultdict(set)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_deck_screws':continue
        block=members[c['member_ids'][0]];seen[block['level']].update(c['design_record_ids'])
        for q in c['parameters']['points_relative']:
            pt=[a+b for a,b in zip(q,c['point'])]
            assert abs((pt[0]-3)/6-round((pt[0]-3)/6))<1e-6
            assert pt[2]-c['parameters']['deck_bottom_in']==pytest.approx(.036)
            by_block[block['id']].append(pt)
    assert set(seen)=={1,2,3} and all(v==sources for v in seen.values())
    blocks=[m for m in members.values() if m['kind']=='deck_blocking']
    assert len(blocks)==len(by_block)>1000
    linked={(v['member_id'],v['end']) for v in m['connection_endpoint_links']}
    for block in blocks:
        assert block['basis']=='A' and block['profile_id']=='600T150-54'
        assert all((block['id'],end) in linked for end in ('start','end'))
        points=sorted(by_block[block['id']]);assert points
        assert all(math.dist(a,b)<=6.000001 for a,b in zip(points,points[1:]))
    assert all(p.get('perimeter_chord_design') and p.get('reinforcement_design_mat') for p in m['panels'] if p['kind']=='floor')


def test_actual_deck_links_and_screws_have_contact_and_no_solid_overlap(actual):
    m,p=actual;seen=set();families=set()
    for c in m['connections']:
        if c['detail_ref']['id'] not in ('review_deck_screws','review_deck_block_link'):continue
        scene=build_scene(m,p,c)
        # Every distinct actual detail geometry is checked; identical translated
        # copies are covered by the separate occurrence-placement audit.
        token=fingerprint(dict(parts=[{k:v for k,v in x.items() if k not in ('description','member','section_definitions')} for x in scene['parts']],fasteners=scene['fasteners']))
        if token in seen:continue
        seen.add(token);families.add(scene['family']);parts={x['id']:x for x in scene['parts']}
        for f in scene['fasteners']:
            assert f['basis']=='A' and f['diameter']==.216
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(c['id'],f['id'],target,q)
        # Horizontal slices cross actual webs and every folded clip leg. Touching
        # steel is allowed; overlapping volumes are not a valid clip fit.
        solids=[x for x in scene['parts'] if x['kind']!='fastener' and x.get('representation_role')!='context_only']
        heights=sorted({v for x in solids for v in x['bounds'][2]})
        heights=sorted(set(heights+[(a+b)/2 for a,b in zip(heights,heights[1:])]))
        for z in heights:
            sections={x['id']:unary_union([Polygon(v) for v in section_polygons(x,2,z)]) for x in solids}
            for i,a in enumerate(solids):
                for b in solids[i+1:]:
                    assert sections[a['id']].intersection(sections[b['id']]).area<1e-6,(c['id'],a['id'],b['id'],z)
    assert families=={'review_deck_screws','review_deck_block_link'} and len(seen)>10
