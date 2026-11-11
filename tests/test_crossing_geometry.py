import math
import pytest
from steltic_openbim.pilots.geometry import member_faces
from steltic_openbim.pilots.model import dot,cross
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_assemblies import build_scene


def volume(faces):return sum(dot(f[0],cross(a,b))/6 for f in faces for a,b in zip(f[1:],f[2:]))


def test_end_selections_are_bound_to_the_split_members_only():
    from steltic_openbim.hr_detail_selections import selected_fields
    fields=[dict(role='split_brace_slot_weld',field='length_in',value=9,applicability={'crossing_receiver':'split'}),
            dict(role='split_gusset',field='whitmore_effective_width_in',value=16.4,
                 applicability={'crossing_receiver':'split'}),
            dict(role='continuous_brace_slot_weld',field='run',value='all_round_slot',
                 applicability={'crossing_receiver':'continuous'})]
    handoff=dict(records={'row':{'fields':fields}},occurrences={'X':{'applications':[dict(
        record_id='row',selected=[0,1,2],crossing_members={'split':['B1','B2'],'continuous':['A']})]}})
    c={'id':'X'};p={'source_handoff':handoff}
    assert selected_fields(p,c,'A')=={('brace_slot_weld','run'):'all_round_slot'}
    for mid in ('B1','B2'):
        assert selected_fields(p,c,mid)=={('brace_slot_weld','length_in'):9,('gusset','whitmore_effective_width_in'):16.4}


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
    through=[w for w in scene['welds'] if w['connects']==['CONT','GUSSET']]
    assert len([w for w in through if w.get('attachment_role')=='continuous_brace_slot_weld'])==4
    assert len([w for w in through if w.get('attachment_role')=='continuous_slot_end_return'])==(4 if key=='hr21' else 0)
    if key=='hr33':
        assert not cs[0]['design_record_ids'] and cs[0]['engineering_status']=='not_checked'
        assert all(w['basis']=='A' for w in scene['welds'])
    else:assert cs[0]['parameters']['crossing']['source_selected']


def test_shallow_crossing_gusset_clears_each_uncut_tube_and_meets_its_welds():
    from types import SimpleNamespace
    import numpy as np
    from shapely.geometry import Point
    from steltic_openbim.assembly_scene import Assembly
    from steltic_openbim.joint_mesh_readback import Mesh
    from steltic_openbim.pilots.model import mul,unit
    from steltic_openbim.review_crossings import draw

    profiles={'HSS':dict(id='HSS',family='rhs',dimensions=dict(h=9,b=9,t=.5))}
    through=unit([330,0,168]);split=unit([330,0,-168])
    cutback=11.3392857143;slot=43.6785714286
    def tube(name,d,lo,hi,cut_lo,cut_hi):
        return dict(id=name,kind='brace',profile_id='HSS',axis=[mul(d,lo),mul(d,hi)],
                    local_y=[0,1,0],end_offsets=[[0,0,0],[0,0,0]],slots=[
                        dict(start_in=cut_lo-lo,end_in=cut_hi-lo,width_in=.875,section_axis=0)])
    members=[tube('A',through,-100,100,-slot/2,slot/2),
             tube('B1',split,-100,-cutback,-cutback-9.5,-cutback),
             tube('B2',split,cutback,100,cutback,cutback+9.5)]
    selected=dict(thickness_in=.75,end_distance_in=cutback,split_weld_length_in=9,
                  proposed_width_in=slot-1,source_width_in=None,source_selected=True,
                  continuous_slot_length_in=slot,continuous_weld_size_in=.3125,split_weld_size_in=.3125)
    assembly=Assembly('HSS crossing',profiles)
    draw(SimpleNamespace(a=assembly,p=profiles,params={'crossing':selected},ms=members,
                         c=dict(id='X',point=[0,0,0],member_ids=['A','B1','B2']),selected={},text=''))
    def section(part):
        vertices=[];faces=[]
        for ring in part['faces']:
            faces.append(tuple(range(len(vertices),len(vertices)+len(ring))))
            vertices.extend(ring)
        return Mesh(np.asarray(vertices),tuple(faces)).section([0,1,0],0,([1,0,0],[0,0,1]))
    by_id={p['id']:p for p in assembly.parts}
    gusset=section(by_id['GUSSET'])
    for role in ('CONT','SPLIT-1','SPLIT1'):
        assert section(by_id[role]).intersection(gusset).area<1e-4
        for weld in (w for w in assembly.welds if w['connects']==[role,'GUSSET']):
            for x,y,z in (weld['a'],weld['b']):
                assert gusset.distance(Point(x,z))<1e-4
