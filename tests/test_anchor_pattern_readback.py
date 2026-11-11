from math import cos,radians,sin

import pytest

from steltic_openbim.source_selection_readback import verify_source_selections


def base_case(angle):
    c,s=cos(radians(angle)),sin(radians(angle))
    plate=dict(id='BP',kind='plate',geometry=dict(type='box',origin=[-20.5,-19.5,2],x_axis=[1,0,0],y_axis=[0,1,0],size=[41,39,6.5]))
    rods=[]
    for n in (-15.65,15.65):
        for a in (-14.5,0,14.5):
            rods.append(dict(id='rod'+str(len(rods)),kind='anchor',
                             geometry=dict(type='cylinder',origin=[n,a,-8.],axis=[0,0,1],radius=1.75,length=24.)))
    frame=dict(template_id='BASE',origin=[90.,230.,13.],x_axis=[c,s,0],y_axis=[-s,c,0],bindings={'C':'column'})
    fields=[dict(role='anchor_pattern',field=name,value=number) for name,number in (
        ('edge_flange_normal_in',4.85),('edge_along_flange_in',5.),('minimum_edge_in',4.5),
        ('flange_offset_in',6.5),('spacing_in',14.5))]
    return dict(physical=dict(materials=[],connections=[dict(id='footing',assembly_instance=frame)],
                assemblies=[dict(id='BASE',parts=[plate]+rods)],
                profiles=[dict(id='W14X398',family='i',dimensions={'d':18.3,'bf':16.6})],
                members=[dict(id='column',kind='column',profile_id='W14X398',axis=[[90,230,13],[90,230,99]],local_y=[-s,c,0])]),
                source_handoff=dict(records={'detail':{'fields':fields}},
                occurrences={'footing':{'applications':[dict(record_id='detail',selected=list(range(len(fields))))]}}))


@pytest.mark.parametrize('angle',[0,37,90,217])
def test_plate_edges_use_the_bound_column_frame(angle):
    p=base_case(angle)
    r=verify_source_selections(p)
    assert r['passed'],r['findings']
    assert len(r['selected_comparisons'])==5


@pytest.mark.parametrize('defect,expected',[
    ('swapped','anchor_edge_flange_normal_in'),('rod_shift','anchor_spacing_in'),
    ('minimum','anchor_minimum_edge_in'),('depth','anchor_flange_offset_in'),
    ('inset','anchor_edge_along_flange_in'),('missing','anchor_setout_geometry')])
def test_changed_selected_field_or_real_solid_fails(defect,expected):
    p=base_case(37)
    fields=p['source_handoff']['records']['detail']['fields']
    parts=p['physical']['assemblies'][0]['parts']
    if defect=='swapped':
        fields[0]['value'],fields[1]['value']=fields[1]['value'],fields[0]['value']
    if defect=='rod_shift':
        parts[2]['geometry']['origin'][1]=1.0
        parts[2]['parameters']={'point':[-15.65,0,-8.]}
    if defect=='minimum':fields[2]['value']=4.99
    if defect=='depth':p['physical']['profiles'][0]['dimensions']['d']=19.3
    if defect=='inset':parts[0]['geometry']['origin'][1]+=.25
    if defect=='missing':p['physical']['members']=[]
    r=verify_source_selections(p)
    assert not r['passed']
    assert expected in {issue['issue'] for issue in r['findings']}
