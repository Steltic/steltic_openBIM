from collections import defaultdict
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.pilots.model import add
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_collector_laps_and_stitches_join_actual_distinct_webs(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']};records=set();splices=0;stations=defaultdict(list)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_collector':continue
        par=c['parameters'];records.update(c['design_record_ids'])
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        if par['purpose']=='splice':
            expected=6 if lookup[c['member_ids'][0]]['level']==1 else 4
            assert [f['count'] for f in scene['fasteners']]==[expected,expected]
            a,b=parts['OUTER-L']['bounds'][0],parts['OUTER-R']['bounds'][0]
            assert b[0]-a[1]==pytest.approx(.125)
            splices+=1
        else:stations[c['member_ids'][1]].append(c['point'][par['along']])
        for f in scene['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
    assert splices==24 and len(stations)==32
    assert records=={f'framing/mezz-collector-{d}-L{k}' for d in ('X','Y') for k in (2,3)}
    for values in stations.values():assert max(d-a for a,d in zip(sorted(values),sorted(values)[1:]))<=24.00001


def test_nested_webs_touch_without_moving_floor_bearing_and_heads_clear_lower_web(actual):
    m,_=actual;lookup={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    for upper in m['members']:
        if not upper['id'].startswith('MEZZ-') or '-COLLECTOR' not in upper['id']:continue
        lower=lookup[upper['id'].split('-COLLECTOR')[0]]
        ud=profiles[upper['profile_id']]['dimensions'];ld=profiles[lower['profile_id']]['dimensions']
        uz=add(upper['axis'][0],upper['end_offsets'][0])[2];lz=add(lower['axis'][0],lower['end_offsets'][0])[2]
        assert uz+ud['t']/2==pytest.approx(lower['axis'][0][2])
        assert uz-ud['t']/2==pytest.approx(lz+ld['t']/2)
        assert ud['d']/2-ud['t']-ld['d']/2==pytest.approx(.03125)
        assert profiles[upper['profile_id']]['source_profile_id']=='600T162-54'
        assert profiles[upper['profile_id']]['basis'].startswith('A')
        label=lower['id'].removesuffix('TT')
        for chord in [v for v in m['members'] if v['id'].startswith(label+'-CH-') and v['kind']=='chord']:
            assert add(chord['axis'][1],chord['end_offsets'][1])[2]==pytest.approx(lz-ld['t']/2)
