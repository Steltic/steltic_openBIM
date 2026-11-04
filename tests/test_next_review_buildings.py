"""Regressions for source-specific interfaces in the second twenty buildings."""
import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.connection_details import prepare

def model(key):
    spec=scenario(key);p=evidence(key)['package']
    return p,build_model(p,{'revision':1,'design_scenario':{'id':key,'source_sha256':spec['source_sha256'],'answers_sha256':fingerprint(spec['answers'])}})

def test_hillside_footing_datum_is_not_a_floor_and_auxiliary_basement_is_framed():
    _,m=model('hr14')
    assert 132 not in {z for _,_,z in m['levels']}
    assert 144 in {z for _,_,z in m['levels']}
    assert len(m['panels'])==232
    assert len([mm for mm in m['members'] if mm['id'].startswith('B1-G-')])==9
    assert any(c['point'][2]==132 and c['detail_ref']['id']=='review_base' for c in m['connections'])

@pytest.mark.parametrize('key',['hr18','hr21','hr30'])
def test_crossing_details_do_not_replace_brace_end_connections(key):
    _,m=model(key)
    for brace in (x for x in m['members'] if x['kind']=='brace'):
        ends=[c['point'] for c in m['connections'] if brace['id'] in c['member_ids'] and c['detail_ref']['id'] in ('review_brace','review_brace_crossing')]
        assert all(any(math.dist(point,end)<.001 for end in ends) for point in brace['axis'])
    assert any(c['detail_ref']['id']=='review_brace_crossing' for c in m['connections'])

def test_boxed_school_columns_use_axis_specific_details_and_classroom_pinned_bases():
    p,m=model('hr16');scenes=prepare(m,p)
    ids={rid for s in scenes for rid in s['source_record_ids']}
    assert 'connections/conn-two-way-W14X193-strong-W24X76' in ids
    assert 'connections/conn-two-way-W14X193-weak-W27X94' in ids
    assert len([c for c in m['connections'] if 'connections/conn-base-pinned-W14X176' in c['design_record_ids']])==4
    assert any(s['family']=='review_roof_step' for s in scenes)

def test_composite_studs_have_heads_without_bolt_nuts_and_stair_holes_avoid_them():
    p,m=model('hr30');scenes=prepare(m,p)
    for scene in (s for s in scenes if s['family']=='review_composite_studs'):
        assert not scene['fasteners']
        studs=next(p for p in scene['parts'] if p['id']=='STUDS')
        assert studs['count'] in (49,53,80)
        assert len(studs['points'])==studs['count']
    assert not any(c['kind']=='framed_opening_cut' and 'INF-' in c['old_member'] for c in m['changes'])

def test_atrium_column_bears_on_the_continuous_source_transfer_girder():
    _,m=model('hr25');members={x['id']:x for x in m['members']}
    girders=[x for x in m['members'] if x['profile_id']=='W36X925']
    assert len(girders)==1 and math.dist(*girders[0]['axis'])==720
    c=next(c for c in m['connections'] if c['id']=='ATRIUM-COLUMN-BEARING')
    assert members[c['member_ids'][1]]['profile_id']=='W36X925'

def test_cfs_strap_area_is_never_used_as_thickness():
    p,m=model('cfs2');profiles={x['id']:x for x in m['profiles']}
    straps=[x for x in m['members'] if x['kind']=='strap']
    assert straps and all(profiles[x['profile_id']]['dimensions']['thickness']<.08 for x in straps)
    refs={r for c in m['connections'] for r in c['design_record_ids']}
    assert {f'connections/conn-strap-end-{w}x{mil}' for w,mil in [(3,54),(4,54),(5,54),(8,68)]}<=refs

@pytest.mark.parametrize('key',['cfs10','cfs18'])
def test_sbmf_roof_and_separated_wing_keep_source_load_paths(key):
    _,m=model(key)
    main=[x for x in m['members'] if x['id'].startswith('FRAME-') and x['kind']=='moment_beam']
    assert main and all(x['level']==3 for x in main)
    assert any(c['detail_ref']['id']=='review_sbmf_strut' for c in m['connections'])
    assert len([p for p in m['panels'] if p['kind']=='roof' and p['level']==3])==2
    assert all(math.dist(*x['axis'])<145 for x in m['members'] if x['id'].startswith('SIDE-STUD-'))
    if key=='cfs18':assert len([x for x in m['members'] if x['id'].startswith('END-POST-')])==6

