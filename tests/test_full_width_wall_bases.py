import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.fixture(scope='module')
def hr9():
    p=evidence('hr9')['package'];s=scenario('hr9')
    m=build_model(p,dict(design_scenario=dict(id='hr9',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    return m,p


def test_all_hr9_bases_keep_actual_panel_width_and_source_stud_density(hr9):
    m,p=hr9;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    bases=[c for c in m['connections'] if c['detail_ref']['id']=='review_plate_base']
    assert bases
    for c in bases:
        wall=members[c['member_ids'][0]];width=profiles[wall['profile_id']]['dimensions']['width']
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        receiver=parts['WALL']['member']
        assert receiver['profile_id']==wall['profile_id'] and receiver['source_member_index']==0
        assert receiver['axis'][0]==[0,0,2] and wall['end_offsets'][0]==[0,0,2]
        assert parts['WALL']['bounds'][0]==pytest.approx([-width/2,width/2])
        assert parts['EMBED']['bounds'][0]==pytest.approx([-width/2,width/2])
        assert parts['EMBED']['representation_role']=='assembly_component'
        assert parts['STUDS']['count']==round(width*4/12)
        assert parts['STUDS']['count']>12
        assert 'connections/conn-web-base' in c['design_record_ids']
        assert any(r.startswith('connections/conn-brace-') for r in c['design_record_ids'])
        for f in scene['fasteners']:
            for q in f['points']:
                # A welded stud starts on its host face; it is not a through bolt.
                # Its shaft enters the concrete, without drilling through steel.
                assert q[1]==pytest.approx(parts['EMBED']['bounds'][1][0])
                for axis in (0,2):assert parts['EMBED']['bounds'][axis][0]<q[axis]<parts['EMBED']['bounds'][axis][1]
                assert contact(parts['CONC'],f,q)
                assert f['axis']==[0,-1,0]
        assert len([w for w in scene['welds'] if w['id'].startswith('WF')])==2
        assert len([w for w in scene['welds'] if w['id'].startswith('WW')])==2


def test_hr9_base_fit_changes_keep_analysis_worklines_and_report_assumptions(hr9):
    m,_=hr9;members={v['id']:v for v in m['members']}
    changes=[v for v in m['changes'] if v['kind']=='plate_wall_base_clearance']
    assert changes
    for change in changes:
        wall=members[change['member_id']]
        assert wall['axis'][0][2]==0
        assert 'A:' in change['basis'] and 'unverified' in change['basis']
        panel=next(p for p in m['panels'] if p['id']==wall['id']+'-PL')
        assert min(q[2] for q in panel['vertices'])==2
