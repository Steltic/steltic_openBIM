"""Assembly checks target the actual regressions hidden by component-only diagrams."""
import json
from pathlib import Path
import zipfile
import pytest

from steltic_openbim.design_scenarios import adopt_scenario
from steltic_openbim.drawing_workflow import initial_state
from steltic_openbim.design_geometry import build_model
from steltic_openbim.connection_details import prepare
from steltic_openbim.assembly_scene import section_polygons


@pytest.fixture(scope='module')
def pilots():
    result={}
    with zipfile.ZipFile(Path(__file__).resolve().parents[1]/'docs/stage3/pilots.zip') as z:
        for key in ('hr22','cfs16','cfs8'):
            p=json.loads(z.read(key+'/bim_package.json'));s=initial_state(p,1)
            s=adopt_scenario(p,s,dict(revision=1,source_model_sha256=s['source_model_sha256'],confirm_fictional=True,author='Assembly acceptance'))
            m=build_model(p,s);prepare(m,p);result[key]=m
    return result


@pytest.mark.parametrize('key',('hr22','cfs16','cfs8'))
def test_every_occurrence_has_an_assembled_variant_and_real_section(pilots,key):
    m=pilots[key];scenes={s['id']:s for s in m['connection_assemblies']}
    occurrences=[c['id'] for c in m['connections']]
    assert sorted(occurrences)==sorted(c for s in scenes.values() for c in s['occurrences'])
    for c in m['connections']:assert scenes[c['assembly_id']]['reference']==c['drawing_ref']
    for s in scenes.values():
        members=[p for p in s['parts'] if p['kind']=='member']
        assert len(members)>=2 or any(p['kind']=='concrete' for p in s['parts'])
        assert s['fasteners'] or s['welds']
        cut_parts=[p for p in s['parts'] if section_polygons(p,s['section_axis'],s['section_at'])]
        assert any(p['kind']=='member' for p in cut_parts) or (
            any(p['kind']=='concrete' for p in s['parts']) and {'plate','fastener'}<={p['kind'] for p in cut_parts})
        for f in s['fasteners']:assert 0<f['diameter']<=3 and 0<f['grip']<=150


def test_shear_plate_dimensions_cannot_be_parsed_as_bolt_diameters(pilots):
    scenes=[s for s in pilots['hr22']['connection_assemblies'] if s['family']=='hr_simple_shear_plate']
    for s in scenes:
        f=next(f for f in s['fasteners'] if f['id']=='F1')
        assert f['diameter']==.875 and f['count']==6
        assert any(w['connects']==['M1','P1'] for w in s['welds'])


def test_simple_shear_plate_draws_the_actual_column_web_or_flange(pilots):
    from steltic_openbim.pilots.model import unit,sub,dot
    m=pilots['hr22'];members={v['id']:v for v in m['members']};scenes={s['id']:s for s in m['connection_assemblies']}
    profiles={p['id']:p for p in m['profiles']};seen=set()
    for c in m['connections']:
        if c['detail_ref']['id']!='hr_simple_shear_plate':continue
        beam=members[c['member_ids'][0]];column=next(members[mid] for mid in c['member_ids'] if members[mid]['kind']=='column')
        weak=abs(dot(unit(sub(*beam['axis'][::-1])),column['local_y']))>.7;seen.add(weak)
        scene=scenes[c['assembly_id']];parts={q['id']:q for q in scene['parts']};dim=profiles[column['profile_id']]['dimensions']
        assert parts['M1']['member']['local_y']==([1,0,0] if weak else [0,1,0])
        assert parts['M2']['member']['axis'][0][0]==pytest.approx((dim['tw'] if weak else dim['d'])/2+1.25)
    assert seen=={True,False}


def test_pilot_kicker_bolts_cross_the_angle_leg_and_gusset_and_welds_reach_hosts(pilots):
    from shapely.geometry import Point,Polygon
    from shapely.ops import unary_union
    from steltic_openbim.pilots.geometry import strips
    from steltic_openbim.pilots.model import unit,sub,dot,cross,add,mul
    m=pilots['hr22'];profiles={p['id']:p for p in m['profiles']}
    checked=0
    for scene in m['connection_assemblies']:
        if scene['family']!='hr_required_bottom_flange_brace':continue
        parts={p['id']:p for p in scene['parts']};checked+=1
        def section_point(member,position):
            u=unit(sub(*member['axis'][::-1]));delta=sub(position,member['axis'][0]);station=dot(delta,u)
            assert -1e-5<=station<=sum(x*x for x in sub(*member['axis'][::-1]))**.5+1e-5
            yz=(dot(delta,member['local_y']),dot(delta,cross(u,member['local_y'])))
            return unary_union([Polygon(poly) for poly in strips(profiles[member['profile_id']],profiles)]),Point(yz)
        for fastener in scene['fasteners']:
            plate=parts[next(k for k in fastener['connects'] if k.startswith('TAB'))]
            normal=fastener['axis'];u=unit(sub(plate['polygon'][1],plate['polygon'][0]));v=cross(normal,u)
            poly=Polygon([(dot(sub(q,plate['polygon'][0]),u),dot(sub(q,plate['polygon'][0]),v)) for q in plate['polygon']])
            for q in fastener['points']:
                section,position=section_point(parts['KICKER']['member'],add(q,mul(normal,.5)))
                assert section.covers(position),'Bolt misses the physical angle leg'
                assert poly.covers(Point(dot(sub(q,plate['polygon'][0]),u),dot(sub(q,plate['polygon'][0]),v)))
        for weld in scene['welds']:
            host=parts[weld['connects'][0]]['member']
            tab=parts[weld['connects'][1]]
            origin=tab['polygon'][0];normal=tab['normal']
            u=unit(sub(tab['polygon'][1],origin));v=cross(normal,u)
            footprint=Polygon([(dot(sub(q,origin),u),dot(sub(q,origin),v)) for q in tab['polygon']])
            for position in (weld['a'],weld['b']):
                section,point=section_point(host,position)
                assert section.distance(point)<1e-6,'Gusset weld is detached from its actual host'
                offset=sub(position,origin)
                assert -1e-6<=dot(offset,normal)<=tab['thickness']+1e-6
                assert footprint.distance(Point(dot(offset,u),dot(offset,v)))<1e-6
    assert checked>1


