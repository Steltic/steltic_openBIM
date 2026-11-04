"""Native assembly frames and graph relationships survive the real IFC route."""
import copy,json
import ifcopenshell
import ifcopenshell.util.element as element
import numpy as np
from test_ifc import drawing_source
from steltic_openbim import bim_assemblies as A
from steltic_openbim.drawing_workflow import initial_state,write_json
from steltic_openbim.ifc_export import export_drawing,export_import,schema_errors
from steltic_openbim.ifc_import import build_review


def test_rotated_native_assembly_preserves_geometry_members_and_source_template(tmp_path):
    folder,package,_=drawing_source(tmp_path);physical=package['physical']
    frame=dict(origin=[120,240,360],x_axis=[0,1,0],y_axis=[-1,0,0],bindings={'receiver':'beam'})
    member=physical['members'][0]
    receiver=dict(id='receiver',kind='member',axis=copy.deepcopy(member['axis']),profile_id='TEST',local_y=member['local_y'])
    member['axis']=[A.transformed(p,frame) for p in member['axis']]
    member['local_y']=A.transformed(member['local_y'],frame,True)
    for joint in physical['joints']:joint['point']=A.transformed(joint['point'],frame)
    connection=physical['connections'][0]
    template=dict(id='selected-clip',basis='Synthetic source selection',source_record_ids=connection['design_record_ids'],receivers=[receiver],parts=connection.pop('parts'))
    template['revision']=A.fingerprint(template);physical['assemblies']=[template]
    connection.update(parts=[],assembly_instance=dict(frame,template_id=template['id'],revision=template['revision']))
    write_json(folder/'source.json',package);write_json(folder/'state.json',initial_state(package,1))
    source=tmp_path/'source.ifc';report=export_drawing(folder,source)
    assert report['counts']['connection_assemblies']==1
    assert len(report['relationships'])==1
    model=ifcopenshell.open(str(source));rel=model.by_type('IfcRelConnectsElements')[0]
    assert rel.RelatingElement.is_a('IfcElementAssembly') and rel.RelatedElement.is_a('IfcBeam')
    props=element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert json.loads(props['AssemblyTemplates'])==[template]
    review=build_review(source,dict(units='auto',scope='all'))
    obj=next(o for o in review['objects'] if o['ifc_class']=='IfcElementAssembly')
    assert np.allclose(obj['bounds_m'],np.array([[116,120],[240,240.5],[360,366]])*.0254)
    returned=tmp_path/'returned.ifc'
    export_import(source,returned,dict(source_sha256=report['sha256'],revision=1,status='built',options={'units':'auto'}))
    result=ifcopenshell.open(str(returned));back=result.by_guid(rel.GlobalId)
    assert back.RelatingElement.GlobalId==rel.RelatingElement.GlobalId
    assert back.RelatedElement.GlobalId==rel.RelatedElement.GlobalId
    assert not schema_errors(returned)
    assert build_review(returned,dict(units='auto',scope='all'))['objects']==review['objects']


def test_legacy_component_group_keeps_original_occurrence_and_part_membership(tmp_path):
    folder,package,_=drawing_source(tmp_path);source=tmp_path/'parts.ifc'
    report=export_drawing(folder,source);model=ifcopenshell.open(str(source))
    group=model.by_type('IfcGroup')[0];relation=model.by_type('IfcRelAssignsToGroup')[0]
    assert relation.RelatingGroup==group
    assert {p.is_a() for p in relation.RelatedObjects}=={'IfcPlate','IfcBeam'}
    assert json.loads(element.get_psets(group)['Steltic_Coordination']['SourceConnection'])==package['physical']['connections'][0]
    assert report['relationships'][0]['role']=='connection_group'
