import math
from collections import Counter,defaultdict
import pytest
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs_occurrences import axis
from steltic_openbim.pilots.geometry import strips
from steltic_openbim.member_slots import cut_sections
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_every_floor_fastener_crosses_its_real_declared_receivers(actual):
    m,p=actual;counts=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_floor':continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            counts[c['parameters']['purpose']]+=f['count']
            if c['parameters']['purpose']=='lower':assert f['grip']==pytest.approx(.30575)
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],f['id'],label,q,parts[label]['bounds'])
    assert counts['stiffener']==684
    assert counts['transfer']==40
    assert counts['lap']==304
    assert counts['interior_transfer']==152


def test_source_lengths_and_steel_bearing_route_clear_plywood(actual):
    m,p=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    blocks=[v for v in m['members'] if v['kind']=='chord_squash_pack'];assert len(blocks)==16
    plates=[v for v in m['members'] if v['id'].endswith('-BEARING-PL')];assert len(plates)==16
    for block in blocks:
        assert block['profile_id']=='2X600S162-54'
        assert math.dist(*axis(block))==pytest.approx(10.25)
        assert axis(block)[0][2]==107.5
    for plate in plates:
        assert math.dist(*axis(plate))==3.5
        assert profiles[plate['profile_id']]['dimensions']=={'width':6,'thickness':.75}
        assert plate['slots'] and plate['axis'][0][2]+.375==118.5
        assert any(plate['id'] in o.get('penetrating_member_ids',[]) for o in m['openings'])
    stiff=[v for v in m['members'] if v['kind']=='bearing_stiffener'];assert len(stiff)==228
    assert all(v['profile_id']=='600S162-43' and math.dist(*axis(v))==pytest.approx(9.62) for v in stiff)
    # The cuts remove only the rim flanges; full web height remains at every
    # source chord block. No single packing member crosses those cut-outs.
    for rim in [v for v in m['members'] if v['kind']=='rim_track' and v['id'].startswith('MEZZ-RIM-')]:
        shape=strips(profiles[rim['profile_id']],profiles)
        for cut in rim['slots']:
            clipped=unary_union([Polygon(poly) for poly in cut_sections(shape,rim['slots'],(cut['start_in']+cut['end_in'])/2)])
            assert clipped.area==pytest.approx(.0713*10.2051,abs=1e-6)
    assert len([v for v in m['members'] if v['id'].startswith('MEZZ-RIM-PACK-')])==20


def test_laps_clear_squash_blocks_and_preserve_maximum_grid(actual):
    m,p=actual;js=[v for v in m['members'] if v['kind']=='joist' and v['id'].startswith('WING-J-1-')]
    assert len(js)==114
    xs=sorted({v['axis'][0][0] for v in js});assert max(b-a for a,b in zip(xs,xs[1:]))<=16
    assert 1930 not in xs and 2154 not in xs and 1818 not in xs and 2382 not in xs
    for x in xs:
        row=sorted([v for v in js if v['axis'][0][0]==x],key=lambda v:v['axis'][0][1])
        for a,b in zip(row,row[1:]):
            assert axis(a)[1][1]-axis(b)[0][1]==6.25
            assert abs(axis(a)[0][0]-axis(b)[0][0])==pytest.approx(.1017)
            assert a['local_y'][0]==-b['local_y'][0]
    for label in ('BEARING-1-0','BEARING-1-1'):
        studs=[v for v in m['members'] if v['id'].startswith(label+'-ST-')]
        assert sorted(v['axis'][0][0] for v in studs)==xs


def test_source_transfer_counts_and_distinct_floor_layers(actual):
    m,p=actual;groups=[v for v in m['connections'] if v['detail_ref']['id']=='review_sbmf_floor'];counts=Counter()
    for c in groups:
        if c['parameters']['purpose']=='lower' and c['parameters']['two_rows']:
            counts[c['member_ids'][0]]+=2
        if c['parameters']['purpose']=='transfer':
            assert c['parameters']['bolt_stations']==[-48,-24,0,24,48]
    assert list(counts.values())==[32]*4
    panels={v['id']:v for v in m['panels']}
    assert panels['WING-FLOOR-1']['thickness_in']==23/32
    assert panels['WING-FLOOR-GYPSUM']['thickness_in']==1.5
    assert panels['WING-FLOOR-1']['vertices'][0][2]==118.5
    assert panels['WING-FLOOR-GYPSUM']['vertices'][0][2]==120


def test_finish_clearances_name_only_the_actual_intersecting_wall_members(actual):
    from steltic_openbim.review_sbmf_floor import crosses_box
    m,p=actual;lookup={v['id']:v for v in m['members']}
    openings=[o for o in m['openings'] if o.get('host_id')=='WING-FLOOR-GYPSUM']
    assert len(openings)==6
    for o in openings:
        lower=[o['x_ft']*12,o['y_ft']*12,118.5];upper=[(o['x_ft']+o['width_ft'])*12,(o['y_ft']+o['height_ft'])*12,120]
        ids=o['penetrating_member_ids'];assert ids and len(ids)==len(set(ids))
        for mid in ids:
            member=lookup[mid]
            assert member['level']==2 and crosses_box(axis(member),lower,upper)
        assert any(lookup[mid]['kind']=='stud' for mid in ids)
