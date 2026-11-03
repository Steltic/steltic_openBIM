"""IFC4 coordination export of the current, immutable drawing revision."""
from collections import defaultdict
import hashlib
import json
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

INCH=.0254


def property_set(model,product,values,name='Steltic_Coordination'):
    pset=ifcopenshell.api.pset.add_pset(model,product=product,name=name)
    clean={k:(json.dumps(v,ensure_ascii=True,sort_keys=True) if isinstance(v,(list,dict)) else v)
           for k,v in values.items() if v is not None}
    ifcopenshell.api.pset.edit_pset(model,pset=pset,properties=clean)


def schema_errors(path):
    logger=ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(str(path),logger)
    return [dict(message=r.get('message',''),attribute=r.get('attribute','')) for r in logger.statements if r.get('level')=='error']


def export_drawing(directory,destination):
    directory=Path(directory);destination=Path(destination)
    package=json.loads((directory/'source.json').read_text(encoding='utf-8'))
    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
    from .validation import inspect_package
    if inspect_package(package)['status']=='invalid':raise ValueError('The drawing source contains invalid physical data')
    if fingerprint(package)!=state['source_model_sha256']:raise ValueError('The drawing source fingerprint changed')
    recovered=state.get('representation')=='captured_source_worklines'
    if (directory/'design_model.json').is_file():
        physical=json.loads((directory/'design_model.json').read_text(encoding='utf-8'));basis='Adopted fictional design geometry'
    elif recovered:
        from .source_worklines import build
        physical=build(package);physical['profiles']=package['physical']['profiles'];basis='Captured reference axes; physical placement remains TBD'
    else:
        from .source_worklines import physical_view
        physical=physical_view(package);basis='Source-declared design coordination geometry'
    model=ifcopenshell.file(schema='IFC4')
    def entity(cls,label,key):
        obj=ifcopenshell.api.root.create_entity(model,ifc_class=cls,name=str(label))
        obj.GlobalId=ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL,'steltic:'+package['building_id']+':'+key).hex)
        return obj
    project=entity('IfcProject',package['building_id'],'project')
    metre=ifcopenshell.api.unit.add_si_unit(model,unit_type='LENGTHUNIT')
    ifcopenshell.api.unit.assign_unit(model,units=[metre])
    context=ifcopenshell.api.context.add_context(model,context_type='Model')
    body_context=ifcopenshell.api.context.add_context(model,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=context)
    site=entity('IfcSite','Site','site');building=entity('IfcBuilding',package['building_id'],'building')
    ifcopenshell.api.aggregate.assign_object(model,products=[site],relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model,products=[building],relating_object=site)
    members=physical.get('members',[]);panels=physical.get('panels',[]);connections=physical.get('connections',[])
    levels=sorted({int(m.get('level') or 1) for m in members+panels}) or [1]
    storeys={}
    for level in levels:
        s=entity('IfcBuildingStorey','Level '+str(level),'level:'+str(level))
        points=[p[2] for m in members if int(m.get('level') or 1)==level for p in m['axis']]
        # Storey elevation follows the source floor framing plane, not a moved member placement.
        floor=[p[2] for m in members if int(m.get('level') or 1)==level and abs(m['axis'][0][2]-m['axis'][1][2])<1e-6 for p in m['axis']]
        s.Elevation=(min(floor) if floor else min(points,default=0))*INCH
        ifcopenshell.api.aggregate.assign_object(model,products=[s],relating_object=building);storeys[level]=s
    profiles={p['id']:p for p in physical.get('profiles',[])}
    materials={};material_source={m['id']:m for m in package['physical'].get('materials',[])}
    containment=defaultdict(list);material_products=defaultdict(list)
    origin=model.create_entity('IfcAxis2Placement3D',Location=model.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
    records={r['id']:r for r in package.get('design_records',[])}
    counts=dict(members=0,member_surfaces=0,reference_axes=0,panel_surfaces=0,connection_parts=0,connection_reference_parts=0,connection_references=0)
    warnings=[];objects=[];unlocated_connections=[]
    def add(cls,item,faces=(),lines=(),key=None):
        key=key or item['id'];obj=entity(cls,item.get('mark') or item['id'],key)
        obj.Description=item.get('description') or item.get('kind') or basis
        obj.ObjectPlacement=model.create_entity('IfcLocalPlacement',RelativePlacement=origin)
        containment[int(item.get('level') or 1)].append(obj)
        if faces:
            vertices=[];indices=[];lookup={}
            for face in faces:
                row=[]
                for p in face:
                    point=tuple(float(v)*INCH for v in p)
                    if point not in lookup:lookup[point]=len(vertices);vertices.append(point)
                    row.append(lookup[point])
                if len(set(row))>=3:indices.append(row)
            rep=ifcopenshell.api.geometry.add_mesh_representation(model,context=body_context,vertices=[vertices],faces=[indices])
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
            Basis=item.get('basis',basis),Status=item.get('status',state['drawing_status']),
            Geometry='design surfaces' if faces else 'reference axes only' if lines else 'reference metadata only',
            PhysicalDetails='TBD' if recovered else 'Design coordination; not fabrication geometry',
            SourceModelSHA256=state['source_model_sha256'],DrawingRevision=state['revision'],
            SectionDefinition=profiles.get(item.get('profile_id')),ThicknessIn=item.get('thickness_in',item.get('thickness')),
            DetailReference=item.get('detail_ref'),PartParameters=item.get('parameters'),PartKind=item.get('kind') if item.get('geometry') else None,
            DesignRecords=[records[r] for r in refs if r in records]))
        objects.append(dict(source_id=item['id'],guid=obj.GlobalId,ifc_class=cls,geometry='surfaces' if faces else 'axes' if lines else 'metadata'))
        return obj
    for m in members:
        faces=[]
        if not recovered:
            try:faces=member_faces(m,profiles)
            except (ValueError,KeyError,TypeError,ZeroDivisionError) as ex:warnings.append(dict(id=m['id'],message='Reference axis only: '+str(ex)[:160]))
        cls='IfcColumn' if m['kind'] in ('column','col','stud','post','endwall_post') else 'IfcBeam' if m['kind'] in ('beam','girder','joist','rafter','moment_beam') else 'IfcMember'
        add(cls,m,faces,[m['axis']]);counts['members']+=1;counts['member_surfaces' if faces else 'reference_axes']+=1
    for p in panels:
        vertices=p.get('vertices',[])
        if len(vertices)>=3:
            add('IfcWall' if 'wall' in p.get('kind','') else 'IfcSlab',p,[vertices],key='panel:'+p['id']);counts['panel_surfaces']+=1
    for c in connections:
        for i,part in enumerate(c.get('parts',[])):
            faces=part_faces(part,profiles);lines=part_lines(part)
            if not faces and not lines:warnings.append(dict(id=c['id'],message='Unsupported connection-part geometry'));continue
            kind=part.get('kind','plate');item=dict(part,level=c.get('level',1),design_record_ids=c.get('design_record_ids',[]))
            cls='IfcAnnotation' if lines else 'IfcMechanicalFastener' if kind in ('bolt','screw','anchor') else 'IfcPlate'
            if lines:item['description']='Connection reference only: '+kind+'; physical part set-out remains unspecified'
            add(cls,item,faces,lines,key='connection:'+c['id']+':'+str(i))
            counts['connection_reference_parts' if lines else 'connection_parts']+=1
        if not c.get('parts'):
            unlocated_connections.append({k:c[k] for k in ('id','point','joint_id','member_ids','detail_ref','design_record_ids','basis') if k in c})
            counts['connection_references']+=1
    for level,items in containment.items():
        ifcopenshell.api.spatial.assign_container(model,products=items,relating_structure=storeys.get(level,storeys[levels[0]]))
    for material,items in material_products.items():
        ifcopenshell.api.material.assign_material(model,products=items,material=materials[material])
    property_set(model,project,dict(SourceModelSHA256=state['source_model_sha256'],DrawingRevision=state['revision'],Basis=basis,
        DrawingStatus=state['drawing_status'],OpenRequests=[dict(id=r['id'],proposal=r['proposal'],confirmed=r['confirmed']) for r in state['requests']],
        ConnectionSchedules=[r for r in package.get('design_records',[]) if r['table']=='connections'],
        UnlocatedConnectionReferences=unlocated_connections,Interfaces=package['physical'].get('interfaces',[]),
        Limits='Coordination surfaces omit rolled fillets and unmodelled cuts. Panels are source surfaces with thickness properties. Unconfirmed openings are not cut into geometry. Unlocated assembly details are not placed at guessed joints.'))
    model.header.file_name.name=destination.name
    model.header.file_name.originating_system='Steltic openBIM 0.8.3'
    model.write(str(destination));errors=schema_errors(destination)
    if errors:raise ValueError('Generated IFC failed schema validation: '+str(errors[:3]))
    reopened=ifcopenshell.open(str(destination))
    if len(reopened.by_type('IfcElement'))+len(reopened.by_type('IfcAnnotation'))!=len(objects):raise ValueError('IFC round-trip product count changed')
    return dict(schema='IFC4',source='steltic',drawing_revision=state['revision'],source_sha256=state['source_model_sha256'],
        counts=counts,objects=objects,warnings=warnings,schema_errors=errors,sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        limits=['Coordination IFC, not an editable Revit family library or a fabrication issue.',
                'Panels are surfaces; their thickness is metadata. Unconfirmed openings do not cut the model.',
                'Unlocated connection assemblies are metadata only. Captured worklines remain reference axes where physical set-out is unknown.',
                'Connection reference polylines are annotations with source detail notes, not fabricated plate or weld solids.'])


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
