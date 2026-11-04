from types import SimpleNamespace
import pytest
from steltic_openbim.review_cfs_source_bindings import apply


def fixture():
    b=SimpleNamespace(key='cfs12',cfg=dict(heights_ft=[10]*8),walls=[],members=[],profiles={},records={},used_records=set(),changes=[])
    b.profiles['600S162-54']=dict(family='channel',dimensions=dict(t=.0566))
    b.profiles['600T150-54']=dict(family='channel',dimensions=dict(t=.0566))
    for k in range(1,9):
        b.walls.append(dict(line='X15',level=k,runs=[dict(start_in=0,end_in=120),dict(start_in=144,end_in=264)]))
        for bay in (1,2):
            for suffix,kind,profile in [('S0','stud','600S162-54'),('BT','bottom_track','600T150-54'),('TT','top_track','600T150-54')]:
                b.members.append(dict(id=f'X15-L{k}-B{bay}-{suffix}',kind=kind,profile_id=profile,design_record_ids=[]))
    b.records={
        'segment_framing/@0':dict(table='segment_framing',data=dict(line='X15',framing_mil_stories_1_to_8=' / '.join(['43']*8))),
        'braced_wall_layout/@0':dict(table='braced_wall_layout',data=dict(line='X15',walls='2 x 10 ft',per_line_ft=20))}
    return b


def test_bindings_require_every_storey_run_and_actual_framing_thickness():
    b=fixture();apply(b)
    assert b.used_records==set(b.records)
    for m in b.members:
        assert set(m['design_record_ids'])==set(b.records)
        assert len(m['design_mapping_evidence'])==2
    apply(b)
    assert all(len(m['design_mapping_evidence'])==2 for m in b.members)


@pytest.mark.parametrize('defect',['thinner_track','mislabeled_thickness','missing_floor','wrong_segment_length','wrong_count'])
def test_invalid_source_scope_stays_unmapped(defect):
    b=fixture()
    if defect=='thinner_track':
        b.profiles['600T150-33']=dict(family='channel',dimensions=dict(t=.0346))
        b.members[-1]['profile_id']='600T150-33'
    elif defect=='mislabeled_thickness':b.profiles['600T150-54']['dimensions']['t']=.01
    elif defect=='missing_floor':b.members=[m for m in b.members if '-L8-' not in m['id']]
    elif defect=='wrong_segment_length':b.walls[-1]['runs'][0]['end_in']=119
    else:b.walls[-1]['runs'].pop()
    apply(b)
    expected='segment_framing/@0' if defect in ('thinner_track','mislabeled_thickness','missing_floor') else 'braced_wall_layout/@0'
    assert expected not in b.used_records
    assert all(expected not in m['design_record_ids'] for m in b.members)
    assert any(c['record_id']==expected and c['kind']=='source_wall_schedule_unbound' for c in b.changes)


def test_continuous_source_bays_cannot_be_replaced_by_isolated_segments():
    b=fixture();b.records['braced_wall_layout/@0']['data']['walls']='1 continuous walls of 2 bays x 10 ft'
    apply(b)
    assert 'braced_wall_layout/@0' not in b.used_records


def test_actual_cross_plan_binds_layout_and_segment_schedules_without_hiding_other_omissions():
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    p=evidence('cfs12')['package'];s=scenario('cfs12')
    m=build_model(p,dict(design_scenario=dict(id='cfs12',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    used=set(m['record_coverage']['used'])
    expected={r['id'] for r in p['design_records'] if r['table'] in ('segment_framing','braced_wall_layout')}
    assert len(expected)==22 and expected<=used
    assert 'studs/stud-segments-97' in used
    changes=[c for c in m['changes'] if c['kind']=='source_segment_stud_binding']
    assert changes
    members={v['id']:v for v in m['members']}
    for c in changes:
        stud=members[c['member_id']]
        assert stud['profile_id']=='600S162-97'
        assert 'studs/stud-segments-97' in stud['design_record_ids']
        assert 'studs/stud-party-walls' not in stud['design_record_ids']
    assert 'collectors/collector-reentrant-X' not in used
    assert any(r.startswith('diaphragms/') for r in m['record_coverage']['retained_without_physical_occurrence'])


@pytest.mark.parametrize('key,count',[('cfs2',4),('cfs3',5)])
def test_actual_other_wall_layouts_include_the_entire_source_line_ranges(key,count):
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    p=evidence(key)['package'];s=scenario(key)
    m=build_model(p,dict(design_scenario=dict(id=key,source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    records=[r for r in p['design_records'] if r['table']=='braced_wall_layout']
    assert len(records)==count
    assert all(r['id'] in m['record_coverage']['used'] for r in records)
    ranged=next(r for r in records if r['data']['line']==('Y1-Y5' if key=='cfs2' else 'Y28 to Y168'))
    bound=[v for v in m['members'] if ranged['id'] in v['design_record_ids']]
    names={v['id'].split('-L')[0] for v in bound}
    assert names==({'Y'+str(i) for i in range(1,6)} if key=='cfs2' else {'Y'+str(i) for i in range(28,169,28)})
