import copy
import pytest
from steltic_openbim.review_cases import evidence,build_model,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene


@pytest.fixture(scope='module')
def example():
    package=evidence('hr9')['package'];saved=copy.deepcopy(package)
    model=build_model(package,dict(design_scenario=dict(id='hr9',answers_sha256=fingerprint(scenario('hr9')['answers']))))
    assert package==saved
    return model,package


def test_each_plate_has_actual_boundaries_clear_fields_and_retained_source(example):
    model,package=example;members={m['id']:m for m in model['members']};profiles={p['id']:p for p in model['profiles']}
    connections=[c for c in model['connections'] if c['detail_ref']['id']=='review_plate_wall']
    assert len(connections)>50
    for c in connections:
        data=c['parameters']['actual_plate_boundary'];wall=members[c['member_ids'][0]]
        assert profiles[wall['profile_id']]['dimensions']['thickness']==.1875
        assert data['field_right_in']-data['field_left_in']<data['source_bay_width_in']==168
        assert wall['source_gross_width_in'] in (336,672)
        assert wall['source_workline'] and set(c['design_record_ids'])<=set(wall['design_record_ids'])
        assert any(r.startswith('members/brace-WEB') for r in wall['design_record_ids'])
        assert any(members[e['member_id']]['kind']=='rocking_post' for e in data['column_faces'])
        for edge in data['column_faces']:
            assert members[edge['member_id']]['kind'] in ('column','rocking_post')
            field=data['field_left_in'] if edge['side']>0 else data['field_right_in']
            assert (field-edge['face_in'])*edge['side']>=2-1e-6
        scene=build_scene(model,package,c)
        for part in scene['parts']:
            if not part.get('member'):continue
            actual=members[c['member_ids'][part['member']['source_member_index']]]
            assert part['member']['profile_id']==actual['profile_id']
        assert all(w['size'] in (.25,.1875) for w in scene['welds'])
    assert not any(p['kind']=='steel_plate_wall' for p in model['panels'])


def test_source_multi_bay_is_split_at_real_intermediate_column(example):
    model,_=example
    fields=[m for m in model['members'] if m.get('source_wall_id')=='SPSW-PXB-13']
    assert len(fields)==4
    assert {m['source_gross_width_in'] for m in fields}=={672}
    assert all(m['perforations']=={'diameter_in':6,'diagonal_pitch_in':10.75} for m in fields)
    assert all(m['basis']=='A' for m in fields)
