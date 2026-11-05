from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.pilots.geometry import member_faces
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_source_chord_track_and_collector_fasteners_reach_actual_parts(actual):
    m,p=actual;counts=Counter()
    families={'review_sbmf_chord_stitch','review_sbmf_chord_track','review_sbmf_track_anchor','review_sbmf_top_collector','review_sbmf_wall_bridging'}
    for c in m['connections']:
        family=c['detail_ref']['id']
        if family not in families or not c['member_ids'][0].startswith('SIDE-'):continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        if family=='review_sbmf_chord_track':
            assert sum(f['count'] for f in scene['fasteners'])==c['parameters']['screws']
            points=[q for f in scene['fasteners'] for q in f['points']]
            assert len(set(tuple(q) for q in points))==len(points)
        counts[family]+=1
    assert counts['review_sbmf_chord_stitch']==192
    assert counts['review_sbmf_chord_track']==16
    assert counts['review_sbmf_track_anchor']==8
    assert counts['review_sbmf_top_collector']==52
    assert counts['review_sbmf_wall_bridging']>100


def test_header_bottom_now_meets_track_but_roof_chords_keep_saved_height(actual):
    m,p=actual;profiles={v['id']:v for v in m['profiles']}
    headers=[v for v in m['members'] if v['id'].startswith('HEADER-') and v['kind']=='girder']
    assert len(headers)==32
    assert all(min(q[2] for f in member_faces(v,profiles) for q in f)==pytest.approx(288) for v in headers)
    chords=[v for v in m['members'] if v['id'].startswith('ROOF-') and v['kind']=='truss_chord' and '-B' in v['id']]
    assert all(q[2]==pytest.approx(303.1017) for v in chords for q in v['axis'])
    for c in m['connections']:
        if c['detail_ref']['id']=='review_sbmf_roof_seat' and c['parameters']['support']=='header':
            scene=build_scene(m,p,c);packs=[v for v in scene['parts'] if v['id'].startswith('PACK')]
            assert len(packs)==2
            assert all(v['bounds'][2][1]-v['bounds'][2][0]==pytest.approx(2) for v in packs)
