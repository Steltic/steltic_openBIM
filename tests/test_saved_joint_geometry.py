import copy
import math

import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.bim_assemblies import has_physical_connection
from steltic_openbim.connection_cuts import drill_plate
from steltic_openbim.gusset_support_welds import place_faces
from steltic_openbim.review_hr_kickers import clear_host
from steltic_openbim.shared_apex import locate_pairs


def test_opposite_faces_of_one_beam_identify_two_independent_shared_pairs():
    drawing=[];conns=[]
    for n,(upper,sign) in enumerate(((True,1),(True,-1),(False,1),(False,-1))):
        cid=str(n);mid='brace'+cid
        frame=dict(origin=[18,12,8],x_axis=[sign,0,0],y_axis=[0,sign,0],bindings={'BRACE':mid,'BEAM':'beam'})
        conns.append(dict(id=cid,joint_id='j',parameters={'joint':'apex'},assembly_instance=frame,member_ids=[mid,'beam']))
        drawing.append(dict(id=cid,assembly_id='S',parameters={'upper_end':upper}))
    plate=dict(id='GUSSET',polygon=[[-8,-.25,0],[8,-.25,0],[0,-.25,12]])
    model=dict(connections=drawing,connection_assemblies=[dict(id='S',parts=[plate])])
    assert locate_pairs({'physical':{'connections':conns}},model)==[('0','1'),('2','3')]
    assert all(c['parameters']['common_apex_datum'] for c in drawing)
    displaced=copy.deepcopy(model)
    for q in displaced['connection_assemblies'][0]['parts'][0]['polygon']:q[0]+=25
    assert not locate_pairs({'physical':{'connections':conns}},displaced)


def test_dependent_weld_is_physical_only_if_its_identified_owner_is_real_and_colocated():
    parts=[dict(id='W1',kind='weld',connects=['BRACE','GUSSET'],geometry={'type':'polyline','points':[[0,0,0],[4,0,0]]})]
    templates={'secondary':{'receivers':[{'id':'BRACE','kind':'member'}],'parts':parts},
               'primary':{'id':'primary','revision':'r','parts':[{'id':'GUSSET','geometry':{'type':'mesh','faces':[[[0,0,0],[1,0,0],[0,1,0]]]}}]}}
    owner=dict(id='a',joint_id='joint',assembly_instance={'origin':[0,0,0],'template_id':'primary','revision':'r'},
               parameters={'shared_brace_ends':[{'connection_id':'b','member_id':'second'}]})
    reference=dict(role='GUSSET',owner_connection_id='a',owner_template_id='primary',owner_template_revision='r',owner_part_id='GUSSET')
    end=dict(id='b',joint_id='joint',parameters={'shared_constituents':[reference]},
             assembly_instance={'origin':[0,0,0],'template_id':'secondary','bindings':{'BRACE':'second'}})
    assert has_physical_connection(end,templates,connections={'a':owner,'b':end})
    reference['owner_template_revision']='stale'
    assert not has_physical_connection(end,templates,connections={'a':owner,'b':end})


def test_selected_two_sided_fillet_preserves_each_face_and_each_existing_receiver_segment():
    scene=Assembly('Split support',{})
    scene.box('GUSSET',[0,-.25,0],[5,.5,4])
    for i,(start,end) in enumerate(((0,2),(2,5))):
        scene.weld('WGB-'+str(i),[start,0,0],[end,0,0],['BEAM'+str(i),'GUSSET'],.375)
        scene.welds[-1].update(source_weld_id='WGB',segment_index=i,selected_total_length_in=5)
    scene.weld('WGC',[0,0,0],[0,0,4],['COLUMN','GUSSET'],kind='CJP')
    place_faces(scene,{('gusset_base_weld','faces'):2,('gusset_column_weld','faces'):2},'gusset_base_weld')
    assert len(scene.welds)==5
    for side in (-1,1):
        runs=[w for w in scene.welds if w.get('source_weld_side')==side]
        assert {w['segment_index'] for w in runs}=={0,1}
        assert {q[1] for w in runs for q in (w['a'],w['b'])}=={side*.25}
        assert sum(math.dist(w['a'],w['b']) for w in runs)==5.
    assert sum(w['kind']=='CJP' for w in scene.welds)==1


def test_tab_thickness_and_actual_i_web_material_control_its_free_edge():
    profile=dict(id='I',family='i',dimensions=dict(bf=2,d=4,tw=.5,tf=.5))
    member=dict(id='host',profile_id='I',axis=[[0,0,0],[10,0,0]],local_y=[0,1,0],end_offsets=[[0,0,0],[0,0,0]])
    points=[[8,.1,-.6],[12,.1,-.6],[12,.1,1],[8,.1,1]]
    fitted=clear_host(points,[0,1,0],.3,[1,0,0],[0,0,1],member,{'I':profile})
    assert min(q[0] for q in fitted)==pytest.approx(10.)
    assert max(q[0] for q in fitted)==pytest.approx(12.)
    clear=[[q[0],.25,q[2]] for q in points]
    assert clear_host(clear,[0,1,0],.3,[1,0,0],[0,0,1],member,{'I':profile})==clear


def test_bore_can_cross_a_computational_strip_seam_but_requires_containment_in_a_plate():
    a=Assembly('Split web',{})
    left=a.box('left',[-3,-.25,-2],[3,.5,4]);right=a.box('right',[0,-.25,-2],[3,.5,4])
    for part in (left,right):
        with pytest.raises(ValueError,match='leaves plate perimeter'):
            drill_plate(part,[[0,0,0]],[0,1,0],1,'selected fit')
        assert drill_plate(part,[[0,0,0]],[0,1,0],1,'selected fit',skip_disjoint=True)
        assert all(math.dist(a,b)>1e-8 for face in part['faces'] for a,b in zip(face,face[1:]+face[:1]))
