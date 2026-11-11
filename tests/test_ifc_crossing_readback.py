import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.unit
import pytest

from steltic_openbim.ifc_brace_readback import verify_member_clearance


@pytest.mark.parametrize("shift_z,shift_x,length,passed",[(0.,0.,2.,False),(.5,0.,2.,True),(.625,0.,2.,False),
                                                        (.5,3.,2.,False),(.5,0.,2.2,False)])
def test_actual_crossing_lap(tmp_path,shift_z,shift_x,length,passed):
    model=ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.root.create_entity(model,ifc_class="IfcProject")
    ifcopenshell.api.unit.assign_unit(model)
    context=ifcopenshell.api.context.add_context(model,context_type="Model")
    body=ifcopenshell.api.context.add_context(model,context_type="Model",context_identifier="Body",target_view="MODEL_VIEW",parent=context)
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    members=[]
    for key,hx,hy,x,z in [("A",5.,1.,0.,0.),("B",1.,5.,shift_x,shift_z)]:
        mm=[[[-5,0,0],[5,0,0]],[[0,-5,0],[0,5,0]]]
        members.append(dict(id=key,kind="truss_web",axis=mm[key=="B"]))
        pts=[((x+u)*.0254,v*.0254,(z+w)*.0254) for w in (-.25,.25) for u,v in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]
        obj=ifcopenshell.api.root.create_entity(model,ifc_class="IfcMember",name=key)
        rep=ifcopenshell.api.geometry.add_mesh_representation(model,context=body,vertices=[pts],faces=[faces])
        ifcopenshell.api.geometry.assign_representation(model,product=obj,representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model,product=obj)
        pset=ifcopenshell.api.pset.add_pset(model,product=obj,name="Steltic_Coordination")
        ifcopenshell.api.pset.edit_pset(model,pset=pset,properties={"SourceId":key})
    path=tmp_path/"crossing.ifc"
    model.write(str(path))
    result=verify_member_clearance(path,dict(connections=[],members=members),
                                   [dict(id="cross",member_ids=["A","B"],point_in=[0.,0.,0.],record_id="web",selected=[0,1])],
                                   {"web":{"fields":[dict(role="flat_bar_crossing_fillet",field="count",value=4),
                                                     dict(role="flat_bar_crossing_fillet",field="length_in",value=length)]}})
    assert result["crossings_checked"]==1
    assert result["passed"]==passed,result
    if shift_z==.5 and shift_x==0.:
        facts=result["crossing_measurements"][0]
        assert sorted(facts["edge_lengths_in"])==pytest.approx([2.,2.,2.,2.])
