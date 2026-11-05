from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs25')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs25',answers_sha256=fingerprint(scenario('cfs25')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_every_cladding_screw_crosses_sheet_flange_packing_and_its_washer(actual):
    m,p=actual;counts=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_retrofit_cladding':continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        counts[c['parameters']['purpose']]+=1
    assert counts['support']>1000 and counts['sidelap']>500


def test_option_a_retains_both_source_options_and_explicit_sheet_geometry(actual):
    m,p=actual
    sheets=[v for v in m['members'] if v['kind'].endswith('cladding_sheet')]
    assert len(sheets)>300
    assert all(v['source_rib_pitch_in']==12 and v['source_rib_depth_in']==1.25 for v in sheets)
    assert all(v['sheet_thickness_in']==.018 for v in sheets)
    panels=[v for v in m['panels'] if v['id'].startswith('SKIN-')]
    assert len(panels)==6
    assert {v['id'] for v in sheets}=={i for v in panels for i in v['physical_constituent_member_ids']}
    assert len([r for r in m['record_dispositions'] if r['record_id']=='schedules/sched-purlin-standing-seam'])==1
    assert not any(c['detail_ref']['id']=='review_skin_fastener' for c in m['connections'])


def test_source_corner_and_general_screw_pitch_are_both_present(actual):
    m,p=actual;counts=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_retrofit_cladding':continue
        par=c['parameters'];counts[par['purpose'],par['pitch']]+=1
        if par['purpose']=='support':
            assert par['pitch'] in (6,12)
            if not par['roof']:assert par['pitch']==12
    assert all(counts[k]>0 for k in [('support',6),('support',12),('sidelap',24)])


def test_sheet_end_links_reference_their_own_local_attachment(actual):
    import math
    m,p=actual;members={v['id']:v for v in m['members']};conns={v['id']:v for v in m['connections']}
    links=[v for v in m['connection_endpoint_links'] if v['member_id'].startswith('SKIN-')]
    assert len(links)==808
    for link in links:
        member=members[link['member_id']];c=conns[link['connection_id']]
        assert member['id'] in c['member_ids']
        end=member['axis'][0 if link['end']=='start' else 1]
        assert math.dist(end,c['point'])<72,(member['id'],c['id'])
