"""Varied case acceptance: physical topology, source binding and difficult interfaces."""
import copy,math
import pytest
from steltic_openbim.review_cases import CASES,evidence
from steltic_openbim.design_scenarios import available_scenario,adopt_scenario
from steltic_openbim.design_geometry import build_model
from steltic_openbim.drawing_workflow import initial_state,fingerprint
from steltic_openbim.connection_details import prepare


def adopted(key):
    package=evidence(key)['package'];state=initial_state(package,0)
    state=adopt_scenario(package,state,dict(revision=0,source_model_sha256=fingerprint(package),confirm_fictional=True,author='Source-bound batch acceptance'))
    return package,state


@pytest.mark.parametrize('key',list(CASES))
def test_registered_cases_are_source_bound_and_have_complete_member_attachment_maps(key):
    package,state=adopted(key);before=fingerprint(package);model=build_model(package,state)
    assert available_scenario(package)==key
    changed=copy.deepcopy(package);changed['building_id']+=' changed'
    assert available_scenario(changed) is None
    assert fingerprint(package)==before
    members={m['id']:m for m in model['members']};attached=set();record_ids={r['id'] for r in package['design_records']}
    for c in model['connections']:
        assert set(c['member_ids'])<=members.keys()
        assert set(c['design_record_ids'])<=record_ids
        attached.update(c['member_ids'])
    assert attached==members.keys()
    assert len(members)==len(model['members'])
    assert all(math.dist(*m['axis'])>.01 for m in members.values())
    assert all(len(m['local_y'])==3 for m in members.values())
    assert len(state['requests'])==4 and all(r['confirmed'] for r in state['requests'])
    assert model['assumptions'] and all(r['basis'].startswith('A') for r in model['assumptions'])
    if key=='hr33':
        profiles={p['id']:p for p in model['profiles']}
        for m in members.values():
            if m['kind']=='crane_rail':assert all(abs(q[2]+profiles[m['profile_id']]['dimensions']['d']/2-336)<1e-8 for q in m['axis'])
        assert any(m['kind']=='truss_web' for m in members.values())
    if key=='cfs17':
        assert len([m for m in members.values() if m['kind']=='endwall_post'])==10
        assert len([o for o in model['openings'] if o['kind']=='overhead door'])==5
        assert any(m.get('full_length_nested') for m in members.values())
    if key=='cfs29':
        rails=[m for m in members.values() if m['kind']=='guard_rail' and m['axis'][0][1]==0 and m['axis'][1][1]==0]
        assert all(max(q[0] for q in m['axis'])<=300 or min(q[0] for q in m['axis'])>=384 for m in rails)
    if key=='hr9':assert any(c['detail_ref']['id']=='review_rocker' for c in model['connections'])
    if key=='hr27':assert any(c['detail_ref']['id']=='review_core_base' for c in model['connections'])
    if key in ('hr28','hr33'):
        bases={i for c in model['connections'] if c['detail_ref']['id']=='review_base' for i in c['member_ids']}
        assert {m['id'] for m in members.values() if m['kind']=='column' and min(p[2] for p in m['axis'])==0}<=bases
    if key=='hr28':
        bars=[m for m in members.values() if m['kind']=='diaphragm_chord_bar']
        assert len(bars)==8*(6*2+3*2)
        assert len([c for c in model['connections'] if c['detail_ref']['id']=='review_edge_bars'])==32
    if key.startswith('cfs'):
        profiles={p['id']:p for p in model['profiles']}
        assert all(.375<=profiles[m['profile_id']]['dimensions']['d']<=3 for m in members.values() if m['kind']=='hold_down_rod')
    if key=='cfs14':
        assert profiles[members['S-L3-B1-ROD0']['profile_id']]['dimensions']['d']==1.125
        assert profiles[members['S-L4-B1-ROD0']['profile_id']]['dimensions']['d']==.75
        assert members['C1S-L1-B1-CH0']['profile_id']=='HSS6X6X5/16'
        assert next(c for c in model['connections'] if c['id']=='S-L3-B1-CH0-HD')['parameters']['bracket_screws']=='34 No. 14'


