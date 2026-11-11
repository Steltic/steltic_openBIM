import numpy as np
import pytest

from steltic_openbim.transfer_joint_fit import fit_end_offsets
from steltic_openbim.transfer_joint_readback import arm_selections, measure_arm, transfer_sources
from test_ifc_assembly_verification import cuboid, export_readback, join


def test_source_application_must_locate_every_real_transfer_arm():
    prefix='transfer_diagonal'
    fields=[dict(role=prefix+'_gusset',field=k,value=v) for k,v in
            {'count':2,'thickness_in':1.5,'whitmore_effective_width_in':109.,'material':'A572 Gr 50'}.items()]
    fields.extend(dict(role=prefix+'_gusset_weld',field=k,value=v) for k,v in
                  {'count':4,'length_in':76.,'size_in':1.,'material':'E70'}.items())
    ids={'M1':'left','M2':'right'}
    members={v:dict(kind=prefix,profile_id='W14X665') for v in ids.values()}
    app=dict(record_id='diagonal-record',transfer_members={prefix:list(ids.values())},selected=list(range(len(fields))))
    handoff=dict(records={'diagonal-record':dict(fields=fields,member_section={'value':'W14X665'})},
                 occurrences={'node':dict(applications=[app]),'other':dict(applications=[])})
    assert transfer_sources(handoff)=={'node'}
    specs,errors=arm_selections(handoff,'node',ids,members)
    assert not errors and set(specs)==set(ids.values()) and specs['right']['whitmore']==109.
    app['transfer_members'][prefix]=['left']
    assert 'right' in {r.get('member') for r in arm_selections(handoff,'node',ids,members)[1]}
    app['transfer_members'][prefix]=['left','unrelated']
    assert arm_selections(handoff,'node',ids,members)[1]


def test_real_member_end_cut_preserves_through_column():
    profile = dict(id='W',dimensions={'d':21.6})
    point = [0.,0.,0.]
    members = [dict(id=key,kind=kind,profile_id='W',local_y=[0,1,0],axis=[a,b],end_offsets=[[0,0,0],[0,0,0]])
               for key,kind,a,b in [('through','column',[0,0,-168],[0,0,48]),
                                     ('diagonal','transfer_diagonal',point,[360,0,-216]),
                                     ('chord','transfer_chord',point,[360,0,0])]]
    model = dict(members=members,profiles=[profile],connections=[
        dict(id='joint',point=point,detail_ref={'id':'review_transfer_truss'},member_ids=[m['id'] for m in members])])
    fit_end_offsets(model)
    assert members[0]['end_offsets']==[[0,0,0],[0,0,0]]
    assert all(np.linalg.norm(m['end_offsets'][0])==pytest.approx(39.24143,abs=1e-5) for m in members[1:])
    fit_end_offsets(model)
    assert all(np.linalg.norm(m['end_offsets'][0])==pytest.approx(39.24143,abs=1e-5) for m in members[1:])


@pytest.mark.parametrize('change',('none','gap','short','duplicate','narrow','grade','thickness','removed'))
def test_step_flange_tip_contacts_and_whitmore(tmp_path,change):
    bottom = cuboid((5,-3,-5),(25,3,-4))
    top = cuboid((5,-3,4),(25,3,5))
    web = cuboid((5,-.5,-4),(25,.5,4))
    y = 3.45 if change=='gap' else 3.
    z = 6. if change=='narrow' else 10.
    t = 1.25 if change=='thickness' else 1.5
    meshes = {'W':join(join(bottom,top),web), 'P1':cuboid((3,-y-t,-z),(18,-y,z)),
              'P2':cuboid((3,y,-z),(18,y+t,z))}
    lines = [np.array([[5,side*3,edge*5],[15,side*3,edge*5]],float)
             for side in (-1,1) for edge in (-1,1)]
    if change=='short':lines[0][1,0]-=.5
    if change=='duplicate':lines[0]=lines[1]
    if change=='removed':lines.pop()
    rb=export_readback(tmp_path,meshes,{'ARM':lines},reader=True)
    curves=rb.curves('ARM')
    paths=[('w'+str(i),'P1' if i<2 else 'P2',q,1.,'E70XX') for i,q in enumerate(curves)]
    spec=dict(count=4,thickness=1.5,size=1.,length=10.,whitmore=16.,material='ASTM A572 Gr 50',metal='E70')
    _,issues=measure_arm(rb.member('W'),{k:rb.member(k) for k in ('P1','P2')},paths,[1,0,0],[0,1,0],[0,0,0],
                         spec,{'P1':'A36' if change=='grade' else 'A572 Grade 50','P2':'A572 Grade 50'})
    assert bool(issues)==(change!='none'), issues
