"""IFC inspection and geometry review. Never infers structural capacity or runs a solver."""
from collections import Counter
import hashlib
import json
import math
import os

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as element_util
import ifcopenshell.util.placement as placement
import ifcopenshell.util.unit as units
import ifcopenshell.validate
import numpy as np

STRUCTURAL = {'IfcBeam','IfcColumn','IfcMember','IfcPlate','IfcSlab','IfcFooting','IfcPile',
              'IfcMechanicalFastener','IfcFastener','IfcElementAssembly','IfcStructuralCurveMember'}
MAX_PRODUCTS = 100000
MAX_TRIANGLES = 6000000
REVIEW_GROUP_SIZE = 1000
GEOMETRY_THREADS = min(4, os.cpu_count() or 1)


def open_model(path):
    try:
        model=ifcopenshell.open(str(path))
    except Exception as ex:
        raise ValueError('The file is not a readable IFC STEP model: '+str(ex)[:200]) from ex
    if model.schema not in ('IFC2X3','IFC4','IFC4X3'):
        raise ValueError('Supported IFC schemas: IFC2X3, IFC4 and IFC4X3')
    if not model.by_type('IfcProject'):raise ValueError('The IFC has no IfcProject')
    if len(model.by_type('IfcProduct'))>MAX_PRODUCTS:raise ValueError(f'This review supports up to {MAX_PRODUCTS:,} products; export a smaller discipline or building model')
    return model


def products(model):
    return [e for e in model.by_type('IfcProduct') if (not e.is_a('IfcSpatialStructureElement') or e.is_a('IfcSpace'))
            and not e.is_a('IfcOpeningElement') and not e.is_a('IfcGrid') and not e.is_a('IfcPort')]


def unit_info(model):
    length=units.get_project_unit(model,'LENGTHUNIT')
    if not length:return dict(known=False,name='Not declared',scale_to_m=1.)
    scale=float(units.calculate_unit_scale(model))
    if not math.isfinite(scale) or scale<=0:raise ValueError('Invalid IFC length unit')
    return dict(known=True,name=((getattr(length,'Prefix',None) or '')+' '+str(length.Name)).strip(),scale_to_m=scale)


def declared_readiness(properties):
    """Display exported completeness evidence without treating it as a new check."""
    if not any(k in properties for k in ('SourceReadiness','SourceFindings','GeometryWarnings')):return []
    provenance='Steltic_Coordination in source IFC; not independently recomputed by import'
    try:
        rows=json.loads(properties.get('SourceFindings','[]'))
        if not isinstance(rows,list):raise ValueError('Expected a list')
        for row in rows:
            if (not isinstance(row,dict) or not isinstance(row.get('code'),str) or not isinstance(row.get('message'),str)
                    or row.get('severity') not in ('needs_input','error') or not isinstance(row.get('entity_ids',[]),list)
                    or any(not isinstance(value,str) for value in row.get('entity_ids',[]))):
                raise ValueError('Invalid source finding')
        result=[dict(code='declared_source_'+row['code'],title='Exported source information: '+row['message'],
                     count=max(1,len(row.get('entity_ids',[]))),source_entity_ids=row.get('entity_ids',[]),
                     severity=row['severity'],provenance=provenance) for row in rows]
        status=properties.get('SourceReadiness')
        if status not in (None,'ready','needs_input','invalid'):raise ValueError('Unknown source readiness')
        if status in ('needs_input','invalid') and not result:
            result.append(dict(code='declared_source_incomplete',title='Exported source reports incomplete physical data',count=1,provenance=provenance))
        warnings=json.loads(properties.get('GeometryWarnings','[]'))
        if not isinstance(warnings,list):raise ValueError('Expected a warning list')
        for warning in warnings:
            if not isinstance(warning,dict) or not isinstance(warning.get('message'),str):raise ValueError('Invalid geometry warning')
            identifiers=list(dict.fromkeys(warning[k] for k in ('id','host_id') if isinstance(warning.get(k),str)))
            result.append(dict(code='declared_geometry_warning',title='Exported geometry warning: '+warning['message'],
                               count=1,source_entity_ids=identifiers,provenance=provenance))
        return result
    except (ValueError,TypeError):
        return [dict(code='source_readiness_unreadable',title='Exported source-readiness metadata could not be read',count=1,provenance=provenance)]


