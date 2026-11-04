"""Regression checks for physically different drawings hidden by analysis nodes."""
import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.connection_details import prepare


@pytest.fixture(scope='module')
def hr1():
    package=evidence('hr1')['package'];answers=scenario('hr1')['answers']
    model=build_model(package,dict(design_scenario=dict(id='hr1',answers_sha256=fingerprint(answers))))
    prepare(model,package)
    return model


def test_field_splices_split_physical_columns_above_analysis_floors(hr1):
    members={m['id']:m for m in hr1['members']}
    splices=[c for c in hr1['connections'] if c['detail_ref']['id']=='review_splice']
    assert splices
    for c in splices:
        columns=[members[mid] for mid in c['member_ids'] if members[mid]['kind']=='column']
        assert len(columns)==2
        assert all(any(math.dist(q,c['point'])<1e-6 for q in m['axis']) for m in columns)
        assert all(m.get('analysis_segments') for m in columns)


def test_brace_support_is_in_brace_bay_and_detail_uses_building_datum(hr1):
    members={m['id']:m for m in hr1['members']}
    for s in hr1['connection_assemblies']:
        if s['family']!='review_brace':continue
        parts={p['id']:p for p in s['parts']};point=s['building_point']
        if 'BEAM' in parts:
            beam=parts['BEAM']['member']
            assert beam['axis'][0][2]<0 # Building levels are top of steel.
        brace=parts['BRACE']['member'];actual=members[s['source_member_ids'][0]]
        far=max(actual['axis'],key=lambda p:math.dist(p,point));v=[p-q for p,q in zip(far,point)]
        actual_slope=v[2]/math.hypot(*v[:2])
        a,b=brace['axis'];assert (b[2]-a[2])/(b[0]-a[0])==pytest.approx(actual_slope)
        if s['subtype']=='corner':
            beam=next(members[mid] for mid in s['source_member_ids'] if members[mid]['kind']=='beam')
            assert any(sum((p[i]-point[i])*v[i] for i in (0,1))>0 for p in beam['axis'])


def test_opening_details_bind_actual_perimeter_and_keep_cut_infill_offsets(hr1):
    members={m['id']:m for m in hr1['members']}
    for c in hr1['connections']:
        if c['detail_ref']['id']!='test_floor_opening':continue
        assert len(c['member_ids'])==2
        assert all(members[mid]['kind']!='column' for mid in c['member_ids'])
    cuts=[m for m in hr1['members'] if m['kind']=='infill' and '-O' in m['id']]
    assert cuts and all(m['end_offsets'][0][2]<0 and m['end_offsets'][1][2]<0 for m in cuts)
    for s in hr1['connection_assemblies']:
        if s['family']!='test_floor_opening':continue
        actual=members[s['source_member_ids'][0]]
        if actual['kind'].startswith('opening_'):
            assert next(p['member'] for p in s['parts'] if p['id']=='M2')['axis'][0][2]==0


def test_base_retains_source_anchor_pattern_washers_and_lug_dimensions(hr1):
    bases=[s for s in hr1['connection_assemblies'] if s['family']=='review_base']
    for scene in bases:
        parts={p['id']:p for p in scene['parts']};anchors=parts['ANCH']
        assert anchors['count'] in (4,16)
        if anchors['count']==16:
            assert anchors['diameter']==1.75
            assert len({round(q[0],4) for q in anchors['points']})==4
            assert sorted({q[1] for q in anchors['points']})==[-11.25,-3.75,3.75,11.25]
            assert len([p for p in parts if p.startswith('WASHER-END-')])==16
            faces=parts['LUGX']['faces'];points=[q for face in faces for q in face]
            assert [max(q[i] for q in points)-min(q[i] for q in points) for i in range(3)]==[30,4.75,14]
        else:
            assert len([p for p in parts if p.startswith('WASHER-TOP-')])==4


def test_selected_studs_share_details_without_losing_occurrence_count(hr1):
    connections=[c for c in hr1['connections'] if c['detail_ref']['id']=='review_selected_studs']
    scenes=[s for s in hr1['connection_assemblies'] if s['family']=='review_selected_studs']
    assert len(scenes)<len(connections)/2
    groups={}
    for c in connections:
        p=c['parameters'];groups.setdefault(p['original_physical_member_id'],[]).append(p)
    assert all(sum(p['count'] for p in ps)==ps[0]['total_source_count'] for ps in groups.values())
    assert all(c['design_record_ids'] for c in connections)
