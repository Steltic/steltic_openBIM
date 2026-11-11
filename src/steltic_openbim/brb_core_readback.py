"""Read core and casing separately from the actual finite steel sections in an IFC."""
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .joint_mesh_readback import TOL,plane_axes,unit


def inside_core(section):
    pieces=list(section.geoms) if section.geom_type=='MultiPolygon' else [section]
    shells=[p for p in pieces if p.geom_type=='Polygon' and len(p.interiors)==1]
    if len(shells)!=1 or len(pieces)!=2:
        raise ValueError('Expected a separate core inside one closed hollow casing')
    shell=shells[0]
    core=next(v for v in pieces if v is not shell)
    opening=Polygon(shell.interiors[0])
    if core.geom_type!='Polygon' or core.interiors or not opening.buffer(-TOL).covers(core):
        raise ValueError('BRB core intersects, touches or leaves the actual casing')
    return core,shell


def core_sections(mesh,area,yield_length):
    cuts=sorted(set(np.round(mesh.vertices[:,0],6)))
    yielding=[];rows=[];errors=[]
    for lo,hi in zip(cuts,cuts[1:]):
        if hi-lo<=TOL:continue
        samples=[]
        for fraction in (.12,.5,.88):
            station=lo+(hi-lo)*fraction
            section=mesh.section([1.,0.,0.],station,([0.,1.,0.],[0.,0.,1.]))
            try:
                core,casing=inside_core(section)
            except ValueError as exc:
                errors.append(str(exc));break
            samples.append(core)
        if len(samples)!=3:continue
        areas=[v.area for v in samples]
        tol=TOL*max(1.,max(p.length for p in samples))
        if min(areas)<area-tol:errors.append('Core section is smaller than the HR yielding area')
        constant=all(abs(a-area)<=tol for a in areas) and all(samples[0].symmetric_difference(q).area<=tol for q in samples[1:])
        rows.append(dict(start_in=lo,end_in=hi,area_range_in2=[min(areas),max(areas)],yielding=constant))
        if constant:
            if yielding and abs(yielding[-1][1]-lo)<=TOL:yielding[-1][1]=hi
            else:yielding.append([lo,hi])
    if len(yielding)!=1 or abs((yielding[0][1]-yielding[0][0])-yield_length)>TOL:
        errors.append('Continuous core length at the selected area differs from HR')
    return dict(required_core_area_in2=area,required_yielding_length_in=yield_length,
                measured_yielding_intervals_in=yielding,actual_intervals=rows),list(dict.fromkeys(errors))


def end_face(mesh,normal,station,axes):
    faces=[]
    for face in mesh.polygons:
        if max(abs(face@normal-station))>TOL:continue
        poly=Polygon(face@np.array(axes).T)
        if poly.is_valid and poly.area>TOL**2:faces.append(poly)
    return unary_union(faces)


def meets_axial_core(member,extension,axis,area):
    normal=unit(axis);axes=plane_axes(normal)
    m=member.vertices@normal;e=extension.vertices@normal
    ends=((min(m),max(e),1.),(max(m),min(e),-1.))
    station,tip,sign=min(ends,key=lambda row:abs(row[0]-row[1]))
    if abs(station-tip)>TOL:
        return dict(axial_gap_in=float(abs(station-tip))),['Supplier projection misses the actual core-end station']
    try:
        core,casing=inside_core(end_face(member,normal,station,axes))
    except ValueError as exc:
        return {},[str(exc)]
    end=end_face(extension,normal,station,axes)
    tol=TOL*max(1.,core.length,end.length)
    errors=[]
    if core.difference(end.buffer(TOL)).area>tol or core.area<area-tol:
        errors.append('Supplier end projection fails to cover its actual core end face')
    if not end.is_empty and (end.intersects(casing) or not Polygon(casing.interiors[0]).buffer(-TOL).covers(end)):
        errors.append('Supplier projection bears on the casing or leaves its clear opening')
    if end.is_empty:errors.append('Supplier projection has no terminal steel face')
    return dict(core_end_area_in2=float(core.area),contact_area_in2=float(core.intersection(end).area),
                casing_clearance_in=float(casing.distance(end)) if not end.is_empty else None),errors


def moving_head_clearance(meshes,axis,required,errors):
    if 'END-CAP' not in meshes:
        errors.append('Source-selected pin has no moving core head')
        return {}
    normal=unit(axis)
    shell=meshes['BRACE'].vertices@normal
    head=meshes['END-CAP'].vertices@normal
    gap=float(max(min(shell)-max(head),min(head)-max(shell)))
    if gap<=TOL or gap+TOL<required:
        errors.append('Moving head has insufficient actual axial clearance to the casing')
    return dict(measured_head_clearance_in=gap,required_stroke_in=required)
