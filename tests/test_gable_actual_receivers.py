import copy,math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.fixture(scope='module')
def case():
    p=evidence('hr31')['package'];before=copy.deepcopy(p);s=scenario('hr31')
    m=build_model(p,dict(design_scenario=dict(id='hr31',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    assert p==before
    return m,p


def test_knees_use_source_column_flange_and_true_sloping_rafter(case):
    m,p=case;lookup={v['id']:v for v in m['members']}
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_gable_knee')]
    assert len(cs)==18
    for c in (cs[0],cs[1],cs[-1]):
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        col=lookup[c['member_ids'][1]];data=c['parameters']['actual_gable_knee']
        assert abs(col['local_y'][0])==pytest.approx(1)
        assert max(q[2]+o[2] for q,o in zip(col['axis'],col['end_offsets']))==pytest.approx(c['point'][2]+data['flange_upper_in']+3.625)
        r=parts['RAFTER']['member'];delta=[r['axis'][1][i]-r['axis'][0][i] for i in range(3)]
        assert delta[2]/delta[0]==pytest.approx(.25)
        assert parts['COLUMN']['member']['source_member_index']==1
        for f in scene['fasteners']:
            assert len(f['points'])==8
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)


def test_cap_physically_bears_below_actual_office_girder_and_bolts_meet_steel(case):
    m,p=case;cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_bearing_cap')]
    assert cs
    for c in cs:
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert parts['CAP']['bounds'][2][0]==pytest.approx(parts['COLUMN']['bounds'][2][1])
        assert parts['CAP']['bounds'][2][1]==pytest.approx(parts['GIRDER']['bounds'][2][0])
        assert parts['CAP']['bounds'][0][1]-parts['CAP']['bounds'][0][0]==12
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)
