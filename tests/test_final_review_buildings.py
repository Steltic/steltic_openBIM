"""Regression checks for the final eighteen source-bound review sets."""
import math
from functools import lru_cache
from collections import Counter
import pytest
from steltic_openbim.review_cases import CASES,evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.connection_details import prepare

@lru_cache(maxsize=12)
def case(key):
    p=evidence(key)['package'];s=scenario(key)
    m=build_model(p,{'revision':1,'design_scenario':{'id':key,'source_sha256':s['source_sha256'],'answers_sha256':fingerprint(s['answers'])}})
    return p,m

def test_catalog_has_all_61_distinct_source_buildings():
    assert len(CASES)==58
    assert Counter(c['module'] for c in CASES.values())=={'HR':35,'CFS':23}
    assert {'hr7a','hr34a','hr34b'}<=CASES.keys()
    assert len({c['source_sha256'] for c in CASES.values()})==58

def test_strap_bays_are_not_lumped_and_rods_only_bound_continuous_wall_runs():
    p,m=case('cfs5');profiles={p['id']:p for p in m['profiles']}
    walls={w['id']:w for w in m['wall_layouts']}
    assert len(walls['YW-L1']['runs'])==3 and len(walls['Y1-L1']['runs'])==4
    assert len([mm for mm in m['members'] if mm['kind']=='hold_down_rod' and mm['id'].startswith('YW-L1-')])==2
    assert len([mm for mm in m['members'] if mm['kind']=='hold_down_rod' and mm['id'].startswith('Y1-L1-')])==4
    assert all(profiles[mm['profile_id']]['dimensions']['thickness'] in (.0566,.0713) for mm in m['members'] if mm['kind']=='strap')
    scenes=prepare(m,p);strap=[s for s in scenes if s['family']=='review_cfs_strap']
    assert {r for s in strap for r in s['source_record_ids']} >= {f'connections/conn-strap-end-{w}x{mil}' for w,mil in [(3,54),(4,54),(5,54),(6,54),(6,68),(8,68)]}
    largest=next(s for s in strap if 'connections/conn-strap-end-8x68' in s['source_record_ids'])
    assert sum(f['count'] for f in largest['fasteners'] if f['id']=='FS')==25
    assert sum(f['count'] for f in largest['fasteners'] if f['id'].startswith('CHORD-S'))==15
    assert sum(f['count'] for f in largest['fasteners'] if f['id'].startswith('TRACK-S'))==19

def test_cfs_bearing_spans_and_stepped_hotel_roof():
    _,m=case('cfs1')
    joists=[mm for mm in m['members'] if mm['kind']=='joist']
    assert max(math.dist(*mm['axis']) for mm in joists)<=168.001
    assert any(mm['profile_id']=='800S162-54' and math.dist(*mm['axis'])==72 for mm in joists)
    _,hotel=case('cfs15')
    assert all(max(q[0] for q in p['vertices'])<=1680 for p in hotel['panels'] if p['level']>=5 and p['kind'] in ('floor','roof'))
    assert len([p for p in hotel['panels'] if p['id'].startswith('EAST-ROOF-')])==2
    assert any(c['detail_ref']['id']=='review_final_roof_transfer' and c['parameters'].get('vertical_slip') for c in hotel['connections'])
    assert any(mm['profile_id']=='600S200-68' and mm['id'].startswith('ORD-') and mm['axis'][0][0]==1512 for mm in hotel['members'])

def test_transfer_girder_is_continuous_with_two_pickups_and_sliding_unbolted_seats():
    p,m=case('hr19');girders=[mm for mm in m['members'] if mm['profile_id']=='PG84X1108']
    assert len(girders)==1 and math.dist(*girders[0]['axis'])==1080
    assert len([c for c in m['connections'] if c['detail_ref']['id']=='review_pg_pickup'])==2
    scenes=prepare(m,p);seats=[s for s in scenes if s['family']=='review_pg_seat'];assert seats
    assert all(not s['fasteners'] for s in seats)
    assert all(any(i['kind']=='guided_sliding_bearing' for i in s['interfaces']) for s in seats)
    collars=[s for s in scenes if s['family']=='review_pg_collar'];assert collars
    assert all(len([p for p in s['parts'] if p['id'].startswith('STUD')])==72 for s in collars)
    assert all(c['point'][2]>264 for c in m['connections'] if c['detail_ref']['id']=='review_splice' and any('W36X925' in r for r in c['design_record_ids']))

@pytest.mark.parametrize('key',['hr2','hr5','hr7a'])
def test_moment_frame_end_joints_are_not_mistaken_for_two_sided_joints(key):
    p,m=case(key);refs={r for c in m['connections'] for r in c['design_record_ids']}
    expected={r['id'] for r in p['design_records'] if r['id'].startswith('connections/conn-joint-')}
    assert expected<=refs
    if key=='hr7a':assert any('conn-simple-' in r for r in refs)

@pytest.mark.parametrize('key',['hr34a','hr34b'])
def test_tower_interface_changes_from_continuous_podium_to_clear_joint(key):
    p,m=case(key);scenes=prepare(m,p)
    for s in scenes:
        if s['family']=='review_tower_joint':
            assert s['level']>=3
            assert any(abs(d['value_in']-19)<1e-8 for d in s['dimensions'])
            assert not s['fasteners']
        if s['family']=='review_tower_podium':assert s['level']==2
    assert any(s['family']=='review_tower_podium' for s in scenes)
    assert any(s['family']=='review_tower_joint' for s in scenes)

def test_cellar_continuity_and_roof_damper_are_explicit_supplements():
    _,m=case('hr3')
    cellar=[mm for mm in m['members'] if min(q[2]+mm['end_offsets'][i][2] for i,q in enumerate(mm['axis']))==-144]
    assert cellar and all(mm['basis']=='A' for mm in cellar)
    assert all(min(q[2] for q in mm['axis'])==0 for mm in cellar)  # Analysis workline stays at grade.
    _,damper=case('hr26');beams=[mm for mm in damper['members'] if mm['id'].startswith('TMD-SUPPORT-')]
    assert len(beams)==2 and all(math.dist(*mm['axis'])==360 for mm in beams)
    assert abs(beams[0]['axis'][0][0]-beams[1]['axis'][0][0])==120

@pytest.mark.parametrize('key',['cfs1','cfs5','cfs15'])
def test_local_clip_fasteners_reach_the_declared_receiving_parts(key):
    from steltic_openbim.pilots.geometry import clip_axis
    p,m=case(key)
    for scene in prepare(m,p):
        if scene['family'] not in {'review_final_cfs_joist','review_final_header','review_final_guard','review_final_roof_transfer'}:continue
        parts={p['id']:p for p in scene['parts']}
        for group in scene['fasteners']:
            for start in group['points']:
                end=[v+group['grip']*a for v,a in zip(start,group['axis'])]
                for target in group['connects']:
                    limits=[(lo-1e-5,hi+1e-5) for lo,hi in parts[target]['bounds']]
                    assert clip_axis(start,end,limits) is not None,(key,scene['id'],group['id'],target,start)
        if any(p['id']=='TRUSS' for p in scene['parts']):
            assert parts['TRUSS']['bounds'][2][0]>=2-1e-6
            assert any(f.get('slot',{}).get('length_in')==1.5 for f in scene['fasteners'])
