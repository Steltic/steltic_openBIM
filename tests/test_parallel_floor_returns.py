import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def builder():
    b=object.__new__(CaseModel);b.key='cfs2';b.members=[];b.connections=[];b.profiles={};b.used_records=set()
    return b


def scene(b,primary,family,point):
    b.connection('JOINT',family,point,[primary],parameters={})
    model=dict(pilot='cfs2',members=b.members,connections=b.connections,profiles=list(b.profiles.values()))
    bind(model);result=build_scene(model,dict(design_records=[]),b.connections[0])
    parts={p['id']:p for p in result['parts']}
    assert result['fasteners']
    for f in result['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(f['id'],name,q)
    return result,b.connections[0]['parameters']['physical_floor_stack']


@pytest.mark.parametrize('mirror',[-1,1])
@pytest.mark.parametrize('built_up',[False,True])
def test_corner_parallel_truss_uses_both_actual_chords_and_real_channel_flange_plies(mirror,built_up):
    b=builder()
    b.member('LOW','600T150-54','top_track',[0,0,0],[mirror*30,0,0],1,'S',local_y=[0,0,-1])
    b.member('UP','600T150-54','bottom_track',[0,0,15.5],[mirror*30,0,15.5],2,'S',local_y=[0,0,1])
    # The transverse track is cut clear of the corner. It cannot receive bolts.
    b.member('CUT','600T150-54','top_track',[0,6,0],[0,30,0],1,'S',local_y=[0,0,-1])
    pid=('2X' if built_up else '')+'250S162-68'
    lower=b.member('TRUSS-B0',pid,'truss_chord',[0,0,1.3],[mirror*24,0,1.3],1,'A',local_y=[0,mirror,0])
    b.member('TRUSS-T0',pid,'truss_chord',[0,0,11.3],[mirror*24,0,11.3],1,'A',local_y=[0,mirror,0])
    result,data=scene(b,lower,'review_roof_seat',[0,0,1.3])
    assert set(data['truss_ids'])=={'TRUSS-B0','TRUSS-T0'}
    assert set(data['track_ids'])=={'LOW','UP'}
    assert len(result['fasteners'])==(4 if built_up else 2)
    assert all(f['basis']=='A' for f in result['fasteners'])
    assert len(result['interfaces'])==(4 if built_up else 2)


@pytest.mark.parametrize('mirror',[-1,1])
def test_butt_ended_parallel_joist_has_a_formed_return_instead_of_fictitious_flange_overlap(mirror):
    b=builder()
    for tag,z,kind,ly in [('LOW',0,'top_track',[0,0,-1]),('UP',12,'bottom_track',[0,0,1])]:
        b.member(tag,'600T150-54',kind,[0,0,z],[-mirror*24,0,z],1,'S',local_y=ly)
    joist=b.member('JOIST','1000S200-54','joist',[0,0,5.1],[mirror*24,0,5.1],1,'A',local_y=[0,mirror,0])
    before=[m['axis'][:] for m in b.members]
    result,data=scene(b,joist,'review_cfs_joist',[0,0,5.1])
    assert [m['axis'] for m in b.members]==before
    assert len([p for p in result['parts'] if p['id'].startswith('PAR-END-') and p['kind']=='plate'])==4
    assert not any(f['id'].startswith('RIM-') for f in result['fasteners'])
    assert any('opposite sides' in n and 'no direct flange overlap' in n for n in result['notes'])


@pytest.mark.parametrize('case',['cfs11','cfs13','cfs14'])
def test_ordinary_roof_tracks_use_roof_bearing_level_without_floor_depth_deduction(case):
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    package=evidence(case)['package'];s=scenario(case)
    m=build_model(package,dict(design_scenario=dict(id=case,source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    change=next(c for c in m['changes'] if c['kind']=='ordinary_roof_wall_bearing_datum')
    tracks=[v for v in m['members'] if v['kind']=='ordinary_track' and v['level']==change['level'] and v['local_y'][2]<0]
    assert tracks
    assert all(abs(q[2]-change['top_z_in'])<.001 for v in tracks for q in v['axis'])
    assert change['basis'].startswith('A:')
    profiles={p['id']:p for p in m['profiles']}
    for track in tracks:
        t=profiles[track['profile_id']]['dimensions']['t']
        assert all(abs(q[2]+off[2]+t/2-change['top_z_in'])<.001 for q,off in zip(track['axis'],track['end_offsets']))


def test_parallel_chord_intersecting_track_is_rejected():
    b=builder()
    b.member('LOW','600T150-54','top_track',[0,0,0],[24,0,0],1,'S',local_y=[0,0,-1])
    joist=b.member('JOIST','1000S200-54','joist',[0,0,4.9],[24,0,4.9],1,'A',local_y=[0,1,0])
    with pytest.raises(ValueError,match='intersects the track'):
        scene(b,joist,'review_cfs_joist',[0,0,4.9])
