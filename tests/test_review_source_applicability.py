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
