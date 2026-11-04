import math
import pytest
from steltic_openbim.pilots.geometry import member_faces
from steltic_openbim.pilots.model import dot,cross
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_assemblies import build_scene


def volume(faces):return sum(dot(f[0],cross(a,b))/6 for f in faces for a,b in zip(f[1:],f[2:]))


@pytest.mark.parametrize('coordinate',[0,1])
def test_selected_slot_removes_only_two_walls_with_correct_volume(coordinate):
    profiles={'HSS':dict(family='rhs',dimensions=dict(h=4,b=4,t=.25))}
    m=dict(profile_id='HSS',axis=[[0,0,0],[40,0,0]],end_offsets=[[0,0,0],[0,0,0]],local_y=[0,1,0])
    before=volume(member_faces(m,profiles))
    m['slots']=[dict(start_in=14,end_in=26,width_in=.625,section_axis=coordinate)]
    assert before-volume(member_faces(m,profiles))==pytest.approx(2*.25*.625*12)


@pytest.mark.parametrize('key,count',[('hr3',14),('hr18',32),('hr21',8),('hr30',24),('hr33',8)])
def test_each_crossing_has_one_continuous_and_two_actual_halves(key,count):
    p=evidence(key)['package'];m=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(scenario(key)['answers']))))
    cs=[c for c in m['connections'] if c['detail_ref']['id']=='review_brace_crossing']
    assert len(cs)==count
    lookup={member['id']:member for member in m['members']}
    for c in cs:
        continuous,*halves=[lookup[i] for i in c['member_ids']]
        assert len(halves)==2 and continuous.get('slots')
        assert all(h.get('slots') for h in halves)
        claims=[h['analysis_segments'][0] for h in halves]
        assert claims[0]['analysis_id']==claims[1]['analysis_id']
        assert claims[0]['start']==0 and claims[0]['end']==claims[1]['start'] and claims[1]['end']==1
        assert all(any(math.dist(q,c['point'])<1e-6 for q in h['axis']) for h in halves)
    scene=build_scene(m,p,cs[0]);parts={part['id']:part for part in scene['parts']}
    assert all(parts[label]['member']['slots'] for label in ('CONT','SPLIT-1','SPLIT1'))
    assert len([w for w in scene['welds'] if w['connects']==['CONT','GUSSET']])==4
    if key=='hr33':
        assert not cs[0]['design_record_ids'] and cs[0]['engineering_status']=='not_checked'
        assert all(w['basis']=='A' for w in scene['welds'])
    else:assert cs[0]['parameters']['crossing']['source_selected']
