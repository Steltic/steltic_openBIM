from collections import defaultdict
import math
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


def test_mezzanine_chord_screws_are_real_distinct_and_inside_actual_plies(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']};count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_chord_track' or not c['member_ids'][0].startswith('MEZZ-'):continue
        chord,track=[lookup[mid] for mid in c['member_ids']]
        expected=24 if chord['level']==1 else 12
        assert track['profile_id']==('600T300-97' if expected==24 else '600T200-54')
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert sum(f['count'] for f in scene['fasteners'])==expected
        points=[q for f in scene['fasteners'] for q in f['points']]
        assert len({tuple(q) for q in points})==expected
        assert min(math.dist(a,b) for i,a in enumerate(points) for b in points[i+1:])>=3*.216
        for f in scene['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        count+=1
    assert count==64


def test_mezzanine_anchors_follow_source_groups_and_maximum_field_pitch(actual):
    m,p=actual;by_track=defaultdict(list);groups=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_track_anchor' or not c['member_ids'][0].startswith('MEZZ-'):continue
        par=c['parameters'];axis=par['along'];stations=par['stations']
        by_track[c['member_ids'][0]].extend(c['point'][axis]+s for s in stations)
        if len(stations)==4:
            assert all(abs(s)<=16 for s in stations);groups+=1
        else:assert stations==[0]
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            assert f['diameter']==.75
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
    assert groups==16 and len(by_track)==5
    for values in by_track.values():
        values=sorted(values)
        assert len(set(round(v,6) for v in values))==len(values)
        assert max(d-a for a,d in zip(values,values[1:]))<=32.000001


def test_ten_foot_panel_worklines_and_wsp_bearing_leave_floor_transfer_bolts_clear(actual):
    m,_=actual;lookup={v['id']:v for v in m['members']}
    for w in m['wall_layouts']:
        if not w['id'].startswith('MEZZ-'):continue
        axis=0 if w['direction']=='X' else 1
        lo=lookup[w['id']+'TT']['axis'][0][axis]
        for j,r in enumerate(w['runs']):
            left=lookup[w['id']+'-CH-'+str(j)+'-0'];right=lookup[w['id']+'-CH-'+str(j)+'-1']
            assert right['axis'][0][axis]-left['axis'][0][axis]==120
            for distance in (12,36,60,84,108):
                station=r['start_in']+distance-lo
                assert min(station%16,16-station%16)==4
        if w['level']==2:
            assert w['base_z_in']==118.5
    assert dict((v[1],v[2]) for v in m['levels'])['MEZZ L2']==120


def test_mezzanine_corners_keep_real_tracks_clear_and_clip_both_flanges(actual):
    m,p=actual;count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_track_corner' or not all(mid.startswith('MEZZ-') for mid in c['member_ids']):continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        assert c['basis']=='A' and not c['design_record_ids']
        count+=1
    assert count==16
    assert not any(m['id'].startswith('MEZZ-W') and m['kind']=='stud' and m['axis'][0][1]==24 for m in m['members'])
