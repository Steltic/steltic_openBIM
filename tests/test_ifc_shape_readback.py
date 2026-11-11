import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.root
import pytest

from steltic_openbim.ifc_shape_readback import ShapeReadback
from steltic_openbim.pilots.geometry import member_faces


def make_body(tmp_path,faces,holes):
    model=ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.root.create_entity(model,ifc_class="IfcProject")
    ctx=ifcopenshell.api.context.add_context(model,context_type="Model")
    body=ifcopenshell.api.context.add_context(model,context_type="Model",context_identifier="Body",target_view="MODEL_VIEW",parent=ctx)
    zeros=model.createIfcCartesianPoint((0.,0.,0.))
    placement=model.createIfcAxis2Placement3D(zeros)
    vertices=[]
    def indexes(points):
        start=len(vertices)+1
        vertices.extend(tuple(map(float,p)) for p in points)
        return tuple(range(start,start+len(points)))
    polygons=[]
    for face,inner in zip(faces,holes):
        outer=indexes(face)
        polygons.append(model.createIfcIndexedPolygonalFaceWithVoids(outer,[indexes(r) for r in inner])
                        if inner else model.createIfcIndexedPolygonalFace(outer))
    mesh=model.createIfcPolygonalFaceSet(model.createIfcCartesianPointList3D(vertices),False,polygons)
    rep=model.createIfcShapeRepresentation(body,"Body","Tessellation",[mesh])
    mapped=model.createIfcMappedItem(model.createIfcRepresentationMap(placement,rep),
                                     model.createIfcCartesianTransformationOperator3D(LocalOrigin=zeros))
    mapping=model.createIfcShapeRepresentation(body,"Body","MappedRepresentation",[mapped])
    obj=ifcopenshell.api.root.create_entity(model,ifc_class="IfcBuildingElementProxy")
    obj.Representation=model.createIfcProductDefinitionShape(Representations=[mapping])
    obj.ObjectPlacement=model.createIfcLocalPlacement(RelativePlacement=placement)
    path=tmp_path/"delivered.ifc"
    model.write(str(path))
    reopened=ifcopenshell.open(str(path))
    return reopened,reopened.by_type("IfcBuildingElementProxy")[0]


@pytest.mark.parametrize("defect",["none","thicker_web","missing_face","rotated_ring"])
def test_actual_member_faces(tmp_path,defect):
    profile=dict(id="W",family="i",dimensions=dict(d=10,bf=8,tf=1,tw=.5))
    member=dict(axis=[[10,0,0],[40,0,0]],end_offsets=[[0,0,0],[0,0,0]],local_y=[0,1,0],profile_id="W")
    physical=dict(profiles=[profile])
    as_drawn={**profile,"dimensions":{**profile["dimensions"],"tw":1 if defect=="thicker_web" else .5}}
    faces=member_faces(member,{"W":as_drawn})
    if defect=="missing_face":
        faces.pop()
    if defect=="rotated_ring":
        faces[-1]=faces[-1][::-1]
    model,obj=make_body(tmp_path,faces,[[] for _ in faces])
    issue=ShapeReadback(physical,1.).check_member(obj,member)
    assert bool(issue)==(defect!="none"),issue


@pytest.mark.parametrize("defect",["none","filled","shifted","host_height","wrong_plane"])
def test_actual_host_and_void(tmp_path,defect):
    outer=[[0,0,0],[24,0,0],[24,0,18],[0,0,18]]
    hole=[[3,0,3],[9,0,3],[9,0,9],[3,0,9]]
    panel=dict(id="wall",vertices=outer)
    physical=dict(profiles=[],panels=[panel],openings=[dict(id="window",host_id="wall",vertices=hole)])
    boundary=[[x,y+(1 if defect=="wrong_plane" else 0),z*(2 if defect=="host_height" else 1)] for x,y,z in outer]
    void=[[x+(1 if defect=="shifted" else 0),y,z] for x,y,z in hole]
    model,obj=make_body(tmp_path,[boundary],[[] if defect=="filled" else [void]])
    issue=ShapeReadback(physical,1.).check_panel(obj,panel)
    assert bool(issue)==(defect!="none"),issue


def test_slotted_translated_chs_retains_native_end_cap_topology(tmp_path):
    profile=dict(id="CHS",family="chs",dimensions=dict(d=6.,t=.465))
    member=dict(axis=[[1080.,720.,2226.],[1260.,720.,2376.]],
                end_offsets=[[7.267373304991176,0.,6.05614442082598],[-33.965596606550555,0.,-28.304663838792127]],
                local_y=[0.,1.,0.],profile_id="CHS",
                slots=[dict(start_in=0.,end_in=17.15387090263231,width_in=.8125,section_axis=0),
                       dict(start_in=165.7022500637919,end_in=180.63419196248475,width_in=.8125,section_axis=0)])
    faces=member_faces(member,{"CHS":profile})
    model,obj=make_body(tmp_path,faces,[[] for _ in faces])
    assert ShapeReadback(dict(profiles=[profile]),1.).check_member(obj,member) is None
