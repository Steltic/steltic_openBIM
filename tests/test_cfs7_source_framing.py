import math
import pytest
from steltic_openbim.review_cases import evidence
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cfs7 import floors,wall_ranges,ordinary_sections,roof_selection,finish,depth
from steltic_openbim.assembly_scene import Assembly


def builder():
    source=evidence('cfs7');b=object.__new__(CaseModel);b.key='cfs7';b.cfg=source['configuration']['cfg'];b.raw=source['calc']
    b.records={r['id']:r for r in source['package']['design_records']}
    b.members=[];b.connections=[];b.panels=[];b.profiles={};b.used_records=set();b.notes=[];b.changes=[];b.walls=[]
    return b


@pytest.fixture(scope='module')
def floor_model():
    b=builder()
    for k,z in enumerate((132,246),1):
        b.member('TRACK-'+str(k),'600T150-54','top_track',[0,696,z-depth(k==2)],[0,800,z-depth(k==2)],k,'S',local_y=[0,0,-1])
    floors(b,b.cfg['plan_outline_ft'],[0,132,246]);return b


def test_each_bar_retains_its_own_125_foot_grid_and_source_profiles(floor_model):
    js=[m for m in floor_model.members if m['kind']=='joist' and not m['id'].startswith('CORRIDOR-')]
    assert js and all(math.dist(*m['axis'])==pytest.approx(150) for m in js)
    for m in js:
        bar=m['id'].split('-')[2];lo=m['axis'][0][0]/12
        assert ((lo-(90 if bar=='S' else 0))/12.5)%1==pytest.approx(0)
        assert m['profile_id'] in ('1000S200-54','1000S162-54')
        assert len(m['design_record_ids'])==2
        assert {r.split('/')[0] for r in m['design_record_ids']}=={'framing','gravity_framing'}
    assert all(m['axis'][0][1]<696 for m in js if '-S-' in m['id'])


def test_corridor_joists_have_six_foot_north_south_span_only_on_floors(floor_model):
    js=[m for m in floor_model.members if m['id'].startswith('CORRIDOR-')]
    assert js and all(m['level']==1 and m['profile_id']=='1000S162-54' for m in js)
    assert all(m['axis'][0][0]==m['axis'][1][0] and math.dist(*m['axis'])==pytest.approx(72) for m in js)
    assert {tuple(q[1] for q in m['axis']) for m in js}=={(312,384),(1008,1080)}
    assert not any(m['level']==1 and any(lo<m['axis'][0][1]<hi for lo,hi in ((312,384),(1008,1080)))
                   for m in floor_model.members if m['id'].startswith('JOIST-'))


def test_source_layers_meet_actual_joist_and_track_surfaces(floor_model):
    b=floor_model;a=Assembly('CFS7 surfaces',b.profiles)
    for k,z in enumerate((132,246),1):
        j=next(m for m in b.members if m['id'].startswith(f'JOIST-{k}-N-'))
        t=next(m for m in b.members if m['id']==f'TRACK-{k}')
        track=a.member(t['id'],t['profile_id'],*[[x+o for x,o in zip(q,off)] for q,off in zip(t['axis'],t['end_offsets'])],y=t['local_y'])
        joist=a.member(j['id'],j['profile_id'],*j['axis'],y=j['local_y'])
        panel=next(p for p in b.panels if p['id']==f'FLOOR-{k}')
        assert panel['vertices'][0][2]-panel['thickness_in']==pytest.approx(joist['bounds'][2][1])
        assert joist['bounds'][2][0]==pytest.approx(track['bounds'][2][1])
        assert panel['thickness_in']==(23/32 if k==1 else 19/32)
        assert panel['thickness_direction']=='negative_global_z'
        assert panel['finished_floor_z_in']==z
    gypsum=next(p for p in b.panels if p['kind']=='finish')
    wood=next(p for p in b.panels if p['id']=='FLOOR-1')
    assert gypsum['thickness_in']==1.5 and not gypsum['structural']
    assert gypsum['vertices'][0][2]-gypsum['thickness_in']==wood['vertices'][0][2]
    materials={m['id']:m for m in b.material_selections}
    assert materials[wood['material_id']]['specification']=='Structural I wood structural panel'
    assert materials[gypsum['material_id']]['specification']=='Nonstructural gypsum floor underlayment'
    assert all(m['source_selection_text']==b.cfg['diaphragm_material'] for m in materials.values())


def test_mechanical_zone_and_full_span_drift_extent_are_explicit(floor_model):
    assert roof_selection(45*12,57.5*12,80*12)=='joist-roof-mech'
    assert roof_selection(30*12,42.5*12,80*12)=='joist-roof-unit-drift'
    assert roof_selection(112.5*12,125*12,80*12)=='joist-roof'
    assert floor_model.changes[-1]['mechanical_zone_ft']==[50,70,90,100]
    assert 'A: locate' in floor_model.notes[-1]['answer']
    assert {r for m in floor_model.members for r in m['design_record_ids'] if r.startswith('framing/joist-roof')}=={
        'framing/joist-roof','framing/joist-roof-mech','framing/joist-roof-unit-drift'}


def test_ordinary_cross_walls_do_not_extend_the_other_bar_grid():
    b=builder()
    assert wall_ranges(b,1,100*12,[(0,116)])==[(58,116)]
    assert wall_ranges(b,1,102.5*12,[(0,116)])==[(0,58)]
    assert wall_ranges(b,0,58*12,[(0,150)])==[(0,240)]


@pytest.mark.parametrize('axis,x,y,k,pid,rid',[
    (0,120,0,1,'600S162-43','stud-ext-long'),(0,120,0,3,'600S162-33','stud-ext-long'),
    (0,20,84,2,'600S162-68','stud-corridor'),(1,0,70,2,'600S162-68','stud-end-walls'),
    (1,102.5,20,2,'600S200-68','stud-cross-walls'),(1,100,100,3,'600S162-68','stud-cross-walls')])
def test_ordinary_studs_use_their_actual_source_location_and_story(axis,x,y,k,pid,rid):
    b=builder();m=b.member(f'ORD-{axis}-TEST','600S162-54','stud',[x*12,y*12,0],[x*12,y*12,100],k,'A')
    ordinary_sections(b)
    assert m['profile_id']==pid and m['design_record_ids']==['studs/'+rid]
