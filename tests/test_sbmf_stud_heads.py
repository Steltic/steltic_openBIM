from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs_occurrences import axis
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_every_field_head_has_clearance_and_two_guides_on_its_real_track(actual):
    m,p=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']};count=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_stud_head':continue
        stud,track=[members[mid] for mid in c['member_ids']];count[c['parameters']['tier']]+=1
        td=profiles[track['profile_id']]['dimensions']
        underside=axis(track)[0][2]-td['t']/2
        assert underside-axis(stud)[1][2]==pytest.approx(.625)
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert len(scene['fasteners'])==2
        for f in scene['fasteners']:
            assert f['basis']=='A' and f['slot']['host_part_id']=='TRACK'
            assert f['slot']['travel_in']==1 and f['slot']['length_in']-f['diameter']>=1
            assert f['shoulder_length_in']>td['t']
            q=f['points'][0]
            for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label)
            # Both slot ends stay in the actual two-inch track leg. Head
            # clearance remains positive at the extreme downward movement.
            z=c['point'][2]+q[2]
            assert z-.625>axis(track)[0][2]-td['b']
            assert z+.625<underside
        assert .625-c['parameters']['travel_in']/2>=.125
    assert count=={'lower':32,'upper':32}


def test_only_nonbearing_field_heads_slide_and_source_chords_remain_fixed(actual):
    m,_=actual;members={v['id']:v for v in m['members']}
    chords=[c for c in m['connections'] if c['detail_ref']['id']=='review_sbmf_chord_track' and c['id'].startswith('SIDE-')]
    assert len(chords)==16
    assert all(members[c['member_ids'][0]]['kind']=='chord' for c in chords)
    feet=[c for c in m['connections'] if c['id'].startswith('SIDE-') and '-ST-' in c['id'] and c['id'].endswith(':0')]
    assert len(feet)==64 and all(c['detail_ref']['id']=='cfs_stud' for c in feet)
