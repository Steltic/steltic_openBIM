import pytest
import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.unit

from steltic_openbim.ifc_brace_readback import verify_member_clearance


@pytest.mark.parametrize('shift,passed',[(0.,False),(1.,True),(1.25,True)])
def test_ifc_brace_and_receiver_solids(tmp_path,shift,passed):
    model=ifcopenshell.file(schema='IFC4')
    ifcopenshell.api.root.create_entity(model,ifc_class='IfcProject',name='Geometry check')
    ifcopenshell.api.unit.assign_unit(model)
    model_context=ifcopenshell.api.context.add_context(model,context_type='Model')
    body=ifcopenshell.api.context.add_context(model,context_type='Model',context_identifier='Body',
                                              target_view='MODEL_VIEW',parent=model_context)
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    for name,cls,x in [('brace','IfcMember',0.),('host','IfcColumn',shift)]:
        obj=ifcopenshell.api.root.create_entity(model,ifc_class=cls,name=name)
        verts=[(a+x,b,c) for a,b,c in [(0,0,0),(1,0,0),(1,1,0),(0,1,0),
                                        (0,0,1),(1,0,1),(1,1,1),(0,1,1)]]
        if name=='host':
            verts=[(a,b+.25,c+.25) for a,b,c in verts]
        rep=ifcopenshell.api.geometry.add_mesh_representation(model,context=body,vertices=[verts],faces=[faces])
        ifcopenshell.api.geometry.assign_representation(model,product=obj,representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model,product=obj)
        pset=ifcopenshell.api.pset.add_pset(model,product=obj,name='Steltic_Coordination')
        ifcopenshell.api.pset.edit_pset(model,pset=pset,properties={'SourceId':name})
    path=tmp_path/'mesh.ifc'
    model.write(str(path))
    physical=dict(members=[dict(id='brace',kind='truss_web'),dict(id='host',kind='column')],
                  connections=[dict(id='joint',assembly_instance=dict(bindings=dict(web='brace',column='host')))])
    result=verify_member_clearance(path,physical)
    assert result['meshed_members']==2
    assert result['bound_pairs']==1
    assert result['passed']==passed,result
    if not passed:
        assert result['findings'][0]['intersection_in3']==pytest.approx(.5625/.0254**3)
