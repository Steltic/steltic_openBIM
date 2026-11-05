import pytest
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('width',[1.625,2.5])
def test_nested_stiffener_fits_inside_real_joist_and_bears_between_flange_faces(side,width):
    profiles=[dict(id='J',family='channel',dimensions=dict(d=10,b=width,t=.0713,lip=.625)),
              dict(id='T',family='channel',dimensions=dict(d=6.2,b=2,t=.0566,lip=0))]
    members=[dict(id='J',kind='joist',profile_id='J',axis=[[0,0,5.0283],[0,32,5.0283]],
                  local_y=[side,0,0],end_offsets=[[0,0,0]]*2,level=1),
             dict(id='T',kind='top_track',profile_id='T',axis=[[-24,0,0],[24,0,0]],
                  local_y=[0,0,-1],end_offsets=[[0,0,0]]*2,level=1)]
    c=dict(id='F',point=[0,0,5.0283],member_ids=['J'],detail_ref=dict(id='review_cfs_joist'),design_record_ids=[],parameters={})
    model=dict(pilot='cfs-fixture',members=members,profiles=profiles,connections=[c])
    bind(model);scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    stiff=parts['STIFF0'];joist=next(p for p in scene['parts'] if p.get('member',{}).get('profile_id')=='J')
    assert stiff['bounds'][2]==pytest.approx([joist['bounds'][2][0]+.0713,joist['bounds'][2][1]-.0713])
    xs=sorted(side*q for q in stiff['bounds'][0])
    assert xs[0]==pytest.approx(.0713/2)
    assert xs[1]<width-.0713/2
    assert stiff['bounds'][1][0]>=joist['bounds'][1][0] and stiff['bounds'][1][1]<=joist['bounds'][1][1]
    assert stiff['bounds'][1][1]-stiff['bounds'][1][0]==pytest.approx(3.625)
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(side,width,f['id'],name,q)