def metadata(model):
    unit=unit_info(model);rows=[];storeys=[]
    for s in model.by_type('IfcBuildingStorey'):
        matrix=placement.get_local_placement(s.ObjectPlacement)
        z=float(matrix[2,3] if s.ObjectPlacement else s.Elevation or 0)*unit['scale_to_m']
        storeys.append(dict(id=s.GlobalId,name=s.Name or s.GlobalId,elevation_m=z))
    for e in products(model):
        container=element_util.get_container(e,ifc_class='IfcBuildingStorey')
        if e.is_a('IfcSpace') and container is None:
            parent=element_util.get_aggregate(e)
            while parent and not parent.is_a('IfcBuildingStorey'):parent=element_util.get_aggregate(parent)
            container=parent
        spatial=element_util.get_container(e)
        kind=element_util.get_type(e)
        mats=element_util.get_materials(e)
        profiles=[]
        for start in (getattr(e,'Representation',None),element_util.get_material(e)):
            if start:
                profiles += [x.ProfileName or x.is_a() for x in model.traverse(start) if x.is_a('IfcProfileDef')]
        props=element_util.get_psets(e)
        bearing_wall=e.is_a('IfcWall') and props.get('Pset_WallCommon',{}).get('LoadBearing') is True
        if not profiles:
            profiles=[str(v) for p in props.values() if isinstance(p,dict) for k,v in p.items()
                      if k.lower() in ('section','sectionname','profile','profile_id') and v]
        rows.append(dict(id=str(e.id()),guid=e.GlobalId,ifc_class=e.is_a(),name=e.Name or '',
            type_name=kind.Name if kind else '',storey=container.GlobalId if container else None,
            storey_name=container.Name if container else 'Unassigned',spatial_container=spatial.Name if spatial else None,materials=sorted({m.Name for m in mats if m.Name}),
            sections=sorted(set(profiles)),has_representation=bool(getattr(e,'Representation',None)),
            structural=bearing_wall or any(e.is_a(cls) for cls in STRUCTURAL),linear_structural=any(e.is_a(cls) for cls in ('IfcBeam','IfcColumn','IfcMember')),properties=props))
    ids=Counter(r['guid'] for r in rows)
    problems=[]
    def finding(code,title,items):
        if items:problems.append(dict(code=code,title=title,count=len(items),element_ids=items))
    finding('missing_geometry','Products without a geometric representation',[r['id'] for r in rows if not r['has_representation']])
    finding('missing_storey','Products without an assigned building storey',[r['id'] for r in rows if not r['storey']])
    finding('missing_material','Structural products without materials',[r['id'] for r in rows if r['structural'] and not r['materials']])
    finding('missing_section','Linear structural products without a section definition',[r['id'] for r in rows if r['linear_structural'] and not r['sections']])
    finding('missing_global_id','Products without a GlobalId',[r['id'] for r in rows if not r['guid']])
    finding('duplicate_global_id','Duplicate GlobalIds',[r['id'] for r in rows if ids[r['guid']]>1])
    for project in model.by_type('IfcProject'):
        project_properties=element_util.get_psets(project)
        problems.extend(declared_readiness(project_properties.get('Steltic_Coordination',{})))
        declared=project_properties.get('Steltic_PhysicalChecks',{})
        if not declared:
            continue
        try:
            source_findings=json.loads(declared.get('Findings','[]'))
            if not isinstance(source_findings,list):raise ValueError('Expected a list')
            for row in source_findings:
                if not isinstance(row,dict) or not isinstance(row.get('title'),str) or type(row.get('count')) is not int or row['count']<0:
                    raise ValueError('Invalid finding')
            for row in source_findings:
                problems.append(dict(code='declared_'+str(row.get('code','physical_finding')),
                    title='Exported source check: '+row['title'],count=row['count'],
                    provenance='Steltic_PhysicalChecks in source IFC; not independently recomputed by import'))
        except (ValueError,TypeError):
            problems.append(dict(code='physical_checks_unreadable',title='Source physical-check metadata could not be read',count=1))
    logger=ifcopenshell.validate.json_logger();ifcopenshell.validate.validate(model,logger)
    errors=[r for r in logger.statements if r.get('level')=='error']
    if errors:problems.append(dict(code='ifc_schema',title='IFC schema findings',count=len(errors),messages=[r.get('message','')[:300] for r in errors[:100]]))
    return dict(schema=model.schema,units=unit,storeys=storeys,products=rows,review_group_size=REVIEW_GROUP_SIZE,counts=dict(products=len(rows),
        structural=sum(r['structural'] for r in rows),classes=dict(Counter(r['ifc_class'] for r in rows))),findings=problems,
        questions=[dict(id='scope',question='Which objects should the review model include?',proposal='all',options=['all','structural'],
                        explanation='Keep the complete architectural context, or show structural IFC classes only. No class is silently reclassified.'),
                   dict(id='units',question='Which length units should the review use?',proposal='auto' if unit['known'] else '',
                        options=['auto','m','mm','ft','in'],explanation='Use the declared IFC units. If they are absent, choose units explicitly before building.'),
                   dict(id='missing_data',question='How should missing model data be handled?',proposal='Keep the supplied geometry; identify missing information as TBD.',
                        explanation='Materials, sections, supports, loads and connection behaviour are not invented. This step performs model-data review, not structural analysis.')])


