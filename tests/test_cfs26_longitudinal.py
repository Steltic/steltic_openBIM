from collections import Counter
from test_cfs26_primary import actual
from test_sbmf_header_fit import contact
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs26_longitudinal import roof_bottom


def test_longitudinal_source_members_and_every_actual_attachment(actual):
    m,p=actual;counts=Counter()
    for member in m['members']:
        if member['kind']=='eave_strut':
            assert member['design_record_ids']==['schedules/sched-longitudinal']
            assert abs(member['axis'][0][2]+5+2-roof_bottom(member['axis'][0][0]))<1e-8
    for c in m['connections']:
        if c['detail_ref']['id']!='review_canopy_longitudinal':continue
        counts[c['parameters']['purpose']]+=1;s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        if c['parameters']['purpose']=='cap':
            fs=[f for f in s['fasteners'] if 'SOURCE' in f['id']]
            assert sum(f['count'] for f in fs)==4
            assert all(f['diameter']==.625 for f in fs)
        else:assert sum(f['count'] for f in s['fasteners'] if f['id'].startswith('BRACE'))==2
    assert counts==dict(cap=12,brace=24)
