import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_column_local_checks import schedule
from steltic_openbim.review_shear_selection import paired
from steltic_openbim.review_assemblies import build_scene


def source(key,rid):
    return next(r['components'] for r in evidence(key)['calc']['connections'] if r['id']==rid)


@pytest.mark.parametrize('key,rid,count',[('hr13','conn-collector-column-webs',14),('hr17','conn-collector-column-webs',16),('hr24','conn-collector-columns-J10',8)])
def test_source_j10_schedule_preserves_every_explicit_location(key,rid,count):
    rows=schedule(source(key,rid))
    assert len(rows)==count
    assert len({(r['grid_x'],r['grid_y'],r['level']) for r in rows})==count
    assert all(r['t']>0 and r['width']>0 and r['web_weld']>0 for r in rows)
    if key=='hr24':assert all(r['flange_weld_kind']=='CJP' and r['web_weld']==.3125 for r in rows)


def test_web_side_and_flange_paired_plates_select_different_source_variants():
    text=source('hr17','conn-floor-W21X73')
    flange,match=paired(text,column='W14X176')
    assert match.groups()==('0.375','14.5')
    assert 'one 9/16 in' in flange and 'web-side ends on the' not in flange
    web,match=paired(text,weak=True,column='W14X257')
    assert match.groups()==('0.4375','14.5')
    assert '8.41 in' in web and 'one 3/4 in' in web and 'finger shim' in web


def test_alternate_paired_plate_wording_retains_two_actual_plates_and_welds():
    key='hr17';p=evidence(key)['package']
    m=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(scenario(key)['answers']))))
    c=next(c for c in m['connections'] if 'connections/conn-floor-W27X129' in c['design_record_ids'])
    scene=build_scene(m,p,c);parts={r['id']:r for r in scene['parts']}
    assert parts['P1']['geometry']['size'][1:]==[.5,20.5]
    assert parts['P2']['geometry']['size'][1:]==[.5,20.5]
    assert parts['F1']['count']==7 and parts['F1']['diameter']==1
    assert {w['size'] for w in scene['welds'] if w['id'] in ('W1','W2')}=={.625}
    assert parts['M2']['member']['axis'][0][0]-parts['P1']['geometry']['origin'][0]==.5


@pytest.mark.parametrize('key',['hr24','hr15','hr23','hr29'])
def test_braced_frame_prescriptive_fr_is_retained_despite_source_analysis_release(key):
    p=evidence(key)['package']
    m=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(scenario(key)['answers']))))
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('analysis_release_with_prescriptive_fr')]
    assert cs
    for c in cs:
        scene=build_scene(m,p,c)
        assert any(w['kind']=='CJP' for w in scene['welds'])
        assert not any(part.get('member',{}).get('rbs') for part in scene['parts'])
