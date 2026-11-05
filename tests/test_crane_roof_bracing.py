import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_crane_roof_bracing import ends


@pytest.fixture(scope='module')
def case():
    p=evidence('hr33')['package'];s=scenario('hr33')
    return build_model(p,dict(design_scenario=dict(id='hr33',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers'])))),p


def test_source_rbs_and_intermediate_bracing_stations_are_all_present(case):
    m,_=case;rows=[c for c in m['changes'] if c['kind']=='hr33_source_roof_brace_schedule'];assert len(rows)==1
    row=rows[0];stations=row['stations_in']
    assert stations[0]-row['source_raft_face_in']==pytest.approx(37)
    assert 840-stations[-1]-row['source_raft_face_in']==pytest.approx(37)
    assert max(b-a for a,b in zip(stations,stations[1:]))<=148.8
    beams=[v for v in m['members'] if v['kind']=='flange_bracing_beam']
    assert len(beams)==10*len(stations)
    assert all(v['profile_id']=='HSS6X6X3/8' and math.dist(*v['axis'])==300 for v in beams)
    kicks=[v for v in m['members'] if v['id'].startswith('RBS-ROOF-') and v['kind']=='flange_kicker']
    assert len(kicks)==2*len(beams)
    for k in kicks:
        assert math.dist(*k['axis'])==pytest.approx(46.5)
        delta=[b-a for a,b in zip(*k['axis'])]
        assert abs(delta[0])==pytest.approx(delta[2]) and delta[1]==0
        assert len(k['slots'])==2 and all(s['width_in']==.625 for s in k['slots'])


def test_roof_support_datums_meet_instead_of_leaving_braces_below_the_rafters(case):
    m,p=case;lookup={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('crane_roof_bracing')]
    assert len(cs)==60
    for c in (cs[0],cs[5],cs[-1]):
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for i,label in enumerate(('LEFT','RIGHT')):
            assert parts['CAP'+str(i)]['bounds'][2][0]==pytest.approx(parts[label]['bounds'][2][1])
            assert parts['CAP'+str(i)]['bounds'][2][1]==pytest.approx(parts['BRACING']['bounds'][2][0])
        for i in (0,1):
            welds=[w for w in scene['welds'] if w['id'].startswith('K'+str(i))]
            assert len(welds)==8
            assert all(math.dist(w['a'],w['b'])==pytest.approx(4) for w in welds)
    top=max(ends(v)[0][2]+3 for v in m['members'] if v['kind']=='flange_bracing_beam')
    assert all(v['vertices'][0][2]==top for v in m['panels'] if v['kind']=='floor')


def test_raised_supplier_joists_retain_connected_workpoints(case):
    m,_=case;cs=m['connections'];lookup={v['id']:v for v in m['members']}
    joists=[v for v in m['members'] if v['id'].startswith('ROOF-JOIST-')]
    points={tuple(round(v,5) for v in c['point']) for c in cs}
    for member in joists:
        for q in member['joint_workpoints']:assert tuple(round(v,5) for v in q) in points,member['id']


def test_eave_restraints_reach_real_eave_and_supplier_joist_chords(case):
    m,p=case;lookup={v['id']:v for v in m['members']}
    cs=[c for c in m['connections'] if c.get('parameters',{}).get('crane_eave_bracing')]
    assert len(cs)==40
    for c in cs:
        eave,top,bottom,strut,kicker=[lookup[mid] for mid in c['member_ids']]
        assert eave['profile_id']=='W12X26' and top['kind']==bottom['kind']=='truss_chord'
        assert math.dist(*strut['axis'])==60 and strut['axis'][0][2]+2==454.5
        assert math.dist(*kicker['axis'])==pytest.approx(12)
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert parts['JOIST-TOP']['member']['source_member_index']==1
        assert parts['JOIST-BOTTOM']['member']['source_member_index']==2
        assert len([w for w in scene['welds'] if w['id'].startswith(('FOOT','HEAD'))])==4
