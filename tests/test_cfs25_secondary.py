from collections import Counter
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs25')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs25',answers_sha256=fingerprint(scenario('cfs25')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_every_retrofit_bolt_crosses_its_actual_finite_plies(actual):
    m,p=actual;families=Counter()
    for c in m['connections']:
        if not c['detail_ref']['id'].startswith('review_retrofit_z'):continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']};families[scene['family']]+=1
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        if c['detail_ref']['id'].endswith('_lap'):assert [v['count'] for v in scene['fasteners']]==[2]
        else:assert next(v for v in scene['fasteners'] if v['id']=='FLANGES')['count']==c['parameters']['flange_bolts']
    assert families=={'review_retrofit_z_support':327,'review_retrofit_z_lap':522}


def test_every_physical_lap_has_touching_webs_without_overlapping_steel(actual):
    m,p=actual;count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_retrofit_z_lap':continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        shapes=[unary_union([Polygon(q) for q in section_polygons(parts['Z'+str(i)],1,0)]) for i in (0,1)]
        assert shapes[0].intersection(shapes[1]).area<1e-7,c['id']
        assert shapes[0].distance(shapes[1])<1e-7,c['id']
        count+=1
    assert count==522


def test_lap_ends_have_their_own_located_bolts_and_source_profiles_remain(actual):
    m,p=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    conns={c['id']:c for c in m['connections']};links={(v['member_id'],v['end']):v for v in m['connection_endpoint_links']}
    for member in members.values():
        if not member.get('source_profile_id'):continue
        shape=profiles[member['profile_id']];source=profiles[member['source_profile_id']]
        assert shape['source_dimensions']==source['dimensions']
        assert member['basis']=='A' and 'capacity' in shape['fit_proposal']
        for end in ('start','end'):
            conn=conns[links[member['id'],end]['connection_id']]
            assert member['id'] in conn['member_ids']