@pytest.mark.parametrize('key',('hr8','hr9','cfs17','cfs29'))
def test_assemblies_preserve_critical_source_counts_and_fit(key):
    package,state=adopted(key);model=build_model(package,state);scenes=prepare(model,package)
    occurrences=[o for s in scenes for o in s['occurrences']]
    assert sorted(occurrences)==sorted(c['id'] for c in model['connections'])
    if key=='hr8':
        braces=[s for s in scenes if s['family']=='review_brace']
        assert len({tuple(s['source_record_ids']) for s in braces})>10
        assert {'base','corner','link_end'}<={s['subtype'] for s in braces}
    if key=='hr9':
        embedded=[s for s in scenes if any('base-lateral_col-BOX' in r for r in s['source_record_ids'])]
        assert embedded
        for s in embedded:
            end=next(p for p in s['parts'] if p['id']=='P1');size=end['geometry']['size']
            assert size[2]<size[0]/4 and size[2]<size[1]/4
            assert sum(f['count'] for f in s['fasteners']) in (256,468)
    if key=='cfs17':
        for s in scenes:
            if s['family']=='review_portal_joint':assert sum(f['count'] for f in s['fasteners']) in (72,96)
    for s in scenes:
        ids={p['id'] for p in s['parts']}
        assert all(set(f['connects'])<=ids and len(f['connects'])>=2 for f in s['fasteners'])


def test_rebar_lap_is_a_bond_interface_and_not_a_fictitious_weld():
    from steltic_openbim.review_assemblies import build_scene
    package,state=adopted('hr28');model=build_model(package,state)
    connection=next(c for c in model['connections'] if c['detail_ref']['id']=='review_edge_bars')
    scene=build_scene(model,package,connection)
    assert not scene['welds'] and not scene['fasteners']
    assert len(scene['interfaces'])==6
    assert all(i['kind']=='reinforcement_bond_lap' and i['length_in']==66 for i in scene['interfaces'])


@pytest.mark.parametrize('key,count',[('hr8',172),('hr9',196),('hr10',334),('hr11',313),('hr12',261),('hr13',64),('hr27',280)])
def test_floor_footprints_include_bays_missing_from_segmented_legacy_viewers(key,count):
    from types import SimpleNamespace
    from steltic_openbim.review_floor_layout import cells,interval
    src=evidence(key);b=SimpleNamespace(key=key,source=src,config=src['configuration'],note=lambda *args:None)
    floors=cells(b,src['package']['layout_evidence']['levels_in'])
    assert len(floors)==count
    if key=='hr27':assert not any(360<=(c[0]+c[1])/2<=1080 and 360<=(c[2]+c[3])/2<=720 for c in floors)
    if key=='hr11':assert not any(1008<(c[0]+c[1])/2<1680 and (c[2]+c[3])/2>672 for c in floors)
    assert interval([[0,336,0],[336,0,0],[336,336,0]],120,0,1)==(216,336)


def test_embedded_box_reinforcement_extends_up_from_the_bearing_plate():
    package,state=adopted('hr10');model=build_model(package,state)
    scenes=prepare(model,package)
    scene=next(s for s in scenes if s['family']=='review_base' and any(p['id']=='REINF1' for p in s['parts']))
    parts={p['id']:p for p in scene['parts']}
    plate_top=max(q[2] for f in parts['P1']['faces'] for q in f)
    for part in (p for p in scene['parts'] if p['id'].startswith('REINF')):
        zs=[q[2] for f in part['faces'] for q in f]
        assert min(zs)==pytest.approx(plate_top)
        assert max(zs)==pytest.approx(50)


def test_weak_axis_continuity_plates_stay_inside_column_flange_envelope():
    package,state=adopted('hr32');scenes=prepare(build_model(package,state),package)
    checked=0
    for scene in scenes:
        parts={p['id']:p for p in scene['parts']}
        column=parts.get('M1',{})
        if 'weak-axis' not in column.get('description',''):continue
        pts=[q for f in column['faces'] for q in f]
        for part in (p for p in scene['parts'] if p['id'].startswith('CP')):
            for axis in (0,1):
                values=[q[axis] for f in part['faces'] for q in f]
                assert min(values)>=min(q[axis] for q in pts)-1e-8
                assert max(values)<=max(q[axis] for q in pts)+1e-8
            checked+=1
    assert checked
