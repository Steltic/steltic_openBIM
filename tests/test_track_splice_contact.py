from types import SimpleNamespace
import copy
import pytest
from steltic_openbim.review_track_splices import apply
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def fixture(along=0,reverse=False):
    p=dict(id='600T150-97',family='channel',dimensions=dict(d=6.2659,b=1.5,t=.1017,lip=0))
    def point(x):return [x,0,120] if along==0 else [0,x,120]
    ms=[dict(id=label,profile_id=p['id'],kind='bottom_track',axis=[point(a),point(b)],
             end_offsets=[[0,0,.05085],[0,0,.05085]],local_y=[0,0,1],level=2,basis='S')
        for label,a,b in [('A',-48,0),('B',0,48)]]
    if reverse:
        for m in ms:m['axis'].reverse()
    b=SimpleNamespace(key='cfs2',profiles={p['id']:p},members=ms,connections=[],changes=[],notes=[])
    def connection(cid,family,point,members,parameters,title):
        b.connections.append(dict(id=cid,detail_ref=dict(id=family),point=point,
            member_ids=[m['id'] for m in members],design_record_ids=[],parameters=parameters,title=title))
    b.connection=connection;b.note=lambda kind,text:b.notes.append(text)
    return b


@pytest.mark.parametrize('along',[0,1])
@pytest.mark.parametrize('reverse',[False,True])
def test_splice_screws_reach_both_actual_tracks_without_changing_bearing(along,reverse):
    b=fixture(along,reverse);before=copy.deepcopy(b.members);apply(b)
    assert len(b.connections)==1 and len(b.changes)==2
    model=dict(pilot=b.key,members=b.members,profiles=list(b.profiles.values()))
    scene=build_scene(model,dict(design_records=[]),b.connections[0]);parts={p['id']:p for p in scene['parts']}
    assert all(m['axis']==old['axis'] for m,old in zip(b.members,before))
    assert all(o[2]==pytest.approx(.05085) for m in b.members for o in m['end_offsets'])
    assert parts['TRACK1']['bounds'][0][0]==pytest.approx(.0625)
    assert parts['TRACK2']['bounds'][0][1]==pytest.approx(-.0625)
    assert {parts[k]['member']['source_member_index'] for k in ('TRACK1','TRACK2')}=={0,1}
    assert sum(len(f['points']) for f in scene['fasteners'])==12
    for f in scene['fasteners']:
        assert f['basis']=='A'
        for q in f['points']:
            assert all(contact(parts[name],f,q) for name in f['connects'])
    # Repeat application cannot cut the same physical ends a second time.
    accepted=copy.deepcopy(b.members);apply(b)
    assert b.members==accepted and len(b.connections)==1


def test_does_not_replace_an_existing_source_connection_or_mixed_track_selection():
    b=fixture();b.connections=[dict(id='source',point=[0,0,120],member_ids=['A','B'],detail_ref=dict(id='source-splice'))];apply(b)
    assert len(b.connections)==1 and not b.changes
    b=fixture();other=copy.deepcopy(next(iter(b.profiles.values())));other['id']='OTHER';other['dimensions']['t']=.0713
    b.profiles['OTHER']=other;b.members[1]['profile_id']='OTHER';apply(b)
    assert not b.connections and not b.changes


def test_all_reported_cfs2_coincident_bottom_tracks_gain_explicit_splices():
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    p=evidence('cfs2')['package'];s=scenario('cfs2')
    m=build_model(p,dict(design_scenario=dict(id='cfs2',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    cs=[c for c in m['connections'] if c['detail_ref']['id']=='review_track_splice']
    assert len(cs)==108
    assert any(set(c['member_ids'])=={'YW-L1-B1-BT','YW-L1-B2-BT'} for c in cs)
    for c in cs:
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert len(scene['source_member_ids'])==2
        for f in scene['fasteners']:
            for q in f['points']:
                assert all(contact(parts[name],f,q) for name in f['connects'])