def test_transfer_slip_is_drawn_and_lower_chord_has_no_stud_attachment():
    p,m=model('hr20');scenes=prepare(m,p)
    slips=[s for s in scenes if s['family']=='review_transfer_slip']
    assert slips and all(f['slot']['length_in']==3 for s in slips for f in s['fasteners'])
    assert all(s['subtype']=='transfer' for s in scenes if s['family']=='review_diaphragm' and s['level']==2)

def test_equipment_plan_gussets_are_notched_and_do_not_hide_primary_girder_ends():
    p,m=model('hr35');scenes=prepare(m,p)
    joints=[s for s in scenes if s['family']=='review_plan_angle' and s['subtype']=='column_quadrant']
    assert joints
    for scene in joints:
        plate=next(q for q in scene['parts'] if q['id']=='PLATE')
        points={tuple(abs(x) for x in v[:2]) for face in plate['faces'] for v in face}
        assert points=={(0,6),(6,6),(6,0),(15,0),(15,15),(0,15)}
        hosts=[q for q in scene['parts'] if q['id'].startswith('HOST')]
        assert len(hosts)==3
        assert sorted(q['member']['profile_id'] for q in hosts)==['W10X39','W16X40','W16X40']
    for mm in (q for q in m['members'] if q['profile_id']=='W16X40'):
        ends=[c['point'] for c in m['connections'] if c['member_ids'][0]==mm['id'] and c['detail_ref']['id']=='review_beam']
        assert all(any(math.dist(point,end)<.01 for end in ends) for point in mm['axis'])

def test_school_splices_follow_the_classroom_floor_not_the_lower_gym_roof_index():
    _,m=model('hr16')
    splices=[c for c in m['connections'] if c['detail_ref']['id']=='review_splice' and any('lateral_col-W14X' in r for r in c['design_record_ids'])]
    assert splices and all(c['point'][2]==336 for c in splices)
    assert {'connections/conn-lateral_col-W14X159','connections/conn-lateral_col-W14X193','connections/conn-lateral_col-W14X193B'}<={r for c in splices for r in c['design_record_ids']}

def test_boxed_column_splice_includes_side_plates_and_source_erection_bolts():
    p,m=model('hr16');scenes=prepare(m,p)
    for c in m['connections']:
        if c['detail_ref']['id']=='review_splice' and not c.get('parameters',{}).get('boxing_t'):
            assert 'connections/conn-lateral_col-W14X193B' not in c['design_record_ids']
    scene=next(s for s in scenes if s['family']=='review_splice' and 'connections/conn-lateral_col-W14X193B' in s['source_record_ids'])
    assert {'BOX00','BOX01','BOX10','BOX11','ERECT'}<={q['id'] for q in scene['parts']}
    assert {'BOX-SPLICE0','BOX-SPLICE1'}<={q['id'] for q in scene['welds']}
    assert sum(len(f['points']) for f in scene['fasteners'] if f['id'].startswith('ERECT-B'))==4
    assert all(f['diameter']==.875 for f in scene['fasteners'] if f['id'].startswith('ERECT-B'))

def test_apex_dimension_uses_the_actual_gusset_beam_interface():
    p,m=model('hr24')
    for scene in (s for s in prepare(m,p) if s['family']=='review_brace' and s['subtype']=='apex'):
        dim=next(d for d in scene['dimensions'] if 'source interface' in (d.get('label') or ''))
        weld=next(w for w in scene['welds'] if w['id']=='WGB')
        assert dim['a']==weld['a'] and dim['b']==weld['b']

def test_box_splice_transition_uses_its_own_source_pair_and_division_diaphragm():
    p,m=model('hr10');scenes=prepare(m,p)
    stepped=next(s for s in scenes if s['family']=='review_splice' and s['title'].endswith('BOX20X1.75 / BOX22X2'))
    assert next(q for q in stepped['parts'] if q['id']=='TRANSITION')['transition_height_in']==4
    assert {'KINK0','KINK1','ERECT'}<={q['id'] for q in stepped['parts']}
    mixed=next(s for s in scenes if s['family']=='review_splice' and s['title'].endswith('W14X730 / BOX24X4'))
    assert next(q for q in mixed['parts'] if q['id']=='DIVISION')['geometry']['size'][2]==5
    assert next(q for q in mixed['parts'] if q['id']=='WEB-DIAPH')['geometry']['size'][1]==3.125
