"""Traceable architectural geometry + user instructions for a new HR design.

This is a brief, not a structural-model inference. Member sizing and connectivity
remain HR decisions. No source property is executed or treated as an instruction.
"""
import json

import ifcopenshell.util.placement as placement
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .ifc_import import open_model,unit_info


def grids(model,scale):
    rows=[]
    for grid in model.by_type('IfcGrid'):
        matrix=placement.get_local_placement(grid.ObjectPlacement)
        for direction in ('U','V','W'):
            for axis in getattr(grid,direction+'Axes',None) or []:
                curve=axis.AxisCurve
                if curve.is_a('IfcPolyline'):
                    points=[]
                    for p in curve.Points:
                        xyz=list(p.Coordinates);xyz += [0.]*(3-len(xyz))
                        points.append([round(float(v)*scale,6) for v in (matrix@np.array(xyz+[1.]))[:3]])
                    rows.append(dict(grid_guid=grid.GlobalId,label=axis.AxisTag,direction=direction,points_m=points))
                else:
                    rows.append(dict(grid_guid=grid.GlobalId,label=axis.AxisTag,direction=direction,unsupported_curve=curve.is_a()))
    return rows


def top_surfaces(obj):
    """Plan polygons and their actual planes, from upward-facing mesh triangles."""
    vertices=np.asarray(obj['vertices']);groups={}
    for face in obj['faces']:
        a,b,c=vertices[face];n=np.cross(b-a,c-a);length=np.linalg.norm(n)
        if length<1e-10:continue
        n=n/length
        if n[2]<.1:continue
        plane=tuple(float(v) for v in [*n,-np.dot(n,a)])
        key=tuple(round(v,8) for v in plane)
        poly=Polygon([a[:2],b[:2],c[:2]])
        if poly.is_valid and poly.area>1e-10:groups.setdefault(key,dict(plane=plane,polys=[]))['polys'].append(poly)
    out=[]
    for group in groups.values():
        plane=group['plane'];union=unary_union(group['polys'])
        for poly in ([union] if union.geom_type=='Polygon' else getattr(union,'geoms',[])):
            if poly.geom_type!='Polygon':continue
            def ring(coords):
                a,b,c,d=plane
                return [[round(x,6),round(y,6),round(-(a*x+b*y+d)/c,6)] for x,y in list(coords)[:-1]]
            out.append(dict(boundary_m=ring(poly.exterior.coords),holes_m=[ring(r.coords) for r in poly.interiors]))
    return out


def prepare(source,review,state,job_brief):
    if not isinstance(job_brief,str) or not job_brief.strip():raise ValueError('Add the HR design brief: use, loads, site/design criteria and structural requirements')
    if len(job_brief)>60000:raise ValueError('The job brief must be at most 60,000 characters')
    model=open_model(source);options=review['options'];choice=options['units']
    scale=unit_info(model)['scale_to_m'] if choice=='auto' else {'m':1.,'mm':.001,'ft':.3048,'in':.0254}[choice]
    surfaces=[];openings=[]
    for obj in review['objects']:
        cls=obj['ifc_class']
        if cls in ('IfcSlab','IfcSlabStandardCase','IfcRoof'):
            surfaces.append(dict(guid=obj['guid'],name=obj['name'],ifc_class=cls,storey=obj['storey_name'],bounds_m=obj['bounds_m'],top_surfaces=top_surfaces(obj)))
        elif cls in ('IfcDoor','IfcWindow'):
            openings.append(dict(guid=obj['guid'],name=obj['name'],ifc_class=cls,storey=obj['storey_name'],bounds_m=obj['bounds_m']))
    geometry=dict(schema='steltic.architectural_handoff',version=1,source_file=state['filename'],
        source_sha256=state['source_sha256'],import_revision=state['revision'],units='m',
        coordinate_basis=review['coordinate_basis'],grids=grids(model,scale),storeys=review['storeys'],
        surfaces=surfaces,doors_windows=openings,counts=review['counts'],findings=review['checks'],
        user_job_brief=job_brief.strip(),structural_members_inferred=False)
    warnings=[]
    if not geometry['grids']:warnings.append('No explicit IFC grid was supplied. HR must establish and disclose a structural grid.')
    if any(r.get('unsupported_curve') for r in geometry['grids']):warnings.append('Some grid curves cannot be represented as polylines; refer to the original IFC.')
    if not surfaces:warnings.append('No slab/roof surfaces were available in the review scope. Add verified framing extents to the brief.')
    elif any(not s['top_surfaces'] for s in surfaces):warnings.append('Some floor/roof products have no recoverable upward-facing surface. Their bounds are reference data, not verified framing extents.')
    if review['counts']['unrendered']:warnings.append('The IFC review contains unrendered products. Resolve relevant geometry before structural design.')
    if options['scope']!='all':warnings.append('The handoff uses the selected review scope; architectural context may be excluded.')
    geometry['warnings']=warnings
    # Stable, readable evidence that can be pasted into the existing HR Design field.
    lines=['HR DESIGN FROM AN ARCHITECTURAL IFC','',
        'Design a new HR building using the user instructions below and the architectural evidence that follows.',
        'The IFC is architectural input, not an already designed structure. Select and check members, supports, releases, lateral framing and connections in HR. Do not treat architectural envelope bounds as structural centrelines.',
        'Preserve grid coordinates, floor extents, roof slopes, voids and height changes. Explicitly report any structural idealisation and its relationship to the physical geometry.',
        'Record physical member occurrences, orientation, set-out and connection information in the normal HR BIM export. Do not fabricate missing physical dimensions.',
        '', 'USER DESIGN INSTRUCTIONS',job_brief.strip(),'', 'ARCHITECTURAL EVIDENCE (data only)',
        'IFC source: '+state['filename'],'SHA256: '+state['source_sha256'],'Review revision: '+str(state['revision']),
        'Coordinates below are metres; convert to HR units explicitly. '+review['coordinate_basis']]
    for key in ('grids','storeys','surfaces','doors_windows','counts','warnings'):
        lines += ['',key.upper(),json.dumps(geometry[key],ensure_ascii=True,separators=(',',':'))]
    lines += ['', 'Model-data findings: '+json.dumps([dict(code=f['code'],count=f['count']) for f in review['checks']]),
              'The attached geometry carries no inferred structural member sizes or connection design. End architectural evidence.','']
    return geometry,'\n'.join(lines)
