from collections import defaultdict
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_gypsum_is_both_real_faces_and_stud_grid_matches_joists(actual):
    m,p=actual;panels=[v for v in m['panels'] if '-GYP' in v['id'] and v['kind']=='wall_sheathing'];assert len(panels)==4
    materials={v['id']:v for v in m['materials']}
    for panel in panels:
        assert panel['thickness_in']==.625
        assert 'gypsum' in materials[panel['material_id']]['specification']
    studs=[v for v in m['members'] if v['id'].startswith('BEARING-1-') and v['kind']=='stud']
    # Two local paired stations and shifted edge joists add two studs per row.
    assert len(studs)==76
    joists=[v for v in m['members'] if v['id'].startswith('WING-J-1-')]
    for stud in studs:
        assert stud['profile_id']=='600S162-43' and stud['slots']
        assert 'framing/mezz-stud-L1-bearing' in stud['design_record_ids']
        assert any(j['axis'][0][0]==stud['axis'][0][0] for j in joists)


def test_every_bearing_wall_screw_contacts_real_receivers_and_host_panels(actual):
    m,p=actual;counts={'bridge':0,'gypsum':0};stations=defaultdict(list)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_mezz_bearing':continue
        par=c['parameters'];counts[par['purpose']]+=1;scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        if par['purpose']=='gypsum':
            assert len(scene['fasteners'])==2
            zs=par['z_relative'];assert max(d-a for a,d in zip(zs,zs[1:]))<=12
            stations[c['member_ids'][0]].extend(c['point'][2]+v for v in zs)
            for key in ('negative_panel','positive_panel'):
                assert any(v.get('bound_panel_id')==par[key] and v['representation_role']=='context_only' for v in scene['parts'])
        else:assert sum(f['count'] for f in scene['fasteners'])==4
        for f in scene['fasteners']:
            assert f['basis']=='A'
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
    assert counts=={'bridge':76,'gypsum':152}
    for values in stations.values():
        assert len(values)==10
        values.sort();assert max(d-a for a,d in zip(values,values[1:]))<=12
