import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cfs_occurrences import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('plies',[1,2,6])
@pytest.mark.parametrize('top',[False,True])
def test_every_fitted_stud_track_screw_passes_through_both_real_sheets(plies,top):
    b=object.__new__(CaseModel);b.key='cfs5';b.members=[];b.connections=[];b.profiles={};b.used_records=set()
    pid='600S162-43' if plies==1 else str(plies)+'X600S162-43'
    m=b.member('STUD',pid,'stud',[0,0,-24 if top else 0],[0,0,0 if top else 24],1,'S',local_y=[1,0,0])
    track=b.member('TRACK','600T125-43','top_track' if top else 'bottom_track',[-24,0,0],[24,0,0],1,'S',local_y=[0,0,-1 if top else 1])
    b.connection('END','cfs_stud',[0,0,0],[m])
    model=dict(pilot='cfs5',members=b.members,connections=b.connections,profiles=list(b.profiles.values()))
    bind(model);scene=build_scene(model,dict(design_records=[]),b.connections[0]);parts={p['id']:p for p in scene['parts']}
    assert sum(len(f['points']) for f in scene['fasteners'])==2*plies
    for f in scene['fasteners']:
        assert f['basis']=='A'
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(plies,top,f['id'],name,q)
