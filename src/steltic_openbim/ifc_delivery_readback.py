"""Read final IFC placements, finite member extents and material assignments."""
import json
from collections import defaultdict

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np


def properties(product):
    for relation in product.IsDefinedBy:
        pset=relation.RelatingPropertyDefinition
        if pset.is_a('IfcPropertySet') and pset.Name=='Steltic_Coordination':
            return {p.Name:p.NominalValue.wrappedValue for p in pset.HasProperties if p.is_a('IfcPropertySingleValue') and p.NominalValue}
    return {}


def mapped_vertices(item,cache):
    if item.id() in cache:return cache[item.id()]
    if item.is_a('IfcTessellatedFaceSet'):
        points=np.asarray(item.Coordinates.CoordList,dtype=float)
    elif item.is_a('IfcMappedItem'):
        parts=[mapped_vertices(x,cache) for x in item.MappingSource.MappedRepresentation.Items]
        parts=[a for a in parts if len(a)]
        points=np.concatenate(parts) if parts else np.empty((0,3))
        tr=ifcopenshell.util.placement.get_mappeditem_transformation(item)
        points=points@tr[:3,:3].T+tr[:3,3]
    else:
        points=np.empty((0,3))
    cache[item.id()]=points
    return points


def body_vertices(obj,cache,unit_in):
    arrays=[mapped_vertices(item,cache) for rep in obj.Representation.Representations
            if rep.RepresentationIdentifier=='Body' for item in rep.Items] if obj.Representation else []
    arrays=[a for a in arrays if len(a)]
    if not arrays:return np.empty((0,3))
    points=np.concatenate(arrays)
    placement=ifcopenshell.util.placement.get_local_placement(obj.ObjectPlacement)
    return (points@placement[:3,:3].T+placement[:3,3])*unit_in


def verify_assembly_surface(obj,frame,template,profiles,cache,unit_in):
    """Compare actual IFC occurrence placement and all polygon rings to each native solid."""
    from .pilots.geometry import part_faces
    tid=template['id']
    if tid not in cache['native']:
        source=[face for p in template['parts'] for face in part_faces(p,profiles)]
        cache['native'][tid]=source
    source=cache['native'][tid]
    if not source:return None
    reps=[item for rep in obj.Representation.Representations if rep.RepresentationIdentifier=='Body'
          for item in rep.Items] if obj.Representation else []
    if len(reps)!=1 or not reps[0].is_a('IfcMappedItem'):return 'Missing mapped solid representation'
    mapped=reps[0]
    shape=mapped.MappingSource.MappedRepresentation.Items
    if len(shape)!=1 or not shape[0].is_a('IfcPolygonalFaceSet'):return 'Missing polygonal constituent solid'
    mesh=shape[0];origin=np.asarray(source[0][0])
    R=np.array([frame['x_axis'],frame['y_axis'],np.cross(frame['x_axis'],frame['y_axis'])]).T
    position=ifcopenshell.util.placement.get_local_placement(obj.ObjectPlacement)@ifcopenshell.util.placement.get_mappeditem_transformation(mapped)
    if np.max(np.abs(position[:3,:3]-R))>1e-7 or np.max(np.abs(position[:3,3]*unit_in-(R@origin+frame['origin'])))>1e-4:
        return 'Actual IFC placement or rotation differs from the physical occurrence'
    key=(tid,mesh.id())
    if key in cache['checked']:return cache['checked'][key]
    expected=[np.asarray(face) for face in source if len({tuple(round((x-y)*.0254,9) for x,y in zip(p,origin)) for p in face})>=3]
    faces=mesh.Faces;message=None
    if len(faces)!=len(expected):
        message='Actual constituent solid face count differs'
    else:
        indices=[face.CoordIndex for face in faces]
        if [len(row) for row in indices]!=[len(row) for row in expected]:
            message='Actual constituent ring cardinality or order differs'
        else:
            coords=np.asarray(mesh.Coordinates.CoordList)*unit_in+origin
            actual=coords[np.concatenate(indices)-1]
            if np.max(np.abs(actual-np.vstack(expected)))>1e-4:
                message='Actual constituent polygon coordinate differs'
    cache['checked'][key]=message
    return message


