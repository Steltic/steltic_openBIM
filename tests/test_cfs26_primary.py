from collections import Counter
import pytest
from steltic_openbim.review_cases import build_model,evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs26')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs26',answers_sha256=fingerprint(scenario('cfs26')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_canopy_source_groups_contact_every_actual_selected_ply(actual):
    m,p=actual;counts=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_canopy_primary':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']};purpose=c['parameters']['purpose'];counts[purpose]+=1
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        if purpose=='knee':assert sum(f['count'] for f in s['fasteners'])==4
        if purpose=='brace':assert sum(f['count'] for f in s['fasteners'])==4
        if purpose=='base':assert sum(f['count'] for f in s['fasteners'])==12
    assert counts['base']==8 and counts['knee']==8 and counts['brace']==16 and counts['brace_tie']==8 and counts['seams']==8
    assert counts['stitch']>=72


def test_source_face_plies_are_outside_column_and_source_records_retained(actual):
    m,p=actual;ps={v['id']:v for v in m['profiles']}
    r=ps['2X1400S250-97'];t=ps['1400S250-97']['dimensions']['t']
    assert abs(r['components'][1]['offset'][0]-t/2-(3.5+.1242/2))<1e-9
    assert all(v['design_record_ids']==['members/frame-raf'] for v in m['members'] if v['kind']=='rafter')
    assert not any(c['detail_ref']['id']=='review_canopy_brace' and c['member_ids'][0].startswith('F') for c in m['connections'])


def test_reference_axes_retain_native_worklines_separate_from_physical_fit(actual):
    m,p=actual
    for member in m['members']:
        if member['kind']=='column':
            assert member['axis'][0][2]==0
            assert member['axis'][1][2]==168+.1*member['axis'][0][0]
            assert member['end_offsets']==[[0,0,2.75],[0,0,4.5]]
        if member['kind']=='rafter':
            assert len(member['analysis_ids'])==12
            assert {v.rsplit(':',1)[-1] for v in member['analysis_ids']}=={str(i) for i in [*range(3,13),16,19]}
