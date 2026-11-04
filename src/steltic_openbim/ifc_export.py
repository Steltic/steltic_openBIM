"""IFC4 coordination export of immutable physical-source or drawing revisions."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import uuid

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.validate

from .drawing_workflow import fingerprint
from .pilots.geometry import member_faces,part_faces,part_lines
from . import bim_assemblies, bim_bonds

INCH=.0254


def opening_boundary(opening):
    """Read recorded polygon inches or legacy lower-left plane/dimensions in feet.

    This conversion does not infer a host or cut the source panel geometry.
    """
    vertices=opening.get('vertices')
    if vertices is None:
        plane=opening.get('plane','').lower()
        if plane not in ('xy','xz','yz'):
            raise ValueError('Opening '+str(opening.get('id'))+' has no supported boundary or plane')
        try:
            origin=[float(opening[k])*12 for k in ('x_ft','y_ft','z_ft')]
            width=float(opening['width_ft'])*12;height=float(opening['height_ft'])*12
        except (KeyError,TypeError,ValueError) as ex:
            raise ValueError('Opening '+str(opening.get('id'))+' has incomplete dimensions') from ex
        if width<=0 or height<=0:raise ValueError('Opening dimensions must be positive')
        u,v=['xyz'.index(c) for c in plane]
        vertices=[]
        for a,b in ((0,0),(width,0),(width,height),(0,height)):
            point=origin.copy();point[u]+=a;point[v]+=b;vertices.append(point)
    try:
        vertices=[[float(v) for v in point] for point in vertices]
        if len(vertices)<3 or any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in vertices):
            raise ValueError('Invalid opening boundary')
    except (TypeError,ValueError) as ex:
        raise ValueError('Opening '+str(opening.get('id'))+' has invalid boundary coordinates') from ex
    return vertices


def property_set(model,product,values,name='Steltic_Coordination',cache=None):
    clean={k:(json.dumps(v,ensure_ascii=True,sort_keys=True) if isinstance(v,(list,dict)) else v)
           for k,v in values.items() if v is not None}
    if cache is not None:
        properties=[]
        for key,value in clean.items():
            kind='IfcBoolean' if isinstance(value,bool) else 'IfcInteger' if isinstance(value,int) else 'IfcReal' if isinstance(value,float) else 'IfcText'
            if kind=='IfcText':value=str(value)
            token=(key,kind,value)
            if token not in cache:
                cache[token]=model.create_entity('IfcPropertySingleValue',Name=key,NominalValue=model.create_entity(kind,value))
            properties.append(cache[token])
        pset=model.create_entity('IfcPropertySet',GlobalId=ifcopenshell.guid.new(),Name=name,HasProperties=properties)
        model.create_entity('IfcRelDefinesByProperties',GlobalId=ifcopenshell.guid.new(),RelatedObjects=[product],RelatingPropertyDefinition=pset)
        return
    pset=ifcopenshell.api.pset.add_pset(model,product=product,name=name)
    ifcopenshell.api.pset.edit_pset(model,pset=pset,properties=clean)


def schema_errors(path):
    logger=ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(str(path),logger)
    return [dict(message=r.get('message',''),attribute=r.get('attribute','')) for r in logger.statements if r.get('level')=='error']


def export_drawing(directory,destination):
    return _export_source(directory,destination,'steltic')


def export_structural(directory,destination):
    return _export_source(directory,destination,'structural')


def _export_source(directory,destination,source):
    directory=Path(directory);destination=Path(destination)
    package=json.loads((directory/'source.json').read_text(encoding='utf-8'))
    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
    structural=source=='structural'
    if structural and state.get('schema')!='steltic.ifc_physical_source':
        raise ValueError('Choose an immutable structural source snapshot')
    status=state['source_status'] if structural else state['drawing_status']
    revision_properties={'PhysicalSourceRevision' if structural else 'DrawingRevision':state['revision']}
    from .validation import inspect_package
    source_validation=inspect_package(package)
    if source_validation['status']=='invalid':raise ValueError('The source contains invalid physical data')
    if structural and source_validation['status']=='needs_input':status='provisional'
    if fingerprint(package)!=state['source_model_sha256']:raise ValueError('The source fingerprint changed')
    recovered=state.get('representation')=='captured_source_worklines'
    if not structural and (directory/'design_model.json').is_file():
        physical=json.loads((directory/'design_model.json').read_text(encoding='utf-8'));basis='Adopted fictional design geometry'
    elif recovered:
        from .source_worklines import build
        physical=build(package);physical['profiles']=package['physical']['profiles'];basis='Captured reference axes; physical placement remains TBD'
    else:
        from .source_worklines import physical_view
        physical=physical_view(package);basis='Source-declared design coordination geometry'
    physical['openings']=[dict(o,vertices=opening_boundary(o)) for o in physical.get('openings',[])]
    from .physical_review import review_physical
    physical_checks=review_physical(physical)
    model=ifcopenshell.file(schema='IFC4')
    def entity(cls,label,key):
        obj=ifcopenshell.api.root.create_entity(model,ifc_class=cls,name=str(label))
        obj.GlobalId=ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL,'steltic:'+package['building_id']+':'+key).hex)
        return obj
    def relation(cls,key,**attributes):
        guid=ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL,'steltic:'+package['building_id']+':relation:'+key).hex)
        return model.create_entity(cls,GlobalId=guid,**attributes)
    project=entity('IfcProject',package['building_id'],'project')
    metre=ifcopenshell.api.unit.add_si_unit(model,unit_type='LENGTHUNIT')
    ifcopenshell.api.unit.assign_unit(model,units=[metre])
    context=ifcopenshell.api.context.add_context(model,context_type='Model')
    body_context=ifcopenshell.api.context.add_context(model,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=context)
    site=entity('IfcSite','Site','site');building=entity('IfcBuilding',package['building_id'],'building')
    ifcopenshell.api.aggregate.assign_object(model,products=[site],relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model,products=[building],relating_object=site)
    members=physical.get('members',[]);panels=physical.get('panels',[]);connections=physical.get('connections',[])
    level_of=lambda item:int(item['level']) if item.get('level') is not None else None
    levels=sorted({level_of(item) for item in members+panels+connections+physical.get('joints',[])+physical.get('openings',[]) if item.get('level') is not None})
    # Preserve explicit source datums, including the ground datum even when no
    # physical element is assigned to it. Do not derive them from shifted solids.
    reference=package.get('reference_system',{})
    datum_levels={};datum_names={}
    for item in reference.get('levels',[]) or physical.get('levels',[]):
        if isinstance(item,dict) and 'level' in item and 'elevation_in' in item:
            datum_levels[int(item['level'])]=float(item['elevation_in'])
            if item.get('name'):datum_names[int(item['level'])]=item['name']
        elif isinstance(item,(list,tuple)) and len(item)==3:
            datum_levels[int(item[0])]=float(item[2])
    if not datum_levels:
        datum_levels={i:float(z) for i,z in enumerate(package.get('layout_evidence',{}).get('levels_in') or [])}
    levels=sorted(set(levels)|set(datum_levels))
    storeys={}
    for level in levels:
        s=entity('IfcBuildingStorey',datum_names.get(level,'Level '+str(level)),'level:'+str(level))
        points=[p[2] for m in members if level_of(m)==level for p in m['axis']]
        # Storey elevation follows the source floor framing plane, not a moved member placement.
        floor=[p[2] for m in members if level_of(m)==level and abs(m['axis'][0][2]-m['axis'][1][2])<1e-6 for p in m['axis']]
        s.Elevation=datum_levels.get(level,min(floor) if floor else min(points,default=0))*INCH
        ifcopenshell.api.aggregate.assign_object(model,products=[s],relating_object=building);storeys[level]=s
    def grid_axis(label,points):
        curve=model.create_entity('IfcPolyline',Points=[model.create_entity('IfcCartesianPoint',Coordinates=tuple(float(v)*INCH for v in p)) for p in points])
        return model.create_entity('IfcGridAxis',AxisTag=label,AxisCurve=curve,SameSense=True)
    def add_grid(rows,grid_basis):
        grid=entity('IfcGrid','Structural reference grid','source-grid')
        grid.ObjectPlacement=model.create_entity('IfcLocalPlacement',RelativePlacement=model.create_entity('IfcAxis2Placement3D',Location=model.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.))))
        for direction in ('U','V','W'):
            axes=[grid_axis(row['label'],row['points_in']) for row in rows if row['direction']==direction]
            if axes:setattr(grid,direction+'Axes',axes)
        ifcopenshell.api.spatial.assign_container(model,products=[grid],relating_structure=building)
        property_set(model,grid,dict(Basis=grid_basis,SourceModelSHA256=state['source_model_sha256'],SourceIFCSHA256=reference.get('source_ifc_sha256')))
    source_grids=physical.get('grids')
    grid_basis='Reviewed coordination grid' if source_grids else 'Explicit source layout grid'
    if recovered and source_grids:grid_basis='Derived from captured column worklines; not architect-confirmed'
    if not source_grids:
        layout=package.get('layout_evidence',{})
        source_grids={a:layout.get('grid_'+a+'_in') or [] for a in ('x','y')}
    def grid_rows(axis):
        return [(str(v[0]),float(v[1])) if isinstance(v,(list,tuple)) else (str(i+1),float(v)) for i,v in enumerate(source_grids.get(axis,[]))]
    gx,gy=grid_rows('x'),grid_rows('y')
    if reference.get('grids'):
        add_grid(reference['grids'],reference['basis'])
    elif gx and gy:
        xmin,xmax=min(v for _,v in gx),max(v for _,v in gx);ymin,ymax=min(v for _,v in gy),max(v for _,v in gy)
        if xmin<xmax and ymin<ymax:
            rows=[dict(label=label,direction='U',points_in=[(x,ymin,0),(x,ymax,0)]) for label,x in gx]
            rows += [dict(label=label,direction='V',points_in=[(xmin,y,0),(xmax,y,0)]) for label,y in gy]
            add_grid(rows,grid_basis)
    profiles={p['id']:p for p in physical.get('profiles',[])}
    materials={};material_source={m['id']:m for m in package['physical'].get('materials',[])}
    containment=defaultdict(list);material_products=defaultdict(list)
    origin=model.create_entity('IfcAxis2Placement3D',Location=model.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
    records={r['id']:r for r in package.get('design_records',[])}
    counts=dict(members=0,member_surfaces=0,reference_axes=0,panel_surfaces=0,panel_reference_boundaries=0,panel_opening_cuts=0,opening_references=0,connection_parts=0,connection_reference_parts=0,connection_references=0,unassigned_connection_parts=0,unassigned_elements=0)
    warnings=[];objects=[];unlocated_connections=[];property_pool={};mesh_templates={}
    member_objects={};panel_objects={};relationship_manifest=[]
    identity_mapping=model.create_entity('IfcCartesianTransformationOperator3D',LocalOrigin=origin.Location,Scale=1.)
    def add(cls,item,faces=(),lines=(),key=None,face_holes=(),local_frame=None):
        key=key or item['id'];obj=entity(cls,item.get('mark') or item['id'],key)
        obj.Description=item.get('description') or item.get('kind') or basis
        obj.ObjectPlacement=model.create_entity('IfcLocalPlacement',RelativePlacement=origin)
        connection_part=item.get('connection_id') is not None
        containment[level_of(item)].append(obj)
        if level_of(item) is None:counts['unassigned_elements']+=1
        if faces:
            vertices=[];indices=[];holes=[];lookup={}
            # Repeated members/parts share a local mesh. Only their recorded
            # translations differ; no rotation, rounding of source placement or
            # change to the section geometry is inferred.
            translation=tuple(float(v)*INCH for v in faces[0][0])
            def index_ring(face):
                row=[]
                for p in face:
                    point=tuple(round(float(v)*INCH-translation[i],9) for i,v in enumerate(p))
                    if point not in lookup:lookup[point]=len(vertices);vertices.append(point)
                    row.append(lookup[point])
                return row
            for i,face in enumerate(faces):
                row=index_ring(face)
                if len(set(row))>=3:
                    indices.append(row)
                    holes.append([index_ring(ring) for ring in face_holes[i]] if face_holes else [])
            token=(tuple(vertices),tuple(tuple(row) for row in indices),tuple(tuple(tuple(r) for r in rings) for rings in holes))
            if token not in mesh_templates:
                if any(holes):
                    points=model.create_entity('IfcCartesianPointList3D',CoordList=vertices)
                    polygons=[]
                    for row,rings in zip(indices,holes):
                        boundary=tuple(i+1 for i in row)
                        polygons.append(model.create_entity('IfcIndexedPolygonalFaceWithVoids',CoordIndex=boundary,InnerCoordIndices=[tuple(i+1 for i in r) for r in rings]) if rings else model.create_entity('IfcIndexedPolygonalFace',CoordIndex=boundary))
                    mesh=model.create_entity('IfcPolygonalFaceSet',Coordinates=points,Closed=False,Faces=polygons)
                    template=model.create_entity('IfcShapeRepresentation',ContextOfItems=body_context,RepresentationIdentifier='Body',RepresentationType='Tessellation',Items=[mesh])
                else:
                    template=ifcopenshell.api.geometry.add_mesh_representation(model,context=body_context,vertices=[vertices],faces=[indices])
                mesh_templates[token]=model.create_entity('IfcRepresentationMap',MappingOrigin=origin,MappedRepresentation=template)
            mapped=model.create_entity('IfcMappedItem',MappingSource=mesh_templates[token],MappingTarget=identity_mapping)
            rep=model.create_entity('IfcShapeRepresentation',ContextOfItems=body_context,RepresentationIdentifier='Body',RepresentationType='MappedRepresentation',Items=[mapped])
            if local_frame:
                placement=bim_assemblies.transformed([v/INCH for v in translation],local_frame)
                rotation=dict(Axis=model.create_entity('IfcDirection',DirectionRatios=tuple(float(v) for v in bim_assemblies.cross(local_frame['x_axis'],local_frame['y_axis']))),RefDirection=model.create_entity('IfcDirection',DirectionRatios=tuple(float(v) for v in local_frame['x_axis'])))
                translation=tuple(v*INCH for v in placement)
            else:rotation={}
            obj.ObjectPlacement=model.create_entity('IfcLocalPlacement',RelativePlacement=model.create_entity('IfcAxis2Placement3D',Location=model.create_entity('IfcCartesianPoint',Coordinates=translation),**rotation))
            ifcopenshell.api.geometry.assign_representation(model,product=obj,representation=rep)
        elif lines:
            curves=[model.create_entity('IfcPolyline',Points=[model.create_entity('IfcCartesianPoint',Coordinates=[float(v)*INCH for v in p]) for p in line]) for line in lines]
            geom=model.create_entity('IfcGeometricCurveSet',Elements=curves)
            rep=model.create_entity('IfcShapeRepresentation',ContextOfItems=body_context,RepresentationIdentifier='Body',RepresentationType='GeometricCurveSet',Items=[geom])
            ifcopenshell.api.geometry.assign_representation(model,product=obj,representation=rep)
        mat=item.get('material_id')
        if mat:
            if mat not in materials:
                spec=material_source.get(mat,{}).get('specification',mat)
                materials[mat]=ifcopenshell.api.material.add_material(model,name=str(spec))
            material_products[mat].append(obj)
        refs=item.get('design_record_ids',[])
        property_set(model,obj,dict(SourceId=item['id'],MemberMark=item.get('mark'),Section=item.get('profile_id'),
            Basis=item.get('basis',basis),Status=item.get('status',status),
            Geometry='design surfaces' if faces else 'reference axes only' if lines else 'reference metadata only',
            PhysicalDetails='TBD' if recovered else 'Design coordination; not fabrication geometry',
            SourceModelSHA256=state['source_model_sha256'],**revision_properties,
            SectionDefinition=profiles.get(item.get('profile_id')),ThicknessIn=item.get('thickness_in',item.get('thickness')),
            DetailReference=item.get('detail_ref'),PartParameters=item.get('parameters'),PartKind=item.get('kind') if item.get('geometry') else None,
            ConnectionId=item.get('connection_id'),JointId=item.get('joint_id'),ConnectedMembers=item.get('connected_member_ids'),
            ConnectedPanels=item.get('connected_panel_ids'),
            HostSourceId=item.get('host_id'),GeometryRole=item.get('geometry_role'),
            AppliedOpeningIds=item.get('applied_opening_ids'),OpeningCutInHost=item.get('opening_cut_in_host'),
            AnalysisIds=item.get('analysis_ids'),AnalysisSegments=item.get('analysis_segments'),
            SourceIFCGuid=item.get('source_ifc_guid'),
            SourceEntity=item,AssemblyTemplate=item.get('assembly_instance',{}).get('template_id'),
            SourceKind=item.get('kind'),SourceLevel=None if item.get('level_basis') else item.get('level'),AssignedLevel=item.get('level'),
            SourceStorey=item.get('storey'),LevelSourceField=item.get('level_source_field'),
            StoreyAssignment=item.get('level_basis') or ('source declared' if item.get('level') is not None else 'not supplied; contained in building'),
            DesignRecords=[records[r] for r in refs if r in records]),cache=property_pool)
        row=dict(source_id=item['id'],guid=obj.GlobalId,ifc_class=cls,geometry='surfaces' if faces else 'axes' if lines else 'metadata')
        if connection_part:row.update(connection_id=item['connection_id'],joint_id=item.get('joint_id'),source_level=item.get('level'))
        objects.append(row)
        return obj
    for m in members:
        faces=[]
        if not recovered:
            try:faces=member_faces(m,profiles)
            except (ValueError,KeyError,TypeError,ZeroDivisionError) as ex:warnings.append(dict(id=m['id'],message='Reference axis only: '+str(ex)[:160]))
        cls='IfcColumn' if m['kind'] in ('column','col','stud','post','endwall_post') else 'IfcBeam' if m['kind'] in ('beam','girder','joist','rafter','moment_beam') else 'IfcMember'
        member_objects[m['id']]=add(cls,m,faces,[m['axis']]);counts['members']+=1;counts['member_surfaces' if faces else 'reference_axes']+=1
    from .panel_geometry import panel_rings
    cut_openings=set()
    for p in panels:
        vertices=p.get('vertices',[])
        if len(vertices)>=3:
            kind=p.get('kind','').lower()
            cls='IfcWall' if 'wall' in kind else 'IfcSlab' if any(token in kind for token in ('floor','roof','slab','deck')) else 'IfcBuildingElementProxy'
            # Hosts are explicit. Legacy reviewed panels may list opening IDs;
            # an opening's own host_id takes precedence over that older link.
            related=[o for o in physical['openings'] if o.get('host_id')==p['id'] or (not o.get('host_id') and o['id'] in p.get('openings',[]))]
            rings,applied,findings=panel_rings(p,related)
            warnings.extend(findings);cut_openings.update(applied)
            if not rings:
                # A full-height/full-width opening has no remaining host mesh.
                # Keep its original boundary as an explicit reference, never a
                # filled wall over the opening or an invented residual strip.
                panel_objects[p['id']]=add('IfcAnnotation',dict(p,applied_opening_ids=applied,
                    geometry_role='source_panel_boundary_reference',
                    description='Panel fully removed by declared openings; original boundary reference only'),
                    lines=[vertices+[vertices[0]]],key='panel:'+p['id'])
                counts['panel_reference_boundaries']+=1;status='provisional'
                continue
            obj=add(cls,dict(p,applied_opening_ids=applied),[r['exterior'] for r in rings],key='panel:'+p['id'],face_holes=[r['holes'] for r in rings])
            panel_objects[p['id']]=obj
            if cls=='IfcBuildingElementProxy':obj.ObjectType='Coordination panel: '+kind
            counts['panel_surfaces']+=1
    counts['panel_opening_cuts']=len(cut_openings)
    panel_lookup={p['id']:p for p in panels}
    for opening in physical.get('openings',[]):
        vertices=opening['vertices'];host=panel_lookup.get(opening.get('host_id'),{})
        item=dict(opening,kind=opening.get('kind') or 'opening',geometry_role='source_opening_reference',
                  opening_cut_in_host=opening['id'] in cut_openings,
                  description='Source opening boundary; cut in declared host panel' if opening['id'] in cut_openings else 'Source opening boundary reference; no valid planar host cut')
        if item.get('level') is None and host.get('level') is not None:
            item['level']=host['level'];item['level_basis']='Inherited from host panel: '+str(host.get('level_basis') or 'source declared')
        obj=add('IfcAnnotation',item,lines=[vertices+[vertices[0]]],key='opening:'+opening['id'])
        if opening.get('host_id') in panel_objects:
            host=panel_objects[opening['host_id']]
            rel=relation('IfcRelAssignsToProduct','opening-host:'+opening['id'],Name='Declared opening boundary on host',RelatedObjects=[obj],RelatingProduct=host)
            relationship_manifest.append(dict(guid=rel.GlobalId,type=rel.is_a(),source=opening['id'],target=opening['host_id'],role='opening_host'))
        counts['opening_references']+=1
    joints={j['id']:j for j in physical.get('joints',[])}
    templates=bim_assemblies.index(physical);assembly_meshes={}
    counts['connection_assemblies']=0
    for c in connections:
        joint=joints.get(c.get('joint_id'),{})
        connected=set(c.get('member_ids',[])) | {e['member_id'] for e in joint.get('member_ends',[])+joint.get('attachments',[])}
        source_level=c['level'] if c.get('level') is not None else joint.get('level')
        level_source=c if c.get('level') is not None else joint
        if c.get('assembly_instance'):
            frame=c['assembly_instance'];template=templates[frame['template_id']]
            # Member and panel IDs have separate namespaces. Retain receiver
            # types even when a member and its concrete host share an ID.
            bound_panels=set()
            for receiver in template.get('receivers',[]):
                ident=frame.get('bindings',{}).get(receiver['id'])
                if ident is not None:
                    (bound_panels if receiver.get('kind')=='panel' else connected).add(ident)
            if template['id'] not in assembly_meshes:
                solids=[part_faces(p,profiles) for p in template['parts']]
                curves=[part_lines(p) for p in template['parts']]
                curves.extend([[line] for line in bim_bonds.reference_lines(template)])
                assembly_meshes[template['id']]=([f for fs in solids for f in fs],[line for ls in curves for line in ls],sum(bool(fs) for fs in solids),sum(bool(ls) for ls in curves))
            faces,lines,solid_count,curve_count=assembly_meshes[template['id']]
            item=dict(c,level=source_level,connection_id=c['id'],connected_member_ids=sorted(connected),connected_panel_ids=sorted(bound_panels),
                      description='Located connection assembly; individual component identities and selections are retained in its versioned template')
            located=[[bim_assemblies.transformed(p,frame) for p in line] for line in lines]
            if not faces and lines:
                # A welded joint may contain no additional solid: the actual
                # column and boxing plates are already exported as members.
                # Give the assembly its recorded weld/interface curves instead
                # of emitting an empty product plus an unattached-looking line.
                item['geometry_role']='assembly_weld_and_interface_curves'
                if template.get('bond_interfaces') and not template['parts']:
                    item.update(geometry_role='reinforcement_bond_reference',
                        description='Declared reinforcement bond reference; actual bars and concrete host are separate products. Development and capacity are not verified.')
            obj=add('IfcElementAssembly',item,faces,located if not faces else (),key='connection:'+c['id'],local_frame=frame)
            for mid in sorted(connected):
                if mid not in member_objects:raise ValueError('Connection references missing exported member: '+mid)
                rel=relation('IfcRelConnectsElements','connection:'+c['id']+':'+mid,Name='Declared structural connection',RelatingElement=obj,RelatedElement=member_objects[mid])
                relationship_manifest.append(dict(guid=rel.GlobalId,type=rel.is_a(),source=c['id'],target=mid,role='connection_member'))
            for pid in sorted(bound_panels):
                if pid not in panel_objects:raise ValueError('Connection references missing exported panel: '+pid)
                rel=relation('IfcRelConnectsElements','connection-panel:'+c['id']+':'+pid,Name='Declared connection host panel',RelatingElement=obj,RelatedElement=panel_objects[pid])
                relationship_manifest.append(dict(guid=rel.GlobalId,type=rel.is_a(),source=c['id'],target=pid,role='connection_panel'))
            if lines and faces:
                annotation=add('IfcAnnotation',dict(item,id=c['id']+':references',geometry_role='assembly_reference_curves'),lines=located,key='connection:'+c['id']+':references')
                rel=relation('IfcRelAssignsToProduct','connection-references:'+c['id'],Name='Assembly weld and interface references',RelatedObjects=[annotation],RelatingProduct=obj)
                relationship_manifest.append(dict(guid=rel.GlobalId,type=rel.is_a(),source=c['id']+':references',target=c['id'],role='assembly_references'))
            counts['connection_assemblies']+=1
            counts['connection_parts']+=solid_count
            counts['connection_reference_parts']+=curve_count
            if source_level is None:counts['unassigned_connection_parts']+=len(template['parts'])
            continue
        connected=sorted(connected)
        related=[member_objects[mid] for mid in connected if mid in member_objects]
        for i,part in enumerate(c.get('parts',[])):
            faces=part_faces(part,profiles);lines=part_lines(part)
            if not faces and not lines:warnings.append(dict(id=c['id'],message='Unsupported connection-part geometry'));continue
            kind=part.get('kind','plate');item=dict(part,level=source_level,design_record_ids=c.get('design_record_ids',[]),
                connection_id=c['id'],joint_id=c.get('joint_id'),connected_member_ids=connected)
            for field in ('storey','level_basis','level_source_field'):
                if field in level_source:item[field]=level_source[field]
            cls='IfcAnnotation' if lines else 'IfcMechanicalFastener' if kind in ('bolt','screw','anchor') else 'IfcPlate'
            if lines:item['description']='Connection reference only: '+kind+'; physical part set-out remains unspecified'
            related.append(add(cls,item,faces,lines,key='connection:'+c['id']+':'+str(i)))
            counts['connection_reference_parts' if lines else 'connection_parts']+=1
            if source_level is None:counts['unassigned_connection_parts']+=1
        if related:
            group=entity('IfcGroup',c['id'],'connection-group:'+c['id'])
            group.Description='Source connection occurrence and its participating members, parts and references'
            property_set(model,group,dict(SourceConnection=c),cache=property_pool)
            rel=relation('IfcRelAssignsToGroup','connection-group:'+c['id'],RelatedObjects=list(dict.fromkeys(related)),RelatingGroup=group)
            relationship_manifest.append(dict(guid=rel.GlobalId,type=rel.is_a(),source=c['id'],targets=[o.GlobalId for o in related],role='connection_group'))
        if not c.get('parts'):
            # Keep the complete declared reference, including design parameters,
            # storey and adopted-detail identity. No hardware placement is inferred.
            unlocated_connections.append(c)
            counts['connection_references']+=1
    for level,items in containment.items():
        ifcopenshell.api.spatial.assign_container(model,products=items,relating_structure=storeys.get(level,building))
    for material,items in material_products.items():
        ifcopenshell.api.material.assign_material(model,products=items,material=materials[material])
    property_set(model,project,dict(SourceModelSHA256=state['source_model_sha256'],**revision_properties,Basis=basis,
        SupplementProvenance=state.get('supplement_provenance'),
        SourceModule=state.get('source_module'),SourceJob=state.get('source_job'),
        SourceReadiness=source_validation['status'],SourceFindings=source_validation['findings'],GeometryWarnings=warnings,
        SourceFreshnessChecked=state.get('source_evidence',{}).get('source_freshness_checked',False),
        ReferenceSystem=reference or None,RequireConnectionParts=package.get('require_connection_parts',False),
        **({'SourceStatus':status} if structural else {'DrawingStatus':status}),
        OpenRequests=[dict(id=r['id'],proposal=r['proposal'],confirmed=r['confirmed']) for r in state['requests']],
        # Some saved designs (anchorage, hold-downs, schedules, etc.) have no
        # corresponding solid. Product-level properties alone would lose them.
        DesignRecords=package.get('design_records',[]),
        ConnectionSchedules=[r for r in package.get('design_records',[]) if r['table']=='connections'],
        UnlocatedConnectionReferences=unlocated_connections,Interfaces=package['physical'].get('interfaces',[]),
        AssemblyTemplates=physical.get('assemblies',[]),InformationDecisions=package.get('information'),SourceRelationships=relationship_manifest,
        SourceProfiles=physical.get('profiles',[]),SourceMaterials=physical.get('materials',[]),
        SourceJoints=physical.get('joints',[]),SourceCoverage=physical.get('coverage',{}),
        SourceAnalysisOnly=physical.get('analysis_only',[]),SourceRecordDispositions=physical.get('record_dispositions',[]),
        SourceJointDispositions=physical.get('joint_dispositions',[]),
        UnassignedConnectionParts=counts['unassigned_connection_parts'],
        UnassignedElements=counts['unassigned_elements'],
        SourceOpenings=physical.get('openings',[]),SourceOpeningCoordinateUnits='inch',
        Limits='Coordination surfaces omit rolled fillets and unmodelled member cuts. Panels are source surfaces with thickness properties; valid coplanar openings cut their explicitly declared hosts. Opening annotations retain all source boundaries. Unlocated assembly details are not placed at guessed joints.'))
    property_set(model,project,dict(Status=physical_checks['status'],Findings=physical_checks['findings'],
        StructuralDesignApproval=False,Limits=physical_checks['limits']),name='Steltic_PhysicalChecks')
    model.header.file_name.name=destination.name
    model.header.file_name.originating_system='Steltic openBIM 0.8.17'
    model.write(str(destination));errors=schema_errors(destination)
    if errors:raise ValueError('Generated IFC failed schema validation: '+str(errors[:3]))
    reopened=ifcopenshell.open(str(destination))
    if len(reopened.by_type('IfcElement'))+len(reopened.by_type('IfcAnnotation'))!=len(objects):raise ValueError('IFC round-trip product count changed')
    return dict(schema='IFC4',source=source,**({'physical_revision':state['revision'],'source_job':state['source_job'],'source_module':state['source_module']} if structural else {'drawing_revision':state['revision']}),source_sha256=state['source_model_sha256'],
        counts=counts,objects=objects,relationships=relationship_manifest,warnings=warnings,physical_checks=physical_checks,source_validation=source_validation,
        source_evidence=state.get('source_evidence'),source_status=status,schema_errors=errors,mesh_templates=len(mesh_templates),shared_property_values=len(property_pool),sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        limits=['Coordination IFC, not an editable Revit family library or a fabrication issue.',
                'Panels are surfaces; their thickness is metadata. Valid coplanar openings cut explicitly related host panels, with source boundaries retained as annotations. Members are not cut. Unconfirmed proposals remain request metadata.',
                'Unlocated connection assemblies are metadata only. Captured worklines remain reference axes where physical set-out is unknown.',
                'Connection reference polylines are annotations with source detail notes, not fabricated plate or weld solids.',
                'Objects without a source-declared storey remain contained in the building, with coordinates and parent-connection identity retained; they are not silently assigned to Level 1.'])


def export_import(source,destination,state):
    """Preserve the imported IFC graph and schema, adding traceable review information."""
    from .ifc_import import open_model
    model=open_model(source);project=model.by_type('IfcProject')[0]
    options=state.get('options',{});choice=options.get('units','auto')
    if choice!='auto':
        if choice in ('m','mm'):
            unit=ifcopenshell.api.unit.add_si_unit(model,unit_type='LENGTHUNIT',prefix='MILLI' if choice=='mm' else None)
        else:unit=ifcopenshell.api.unit.add_conversion_based_unit(model,name='foot' if choice=='ft' else 'inch')
        ifcopenshell.api.unit.assign_unit(model,units=[unit])
    property_set(model,project,dict(SourceSHA256=state['source_sha256'],ReviewRevision=state['revision'],
        ReviewStatus=state['status'],ReviewOptions=options,ReviewNote=state.get('review_note',''),
        Scope='Complete source IFC retained, including objects outside the preview selection.',StructuralAnalysis=False),name='Steltic_IFCReview')
    model.write(str(destination));errors=schema_errors(destination)
    return dict(schema=model.schema,source='ifc_import',source_sha256=state['source_sha256'],import_revision=state['revision'],
        counts=dict(products=len(model.by_type('IfcProduct'))),schema_errors=errors,warnings=[],
        sha256=hashlib.sha256(Path(destination).read_bytes()).hexdigest(),
        limits=['All original source objects retained; preview selection does not delete IFC objects.',
                'Explicit unit overrides change interpretation without rescaling coordinates or map-conversion metadata.',
                'Review notes do not establish structural adequacy. Source schema issues are reported without claiming to repair them.'])
