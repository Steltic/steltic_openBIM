import math
from collections import Counter
from test_cfs26_primary import actual
from test_sbmf_header_fit import contact
from steltic_openbim.assembly_templates import build_scene


def test_canopy_source_24ga_panel_and_every_screw_ply(actual):
    m,p=actual;members={v['id']:v for v in m['members']};counts=Counter();sheets=[v for v in m['members'] if v['kind']=='roof_cladding_sheet']
    assert len(sheets)==27 and all(v['sheet_thickness_in']==.0236 for v in sheets)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_canopy_cladding':continue
        counts[c['parameters']['purpose'],c['parameters']['pitch']]+=1
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
    assert all(counts[k]>0 for k in [('support',6),('support',12),('sidelap',24)])
    cs={c['id']:c for c in m['connections']}
    for link in m['connection_endpoint_links']:
        if not link['member_id'].startswith('CANOPY-SHEET-'):continue
        member=members[link['member_id']];c=cs[link['connection_id']]
        assert member['id'] in c['member_ids']
        assert math.dist(member['axis'][0 if link['end']=='start' else 1],c['point'])<72
