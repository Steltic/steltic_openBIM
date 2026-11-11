import copy
import pytest

from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.retained_layout import bind_layout


def revision():
    member=dict(id='bar',kind='truss_web',profile_id='PL2',level=1,axis=[[0,0,0],[10,0,10]],
                local_y=[0,1,0],end_offsets=[[0,0,0],[0,0,0]],analysis_ids=['a'],design_record_ids=['m/bar'])
    aperture=dict(id='door',kind='door',host_id='wall',plane='xz',level=1,x_ft=1,y_ft=0,z_ft=0,
                  width_ft=2,height_ft=7,vertices=[[12,0,0],[36,0,0],[36,0,84],[12,0,84]],confirmed=True)
    p=dict(members=[member],profiles=[dict(id='PL2',family='flat',dimensions=dict(width=2,thickness=.5))],
           panels=[dict(id='wall',kind='wall',vertices=[[0,0,0],[70,0,0],[70,0,90]],level=1,thickness_in=1)],
           openings=[aperture],joints=[],connections=[])
    prior=dict(building_id='original',physical=p)
    model=copy.deepcopy(p);model.update(source_sha256='original',member_schedule=[dict(mark='TW1',profile_id='PL2',member_ids=['bar'])])
    manifest=dict(building_id='original',source_model_sha256='original',model_sha256=fingerprint(model),sheets=[{'number':'G001'}])
    revised=copy.deepcopy(prior);revised['building_id']='revised'
    return prior,revised,model,manifest


@pytest.mark.parametrize('bad',['opening','unrelated_member','unselected_section','unrelated_profile'])
def test_scope_comparison_rejects_changes_outside_connection_revision(bad):
    prior,new,model,manifest=revision();p=new['physical']
    if bad=='opening':p['openings'][0]['vertices'][0][0]+=1.
    elif bad=='unrelated_member':p['members'][0]['axis'][0][2]+=1.
    elif bad=='unselected_section':p['members'][0]['profile_id']='PL3'
    else:p['profiles'].append(dict(id='PL3',family='flat',dimensions=dict(width=3.,thickness=.5)))
    with pytest.raises(ValueError):bind_layout(prior,new,model,manifest)


def test_only_source_bound_crossing_bar_reenters_drawing_schedule():
    prior,new,model,manifest=revision();p=new['physical']
    p['profiles'].append(dict(id='PL3',family='flat',dimensions=dict(width=3.,thickness=.5)))
    p['members'][0]['profile_id']='PL3'
    new['source_handoff']={'crossing_interfaces':[dict(kind='flat_bar_crossing',member_ids=['bar'])]}
    evidence=bind_layout(prior,new,model,manifest)
    assert evidence['revised_crossing_members']['bar']['prior']=='PL2'
    assert model['member_schedule'][0]['profile_id']==model['members'][0]['profile_id']=='PL3'
