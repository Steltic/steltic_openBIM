import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('key',['hr31','hr33'])
def test_endwall_slip_heads_use_actual_post_cut_and_roof_underside(key):
    p=evidence(key)['package'];s=scenario(key)
    m=build_model(p,dict(design_scenario=dict(id=key,source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    heads=[c for c in m['connections'] if c.get('parameters',{}).get('actual_endwall_head')]
    assert heads
    for c in heads:
        d=c['parameters']['actual_endwall_head'];assert d['post_top_in']<=d['roof_z_in']-.4999
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert parts['POST']['member']['source_member_index']==0
        assert parts['RAFTER']['member']['source_member_index']==1
        assert scene['fasteners'][0]['slot']['length_in']==1.875
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)
    if key=='hr33':
        c=next(c for c in m['connections'] if c.get('parameters',{}).get('actual_endwall_base'))
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert len(scene['fasteners'])==4
        assert parts['POST']['bounds'][2][0]==pytest.approx(2.75)
        assert len([v for v in scene['parts'] if v['id'].startswith('WASHER')])==4
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(name,q)
