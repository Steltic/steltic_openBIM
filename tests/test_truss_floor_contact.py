import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('seat',[False,True])
def test_floor_stack_uses_both_real_open_web_chords_and_fitted_bearing(side,seat):
    b=object.__new__(CaseModel);b.key='cfs2';b.members=[];b.connections=[];b.profiles={};b.used_records=set()
    lower=b.member('LOW','600T150-54','top_track',[-30,0,0],[30,0,0],1,'S',local_y=[0,0,-1])
    upper=b.member('UP','600T150-54','bottom_track',[-30,0,15.5],[30,0,15.5],2,'S',local_y=[0,0,1])
    for tag,z in [('B',1.3),('T',10.8)]:b.member('OW-1-'+tag+'0','250S162-68','truss_chord',[0,0,z],[0,side*24,z],1,'A',local_y=[side,0,0])
    chord=next(m for m in b.members if m['id']=='OW-1-B0')
    b.connection('FLOOR','review_roof_seat' if seat else 'review_cfs_floor',chord['axis'][0] if seat else [0,0,0],[chord if seat else lower],parameters=dict(floor_depth=15.5))
    model=dict(pilot='cfs2',members=b.members,connections=b.connections,profiles=list(b.profiles.values()))
    bind(model);c=b.connections[0];data=c['parameters']['physical_floor_stack']
    assert set(data['truss_ids'])=={'OW-1-B0','OW-1-T0'}
    scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    assert not any('STIFF' in name or 'JOIST' in name for name in parts)
    assert len(scene['fasteners'])==2
    for f in scene['fasteners']:
        assert f['basis']=='A'
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(side,f['id'],name,q)
    assert any('full-depth solid joist' in note for note in scene['notes'])
