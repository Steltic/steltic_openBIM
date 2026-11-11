"""Real IFC owner linkage, placed common plate and separately located support weld controls."""
from collections import Counter
import json
from types import SimpleNamespace

import ifcopenshell.api
import numpy as np
import pytest
from steltic_openbim.ifc_assembly_verification import Readback
from steltic_openbim.joint_mesh_readback import frame,transform
from steltic_openbim.shared_constituent_readback import resolve_shared
from test_ifc_assembly_verification import cuboid,export_readback


@pytest.mark.parametrize('change', ['valid','missing_owner','self_owner','duplicate_local','missing_relation','wrong_relation',
    'wrong_IFC_reference','wrong_revision','wrong_joint','missing_shared_weld','absent_actual_weld','wrong_thickness','wrong_grade'])
def test_actual_shared_plate_and_weld(tmp_path,change):
    origin=np.array([23.,-9.,65.]);O=frame(origin,[1,0,0],[0,1,0]);S=frame(origin,[0,1,0],[-1,0,0])
    localplate=cuboid([-4,-2,0],[4,2,.75]);line=np.array([[-4,2,0],[4,2,0]],float)
    references={} if change=='absent_actual_weld' else {'OWN':[transform(line,O)]}
    decoded=export_readback(tmp_path,{'P':localplate.transformed(O)},references=references,reader=True);model=decoded.file
    api=ifcopenshell.api.run;gu=ifcopenshell.guid.new
    pr={n:api('root.create_entity',model,ifc_class='IfcElementAssembly',name=n) for n in ('OWN','OTHER')}
    pr['OWN'].Representation=model.by_type('IfcMember')[0].Representation
    setting={'role':'GUSSET','owner_connection_id':'OWN','owner_part_id':'P','owner_template_id':'T','owner_template_revision':'R',
             'point_in':origin.tolist(),'owner_weld_roles':['WGB']}
    if change=='missing_owner':setting['owner_connection_id']='GONE'
    if change=='self_owner':setting['owner_connection_id']='OTHER'
    if change=='wrong_revision':setting['owner_template_revision']='old'
    if change=='wrong_joint':setting['point_in']=[0,0,0]
    if change=='missing_shared_weld':setting['owner_weld_roles']=[]
    refs=[setting];cid='OTHER'
    connections={'OWN':dict(id='OWN',point=origin.tolist(),assembly_instance=dict(template_id='T',revision='R',origin=origin.tolist(),x_axis=[1,0,0],y_axis=[0,1,0],bindings={'M':'beam'})),
                 'OTHER':dict(id=cid,point=origin.tolist(),assembly_instance={'bindings':{'REC':'beam'}},parameters={'shared_constituents':refs})}
    for n,p in pr.items():
        ps=api('pset.add_pset',model,product=p,name='Source');data=connections[n] if change!='wrong_IFC_reference' or n!='OTHER' else {}
        api('pset.edit_pset',model,pset=ps,properties={'SourceId':n,'SourceEntity':json.dumps(data)})
    if change!='missing_relation':model.create_entity('IfcRelAssignsToProduct',GlobalId=gu(),Name='Shared assembly constituents',Description=json.dumps(refs if change!='wrong_relation' else []),RelatedObjects=[pr['OTHER']],RelatingProduct=pr['OWN'])
    mat=model.create_entity('IfcMaterial',Name='ASTM A572 Grade 50')
    group=model.create_entity('IfcMaterialConstituentSet',Name='Owner materials',MaterialConstituents=[model.create_entity('IfcMaterialConstituent',Name='P',Material=mat)])
    model.create_entity('IfcRelAssociatesMaterial',GlobalId=gu(),RelatedObjects=[pr['OWN']],RelatingMaterial=group)
    src=model.by_type('IfcProject')[0];ps=api('pset.add_pset',model,product=src,name='Parts');api('pset.edit_pset',model,pset=ps,properties={'AssemblyPartRepresentations':json.dumps({'T':[dict(id='P',face_start=0,face_count=6),dict(id='WGB',face_start=6,face_count=0)]})})
    path=tmp_path/'shared.ifc';model.write(str(path))
    parts=[dict(id='P',kind='plate',geometry={'type':'mesh'},parameters={}),dict(id='WGB',kind='weld',geometry=dict(type='polyline',points=line.tolist()),connects=['P','M'])]
    records={n:{'fields':[{'role':'gusset','field':'material','value':'A36' if change=='wrong_grade' and n=='OTHER' else 'A572 Gr 50'},
                           {'role':'gusset','field':'thickness_in','value':1. if change=='wrong_thickness' and n=='OTHER' else .75}]} for n in pr}
    handoff=dict(records=records,occurrences={n:{'applications':[{'record_id':n,'selected':[0,1]}]} for n in pr})
    check=SimpleNamespace(rb=Readback(path),connections=connections,templates={'T':{'revision':'R','parts':parts}},counts=Counter(),handoff=handoff,members={'beam':{'kind':'beam'}})
    def evaluate():return resolve_shared(check,connections['OTHER'],{'GUSSET':{}} if change=='duplicate_local' else {},S)
    if change!='valid':
        with pytest.raises(ValueError):evaluate()
    else:
        virtual,meshes,actual_curves=evaluate();assert len(meshes)==len(actual_curves)==1
        assert np.allclose(np.sort(meshes['GUSSET'].vertices,axis=0),np.sort(transform(localplate.vertices,np.linalg.inv(S)@O),axis=0))
        assert np.allclose(actual_curves[0],transform(line,O))
        assert virtual['shared:OWN:WGB']['connects']==['GUSSET','REC']
