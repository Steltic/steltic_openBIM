"""Positive and corrupt actual STEP solid controls for forged rod terminal interfaces."""
import numpy as np
import pytest

from steltic_openbim.clevis_readback import forged_fit,thread_fit
from test_ifc_assembly_verification import cuboid,cylinder,export_readback


@pytest.mark.parametrize('change,expected',[
    ('complete',None),('translated_as_assembly',None),('short','actual_rod_clevis_engagement_short'),
    ('capped','actual_clevis_thread_bore_missing'),('small_rod','actual_thread_major_diameter_or_center_differs'),
    ('wide_bore','actual_thread_major_diameter_or_center_differs'),('eccentric','actual_thread_major_diameter_or_center_differs'),
    ('mismatched_facets','actual_rod_material_inside_clevis_body'),
])
def test_actual_threaded_major_envelope(tmp_path,change,expected):
    body=cylinder(1.5,0,5,None if change=='capped' else .7 if change=='wide_bore' else .5)
    rod=cylinder(.45 if change=='small_rod' else .5,3. if change=='short' else 0.,25.,x=.15 if change=='eccentric' else 0.)
    if change=='mismatched_facets':
        angle=np.pi/24
        rotation=np.eye(4);rotation[:2,:2]=[[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]]
        rod=rod.transformed(rotation)
    axis=np.array([0.,0.,1.])
    if change=='translated_as_assembly':
        rotate=np.eye(4);rotate[:3,:3]=[[.8,0,.6],[0,1,0],[-.6,0,.8]];rotate[:3,3]=[485.,-1200,108.]
        rod=rod.transformed(rotate);body=body.transformed(rotate);axis=rotate[:3,:3]@axis
    meshes=export_readback(tmp_path,{'BODY':body,'ROD':rod})
    defect,measurements=thread_fit(meshes['BODY'],meshes['ROD'],axis,1.,5.)
    assert defect==expected
    if not expected:
        assert measurements['actual_axial_overlap_in']==pytest.approx(5.)
        assert measurements['actual_bore_diameter_in']==pytest.approx(1.,abs=1e-5)


@pytest.mark.parametrize('change,expected',[
    ('complete',None),('gap','forged_clevis_jaw_end_fit_differs'),('overlap','forged_clevis_jaw_end_fit_differs'),
    ('inside_bore','forged_clevis_jaw_has_no_finite_end_contact'),
    ('outside_body','forged_clevis_jaw_has_no_finite_end_contact'),
])
def test_actual_integral_forged_jaw(tmp_path,change,expected):
    body=cylinder(1.5,0,5,.5)
    x0,x1=(.05,.1) if change=='inside_bore' else (2,3) if change=='outside_body' else (.7,1.)
    jaw=cuboid([x0,-.2,-5],[x1,.2,.25 if change=='overlap' else -.25 if change=='gap' else 0.])
    meshes=export_readback(tmp_path,{'BODY':body,'JAW':jaw})
    defect,measurements=forged_fit(meshes['BODY'],meshes['JAW'],[0,0,1])
    assert defect==expected
    if not expected:
        assert measurements['contact_area_in2']==pytest.approx(.12)


def test_normalized_assembly_drill_reaches_real_interface_check(tmp_path):
    from steltic_openbim.ifc_assembly_verification import Assessment
    rb=export_readback(tmp_path,{'R':cylinder(.5,0,15),'B':cylinder(1.5,0,5,.5),'J':cuboid([.7,-.2,-5],[1,.2,0])},reader=True)
    solids={name:rb.member(key) for name,key in [('BODY','B'),('JAW','J')]}
    part=dict(id='BODY',kind='rod',parameters=dict(source_role='threaded_clevis_body',thread_major_diameter_in=1.,thread_engagement_in=5.,
        holes=[dict(point=[0.,0.,0.],axis=[0.,0.,1.],diameter_in=1.)]))
    parts={'BODY':part,'JAW':dict(id='JAW',kind='plate')};interfaces=[dict(id='T',kind='threaded_clevis',connects=['ROD','BODY']),
        dict(id='F',kind='integral_forged_clevis',connects=['JAW','BODY'])]
    check=Assessment(rb,dict(members=[dict(id='R',kind='rod_brace',profile_id='R1')],profiles=[dict(id='R1',dimensions={'d':1.})]),{})
    check.context={'template':'test'}
    check.paths('END',parts,solids,{'bindings':{'ROD':'R'}},np.eye(4),[],{},set(),{},interfaces)
    assert check.counts['actual_threaded_rod_bore_engagements']==1
    assert check.counts['actual_forged_jaw_mating_faces']==1
    assert not check.findings
