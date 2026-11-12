import pytest
from steltic_openbim.source_selection_readback import verify_source_selections


def example():
    fields=[('connection','variant','beam_pin_hinge'),('pin','diameter_in',4.),
            ('pin','material','A572 Gr 50'),('clevis_outer_fillet','size_in',.75)]
    return dict(
        source_handoff=dict(records={'HR':{'fields':[dict(role=a,field=b,value=c) for a,b,c in fields]}},
            occurrences={'joint':{'applications':[dict(record_id='HR',selected=list(range(len(fields))))]}}),
        physical=dict(materials=[dict(id='steel',specification='ASTM A572 Grade 50'),
                                 dict(id='grout',specification='ASTM C1107 non-shrink grout')],
            connections=[dict(id='joint',assembly_instance=dict(template_id='T'))],
            assemblies=[dict(id='T',source_detail='CD1',parts=[
                dict(id='PIN',kind='pin',material_id='steel',parameters=dict(diameter=4.,count=1)),
                dict(id='WC0',kind='weld',parameters=dict(size_in=.75)),
                dict(id='WC1',kind='weld',parameters=dict(size_in=.75)),
                dict(id='GROUT',kind='grout',material_id='grout')])]))


@pytest.mark.parametrize('error',['none','diameter','reroute','ambiguous','weld','grout','printed_weld','missing_shaft'])
def test_source_selections(error):
    p=example()
    scene=dict(id='CD1',fasteners=[dict(id='PIN',diameter=4)],welds=[dict(id='WC0',size=.75),dict(id='WC1',size=.75)])
    native=p['physical']
    parts=native['assemblies'][0]['parts']
    if error=='diameter':parts[0]['parameters']['diameter']=3.5
    if error=='reroute':native['materials'][0]['specification']='AISI 4140'
    if error=='ambiguous':native['materials'][0]['specification']='AISI 4140 or ASTM A572 Gr 50'
    if error=='weld':parts[1]['parameters']['size_in']=.6875
    if error=='grout':parts[-1]['material_id']='steel'
    if error=='printed_weld':scene['welds'][0]['size']=.6875
    if error=='missing_shaft':parts.pop(0)
    assert verify_source_selections(p,dict(assemblies=[scene]))['passed']==(error=='none')
def test_located_collector_uses_its_own_source_text_and_hole_pattern():
    from types import SimpleNamespace
    from steltic_openbim.hr_detail_selections import selected_fields,selected_shear_text,located_collector_fit
    from steltic_openbim.review_assemblies import source_text
    from steltic_openbim.review_cases import evidence
    rid='connections/collector-irregularity-lines'
    raw=next(r for r in evidence('hr14')['calc']['connections'] if r['id']==rid.split('/')[-1])
    field={'role':'shear_plate','field':'thickness_in','value':.75}
    app={'record_id':rid,'selected':[0],'interface_application':{'role':'scheduled_collector'}}
    c={'id':'collector-end','design_record_ids':[rid]}
    package={'design_records':[{'id':rid,'data':raw}],'source_handoff':{
        'records':{rid:{'fields':[field]}},'occurrences':{c['id']:{'applications':[app]}}}}
    ctx=SimpleNamespace(c=c,package=package,selected=selected_fields(package,c))
    assert not source_text(package,c)
    text=selected_shear_text(ctx)
    assert '5 x 1.125 in A490-X bolts' in text
    assert located_collector_fit(ctx,text)==dict(hole=1.25,line=3.,vertical=1.5,plate_edge=2.25,gap=.75)
