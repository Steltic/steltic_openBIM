from collections import defaultdict
import uuid
import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import pytest

from steltic_openbim.ifc_relationship_readback import check_relations


@pytest.mark.parametrize("defect",["none","hierarchy","level","datum","material","receiver","host","outline"])
def test_actual_ifc_graph(tmp_path,defect):
    f=ifcopenshell.file(schema="IFC4")
    def product(cls,name):
        return ifcopenshell.api.root.create_entity(f,ifc_class=cls,name=name)
    project,site,building=[product("Ifc"+cls,cls) for cls in ("Project","Site","Building")]
    storey=product("IfcBuildingStorey","Level 1")
    storey.GlobalId=ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL,"steltic:job:level:1").hex)
    storey.Elevation=11. if defect=="datum" else 10.
    ifcopenshell.api.aggregate.assign_object(f,products=[site],relating_object=project)
    ifcopenshell.api.aggregate.assign_object(f,products=[building],relating_object=project if defect=="hierarchy" else site)
    ifcopenshell.api.aggregate.assign_object(f,products=[storey],relating_object=building)
    beam,wall,conn,o=[product(c,n) for c,n in (("IfcBeam","B"),("IfcWall","P"),("IfcElementAssembly","C"),("IfcAnnotation","O"))]
    ifcopenshell.api.spatial.assign_container(f,products=[beam,conn,wall],relating_structure=storey)
    if defect=="level":
        ifcopenshell.api.spatial.assign_container(f,products=[beam],relating_structure=building)
    ids=lambda:ifcopenshell.guid.new()
    mat=f.createIfcMaterial("Steel" if defect=="material" else "Concrete")
    f.createIfcRelAssociatesMaterial(ids(),RelatedObjects=[wall],RelatingMaterial=mat)
    f.createIfcRelConnectsElements(ids(),RelatingElement=conn,RelatedElement=wall if defect=="receiver" else beam)
    f.createIfcRelAssignsToProduct(ids(),RelatedObjects=[o],RelatingProduct=beam if defect=="host" else wall)
    verts=[[1.,0.,1.],[2.,0.,1.],[2.,0.,2.],[1.,0.,2.]]
    points=[f.createIfcCartesianPoint([x+(1. if defect=="outline" else 0.),y,z]) for x,y,z in verts]
    curves=f.createIfcGeometricCurveSet([f.createIfcPolyline(points+[points[0]])])
    placement=f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.,0.,0.)))
    ctx=f.createIfcGeometricRepresentationContext(CoordinateSpaceDimension=3,WorldCoordinateSystem=placement)
    rep=f.createIfcShapeRepresentation(ctx,"Body","GeometricCurveSet",[curves])
    o.Representation=f.createIfcProductDefinitionShape(Representations=[rep])
    o.ObjectPlacement=f.createIfcLocalPlacement(RelativePlacement=placement)
    file=tmp_path/"record.ifc"
    f.write(str(file))
    model=ifcopenshell.open(str(file))
    props={}
    products=defaultdict(list)
    for obj in model.by_type("IfcElement")+model.by_type("IfcAnnotation"):
        products[obj.Name].append(obj);props[obj.id()]={"SourceId":obj.Name}
    physical=dict(levels=[[1,"Level 1",10.]],members=[dict(id="B",level=1)],
                  material_id="M",materials=[dict(id="M",specification="Concrete")],
                  panels=[dict(id="P",level=1,material_id="M")],
                  assemblies=[dict(id="T",receivers=[])],joints=[],connections=[dict(id="C",level=1,
                  member_ids=["B"],assembly_instance=dict(template_id="T",bindings={}))],
                  openings=[dict(id="O",host_id="P",vertices=verts)])
    counts,findings=check_relations(model,dict(building_id="job",physical=physical),products,props,1.)
    assert counts["assembly_receiver_links"]==1
    assert counts["opening_hosts"]==1
    assert bool(findings)==(defect!="none"),findings
