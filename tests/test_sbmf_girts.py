import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module',params=('cfs10','cfs18'))
def actual(request):
    key=request.param;p=evidence(key)['package'];before=fingerprint(p);s=scenario(key)
    m=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_all_bypass_bolts_touch_the_actual_host_and_each_girt_web(actual):
    m,p=actual;count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_girt':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        assert len(s['fasteners'])==2
        for f in s['fasteners']:
            assert f['basis']=='A' and f['count']==2
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        if m['pilot']=='cfs10':assert 'PACK0' in parts
        assert parts['GIRT']['member']['source_member_index']==0
        assert parts['HOST']['member']['source_member_index']==1
        count+=1
    assert count==(16 if m['pilot']=='cfs10' else 240)


def test_unselected_cfs18_field_studs_are_removed_but_source_braced_studs_remain(actual):
    m,p=actual
    if m['pilot']!='cfs18':return
    assert not any(v['id'].startswith('SIDE-STUD-') for v in m['members'])
    assert any(v['id'].startswith('SIDE-0-0-ST-') for v in m['members'])
    assert any(v['id']=='framing/sidewall-studs' for v in p['design_records'])
    assert any(c['kind']=='remove_duplicate_unselected_wall_infills' for c in m['changes'])
