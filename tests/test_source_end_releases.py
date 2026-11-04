import pytest
from steltic_openbim.review_releases import major_releases
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.review_assemblies import build_scene
from steltic_openbim.drawing_workflow import fingerprint


@pytest.mark.parametrize('flag,code,wanted',[('-releasey',1,{0}),('-releasey',2,{1}),('-releasey',3,{0,1}),('-releasez',3,set())])
def test_major_axis_release_uses_recorded_inertia_order_and_endpoint(flag,code,wanted):
    args=['elasticBeamColumn',1,1,2,42,29000,11200,10,7450,246,3,flag,code]
    assert major_releases(args)==wanted


def test_source_hr29_released_end_cannot_receive_the_fixed_end_rbs():
    p=evidence('hr29')['package'];m=build_model(p,dict(design_scenario=dict(id='hr29',answers_sha256=fingerprint(scenario('hr29')['answers']))))
    c=next(c for c in m['connections'] if c['id']=='hr:element:504:1')
    assert c['parameters']['released_major_end'] and not c['parameters']['moment']
    assert 'connections/conn-floor-W33X141' in c['source_context_records']
    beam=next(b for b in m['members'] if b['id']=='hr:element:504')
    assert [c['end'] for c in beam['rbs']['cuts']]==[0]
    scene=build_scene(m,p,c)
    assert not any(p.get('member',{}).get('rbs') for p in scene['parts'])
    assert all(w['kind']!='CJP' for w in scene['welds'])


def test_released_beam_keeps_its_selected_paired_shear_plates():
    p=evidence('hr1')['package'];m=build_model(p,dict(design_scenario=dict(id='hr1',answers_sha256=fingerprint(scenario('hr1')['answers']))))
    selected='connections/conn-floor-W40X277'
    cs=[c for c in m['connections'] if selected in c['design_record_ids']]
    assert cs and all(c['parameters']['released_major_end'] for c in cs)
    scene=build_scene(m,p,cs[0]);parts={p['id']:p for p in scene['parts']}
    assert all(parts[k]['geometry']['size'][1]==.625 for k in ('P1','P2'))
    assert parts['F1']['count']==18 and parts['F1']['diameter']==.875
    assert parts['F1']['grip']==pytest.approx(2*.625+.0625+.83)
    assert parts['M2']['member']['axis'][0][0]-parts['P1']['geometry']['origin'][0]==1
    assert all(w['size']==.9375 for w in scene['welds'] if w['id'] in ('W1','W2'))
