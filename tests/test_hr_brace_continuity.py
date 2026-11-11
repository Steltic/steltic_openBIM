"""Regress the disconnected BRB pin and displaced apex support strip."""
import math
import pytest
from shapely.geometry import Polygon,Point,LineString
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_hr_brace_ends import bind,CASES
from test_cfs27_source_fit import contact


@pytest.mark.parametrize('key',sorted(CASES))
def test_every_reviewed_brace_has_continuous_gusset_and_physical_end(key):
    package=evidence(key)['package'];source=fingerprint(package)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(scenario(key)['answers']))))
    bind(model,package);lookup={m['id']:m for m in model['members']}
    count=0
    for c in model['connections']:
        if c['detail_ref']['id'] not in ('review_brace','review_brb'):continue
        count+=1;s=build_scene(model,package,c);parts={p['id']:p for p in s['parts']}
        polygon=Polygon([(q[0],q[2]) for q in parts['GUSSET']['polygon']])
        assert polygon.is_valid and polygon.area>0
        for w in s['welds']:
            if 'GUSSET' in w['connects']:
                assert polygon.buffer(1e-6).covers(LineString([(w[q][0],w[q][2]) for q in ('a','b')])),(key,c['id'],w['id'])
        material_stations={}
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:
                    part=parts[name]
                    if part.get('holes'):
                        assert any(math.dist(h['point'],q)<1e-6 and h['axis']==f['axis'] and
                                   h['diameter_in']>=f['diameter'] for h in part['holes'])
                        axis=tuple(f['axis']);mkey=name,axis
                        if mkey not in material_stations:
                            values=[sum(a*b for a,b in zip(v,axis)) for face in part['faces'] for v in face]
                            material_stations[mkey]=min(values),max(values)
                        shaft_start=sum(a*b for a,b in zip(q,axis));lo,hi=material_stations[mkey]
                        assert lo>=shaft_start-1e-6 and hi<=shaft_start+f['grip']+1e-6
                    else:assert contact(part,f,q),(key,c['id'],f['id'],name)
        if s['subtype'] in ('apex','link_end'):
            lines=[w for w in s['welds'] if w.get('source_weld_id',w['id'])=='WGB']
            endpoints=sorted((w[q] for w in lines for q in ('a','b')),key=lambda p:p[0])
            centre=[(a+b)/2 for a,b in zip(endpoints[0],endpoints[-1])]
            actual=lookup[c['member_ids'][0]];far=max(actual['axis'],key=lambda q:math.dist(q,c['point']));v=[a-b for a,b in zip(far,c['point'])]
            assert centre[0]==pytest.approx(centre[2]*math.hypot(*v[:2])/v[2])
        m=lookup[c['member_ids'][0]];end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']))
        assert math.dist([0,0,0],m['end_offsets'][end])==pytest.approx(math.dist([0,0,0],parts['BRACE']['member']['axis'][0]))
        if c['detail_ref']['id']=='review_brb':
            if 'GUSSET-BOLTS' in parts:
                group=next(f for f in s['fasteners'] if f['id']=='GUSSET-BOLTS')
                assert group['connects']==['SPLICE0','GUSSET','SPLICE1']
                assert all(len(parts[name]['holes'])==len(group['points']) for name in group['connects'])
                assert 'CORE-END' in parts
            else:
                for name in ('CHEEK0','CHEEK1'):
                    assert all(polygon.buffer(1e-6).covers(Point(q[0],q[2])) for face in parts[name]['faces'] for q in face)
                assert 'END-CAP' in parts
    assert count>0 and fingerprint(package)==source
    before=fingerprint(model);bind(model,package);assert fingerprint(model)==before