def review_options(raw,meta):
    if not isinstance(raw,dict):raise ValueError('Provide review options as an object')
    scope=raw.get('scope','all');unit=raw.get('units','auto');note=raw.get('note','')
    if scope not in ('all','structural'):raise ValueError('Choose all or structural objects')
    if unit not in ('auto','m','mm','ft','in'):raise ValueError('Choose a supported length unit')
    if unit=='auto' and not meta['units']['known']:raise ValueError('The IFC has no length unit; explicitly choose one before building')
    if not isinstance(note,str) or len(note)>5000:raise ValueError('Review notes must be at most 5,000 characters')
    storey=raw.get('storey','all')
    if not isinstance(storey,str) or storey not in {'all','unassigned',*(s['id'] for s in meta.get('storeys',[]))}:
        raise ValueError('Choose all storeys, unassigned products, or a storey from this IFC')
    group=raw.get('group','all')
    if group!='all' and (type(group) is not int or group<1):raise ValueError('Choose all objects or a numbered review group')
    result=dict(scope=scope,storey=storey,group=group,units=unit,note=note,missing_data='TBD',structural_analysis=False)
    if group!='all' and group>math.ceil(len(_selected_products(meta,result))/REVIEW_GROUP_SIZE):
        raise ValueError('The review group is outside the selected objects')
    return result


def _selected_products(meta,options):
    return [r for r in meta['products'] if (options['scope']=='all' or r['structural'])
            and (options['storey']=='all' or r['storey']==(None if options['storey']=='unassigned' else options['storey']))]


def axis_lines(model,e,scale,identifiers=('Axis','Body','Annotation')):
    """Fallback for explicit polylines; never manufacture an axis from a bounding box."""
    lines=[];rep=getattr(e,'Representation',None)
    if not rep:return lines
    matrix=placement.get_local_placement(e.ObjectPlacement)
    for representation in rep.Representations:
        if representation.RepresentationIdentifier not in identifiers:continue
        for item in representation.Items:
            curves=item.Elements if item.is_a('IfcGeometricCurveSet') else [item]
            for curve in curves:
                if not curve.is_a('IfcPolyline'):continue
                points=[]
                for point in curve.Points:
                    coords=list(point.Coordinates);coords += [0.]*(3-len(coords))
                    points.append(((matrix@np.array(coords+[1.]))[:3]*scale).tolist())
                lines.extend([[a,b] for a,b in zip(points,points[1:])])
    return lines


def build_review(path,options):
    model=open_model(path);meta=metadata(model)
    return _build_review(model,meta,options)


def iter_storey_reviews(path,options):
    """Review every selected product in bounded, disjoint storey batches.

    The source model and inspection are shared, but callers consume one review
    at a time. The usual per-review geometry limit remains in force. No product
    is silently assigned a storey, and unassigned objects form their own batch.
    """
    model=open_model(path);meta=metadata(model);options=review_options(options,meta)
    if options['storey']!='all' or options['group']!='all':raise ValueError('The complete storey iterator requires all storeys and groups')
    present={r['storey'] for r in meta['products'] if options['scope']=='all' or r['structural']}
    for storey in sorted(present,key=lambda value:value or ''):
        selection=dict(options,storey=storey or 'unassigned')
        count=len(_selected_products(meta,selection));groups=math.ceil(count/REVIEW_GROUP_SIZE)
        for group in range(1,groups+1):
            yield _build_review(model,meta,dict(selection,group='all' if groups==1 else group))


