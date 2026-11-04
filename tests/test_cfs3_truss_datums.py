import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cfs import floors_and_roofs
from steltic_openbim.assembly_scene import Assembly


def test_floor_and_roof_chords_bear_on_tracks_and_preserve_source_finishes():
    b=object.__new__(CaseModel);b.key='cfs3';b.cfg={};b.raw={'framing':[]}
    b.members=[];b.connections=[];b.panels=[];b.profiles={};b.used_records=set();b.notes=[];b.changes=[];b.walls=[]
    b.records={'diaphragms/floor':dict(data=dict(level=1)), 'diaphragms/roof':dict(data=dict(level=2))}
    for k,z in enumerate((300,420),1):
        b.member('TRACK-'+str(k),'600T150-33','top_track',[0,0,z-14],[0,48,z-14],k,'S',local_y=[0,0,-1])
    floors_and_roofs(b,[[0,0],[28,0],[28,4],[0,4]],{},[180,300,420])
    a=Assembly('CFS3 bearing datums',b.profiles)
    shapes={}
    for m in b.members:
        axis=[[q[i]+off[i] for i in range(3)] for q,off in zip(m['axis'],m['end_offsets'])]
        shapes[m['id']]=a.member(m['id'],m['profile_id'],*axis,y=m['local_y'])
    for k,z in enumerate((300,420),1):
        chords=[m for m in b.members if m['kind']=='truss_chord' and m['level']==k]
        bottom=min(shapes[m['id']]['bounds'][2][0] for m in chords)
        top=max(shapes[m['id']]['bounds'][2][1] for m in chords)
        assert bottom==pytest.approx(shapes['TRACK-'+str(k)]['bounds'][2][1])
        assert top-bottom==pytest.approx(11 if k==1 else 14)
        panel=b.panels[k-1]
        assert panel['vertices'][0][2]-panel['thickness_in']==pytest.approx(top)
        assert panel['thickness_direction']=='negative_global_z'
        assert panel['design_record_ids']==['diaphragms/'+('floor' if k==1 else 'roof')]
    assert b.panels[0]['thickness_in']==3
    assert b.panels[1]['thickness_in']==19/32 and b.panels[1]['kind']=='roof'
    assert all(m['axis'][0][2]==286+120*(m['level']-1) for m in b.members if m['id'].startswith('TRACK-'))
    assert b.changes[-1]['kind']=='cfs3_truss_bearing_datums'
