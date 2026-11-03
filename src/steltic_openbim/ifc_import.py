"""IFC inspection and geometry review. Never infers structural capacity or runs a solver."""
from collections import Counter
import hashlib
import json
import math

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as element_util
import ifcopenshell.util.placement as placement
import ifcopenshell.util.unit as units
import ifcopenshell.validate
import numpy as np

STRUCTURAL = {'IfcBeam','IfcColumn','IfcMember','IfcPlate','IfcSlab','IfcFooting','IfcPile',
              'IfcMechanicalFastener','IfcFastener','IfcElementAssembly','IfcStructuralCurveMember'}
MAX_PRODUCTS = 20000
MAX_TRIANGLES = 1500000


def open_model(path):
    try:
        model=ifcopenshell.open(str(path))
    except Exception as ex:
        raise ValueError('The file is not a readable IFC STEP model: '+str(ex)[:200]) from ex
    if model.schema not in ('IFC2X3','IFC4','IFC4X3'):
        raise ValueError('Supported IFC schemas: IFC2X3, IFC4 and IFC4X3')
    if not model.by_type('IfcProject'):raise ValueError('The IFC has no IfcProject')
    if len(model.by_type('IfcProduct'))>MAX_PRODUCTS:raise ValueError('This review supports up to 20,000 products; export a smaller discipline or building model')
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
        declared=element_util.get_psets(project).get('Steltic_PhysicalChecks',{})
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
    return dict(schema=model.schema,units=unit,storeys=storeys,products=rows,counts=dict(products=len(rows),
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
    return dict(scope=scope,units=unit,note=note,missing_data='TBD',structural_analysis=False)


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
    model=open_model(path);meta=metadata(model);options=review_options(options,meta)
    declared=meta['units']['scale_to_m'];scale=declared if options['units']=='auto' else {'m':1.,'mm':.001,'ft':.3048,'in':.0254}[options['units']]
    multiplier=scale/declared
    selected=[r for r in meta['products'] if options['scope']=='all' or r['structural']]
    if not selected:raise ValueError('The chosen scope contains no IFC products')
    settings=ifcopenshell.geom.settings();settings.set('use-world-coords',True)
    settings.set('mesher-linear-deflection',0.002)
    objects=[];failed=[];total=0;bounds=[];duplicates=[];shapes={}
    for row in selected:
        e=model.by_id(int(row['id']));verts=[];faces=[];lines=[];reason=''
        try:
            shape=ifcopenshell.geom.create_shape(settings,e)
            verts=(np.asarray(shape.geometry.verts).reshape((-1,3))*multiplier).tolist()
            faces=np.asarray(shape.geometry.faces,dtype=int).reshape((-1,3)).tolist()
            if not verts or not faces:raise ValueError('No surface geometry')
            if not all(math.isfinite(v) for p in verts for v in p):raise ValueError('Non-finite geometry')
            if total+len(faces)>MAX_TRIANGLES:raise ValueError('Review mesh limit reached; export a smaller model')
            total+=len(faces)
        except Exception as ex:
            verts=[];faces=[];reason=str(ex)[:200]
            lines=axis_lines(model,e,scale)
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
            displayed=len(objects),unrendered=len(failed),excluded_by_scope=len(meta['products'])-len(selected),triangles=total),
        limits=['Geometry and model-data review only; no structural analysis, capacity checks or code compliance assessment.',
                'Unknown materials, member sections and connection behaviour remain TBD. IFC does not guarantee an analytical model.'])
