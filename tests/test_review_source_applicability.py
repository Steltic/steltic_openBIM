import copy
import pytest
from steltic_openbim.review_source_clauses import apply


def fixture():
    record=dict(id='anchorage/base',table='anchorage',data=dict(story=1,
        basis='Sill shear anchorage at the base story',selection='3/4 in. cast-in anchors'))
    model=dict(members=[],connections=[])
    for level in (1,2,3):
        mid='BT-'+str(level);z=(level-1)*120
        model['members'].append(dict(id=mid,kind='bottom_track',level=level,axis=[[0,0,z],[120,0,z]],local_y=[0,0,1]))
        model['connections'].append(dict(id=mid,member_ids=[mid],point=[6,0,z],
            detail_ref=dict(id='review_cfs_sill'),design_record_ids=['anchorage/base']))
    return model,dict(design_records=[record])


def test_base_source_stays_selected_only_at_its_declared_story():
    model,package=fixture();original=copy.deepcopy(package)
    apply(model,package)
    assert model['connections'][0]['design_record_ids']==['anchorage/base']
    for connection in model['connections'][1:]:
        assert connection['design_record_ids']==[]
        assert connection['source_context_records']==['anchorage/base']
        assert connection['source_record_applicability'][0]['source_story']==1
    once=copy.deepcopy(model);apply(model,package)
    assert model==once and package==original


@pytest.mark.parametrize('change',[dict(story=2),dict(basis='Anchorage, unspecified level'),dict(selection='base: cast-in anchors; floors: screws')])
def test_unproven_or_mixed_scope_is_never_discarded(change):
    model,package=fixture();package['design_records'][0]['data'].update(change)
    apply(model,package)
    assert all(c['design_record_ids']==['anchorage/base'] for c in model['connections'])


def test_hold_down_record_is_not_reclassified_as_sill_scope():
    model,package=fixture()
    for c in model['connections']:c['detail_ref']['id']='review_cfs_hold_down'
    apply(model,package)
    assert all(c['design_record_ids']==['anchorage/base'] for c in model['connections'])


def test_located_roof_head_keeps_wall_base_and_interstorey_anchor_schedule_as_context():
    model,package=fixture()
    record=package['design_records'][0]
    record.update(table='connections',data=dict(selection='base: anchors along the bottom track; floors: straps, stud above to stud below across the rim'))
    top=dict(id='TT',kind='top_track',level=3,axis=[[0,0,360],[120,0,360]],local_y=[0,0,-1])
    roof=dict(id='ROOF',member_ids=['TT'],point=[6,0,360],detail_ref=dict(id='review_cfs_floor'),
        design_record_ids=[record['id']],parameters=dict(physical_floor_stack=dict(track_ids=['TT'],truss_ids=['ACTUAL-TRUSS'])))
    model['members'].append(top);model['connections'].append(roof)
    original=copy.deepcopy(package);apply(model,package)
    assert roof['design_record_ids']==[] and roof['source_context_records']==[record['id']]
    assert all(c['design_record_ids']==[record['id']] for c in model['connections'][:-1])
    assert model['connections'][0]['source_record_selections'][0]['clause']=='base'
    assert model['connections'][1]['source_record_selections'][0]['clause']=='floors'
    once=copy.deepcopy(model);apply(model,package)
    assert model==once and package==original


def test_missing_receiver_binding_does_not_discard_a_potential_selection():
    model,package=fixture();c=model['connections'][0];t=model['members'][0]
    c['detail_ref']['id']='review_cfs_floor';t.update(kind='top_track',local_y=[0,0,-1])
    package['design_records'][0]['data']['selection']='base: anchors along the bottom track; floors: straps, stud above to stud below across the rim'
    apply(model,package)
    assert c['design_record_ids']==['anchorage/base']


def test_cfs13_low_roof_has_no_fictitious_base_anchors_but_the_wall_base_keeps_them():
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    from steltic_openbim.review_cfs_wall_bindings import bind
    p=evidence('cfs13')['package'];s=scenario('cfs13')
    m=build_model(p,dict(design_scenario=dict(id='cfs13',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    bind(m);apply(m,p)
    cs={c['id']:c for c in m['connections']}
    rid='connections/anch-typeII-NE'
    roof=cs['NE-L3-B3-TT'];base=cs['NE-L1-B3-BT']
    assert rid not in roof['design_record_ids'] and rid in roof['source_context_records']
    assert rid in base['design_record_ids']
    assert any(r['record_id']==rid and r['clause']=='base' for r in base['source_record_selections'])
