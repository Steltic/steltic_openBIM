import math
from collections import Counter
from test_cfs26_primary import actual
from test_sbmf_header_fit import contact
from steltic_openbim.assembly_templates import build_scene


def test_source_purlins_are_simple_spans_and_all_supports_contact(actual):
    m,p=actual;members=[v for v in m['members'] if v['kind']=='purlin'];counts=Counter()
    assert len(members)==27 and all(v['lap_in']==0 for v in members)
    assert all(v['profile_id']=='1200Z300-118' and v['source_cantilever_in']==48 for v in members)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_canopy_purlin':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']};counts[c['parameters']['purpose']]+=1
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        if c['parameters']['purpose']=='clip':assert sum(f['count'] for f in s['fasteners'] if f['id'].startswith('WEB-BOLTS'))==2
    assert counts=={'clip':54}
