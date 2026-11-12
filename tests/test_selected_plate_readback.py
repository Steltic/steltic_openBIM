import pytest

from steltic_openbim.source_selection_readback import verify_source_selections


def plate(id,size,material='s',kind='plate'):
    return dict(id=id,kind=kind,material_id=material,geometry=dict(type='box',origin=[1,2,3],x_axis=[1,0,0],y_axis=[0,1,0],size=size))


def source(variant,fields,parts):
    rows=[dict(role=r,field=f,value=v) for r,f,v in [('connection','variant',variant)]+fields]
    return dict(source_handoff=dict(records={'r':{'fields':rows}},occurrences={'joint':{'applications':[dict(record_id='r',selected=list(range(len(rows))))]}}),
                physical=dict(connections=[dict(id='joint',assembly_instance=dict(template_id='T'))],assemblies=[dict(id='T',parts=parts)],
                              materials=[dict(id='s',specification='ASTM A588'),dict(id='g',specification='Non-shrink grout')]))


@pytest.mark.parametrize('change',['none','too_small','swapped_gauge','mixed_grade','wrong_grade','thin_grout'])
def test_measured_base_plate_and_committed_constituent_grade(change):
    parts=[plate('P1',[41,39,6.5]),plate('GROUT',[41,39,2],'g','grout')]
    fields=[('base_plate','thickness_in',6.5),('base_plate','width_in',39),('base_plate','length_in',41),
            ('base_plate','material','A588'),('grout','thickness_in',2)]
    p=source('base_plate_anchors',fields,parts)
    if change=='too_small':parts[0]['geometry']['size'][1]=38.5
    if change=='swapped_gauge':parts[0]['geometry']['size']=[41,39,5.]
    if change=='mixed_grade':p['physical']['materials'][0]['specification']='A572 Grade 50 for t <= 4 in; A588 over 4 in'
    if change=='wrong_grade':p['physical']['materials'][0]['specification']='A572 Gr 50'
    if change=='thin_grout':parts[1]['geometry']['size'][2]=1.75
    assert verify_source_selections(p)['passed']==(change=='none')


def test_shear_plate_depth_uses_world_vertical():
    parts=[plate('P1',[.5,12,4]),dict(id='B',kind='bolt')]
    p=source('single_plate_shear',[('shear_plate','depth_in',12),('shear_plate','thickness_in',.5)],parts)
    p['physical']['connections'][0]['assembly_instance'].update(x_axis=[1,0,0],y_axis=[0,0,1])
    assert verify_source_selections(p)['passed']
    parts[0]['geometry']['size'][1]=11.75
    assert not verify_source_selections(p)['passed']


def test_selected_cheek_plate_pair():
    pair=[plate('CHEEK0',[10,.75,8]),plate('CHEEK1',[10,.75,8]),dict(id='PIN',kind='pin')]
    p=source('brb_pinned',[('cheek_plate','thickness_in',.75),('cheek_plate','count',2)],pair)
    assert verify_source_selections(p)['passed']
    pair.pop(0)
    assert any(f['issue']=='selected_cheek_plate_count' for f in verify_source_selections(p)['findings'])


def test_reinforced_gusset_uses_main_plate_stock():
    primary=plate('GUSSET',[18,1.25,16])
    edge=plate('GUSSET-EDGE-1-1',[3,.75,12])
    edge['parameters']=dict(free_edge_bar=True,source_primary_gusset='GUSSET')
    package=source('brb_pinned',[('gusset','thickness_in',1.25)],[primary,edge,dict(id='PIN',kind='pin')])
    assert verify_source_selections(package)['passed']
    primary['geometry']['size'][1]=1.
    assert any(f['issue']=='selected_gusset_thickness' for f in verify_source_selections(package)['findings'])
