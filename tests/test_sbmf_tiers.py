import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p);s=scenario('cfs18')
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_actual_tier_clip_fasteners_and_source_column_angles(actual):
    m,p=actual;count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_tier':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        assert len(c['member_ids'])==4
        assert len(s['fasteners'])==3
        for f in s['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],f['id'],label,q)
        source_welds=[w for w in s['welds'] if w['basis']=='S']
        assert len(source_welds)==4
        assert all(math.dist(w['a'],w['b'])==pytest.approx(6) and w['size']==.25 for w in source_welds)
        count+=1
    assert count==8


def test_tier_webs_touch_and_source_seam_screws_are_at_most_twelve_inches(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']};groups={}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_tier_seam':continue
        lo,hi=[lookup[v] for v in c['member_ids']];assert hi['axis'][0][2]-lo['axis'][0][2]==pytest.approx(.0713)
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        f=scene['fasteners'][0];assert f['count']==1 and f['basis']=='S'
        for label in f['connects']:assert contact(parts[label],f,f['points'][0])
        groups.setdefault(lo['id'],[]).append(c['point'][0])
    assert len(groups)==4
    for values in groups.values():
        assert max(b-a for a,b in zip(sorted(values),sorted(values)[1:]))<=12


def test_strap_collectors_leave_the_vertical_tier_slot_clear(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']};count=0
    for c in m['connections']:
        if not c.get('parameters',{}).get('physical_strap_end') or abs(c['point'][2]-144)>.01:continue
        if not c['member_ids'][1].startswith('SIDE-'):continue
        s=build_scene(m,p,c);part=next(v for v in s['parts'] if v['id']=='COLLECTOR')
        strap=lookup[c['member_ids'][0]];far=max(strap['axis'],key=lambda q:math.dist(q,c['point']))
        if far[2]>144:assert part['bounds'][2][0]>=1-1e-6
        else:assert part['bounds'][2][1]<=-1+1e-6
        count+=1
    assert count==32
