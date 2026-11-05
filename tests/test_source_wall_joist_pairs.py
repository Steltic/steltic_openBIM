import copy
import pytest
from test_parallel_floor_returns import builder,scene
from steltic_openbim.review_cfs_wall_bindings import bind


@pytest.mark.parametrize('side',[-1,1])
def test_outside_pair_web_binds_parallel_wall_without_a_fictitious_corner_track(side):
    b=builder();offset=side*(4-.0713/2)
    b.member('LOW','600T150-54','top_track',[0,0,0],[48,0,0],1,'S',local_y=[0,0,-1])
    b.member('UP','600T150-54','bottom_track',[0,0,12.25],[48,0,12.25],2,'S',local_y=[0,0,1])
    # The perpendicular return begins beyond the cut corner.
    b.member('CUT','600T150-54','top_track',[0,3.25,0],[0,48,0],1,'S',local_y=[0,0,-1])
    joist=b.member('PAIR','1000S250-68','joist',[0,offset,5.05],[48,offset,5.05],1,'S',
        local_y=[0,-side,0],parallel_wall_line='XSB',parallel_wall_axis_in=0.)
    result,data=scene(b,joist,'review_cfs_joist',[0,offset,5.05])
    assert set(data['track_ids'])=={'LOW','UP'}
    assert data['joist_ids']==['PAIR']
    assert all(f['id'].startswith('RIM-') for f in result['fasteners'])
    assert len(result['interfaces'])==2


@pytest.mark.parametrize('jamb_x',[3.,45.])
def test_jamb_foot_allowance_cannot_shorten_track_away_from_existing_end_stud(jamb_x):
    b=builder()
    track=b.member('TRACK','600T150-54','ordinary_track',[0,0,0],[48,0,0],1,'S',local_y=[0,0,1])
    jamb=b.member('JAMB','2X600S162-54','opening_jamb',[jamb_x,0,0],[jamb_x,0,84],1,'A',local_y=[1,0,0])
    b.connection('FOOT','test_wall_opening',[jamb_x,0,0],[jamb],parameters={})
    model=dict(members=b.members,connections=b.connections,profiles=list(b.profiles.values()))
    before=copy.deepcopy(track['end_offsets']);bind(model)
    assert track['end_offsets']==before
    assert b.connections[0]['parameters']['physical_jamb_base']['track']['member_id']=='TRACK'


def test_cfs6_source_pair_and_real_wall_scope():
    from steltic_openbim.review_cases import evidence,build_model,scenario
    from steltic_openbim.drawing_workflow import fingerprint
    p=evidence('cfs6')['package'];s=scenario('cfs6')
    model=build_model(p,dict(design_scenario=dict(id='cfs6',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    pairs=[m for m in model['members'] if m.get('parallel_wall_line')]
    assert pairs and {m['profile_id'] for m in pairs}=={'1000S250-68'}
    for m in pairs:
        normal=1 if m['axis'][0][0]!=m['axis'][1][0] else 0
        d=m['axis'][0][normal]-m['parallel_wall_axis_in']
        assert abs(abs(d)-(4-.0713/2))<1e-6
        assert d*m['local_y'][normal]<0
        assert not m['design_record_ids'] # source squash/transfer check is separate
    ordinary=[m for m in model['members'] if m['kind']=='ordinary_track' and m['axis'][0][0]==m['axis'][1][0]]
    assert ordinary
    for m in ordinary:
        x=m['axis'][0][0];ys=[q[1] for q in m['axis']]
        if x in [v*12 for v in (30,60,90,120,150,180)]:assert min(ys)>=90*12
        if x in [v*12 for v in (14,28,34,48)]:assert max(ys)<=90*12
