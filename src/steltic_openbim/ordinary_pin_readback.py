"""Measure HR's composite pin eye and developed cheek attachments in the reopened STEP."""
from collections import Counter

import numpy as np
from shapely import union_all
from shapely.geometry import LineString, Point, Polygon

from .joint_mesh_readback import TOL, outer_polygon, unit
from .stack_section_readback import _line_spans


def measure(parts, meshes, paths, fields, brace_axis):
    """Use actual joint-local stock and weld trajectories. The brace axis points away from this end."""
    counts=Counter()
    findings=[]
    facts=[]
    def problem(message,**details):
        findings.append(dict(code='ordinary_pin_detail_differs',detail=message,**details))
    def value(role,name):
        values=set(fields.get((role,name),[]))
        if len(values)>1:
            raise ValueError('Competing source values for '+role+'.'+name)
        return next(iter(values),None)
    width=value('gusset','width_at_hole_in')
    extension=value('gusset','extension_in')
    if width is None and extension is None:
        return counts,findings,facts
    pins=[k for k,p in parts.items() if p['kind']=='pin']
    if len(pins)!=1 or pins[0] not in meshes:
        problem('Expected one finite pin through the primary and both cheeks',pins=pins)
        return counts,findings,facts
    pp=parts[pins[0]]['parameters']
    y=unit(pp['axis'])
    v=unit(brace_axis)
    if abs(y@v)>TOL:
        problem('The pin is not transverse to its bound brace')
        return counts,findings,facts
    n=unit(np.cross(v,y))
    pin_mesh=meshes[pins[0]]
    connected=set(parts[pins[0]]['connects'])
    cheeks=sorted(k for k in connected if k.upper().startswith('CHEEK'))
    outer=sorted(k for k in connected if k.upper().startswith('CLEVIS'))
    primary=connected-set(cheeks+outer)
    if len(cheeks)!=2 or len(outer)!=2 or len(primary)!=1:
        problem('The selected ordinary pin requires one main gusset, two face cheeks and two clevis plies',connected=sorted(connected))
        return counts,findings,facts
    main=primary.pop()
    if any(k not in meshes for k in connected):
        problem('A required pin-bearing plate cannot be located in the IFC',missing=sorted(connected-meshes.keys()))
        return counts,findings,facts
    position={k:(float(min(meshes[k].vertices@y)),float(max(meshes[k].vertices@y))) for k in connected}
    main_low,main_high=position[main]
    pin_mid=(main_low+main_high)/2
    shaft=pin_mesh.section(y,pin_mid,(v,n))
    if shaft.geom_type!='Polygon' or shaft.is_empty:
        problem('No finite shaft crosses the primary plate')
        return counts,findings,facts
    centre=np.asarray(shaft.centroid.coords[0])
    dia=value('pin','diameter_in')
    hole=value('pin_hole','diameter_in')
    if hole is None and dia is not None:
        clearance=value('pin_hole','clearance_in')
        if clearance is not None:hole=dia+clearance
    pin_radius=float(np.max(np.linalg.norm(np.asarray(shaft.exterior.coords)-centre,axis=1)))
    if dia is not None and abs(2*pin_radius-dia)>4*TOL:
        problem('Actual pin diameter differs from HR',actual_in=2*pin_radius,selected_in=dia)
    span=10000.
    sections={}
    for key in [main,*cheeks,*outer]:
        low,high=position[key]
        mesh=meshes[key]
        section=mesh.section(y,(low+high)/2,(v,n))
        if not mesh.closed or section.geom_type!='Polygon' or section.is_empty:
            problem('Pin-bearing steel is open, missing or disconnected',part=key)
            continue
        sections[key]=section
        bores=[Polygon(ring) for ring in section.interiors if Polygon(ring).covers(Point(centre))]
        if len(bores)!=1:
            problem('No single bore surrounds the actual pin',part=key)
            continue
        radii=np.linalg.norm(np.asarray(bores[0].exterior.coords)-centre,axis=1)
        actual_hole=2*float(max(radii))
        if ((hole is not None and np.max(np.abs(2*radii-hole))>4*TOL) or
                min(radii)+TOL<pin_radius or abs(float(max(radii)-min(radii)))>4*TOL):
            problem('The actual bore is eccentric, undersized or differs from HR',part=key,actual_in=actual_hole,selected_in=hole)
        counts['actual_ordinary_pin_plies']+=1
        if key in outer:
            continue
        gross=outer_polygon(section)
        cuts=_line_spans(gross,centre,[0.,1.],span)
        breadth=sum(abs(k) for k in cuts) if cuts else None
        if width is not None and (not cuts or max(abs(-cuts[0]-width/2),abs(cuts[1]-width/2))>4*TOL):
            problem('Width across the bore differs from the credited composite pin eye',part=key,actual_in=breadth,selected_in=width)
        lengths=[]
        for dy in (-actual_hole/2,0.,actual_hole/2):
            cut=_line_spans(gross,centre+[0.,dy],[1.,0.],span)
            lengths.append(None if not cut else cut[1]-actual_hole/2)
        if extension is not None and any(x is None or x+4*TOL<extension for x in lengths):
            problem('The source shear path from the bore edge is too short',part=key,actual_in=lengths,selected_in=extension)
        facts.append(dict(part=key,bearing_width_in=breadth,end_extensions_in=lengths,hole_diameter_in=actual_hole))
    thickness=value('cheek_plate','thickness_in')
    per_face=value('cheek_fillet','perimeter_each_in')
    leg=value('cheek_fillet','size_in')
    cheeks.sort(key=lambda k:position[k][0])
    outer.sort(key=lambda k:position[k][0])
    order=outer[:1]+cheeks[:1]+[main]+cheeks[1:]+outer[1:]
    if sorted(order,key=lambda k:position[k][0])!=order:
        problem('Physical pin stack order differs',ordered_parts=sorted(order,key=lambda k:position[k][0]))
    grip=value('pin','grip_in')
    moving_t=value('clevis_plate','thickness_in')
    air=value('clevis_plate','side_gap_in')
    stack_grip=position[outer[1]][1]-position[outer[0]][0]
    extents=pin_mesh.vertices@y
    if (min(extents)>position[outer[0]][0]+TOL or max(extents)<position[outer[1]][1]-TOL or
            (grip is not None and abs(grip-stack_grip)>TOL)):
        problem('Actual shaft or complete bearing grip differs from the selected assembly',actual_grip_in=stack_grip,selected_in=grip)
    for i,key in enumerate(outer):
        low,high=position[key]
        clearance=position[cheeks[0]][0]-high if i==0 else low-position[cheeks[1]][1]
        if (moving_t is not None and abs(high-low-moving_t)>TOL) or (air is not None and abs(clearance-air)>TOL):
            problem('Clevis thickness or individual air gap differs from HR pin flexure geometry',
                    part=key,actual_thickness_in=high-low,selected_thickness_in=moving_t,
                    actual_side_gap_in=clearance,selected_side_gap_in=air)
        facts.append(dict(part=key,actual_thickness_in=high-low,actual_side_gap_in=clearance))
    for i,key in enumerate(cheeks):
        low,high=position[key]
        face=main_low if i==0 else main_high
        if abs((high if i==0 else low)-face)>TOL or (thickness is not None and abs(high-low-thickness)>TOL):
            problem('Bearing cheek is detached or its thickness differs',part=key,thickness_in=high-low,primary_face_in=face)
        if per_face is None and leg is None:
            continue
        if main not in sections or key not in sections:
            continue
        stock=outer_polygon(sections[key])
        parent=sections[main]
        traces=[]
        for wid,p in parts.items():
            if p['kind']!='weld' or not {key,main}<=set(p.get('connects',[])):
                continue
            line=paths.get(wid)
            if line is None:
                problem('Cheek weld has no actual IFC reference',part=wid)
                continue
            par=p['parameters']
            actual_leg=par.get('size_in')
            if (par.get('weld_type','').lower()!='fillet' or actual_leg is None or
                    (leg is not None and abs(actual_leg-leg)>TOL)):
                problem('Cheek attachment weld leg or type differs from HR',part=wid,selected_leg_in=leg,actual_leg_in=actual_leg)
            if np.max(np.abs(line@y-face))>TOL:
                problem('Fillet does not lie on the common cheek and primary face',part=wid)
            path=LineString(np.column_stack((line@v,line@n)))
            if path.difference(stock.exterior.buffer(2*TOL)).length>4*TOL:
                problem('Fillet departs from the real cheek perimeter',part=wid)
            if actual_leg and actual_leg>0:
                toe=path.buffer(actual_leg,cap_style='flat').difference(stock)
                if toe.difference(parent.buffer(2*TOL)).area>4*TOL*max(1.,path.length):
                    problem('Cheek weld lacks primary steel under its fillet leg',part=wid)
            traces.append(path)
        unique=union_all(traces)
        total=sum(line.length for line in traces)
        if abs(total-unique.length)>4*TOL or not traces or (per_face is not None and abs(unique.length-per_face)>4*TOL):
            problem('Developed, nonduplicated fillet length on one cheek differs',part=key,actual_length_in=unique.length,selected_length_in=per_face)
        counts['actual_ordinary_cheek_weld_groups']+=1
        facts.append(dict(part=key,distinct_weld_length_in=unique.length,actual_paths=len(traces)))
    transfer=value('gusset','whitmore_effective_width_in')
    setback=value('gusset','whitmore_distance_beyond_cheek_in')
    support=[]
    for key,p in parts.items():
        logical=p.get('parameters',{}).get('source_weld_id',key)
        if key in paths and main in p.get('connects',[]) and logical in ('WGB','WGC'):
            support.append(LineString(np.column_stack((paths[key]@v,paths[key]@n))))
    if main in sections and transfer is not None and setback is not None and all(k in sections for k in cheeks):
        rear=[sections[k].bounds[0] for k in cheeks]
        s=min(rear)-setback
        d=centre[1]
        cut=_line_spans(outer_polygon(sections[main]),[s,d],[0.,1.],span)
        if not cut or min(-cut[0],cut[1])+4*TOL<transfer/2:
            problem('Full Whitmore section is missing at the selected distance behind the actual cheeks',
                    measured_sides_in=cut,selected_width_in=transfer,station_in=s)
        counts['actual_ordinary_whitmore_sections']+=1
        limit=value('gusset','thornton_length_in')
        distances=[]
        if limit is not None:
            boundary=union_all(support)
            for shift in (-transfer/2,0.,transfer/2):
                origin=Point(s,d+shift)
                ray=LineString([(s+TOL,d+shift),(s-span,d+shift)])
                hit=boundary.intersection(ray)
                distances.append(None if hit.is_empty else origin.distance(hit))
            if any(distance is None for distance in distances) or sum(distances)/3>limit+.05:
                problem('Three-ray Thornton length to the finite restraint differs from HR',
                        measured_rays_in=distances,selected_mean_limit_in=limit)
        facts.append(dict(part=main,whitmore_station_in=s,actual_whitmore_sides_in=cut,thornton_rays_in=distances))
    bar_t=value('gusset_edge_stiffener','thickness_in')
    bar_w=value('gusset_edge_stiffener','width_in')
    faces=value('gusset_edge_stiffener','faces')
    if bar_t is not None and bar_w is not None and main in sections:
        body=outer_polygon(sections[main])
        free=body.exterior.difference(union_all(support).buffer(4*TOL))
        by_face=[[],[]]
        for k,p in parts.items():
            par=p.get('parameters',{})
            if k not in meshes or not par.get('free_edge_bar') or par.get('source_primary_gusset')!=main:
                continue
            mesh=meshes[k]
            levels=mesh.vertices@y
            lo,hi=float(min(levels)),float(max(levels))
            side=0 if abs(hi-main_low)<abs(lo-main_high) else 1
            gap=abs(hi-main_low) if side==0 else abs(lo-main_high)
            material=mesh.section(y,(hi+lo)/2,(v,n))
            attaches=[wid for wid,pw in parts.items() if {k,main}<=set(pw.get('connects',[])) and wid in paths]
            if (not mesh.closed or gap>TOL or abs(hi-lo-bar_t)>TOL or material.is_empty or
                    material.intersection(body).area<TOL or not attaches):
                problem('A selected free-edge bar lacks the attached face, checked thickness or actual welds',part=k)
            by_face[side].append(material)
            counts['actual_ordinary_free_edge_bars']+=1
        for side,bars in enumerate(by_face):
            if not bars:
                if faces==2 or not any(by_face):
                    problem('Selected free-edge stiffening is absent on a primary gusset face',face=side)
                continue
            actual=union_all(bars)
            uncovered=free.difference(actual.buffer(4*TOL)).length
            if uncovered>8*TOL:
                problem('Part of an actual free gusset edge lacks its selected face reinforcement',face=side,uncovered_edge_in=uncovered)
            curves=list(free.geoms) if hasattr(free,'geoms') else [free]
            for curve in curves:
                for a,b in zip(curve.coords,list(curve.coords)[1:]):
                    delta=np.subtract(b,a)
                    length=float(np.linalg.norm(delta))
                    if length<2*bar_w:continue
                    normal=np.array([-delta[1],delta[0]])/length
                    cut=_line_spans(actual,(np.asarray(a)+b)/2,normal,span)
                    width=0. if not cut else cut[1]-cut[0]
                    if width+4*TOL<bar_w:
                        problem('Measured stock across a free-edge bar is narrower than HR selected',
                                face=side,actual_width_in=width,selected_in=bar_w)
    return counts,findings,facts