def _build_review(model,meta,options):
    options=review_options(options,meta)
    declared=meta['units']['scale_to_m'];scale=declared if options['units']=='auto' else {'m':1.,'mm':.001,'ft':.3048,'in':.0254}[options['units']]
    multiplier=scale/declared
    selected=_selected_products(meta,options);group_count=math.ceil(len(selected)/REVIEW_GROUP_SIZE)
    if options['group']!='all':
        start=(options['group']-1)*REVIEW_GROUP_SIZE;selected=selected[start:start+REVIEW_GROUP_SIZE]
    if not selected:raise ValueError('The chosen scope contains no IFC products')
    settings=ifcopenshell.geom.settings();settings.set('use-world-coords',True)
    settings.set('mesher-linear-deflection',0.002)
    # The native iterator batches shared representations and uses a bounded
    # number of geometry threads. Copy each result before advancing: native
    # iterator buffers do not belong to the published review model.
    def native_shapes():
        try:
            iterator=ifcopenshell.geom.iterator(settings,model,GEOMETRY_THREADS,
                include=[model.by_id(int(row['id'])) for row in selected])
            if iterator.initialize():
                while True:
                    yield iterator.get()
                    if not iterator.next():break
        except (RuntimeError,ValueError,TypeError):
            # Missing/unsupported products still take the per-product path
            # below; an iterator failure must never silently omit them.
            return
    def surfaces(shape):
        vertices=(np.asarray(shape.geometry.verts).reshape((-1,3))*multiplier).tolist()
        triangles=np.asarray(shape.geometry.faces,dtype=int).reshape((-1,3)).tolist()
        if not vertices or not triangles:raise ValueError('No surface geometry')
        if not all(math.isfinite(v) for p in vertices for v in p):raise ValueError('Non-finite geometry')
        return vertices,triangles
    geometry={};ambiguous=set();selected_ids={int(row['id']) for row in selected};budget=0
    for shape in native_shapes():
        ident=shape.id
        if ident not in selected_ids:raise ValueError('Geometry iterator returned an unselected product')
        if ident in ambiguous:continue
        if ident in geometry:
            # Preserve the old per-product interpretation if a source emits
            # multiple native results for the same product.
            budget-=len(geometry.pop(ident)[1]);ambiguous.add(ident);continue
        try:vertices,triangles=surfaces(shape)
        except (ValueError,TypeError):continue
        budget+=len(triangles)
        if budget>MAX_TRIANGLES:
            raise ValueError(f'Review exceeds {MAX_TRIANGLES:,} triangles; choose one storey or a numbered review group, or export a smaller model. The complete source IFC is retained.')
        geometry[ident]=(vertices,triangles)
    kernel=None
    objects=[];failed=[];total=0;bounds=[];duplicates=[];shapes={}
    for row in selected:
        e=model.by_id(int(row['id']));verts=[];faces=[];lines=[];reason=''
        try:
            cached=geometry.pop(e.id(),None)
            if cached is not None:verts,faces=cached
            else:
                if kernel is None:kernel=ifcopenshell.geom.kernel(settings,model)
                verts,faces=surfaces(kernel.create_shape(e))
        except Exception as ex:
            verts=[];faces=[];reason=str(ex)[:200]
            lines=axis_lines(model,e,scale)
        # A resource limit is a failed build, not a per-product meshing error.
        # Never publish a partial model or silently replace solids with axes.
        if total+len(faces)>MAX_TRIANGLES:
            raise ValueError(f'Review exceeds {MAX_TRIANGLES:,} triangles; choose one storey or a numbered review group, or export a smaller model. The complete source IFC is retained.')
        total+=len(faces)
        points=verts or [p for line in lines for p in line]
        if points:
            bb=[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)];bounds.append(bb)
            if faces:
                digest=hashlib.sha256(np.round(np.asarray(verts),6).tobytes()+np.asarray(faces,dtype=np.int64).tobytes()).hexdigest()
                if digest in shapes:duplicates.append([shapes[digest],row['id']])
                shapes[digest]=row['id']
            objects.append(dict(row,vertices=verts,faces=faces,lines=lines,bounds_m=bb,representation='surfaces' if faces else 'reference_axes'))
        else:failed.append(dict(id=row['id'],guid=row['guid'],name=row['name'],reason=reason or 'No supported geometry'))
    if not objects:raise ValueError('No displayable geometry in this scope. Check the IFC export settings or choose all objects.')
    bb=[[min(b[i][0] for b in bounds),max(b[i][1] for b in bounds)] for i in range(3)]
    checks=list(meta['findings'])
    if failed:checks.append(dict(code='unrendered',title='Products that could not be displayed',count=len(failed),element_ids=[r['id'] for r in failed]))
    if duplicates:checks.append(dict(code='coincident_geometry',title='Identical coincident geometry; review possible duplicates',count=len(duplicates),pairs=duplicates))
    return dict(schema='steltic.ifc_review',ifc_schema=meta['schema'],units='m',source_units=meta['units'],options=options,
        coordinate_basis='IFC product placements in the project coordinate system. Map-conversion metadata remains in the original IFC; it is not applied to the preview.',
        display_origin_m=[sum(v)/2 for v in bb],bounds_m=bb,storeys=[dict(s,elevation_m=s['elevation_m']*multiplier) for s in meta['storeys']],
        objects=objects,unrendered=failed,checks=checks,counts=dict(source_products=len(meta['products']),selected=len(selected),
            displayed=len(objects),unrendered=len(failed),excluded_by_scope=len(meta['products'])-len(selected),triangles=total,review_groups=group_count),
        limits=['Geometry and model-data review only; no structural analysis, capacity checks or code compliance assessment.',
                'Unknown materials, member sections and connection behaviour remain TBD. IFC does not guarantee an analytical model.'])
