import math
from collections import defaultdict
from types import SimpleNamespace
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs_occurrences import axis
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from test_floor_opening_contact import contact


@pytest.fixture(scope='module')
def actual():
    package=evidence('cfs5')['package'];before=fingerprint(package);s=scenario('cfs5')
    model=build_model(package,dict(design_scenario=dict(id='cfs5',answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(package)==before
    return model,package


def test_exact_source_layers_and_physical_joist_tops(actual):
    m,p=actual;profiles={p['id']:p for p in m['profiles']}
    panels={p['level']:p for p in m['panels'] if p['kind'] in ('floor','roof')}
    finish={p['level']:p for p in m['panels'] if p['kind']=='floor_finish'}
    assert set(panels)==set(range(1,7)) and set(finish)==set(range(1,6))
    assert all(v['local_y']==[1,0,0] for v in m['members'] if v['kind']=='joist' and v['id'].startswith('J-') and v['axis'][0][0] in (0,5.25))
    for k,panel in panels.items():
        assert panel['thickness_in']==(19/32 if k==6 else 23/32)
        assert panel['thickness_direction']=='negative_global_z'
        if k<6:
            assert finish[k]['thickness_in']==1.5
            assert finish[k]['vertices'][0][2]-1.5==panel['vertices'][0][2]
        bottom=panel['vertices'][0][2]-panel['thickness_in']
        for member in m['members']:
            if member['level']==k and member['kind'] in ('joist','diaphragm_blocking'):
                assert axis(member)[0][2]+profiles[member['profile_id']]['dimensions']['d']/2==pytest.approx(bottom)


def test_all_source_diaphragm_zones_have_blocks_and_located_screws(actual):
    m,p=actual;members={m['id']:m for m in m['members']};by_host=defaultdict(list)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_wsp_screws':continue
        par=c['parameters'];by_host[c['member_ids'][0]].extend([[v+o for v,o in zip(q,c['point'])] for q in par['points_relative']])
    blocks=[v for v in m['members'] if v['kind']=='diaphragm_blocking']
    assert len(blocks)>12000
    endpoints={(v['member_id'],v['end']) for v in m['connection_endpoint_links']}
    for block in blocks:
        assert block['basis']=='A' and block['id'] in by_host
        assert all((block['id'],end) in endpoints for end in ('start','end'))
    for mid,points in by_host.items():
        member=members[mid];along=max(range(2),key=lambda i:abs(member['axis'][1][i]-member['axis'][0][i]));points.sort(key=lambda q:q[along])
        assert all(math.dist(a,b)<=6.000001 for a,b in zip(points,points[1:]))
    for panel in m['panels']:
        if panel['kind'] not in ('floor','roof'):continue
        refs={r['id'] for r in p['design_records'] if r['table']=='diaphragms' and r['data']['level']==panel['level']}
        assert len(refs)==4 and refs<=set(panel['design_record_ids'])
        assert panel['attachment_schedule']['maximum_pitch_in']==6
    assert not any(r.startswith('braced_wall_layout/') for r in m['record_coverage']['retained_without_physical_occurrence'])
    assert 'gravity_framing/joist-roof' not in m['record_coverage']['retained_without_physical_occurrence']


def test_distinct_wsp_attachment_geometries_have_contact_without_steel_overlap(actual):
    m,p=actual;members={x['id']:x for x in m['members']};seen=set();families=set()
    for c in m['connections']:
        if c['detail_ref']['id'] not in ('review_wsp_block','review_wsp_screws'):continue
        ms=[members[mid] for mid in c['member_ids']]
        token=fingerprint(dict(family=c['detail_ref']['id'],parameters=c['parameters'],
            members=[dict(profile_id=x['profile_id'],local_y=x['local_y'],axis=[[round(v-o,6) for v,o in zip(q,c['point'])] for q in axis(x)]) for x in ms]))
        if token in seen:continue
        seen.add(token);scene=build_scene(m,p,c);families.add(scene['family']);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(c['id'],target,q)
        if scene['family']=='review_wsp_block':
            solids=[part for part in parts.values() if part['kind']!='fastener'];z=scene['section_at']
            sections={v['id']:unary_union([Polygon(poly) for poly in section_polygons(v,2,z)]) for v in solids}
            for i,one in enumerate(solids):
                for two in solids[i+1:]:
                    assert sections[one['id']].intersection(sections[two['id']]).area<1e-6,(c['id'],one['id'],two['id'])
    assert families=={'review_wsp_block','review_wsp_screws'} and len(seen)>20


def test_source_roof_restraint_and_saved_drift_checks(actual):
    m,p=actual;members={v['id']:v for v in m['members']};straps=[v for v in m['members'] if v['kind']=='roof_joist_bridging']
    assert len(straps)==4
    for strap in straps:
        assert strap['profile_id']=='ROOF-BOTTOM-STRAP-1.5X54'
        row=int(strap['id'].rsplit('-',1)[1]);blocks=[v for v in m['members'] if v['id'].startswith(f'ROOF-RESTRAINT-BLOCK-{row}-')]
        centres=sorted(sum(q[0] for q in axis(v))/2 for v in blocks)
        assert len(centres)>12 and all(d-a<=144.00001 for a,d in zip(centres,centres[1:]))
    for c in m['connections']:
        if c['detail_ref']['id']!='review_roof_bottom_strap':continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            assert f['count']==1 and f['diameter']==.19
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(c['id'],target)
    for member in m['members']:
        if member['kind']!='joist' or 'framing/joist-roof' not in member['design_record_ids']:continue
        x=member['axis'][0][0];lo,hi=sorted(q[1] for q in member['axis'])
        drift=x<297.6 or x>1862.4 or lo<202.8 or hi>517.2
        assert ('framing/joist-roof-parapet' in member['design_record_ids'])==drift
        assert 'gravity_framing/joist-roof' in member['design_record_ids']


def test_layout_mapping_rejects_a_changed_bay_length(actual):
    import copy
    from steltic_openbim.review_cfs_source_bindings import apply
    model,package=actual;m=copy.deepcopy(model);rid='braced_wall_layout/@0'
    for member in m['members']:member['design_record_ids']=[r for r in member['design_record_ids'] if r!=rid]
    next(w for w in m['wall_layouts'] if w['line']=='XS' and w['level']==1)['runs'][0]['end_in']+=1
    b=SimpleNamespace(key='cfs5',walls=m['wall_layouts'],members=m['members'],profiles={p['id']:p for p in m['profiles']},
        records={r['id']:r for r in package['design_records']},cfg={'heights_ft':[11,10,10,10,10,10]},changes=[],used_records=set())
    apply(b)
    assert rid not in b.used_records
    assert any(c['record_id']==rid and c['kind']=='source_wall_schedule_unbound' for c in b.changes)
