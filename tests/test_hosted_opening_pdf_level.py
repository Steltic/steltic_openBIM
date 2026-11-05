import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_pdf import opening_level
from steltic_openbim.review_pdf import plan
from steltic_openbim.design_pdf import DesignSheets
from steltic_openbim.connection_details import prepare


def test_all_cfs18_clearances_schedule_at_their_actual_panel_level_without_mutation():
    p=evidence('cfs18')['package']
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    hosts={v['id']:v for v in m['panels']};before=fingerprint(m['openings'])
    hosted=[v for v in m['openings'] if v.get('level') is None]
    assert hosted
    for opening in hosted:assert opening_level(opening,hosts)==hosts[opening['host_id']]['level']
    assert fingerprint(m['openings'])==before


def test_explicit_base_level_is_preserved_and_unknown_levels_are_not_invented():
    assert opening_level(dict(id='base',level=0,host_id='roof'),{'roof':{'level':3}})==0
    with pytest.raises(ValueError,match='no declared or host level'):
        opening_level(dict(id='unhosted'),{})


def test_cfs18_floor_plan_renders_hosted_clearances_without_changing_them(tmp_path):
    p=evidence('cfs18')['package']
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    prepare(m,p)
    before=fingerprint(m['openings'])
    sh=DesignSheets(p,dict(revision=2,source_model_sha256=fingerprint(p)),tmp_path,m)
    for level in (1,2):
        sh.start('S10'+str(level),'Hosted clearance regression')
        plan(sh,level,'floor')
    sh.c.save()
    assert (tmp_path/'drawings.pdf').stat().st_size>10000
    assert fingerprint(m['openings'])==before
