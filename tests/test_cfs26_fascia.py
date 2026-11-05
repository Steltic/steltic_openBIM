from collections import Counter
from test_cfs26_primary import actual
from test_sbmf_header_fit import contact
from steltic_openbim.assembly_templates import build_scene


def test_source_fascia_below_roof_and_all_actual_receivers_contact(actual):
    m,p=actual;counts=Counter(v['kind'] for v in m['members'])
    assert counts['fascia_post']==8 and counts['fascia_rail']==12 and counts['fascia_kicker']==36
    for v in m['members']:
        if v['kind']=='fascia_post':
            assert v['profile_id']=='2X600S200-68/BOX'
            assert abs(v['axis'][0][2]-(168+.1*v['axis'][0][0]-24))<1e-8
        if v['kind'].startswith('fascia'):assert v['design_record_ids']==['schedules/sched-girt']
    purposes=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_canopy_fascia':continue
        purposes[c['parameters']['purpose']]+=1
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        if c['parameters']['purpose']=='post':assert sum(f['count'] for f in s['fasteners'])==4
    assert purposes==dict(post=8,seams=8,rail=24,kicker_rail=36,kicker_purlin=36)
