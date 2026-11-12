from copy import deepcopy

import numpy as np
import pytest

from steltic_openbim.ifc_beam_ends import beam_end_fits, fitted_member
from steltic_openbim.pilots.geometry import member_faces


def member(mid, kind, axis, y):
    return dict(id=mid,kind=kind,axis=axis,local_y=y,profile_id='W',end_offsets=[[0,0,0],[0,0,0]])


def model(branch, host, face=None):
    p=dict(members=[branch,host],profiles=[dict(id='W',family='i',dimensions=dict(d=14.,bf=10.,tw=.5,tf=.75))],
           connections=[],assemblies=[],joints=[dict(id='J',point=branch['axis'][0],
               member_ends=[dict(member_id=branch['id'],end='start')],attachments=[dict(member_id=host['id'])])])
    if face is not None:
        x,y,z=branch['axis'][0]
        p['connections']=[dict(id='detail',joint_id='J',point=[x,y,z],member_ids=['B','S'],
            detail_ref=dict(legacy_family='review_beam'),
            assembly_instance=dict(template_id='T',bindings=dict(M1='S',M2='B'),
                                   origin=[x,y,z],x_axis=[1,0,0],y_axis=[0,1,0]))]
        p['assemblies']=[dict(id='T',receivers=[dict(id='M2',axis=[[face,0,0],[face+42,0,0]])])]
    return p


def vertices(package, member):
    fitted=fitted_member(member,beam_end_fits(package).get(member['id']))
    faces=member_faces(fitted,{p['id']:p for p in package['profiles']})
    return np.asarray([q for face in faces for q in face])


@pytest.mark.parametrize('roll,station', [([0,1,0],7.),([1,0,0],.25)])
def test_rolled_column_material_face_from_joint_without_drawing(roll,station):
    beam=member('B','beam',[[0,0,24],[120,0,24]],[0,1,0])
    col=member('S','column',[[0,0,0],[0,0,96]],roll)
    p=model(beam,col)
    saved=deepcopy(p)
    v=vertices(p,beam)
    assert v[:,0].min()==pytest.approx(station)
    assert v[:,0].max()==pytest.approx(120)
    assert p==saved


def test_selected_gap_and_rbs_stations_survive_end_fitting():
    beam=member('B','moment_beam',[[0,0,24],[120,0,24]],[0,1,0])
    beam['rbs']=dict(cuts=[dict(end=0,a_in=13,b_in=12,c_in=1)])
    col=member('S','column',[[0,0,0],[0,0,96]],[0,1,0])
    p=model(beam,col,8.25)
    v=vertices(p,beam)
    assert v[:,0].min()==pytest.approx(8.25)
    assert max(abs(v[np.isclose(v[:,0],19),1]))==pytest.approx(4.)
    beam['end_offsets'][0]=[3,0,0]
    assert vertices(p,beam)[:,0].min()==pytest.approx(8.25)


def test_branch_copes_clear_both_flanges_and_preserve_through_beam():
    branch=member('B','infill',[[0,0,0],[120,0,0]],[0,1,0])
    host=member('S','girder',[[0,-80,0],[0,80,0]],[-1,0,0])
    p=model(branch,host,1.5)
    v=vertices(p,branch)
    assert v[:,0].min()==pytest.approx(1.5)
    assert v[np.isclose(v[:,0],1.5),2].max()==pytest.approx(5.75)
    assert v[np.isclose(v[:,0],1.5),2].min()==pytest.approx(-5.75)
    assert v[np.isclose(v[:,2],7),0].min()==pytest.approx(5.25)
    assert not beam_end_fits(p).get('S')
    # Equal sections can swap the detail roles. Interior attachment topology
    # still identifies the branch and the same net cope.
    p['connections'][0]['assembly_instance']['bindings']=dict(M1='B',M2='S')
    np.testing.assert_allclose(vertices(p,branch),v)


def test_a_column_ending_below_the_beam_is_a_bearing_support():
    branch=member('B','beam',[[0,0,24],[120,0,24]],[0,1,0])
    host=member('S','column',[[0,0,0],[0,0,16]],[0,1,0])
    result=vertices(model(branch,host),branch)
    assert result[:,0].min()==0


def test_ridge_rafters_have_full_depth_plumb_caps_on_each_end_plate():
    left=member('L','rafter',[[-96,0,0],[0,0,24]],[0,1,0])
    right=member('R','rafter',[[96,0,0],[0,0,24]],[0,-1,0])
    p=model(left,right)
    p['joints']=[dict(id='J',point=[0,0,24],attachments=[],member_ends=[
        dict(member_id=m['id'],end='end') for m in (left,right)])]
    p['connections']=[dict(id='ridge',joint_id='J',point=[0,0,24],member_ids=['L','R'],
        detail_ref=dict(legacy_family='review_hr_gable_ridge'),assembly_instance=dict(template_id='T',
            bindings=dict(RAFTER0='L',RAFTER1='R'),origin=[0,0,24],x_axis=[1,0,0],y_axis=[0,1,0]))]
    p['assemblies']=[dict(id='T',receivers=[dict(id='RAFTER0'),dict(id='RAFTER1')],
        parts=[dict(id='EP'+str(i),geometry=dict(faces=[[[x,-5,-10],[x,5,-10],[x,5,10],[x,-5,10]]
            for x in (0,sign)])) for i,sign in enumerate((-1,1))])]
    for beam,sign in [(left,-1),(right,1)]:
        v=vertices(p,beam)
        assert (sign*v[:,0]).min()==pytest.approx(1.)
        cap=v[np.isclose(v[:,0],sign)]
        assert np.ptp(cap[:,2])==pytest.approx(14*(1+.25**2)**.5)


def test_reference_only_member_does_not_require_a_support_fit():
    beam=member('B','beam',[[0,0,24],[120,0,24]],[0,1,0])
    col=member('S','column',[[0,0,0],[0,0,96]],[0,1,0])
    del beam['end_offsets']
    assert not beam_end_fits(model(beam,col)).get('B')
