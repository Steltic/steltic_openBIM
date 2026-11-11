"""Read IFC hierarchy, host links, receiver links, panel materials and opening outlines."""
from collections import Counter,defaultdict
import uuid

import ifcopenshell.guid
import ifcopenshell.util.placement
import numpy as np

from .ifc_shape_readback import INCH_TOL, opening_points


MEMBER_CLASSES={"IfcMember","IfcBeam","IfcColumn"}
PANEL_CLASSES={"IfcWall","IfcSlab","IfcPlate","IfcRoof","IfcCovering","IfcBuildingElementProxy"}


def check_relations(model,package,products,props,unit_in):
    p=package["physical"]
    found=[]
    counts=Counter()
    def flag(code,ident,detail):
        found.append(dict(code=code,entity=ident,detail=detail))
    project=model.by_type("IfcProject")
    buildings=model.by_type("IfcBuilding")
    if len(project)!=1 or len(buildings)!=1:
        flag("ifc_spatial_hierarchy",package["building_id"],"expected one containing project and building")
        return dict(counts),found
    building=buildings[0]
    def parents(obj):
        return [r.RelatingObject for r in obj.Decomposes if r.is_a("IfcRelAggregates")]
    sites=parents(building)
    if len(sites)!=1 or not sites[0].is_a("IfcSite") or parents(sites[0])!=[project[0]]:
        flag("ifc_spatial_hierarchy",building.GlobalId,"building is not aggregated under its project through its site")
    def level_id(level):
        key="steltic:"+package["building_id"]+":level:"+str(int(level))
        return ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL,key).hex)
    levels={s.GlobalId:s for s in model.by_type("IfcBuildingStorey")}
    def check_level(obj,level):
        counts["storey_assignments"]+=1
        target=building if level is None else levels.get(level_id(level))
        actual=[r.RelatingStructure for r in obj.ContainedInStructure]
        if target is None or actual!=[target] or (level is not None and parents(target)!=[building]):
            flag("ifc_storey_containment",obj.Name,"actual spatial assignment differs from the source level")
    for level in (package.get("reference_system",{}).get("levels") or p.get("levels",[])):
        if isinstance(level,dict) and "level" in level and "elevation_in" in level:
            number,elevation=level["level"],level["elevation_in"]
        elif isinstance(level,(list,tuple)) and len(level)==3:
            number,elevation=level[0],level[2]
        else:
            continue
        storey=levels.get(level_id(number))
        if storey is None or storey.Elevation is None or abs(storey.Elevation*unit_in-elevation)>INCH_TOL:
            flag("ifc_storey_elevation",str(number),"actual storey datum differs from source elevation")
    globally=Counter(o.GlobalId for o in model.by_type("IfcProduct"))
    for guid,count in globally.items():
        if count!=1:
            flag("ifc_product_guid",guid,f"product identifier used {count} times")
    materials={m["id"]:m["specification"] for m in p["materials"]}
    for group,classes in (("members",MEMBER_CLASSES),("panels",PANEL_CLASSES)):
        for row in p.get(group,[]):
            matches=[o for o in products.get(row["id"],[]) if o.is_a() in classes]
            if len(matches)!=1:
                continue
            obj=matches[0];check_level(obj,row.get("level"))
            if group=="panels" and row.get("material_id"):
                mats=[r.RelatingMaterial.Name for r in obj.HasAssociations if r.is_a("IfcRelAssociatesMaterial") and r.RelatingMaterial.is_a("IfcMaterial")]
                counts["panel_materials"]+=1
                if mats!=[materials.get(row["material_id"])]:
                    flag("ifc_panel_material",row["id"],"actual panel material differs from the selected source specification")
    templates={t["id"]:t for t in p.get("assemblies",[])}
    joints={j["id"]:j for j in p.get("joints",[])}
    related=defaultdict(Counter)
    for r in model.by_type("IfcRelConnectsElements"):
        a,b=r.RelatingElement,r.RelatedElement
        if not a.is_a("IfcElementAssembly"):
            continue
        group="member" if b.is_a() in MEMBER_CLASSES else "panel" if b.is_a() in PANEL_CLASSES else b.is_a()
        related[a.id()][(group,props.get(b.id(),{}).get("SourceId"))]+=1
    for c in p["connections"]:
        occurrence=c.get("assembly_instance")
        if not occurrence:
            continue
        matches=[o for o in products.get(c["id"],[]) if o.is_a("IfcElementAssembly")]
        if len(matches)!=1:
            continue
        joint=joints.get(c.get("joint_id"),{})
        check_level(matches[0],c.get("level") if c.get("level") is not None else joint.get("level"))
        targets={("member",m) for m in c.get("member_ids",[])}
        targets.update(("member",r["member_id"]) for r in joint.get("member_ends",[])+joint.get("attachments",[]))
        for rec in templates[occurrence["template_id"]].get("receivers",[]):
            ident=occurrence.get("bindings",{}).get(rec["id"])
            if ident is not None:
                targets.add(("panel" if rec.get("kind")=="panel" else "member",ident))
        counts["assembly_receiver_links"]+=len(targets)
        if related[matches[0].id()]!=Counter(targets):
            flag("ifc_receiver_links",c["id"],"actual typed receiver links differ from bound members and panels")
    for opening in p.get("openings",[]):
        ident=opening["id"]
        objects=[o for o in products.get(ident,[]) if o.is_a("IfcAnnotation")]
        if len(objects)!=1:
            flag("ifc_opening_reference",ident,"expected one opening annotation")
            continue
        obj=objects[0]
        curves=[curve for rep in obj.Representation.Representations for item in rep.Items if item.is_a("IfcGeometricCurveSet")
                for curve in item.Elements if curve.is_a("IfcPolyline")] if obj.Representation else []
        expected=opening_points(opening)
        counts["opening_outlines"]+=1
        if len(curves)!=1:
            flag("ifc_opening_outline",ident,"expected one actual boundary curve")
        else:
            pts=np.asarray([v.Coordinates for v in curves[0].Points],dtype=float)
            placement=ifcopenshell.util.placement.get_local_placement(obj.ObjectPlacement)
            pts=(pts@placement[:3,:3].T+placement[:3,3])*unit_in
            full=np.vstack([expected,expected[0]])
            if pts.shape!=full.shape or np.abs(pts-full).max()>INCH_TOL:
                flag("ifc_opening_outline",ident,"actual opening polyline differs from its source boundary")
        host=opening.get("host_id")
        if host:
            counts["opening_hosts"]+=1
            assigned=[r.RelatingProduct for r in obj.HasAssignments if r.is_a("IfcRelAssignsToProduct")]
            if len(assigned)!=1 or assigned[0].is_a() not in PANEL_CLASSES or props.get(assigned[0].id(),{}).get("SourceId")!=host:
                flag("ifc_opening_host",ident,"actual host relationship differs from the selected panel")
    return dict(counts),found
