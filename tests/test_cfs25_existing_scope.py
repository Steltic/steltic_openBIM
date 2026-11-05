from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene


def test_existing_joints_retain_the_gold_scope_without_invented_hardware():
    source=evidence('cfs25');p=source['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs25',answers_sha256=fingerprint(scenario('cfs25')['answers']))))
    interface=m['physical_interfaces'][0]
    assert interface['scope']=='existing'
    assert interface['requirements']==source['calc']['existing_structure_interface']
    assert interface['detail_ref']['revision']==fingerprint(interface['requirements'])
    count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_retrofit_existing':continue
        assert c['scope']=='delegated' and c['responsible_party'] and c['representation'] and c['design_record_ids']
        assert set(c['member_ids'])<=set(interface['member_ids'])
        scene=build_scene(m,p,c)
        assert not scene['fasteners'] and not scene['welds']
        assert all(v.get('member') or v.get('representation_role')=='context_only' for v in scene['parts'])
        assert scene['interfaces'][0]['scope']=='existing'
        count+=1
    assert count==139
    assert fingerprint(p)==before
