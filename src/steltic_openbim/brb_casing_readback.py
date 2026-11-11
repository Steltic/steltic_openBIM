"""Measure casing steel, restraint infill and the unbonded core in actual IFC faces."""
from collections import Counter
import re

import numpy as np
from shapely.geometry import MultiPoint, Polygon

from .joint_mesh_readback import Mesh, TOL, matches_rhs_extrusion
from .pin_stack_readback import actual_materials


def constituent_meshes(product, local):
    body=next(r for r in product.Representation.Representations if r.RepresentationIdentifier=='Body')
    if len(body.Items)!=1 or not body.Items[0].is_a('IfcMappedItem'):
        raise ValueError('The delivered BRB has no single located mapped body')
    source=body.Items[0].MappingSource
    mesh=source.MappedRepresentation.Items[0]
    lookup={f.id():i for i,f in enumerate(mesh.Faces)}
    found={};used=Counter()
    for aspect in source.HasShapeAspects:
        if aspect.Name in found or len(aspect.ShapeRepresentations)!=1:
            raise ValueError('BRB material shape aspect is ambiguous')
        shape=aspect.ShapeRepresentations[0]
        if len(shape.Items)!=1 or not shape.Items[0].is_a('IfcPolygonalFaceSet'):
            raise ValueError('BRB material shape aspect has no measured faces')
        group=shape.Items[0]
        if group.Coordinates!=mesh.Coordinates or any(f.id() not in lookup for f in group.Faces):
            raise ValueError('BRB material is assigned to faces outside the delivered body')
        indices=[lookup[f.id()] for f in group.Faces]
        used.update(indices)
        faces=tuple(local.faces[i] for i in indices)
        verts=sorted({k for f in faces for k in f}); remap={k:i for i,k in enumerate(verts)}
        found[aspect.Name]=Mesh(local.vertices[verts],tuple(tuple(remap[k] for k in f) for f in faces))
    if used!=Counter(range(len(mesh.Faces))) or len(mesh.Faces)!=len(local.faces):
        raise ValueError('Actual BRB body faces lack exclusive material ownership')
    if any(not m.closed for m in found.values()):
        raise ValueError('Actual BRB material region has an open shell')
    return found


def material_name(value):
    return re.sub(r'\s+',' ',str(value).lower().replace('astm ','').replace('grade ','gr ').replace('gr. ','gr ')).strip()


def measured_section(mesh,at):
    return mesh.section([1.,0.,0.],at,([0.,1.,0.],[0.,0.,1.]))


def check(product,local,source,profile,length):
    from .brb_casing import hss_dimensions
    try:
        regions=constituent_meshes(product,local)
    except (ValueError,StopIteration,AttributeError,IndexError,KeyError) as exc:
        return {},['Actual casing constituent geometry: '+str(exc)]
    assigned=actual_materials(product);issues=[]
    sets=[rel.RelatingMaterial for rel in product.HasAssociations if rel.is_a('IfcRelAssociatesMaterial') and
          rel.RelatingMaterial.is_a('IfcMaterialConstituentSet')]
    if len(sets)!=1 or len(sets[0].MaterialConstituents)!=len(regions) or set(assigned)!=set(regions):
        issues.append('IFC constituent materials and their actual shape aspects differ')
    casing=regions.get('MAIN');core=regions.get('YIELDING-CORE')
    if casing is None or core is None:
        return {},issues+['Casing steel or yielding core is missing from its actual material region']
    if material_name(assigned.get('MAIN'))!=material_name(source['material']):
        issues.append('Actual BRB casing material differs from the selected grade or supplier delegation')
    dims=hss_dimensions(source['section']) if source.get('section') else profile['dimensions']
    geometry=dict(axis=[1.,0.,0.],local_y=[0.,1.,0.],origin=[0.,0.,0.],length=length)
    if not matches_rhs_extrusion(casing,geometry,dims):
        issues.append('Finite actual casing outer dimensions, walls or hollow region differ')
    changes={round(float(x),6) for group in regions.values() for x in group.vertices[:,0]}
    yzm=MultiPoint(core.vertices[:,1:]).convex_hull
    mortar=regions.get('MORTAR-INFILL')
    if source.get('infill_material'):
        if mortar is None:return {},issues+['Selected mortar infill is absent from the actual IFC body']
        if material_name(assigned.get('MORTAR-INFILL'))!=material_name(source['infill_material']):
            issues.append('Actual casing infill material differs from the source')
        if abs(mortar.vertices[:,0].min())>TOL or abs(mortar.vertices[:,0].max()-length)>TOL:
            issues.append('Casing infill does not span its finite restraint')
    gaps=[];actual_dims=None
    ordered=sorted(changes)
    for lo,hi in zip(ordered,ordered[1:]):
        if hi-lo<=TOL:continue
        station=(lo+hi)/2
        steel=measured_section(casing,station)
        if steel.geom_type!='Polygon' or len(steel.interiors)!=1:
            issues.append('Actual casing does not have one continuous hollow interior');continue
        hole=Polygon(steel.interiors[0]);outer=steel.bounds;inner=hole.bounds
        actual_dims=dict(b=outer[2]-outer[0],h=outer[3]-outer[1],
                         walls_in=[inner[0]-outer[0],inner[1]-outer[1],outer[2]-inner[2],outer[3]-inner[3]])
        if mortar is not None:
            fill=measured_section(mortar,station)
            if fill.geom_type!='Polygon' or len(fill.interiors)!=1:
                issues.append('Mortar does not form one finite shell around a separate core opening');continue
            covered=Polygon(fill.exterior)
            if covered.symmetric_difference(hole).area>TOL*hole.length:
                issues.append('Mortar overlaps casing steel or fails to fill the casing interior')
            hole=Polygon(fill.interiors[0])
        if not hole.buffer(-TOL).covers(yzm):
            issues.append('Fixed restraint intrudes into the swept moving-core envelope')
        else:gaps.append(float(hole.boundary.distance(yzm)))
    return dict(section=source.get('section'),design_mode=source.get('design_mode'),actual_casing_material=assigned.get('MAIN'),
                actual_casing_dimensions=actual_dims,actual_infill_material=assigned.get('MORTAR-INFILL'),
                minimum_transverse_core_clearance_in=min(gaps,default=None)),list(dict.fromkeys(issues))