def test_saved_answers_do_not_resolve_new_completeness_findings():
    with zipfile.ZipFile(Path(__file__).resolve().parents[1]/'docs/stage3/pilots.zip') as z:
        package=json.loads(z.read('hr22/bim_package.json'))
    state=initial_state(package,1)
    state['requests'].append(dict(id='NEW-RECEIVER-FIT',proposal='Check the actual receiver at this joint',confirmed=False,status='provisional'))
    updated=adopt_scenario(package,state,dict(revision=1,source_model_sha256=state['source_model_sha256'],confirm_fictional=True,author='Regression test'))
    assert updated['drawing_status']=='provisional'
    request=next(r for r in updated['requests'] if r['id']=='NEW-RECEIVER-FIT')
    assert not request['confirmed'] and 'resolution' not in request
    model=build_model(package,updated)
    note=next(r for r in model['assumptions'] if r['id']=='NEW-RECEIVER-FIT')
    assert not note['confirmed'] and note['answer'].startswith('TBD - resolve query:')


def test_portal_detail_has_both_member_legs_two_continuous_brackets_and_all_bolts(pilots):
    for s in pilots['cfs16']['connection_assemblies']:
        if s['family'] not in ('cfs_knee_3x4','cfs_apex_3x3'):continue
        assert len([p for p in s['parts'] if p['kind']=='member'])==2
        plates=[p for p in s['parts'] if p['kind']=='plate']
        assert len(plates)==2 and all(len(p['polygon'])>=5 for p in plates)
        assert sum(f['count'] for f in s['fasteners'])==(48 if 'knee' in s['family'] else 36)
        for m in (p for p in s['parts'] if p['kind']=='member'):
            for cut in m['cut_planes']:
                assert all(sum(v*n for v,n in zip(point,cut['normal']))>=cut['offset']-1e-6 for face in m['faces'] for point in face)


def test_housing_hold_down_preserves_line_and_story_rod_sizes_and_total_screws(pilots):
    scenes=[s for s in pilots['cfs8']['connection_assemblies'] if s['family']=='cfs_chord' and 'connections/conn-rod-bracket-Y-HE' in s['source_record_ids']]
    sizes={1:1.25,2:.875,3:.625,4:.625}
    assert {s['level'] for s in scenes}==set(sizes)
    for s in scenes:
        rod=next(p for p in s['parts'] if p['id']=='M2')
        assert rod['profile_id']==f"ASSEMBLY-ROD{sizes[s['level']]:g}"
        assert sum(f['count'] for f in s['fasteners'])==16
        assert len([p for p in s['parts'] if p['id'].startswith('R')])==4


def test_stud_detail_has_both_flange_attachments_and_track(pilots):
    for s in pilots['cfs8']['connection_assemblies']:
        if s['family']!='cfs_stud':continue
        assert len(s['fasteners'])==2 and all(f['count']==1 for f in s['fasteners'])
        assert s['fasteners'][0]['axis']==[0.,1.,0.]
        assert s['fasteners'][1]['axis']==[0.,-1.,0.]


def test_warehouse_endpost_base_clips_follow_actual_web_faces(pilots):
    scenes=[s for s in pilots['cfs16']['connection_assemblies'] if s['family']=='cfs_scheduled_endwall_post' and any(p['id']=='CONC' for p in s['parts'])]
    assert scenes
    for s in scenes:
        clips=[p for p in s['parts'] if p['id'] in ('L0','L1')]
        bolts=[f for f in s['fasteners'] if f['id'].startswith('B')]
        assert len(clips)==len(bolts)==2
        assert all(abs(f['axis'][0])==1 and f['grip']<.5 for f in bolts)
        for f in bolts:
            clip=next(p for p in clips if p['id'] in f['connects'])
            assert all(any(abs(q[0]-v)<1e-8 for v in clip['bounds'][0]) for q in f['points'])
