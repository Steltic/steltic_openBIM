"""The unequal-span garage retains source conditions and finite receivers."""
import math
import copy
from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs_occurrences import axis
from steltic_openbim.pilots.model import dot,sub,cross
from steltic_openbim.review_cfs17_secondary import roof_at,ROOF,POST_ROWS
from test_cfs27_source_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs17')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs17',answers_sha256=fingerprint(scenario('cfs17')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_saved_two_span_frame_and_real_door_openings(actual):
    m,p=actual;counts=Counter(v['kind'] for v in m['members'])
    assert counts['column']==38 and counts['rafter']==76 and counts['prop']==19
    lookup={v['id']:v for v in m['members']}
    assert lookup['F1-R0']['axis']==[[0,0,216],[300,0,270]]
    assert lookup['F1-R3']['axis']==[[816,0,252],[1032,0,216]]
    assert all(v['profile_id']=='HSS6X6X1/4' for v in m['members'] if v['kind']=='prop')
    assert len([v for v in m['members'] if v['id'].startswith('DOOR-HEADER-')])==5
    for end in (0,1):
        a,b=[lookup[f'GAR-ACCESS-{end}-J{j}'] for j in (0,1)]
        assert b['axis'][0][0]-a['axis'][0][0]-4==42
        assert lookup[f'GAR-ACCESS-{end}-H']['axis'][0][2]-2==84
        assert lookup[f'END-G-{end}-SMALL-240']['roof_supported_upper_girt']
    assert all(v.get('physical_constituent_member_ids') for v in m['panels'])
    assert {p['id'] for p in m['panels'] if p['kind']=='roof'}=={'GAR-SKIN-R'+str(j) for j in range(4)}


def test_source_primary_and_brace_groups(actual):
    m,p=actual
    for purpose,count in (('knee',12),('apex',16),('valley',16)):
        c=next(v for v in m['connections'] if v['detail_ref']['id']=='review_garage_primary' and v['parameters']['purpose']==purpose)
        scene=build_scene(m,p,c);groups=[f for f in scene['fasteners'] if f['count']==count and f['diameter']==.75]
        assert len(groups)==6
    kickers=[c for c in m['connections'] if c['detail_ref']['id']=='review_garage_flybrace' and c['parameters'].get('post')]
    assert len(kickers)==20
    assert all(c['parameters']['count']==c['parameters']['lower_count']==4 for c in kickers)
    ordinary=[c for c in m['connections'] if c['id'].startswith('GAR-FLY-')]
    assert ordinary and all(c['parameters']['count']==4 and c['parameters']['lower_count']==3 for c in ordinary)
    posts=[c for c in m['connections'] if c['id'].startswith('GAR-POST-GIRT-')]
    assert len(posts)==32 and all(c['parameters']['count']==c['parameters']['lower_count']==2 for c in posts)
    plates=[v for v in m['members'] if v['kind']=='flange_cross_plate']
    assert len(plates)==380 and all(v['source_plate_size_in']==[4,19] for v in plates)


def test_source_laps_snow_zones_and_single_bay_straps(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']}
    for v in [v for v in m['members'] if v['id'].startswith('GAR-P-')]:
        x=float(v['id'].split('-')[2]);expected=68 if min(abs(x-z) for z in (300,816))<=204 or abs(x-600)<=96 else 54
        assert v['source_profile_id']=='800Z250-'+str(expected)
        assert v['lap_in']==15
    assert len([v for v in m['members'] if v['id'].startswith('GAR-SIDE-X-')])==8
    assert len([v for v in m['members'] if v['id'].startswith('GAR-VALLEY-X-')])==18
    assert len([v for v in m['members'] if v['id'].startswith('GAR-ROOF-X-')])==48
    for v in [v for v in m['members'] if v['kind']=='strap']:
        assert abs(v['axis'][1][1]-v['axis'][0][1])==144
    for c in [c for c in m['connections'] if c['detail_ref']['id']=='review_garage_strap']:
        scene=build_scene(m,p,c);expected={'side':27,'valley':12,'roof':22}[c['parameters']['kind']]
        assert all(f['count']==expected for f in scene['fasteners'] if f['id'].startswith('STRAP-END'))


def test_roof_straps_below_purlins_and_hollow_header_sleeves(actual):
    m,p=actual;profiles={v['id']:v for v in m['profiles']} if isinstance(m['profiles'],list) else m['profiles']
    for v in [v for v in m['members'] if v['id'].startswith('GAR-ROOF-X-')]:
        seg,z,u=roof_at(sum(q[0] for q in v['axis'])/2);origin=[ROOF[seg][0],0,ROOF[seg][1]];n=cross(u,[0,1,0]);t=profiles[v['profile_id']]['dimensions']['thickness']
        assert all(7.375<dot(sub(q,origin),n)-t/2<dot(sub(q,origin),n)+t/2<8.125 for q in axis(v))
    c=next(c for c in m['connections'] if c['member_ids'][0].startswith('DOOR-HEADER-'))
    s=build_scene(m,p,c)
    sleeves=[v for v in s['parts'] if v['id'].startswith('SLEEVE')]
    assert len(sleeves)==2 and all(v['kind']=='member' for v in sleeves)


def test_every_finite_receiver(actual):
    m,p=actual
    for c in m['connections']:
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)


def test_unequal_roof_slopes_keep_distinct_receivers(actual):
    from steltic_openbim.connection_details import prepare
    m,p=actual;subset=copy.deepcopy(m)
    ids={'F1-K0','F1-K1','F1-J1','F1-J3','F2-K0','F2-J1'}
    subset['connections']=[c for c in subset['connections'] if c['id'] in ids]
    prepare(subset,p)
    refs={c['id']:c['assembly_id'] for c in subset['connections']}
    assert refs['F1-K0']!=refs['F1-K1']
    assert refs['F1-J1']!=refs['F1-J3']
    assert refs['F1-K0']==refs['F2-K0']
    assert refs['F1-J1']==refs['F2-J1']


def test_wall_panels_bear_directly_on_eave_strut(actual):
    m,p=actual
    eaves=[c for c in m['connections'] if c['detail_ref']['id']=='review_garage_cladding'
           and any(mid.startswith(('GAR-STRUT-left-','GAR-STRUT-right-')) for mid in c['member_ids'])]
    assert len(eaves)==144
    for c in eaves:
        s=build_scene(m,p,c)
        # A deep bridging pack would conceal a disconnected panel support.
        assert not [v for v in s['parts'] if v['id'].startswith('PACK')]