def verify_ifc(path,package,source_sha256):
    model=ifcopenshell.open(str(path))
    unit_in=ifcopenshell.util.unit.calculate_unit_scale(model)/.0254
    project=model.by_type('IfcProject')
    findings=[]
    result=dict(passed=False,members_checked=0,assemblies_checked=0,panels_checked=0,
                material_sets_checked=0,findings=findings)
    def flag(code,identifier,detail):
        findings.append(dict(code=code,entity=identifier,detail=detail))
    if len(project)!=1:
        flag('ifc_project',None,'Expected one source project')
        return result
    project_props=properties(project[0]);physical=package['physical']
    from .ifc_shape_readback import ShapeReadback
    shapes=ShapeReadback(physical,unit_in)
    if project[0].Name!=package['building_id'] or project_props.get('SourceModelSHA256')!=source_sha256:
        flag('ifc_identity',project[0].Name,'Source job or model digest differs')
    for name,value in [('DesignRecords',package['design_records']),('SourceMaterials',physical['materials']),
                       ('SourceProfiles',physical['profiles']),('AssemblyTemplates',physical.get('assemblies',[]))]:
        if json.loads(project_props.get(name,'null'))!=value:
            flag('ifc_source_graph',name,'Published declaration differs from the handoff')
    material={r['id']:r['specification'] for r in physical['materials']}
    products=defaultdict(list);props={}
    for product in model.by_type('IfcElement')+model.by_type('IfcAnnotation'):
        p=properties(product)
        if p.get('SourceId'):
            products[p['SourceId']].append(product);props[product.id()]=p
    from .ifc_relationship_readback import check_relations
    measured,issues=check_relations(model,package,products,props,unit_in)
    result.update(measured);findings.extend(issues)
    def product_for(ident,cls):
        rows=[p for p in products[ident] if p.is_a()==cls]
        if len(rows)!=1:
            flag('ifc_typed_identity',ident,f'Expected one {cls}, found {len(rows)}')
            return None
        return rows[0]
    vertices={}
    for m in physical['members']:
        cls=('IfcColumn' if m['kind'] in ('column','col','stud','post','endwall_post') else
             'IfcBeam' if m['kind'] in ('beam','girder','joist','rafter','moment_beam') else 'IfcMember')
        obj=product_for(m['id'],cls)
        if obj is None:continue
        result['members_checked']+=1
        shape_issue=shapes.check_member(obj,m)
        if shape_issue:
            flag('ifc_member_solid',m['id'],shape_issue)
        prop=props[obj.id()]
        if prop.get('Section')!=m['profile_id']:
            flag('ifc_profile',m['id'],'Assigned section differs from the physical source')
        mats=[a.RelatingMaterial.Name for a in obj.HasAssociations if a.is_a('IfcRelAssociatesMaterial') and a.RelatingMaterial.is_a('IfcMaterial')]
        if m.get('section_plies'):
            assignments=[a.RelatingMaterial for a in obj.HasAssociations if a.is_a('IfcRelAssociatesMaterial') and a.RelatingMaterial.is_a('IfcMaterialConstituentSet')]
            actual={x.Name:(x.Description,x.Material.Name) for a in assignments for x in a.MaterialConstituents}
            plies=[dict(id='MAIN',material_id=m['material_id']),*m['section_plies']]
            if len(assignments)!=1 or actual!={p['id']:(p['material_id'],material[p['material_id']]) for p in plies}:
                flag('ifc_member_ply_material',m['id'],'Compound member material graph differs from the selected section plies')
        elif mats!=[material.get(m.get('material_id'))]:
            flag('ifc_material',m['id'],'Actual material assignment differs from the selected specification')
        pts=body_vertices(obj,vertices,unit_in)
        if not len(pts):
            flag('ifc_member_body',m['id'],'Missing tessellated finite body')
            continue
        e=np.asarray(m['axis'],float)+np.asarray(m['end_offsets'],float)
        ray=e[1]-e[0];length=np.linalg.norm(ray);ray/=length
        stations=(pts-e[0])@ray
        if m.get('terminal_planes'):
            for cut in m['terminal_planes']:
                distances=pts@np.asarray(cut['normal'])-cut['offset_in']
                if distances.min() < -1e-4:
                    flag('ifc_terminal_plane',m['id'],'Actual material extends across a selected terminal plane')
                    break
        elif abs(stations.min())>1e-4 or abs(stations.max()-length)>1e-4:
            flag('ifc_end_extent',m['id'],'Actual end stations differ from the physical member')
        transverse=pts-e[0]-np.outer(stations,ray)
        y=np.asarray(m['local_y']);z=np.cross(ray,y)
        # The two source section axes must cross the actual projected extents.
        # Section origins such as a channel web can legitimately lie on an edge.
        for u in (y,z):
            bounds=transverse@u
            if bounds.min()>1e-4 or bounds.max() < -1e-4:
                flag('ifc_member_location',m['id'],'Body is transversely displaced from its section reference')
                break
    for panel in physical.get('panels',[]):
        # Panel roles can produce IfcWall, IfcSlab or IfcPlate with the same
        # source identifier as a separate member. Keep their namespaces typed.
        rows=[obj for obj in products[panel['id']] if obj.is_a() in ('IfcWall','IfcSlab','IfcPlate','IfcRoof','IfcCovering','IfcBuildingElementProxy')]
        if len(rows)!=1:
            flag('ifc_panel',panel['id'],'Expected one declared panel product')
        else:
            result['panels_checked']+=1
            shape_issue=shapes.check_panel(rows[0],panel)
            if shape_issue:
                flag('ifc_panel_solid',panel['id'],shape_issue)
    templates={t['id']:t for t in physical.get('assemblies',[])}
    profiles={p['id']:p for p in physical['profiles']}
    geometry_cache={'native':{},'checked':{}}
    ranges=json.loads(project_props.get('AssemblyPartRepresentations','{}'))
    seen={}
    for c in physical['connections']:
        frame=c.get('assembly_instance')
        if not frame:continue
        obj=product_for(c['id'],'IfcElementAssembly')
        if obj is None:continue
        result['assemblies_checked']+=1
        tid=frame['template_id'];p=props[obj.id()]
        if p.get('AssemblyTemplate')!=tid:
            flag('ifc_assembly_template',c['id'],'Occurrence refers to another source template')
        source=json.loads(p.get('SourceEntity','{}'))
        if source.get('assembly_instance')!=frame:
            flag('ifc_assembly_frame',c['id'],'Declared frame or bound receivers differ')
        error=verify_assembly_surface(obj,frame,templates[tid],profiles,geometry_cache,unit_in)
        if error:flag('ifc_constituent_geometry',c['id'],error)
        expected=[x for x in templates[tid]['parts'] if x.get('material_id')]
        if not expected:continue
        sets=[a.RelatingMaterial for a in obj.HasAssociations if a.is_a('IfcRelAssociatesMaterial') and a.RelatingMaterial.is_a('IfcMaterialConstituentSet')]
        if len(sets)!=1 or sets[0].Name!=tid:
            flag('ifc_constituent_set',c['id'],'Missing the native constituent material set for this template')
            continue
        key=(tid,sets[0].id())
        if key in seen:continue
        seen[key]=True;result['material_sets_checked']+=1
        actual={v.Name:(v.Category,v.Description,v.Material.Name) for v in sets[0].MaterialConstituents}
        wanted={v['id']:(v['kind'],v['material_id'],material[v['material_id']]) for v in expected}
        if actual!=wanted:
            flag('ifc_constituent_material',tid,'Actual per-part material graph differs from the physical template')
        declared=ranges.get(tid,[])
        if [(r['id'],r['kind'],r['material_id']) for r in declared]!=[(r['id'],r['kind'],r.get('material_id')) for r in templates[tid]['parts']]:
            flag('ifc_constituent_locator',tid,'Constituent geometry ranges have inconsistent identities')
    result['passed']=not findings
    return result
