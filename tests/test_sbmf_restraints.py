import math
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


def test_every_source_strut_has_real_bolt_and_flange_contacts(actual):
    m,p=actual;count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_strut':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        assert len(s['fasteners'])==2 and len(c['member_ids'])==3
        assert s['fasteners'][0]['count']==2 and s['fasteners'][1]['count']==1
        assert s['fasteners'][1]['slot']['direction']==[0,0,1]
        for f in s['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],f['id'],label,q)
        count+=1
    assert count==(234 if m['pilot']=='cfs10' else 442)


def test_each_receiving_extension_attaches_to_an_actual_truss(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']};count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_restraint_cap':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        vertical,chord=[lookup[mid] for mid in c['member_ids']]
        assert vertical['axis'][1][2]+.125==pytest.approx(chord['axis'][0][2]-3)
        assert len(s['welds'])==3 and len(s['fasteners'])==2
        for f in s['fasteners']:
            for q in f['points']:
                world_y=c['point'][1]+q[1]
                assert min(v[1] for v in chord['axis'])+.75<=world_y<=max(v[1] for v in chord['axis'])-.75
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        count+=1
    assert count==(234 if m['pilot']=='cfs10' else 442)


def test_original_twenty_four_inch_struts_stay_inside_roof_and_source_grid_remains(actual):
    m,p=actual;length=1200 if m['pilot']=='cfs10' else 2400
    for v in m['members']:
        if v['kind']!='flange_strut':continue
        assert math.dist(*v['axis'])==pytest.approx(24)
        assert all(-10<=q[0]<=length+10 for q in v['axis'])
    xs={round(v['axis'][0][0],6) for v in m['members'] if v['kind']=='truss_chord' and v['id'].startswith('ROOF-') and not v['id'].startswith('ROOF-NORTH')}
    assert set(range(0,length+1,48))<=xs
    assert max(b-a for a,b in zip(sorted(xs),sorted(xs)[1:]))<=48
    extra=[x for x in xs if x not in range(0,length+1,48)]
    assert len(extra)==(18 if m['pilot']=='cfs10' else 34)
    first=[v for v in m['members'] if v['kind']=='flange_strut' and v['id'].startswith('FLANGE-STRUT-0-') and v['id'].endswith('--1')]
    stations=sorted(v['axis'][0][1] for v in first);face=6 if m['pilot']=='cfs10' else 5
    assert stations[:4]==[face+18*i for i in range(1,5)]
    assert stations[-4:]==[600-face-18*i for i in range(4,0,-1)]
    assert max(b-a for a,b in zip(stations,stations[1:]))<=96
