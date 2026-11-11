"""Measure the two actual bar-to-plate interfaces and their finite IFC weld paths."""
from collections import defaultdict
import re

import numpy as np
from shapely import union_all
from shapely.geometry import LineString,Point,Polygon


TOL=1e-4


def faces_at_station(mesh,origin,basis):
    """Find solid faces parallel to the truss plane that contain the selected workpoint."""
    faces=defaultdict(list)
    for face in mesh.polygons:
        local=(face-origin)@basis.T
        if np.ptp(local[:,2])>TOL:continue
        poly=Polygon(local[:,:2])
        if poly.area>1e-9:
            faces[round(float(local[:,2].mean()),5)].append(poly)
    surfaces=[]
    for z,facets in sorted(faces.items()):
        merged=union_all(facets)
        if merged.distance(Point(0,0))<=TOL:surfaces.append((z,merged))
    return surfaces


def plate_interfaces(point,axes,bars,plate,welds,selected):
    """All meshes and curve stations are independently identified, world-space IFC inches."""
    if len(axes)!=2 or len(bars)!=2 or set(axes)!=set(bars):
        return {},['Exactly two identified source flat bars are required']
    keys=list(axes)
    directions=[np.subtract(e[1],e[0],dtype=float) for e in axes.values()]
    normal=np.cross(*directions)
    if np.linalg.norm(normal)<1e-8:return {},['The source bars are parallel at their declared crossing']
    normal/=np.linalg.norm(normal)
    if 'plate_normal' in selected:
        reference=np.asarray(selected['plate_normal'],dtype=float)
        if reference.shape!=(3,) or not np.isfinite(reference).all() or abs(np.linalg.norm(reference)-1.)>TOL:
            return {},['HR crossing plate normal is not a finite world unit vector']
        if normal@reference<0:normal=-normal
        if np.linalg.norm(normal-reference)>TOL:
            return {},['HR crossing plate normal differs from its two identified source axes']
    u=directions[0]/np.linalg.norm(directions[0])
    basis=np.array([u,np.cross(normal,u),normal])
    origin=np.asarray(point,dtype=float)
    shape={k:faces_at_station(bars[k],origin,basis) for k in keys}
    faces=faces_at_station(plate,origin,basis)
    if len(faces)!=2 or any(len(s)!=2 for s in shape.values()):
        return {},['Both broad faces of the plate and each bar must span the crossing workpoint']
    keys.sort(key=lambda k:shape[k][0][0])
    thickness=faces[1][0]-faces[0][0]
    issues=[]
    if abs(thickness-selected['plate_thickness_in'])>TOL:
        issues.append('Measured crossing plate thickness differs from HR')
    facts={'plate_thickness_in':thickness,'interfaces':{}}
    if selected.get('centered'):
        offsets=[float(np.hypot(face.centroid.x,face.centroid.y)) for _,face in faces]
        middle=(faces[0][0]+faces[1][0])/2
        facts.update(plate_midplane_offset_in=middle,plate_face_center_offsets_in=offsets)
        if max(abs(middle),*offsets)>TOL:
            issues.append('Crossing plate centroid or mid-plane differs from the selected workpoint')
    if 'plate_width_in' in selected and 'plate_length_in' in selected:
        target=sorted([selected['plate_width_in'],selected['plate_length_in']])
        sizes=[]
        for _,face in faces:
            rectangle=face.minimum_rotated_rectangle
            if rectangle.geom_type!='Polygon':
                issues.append('Crossing plate lacks a measurable plan')
                break
            ring=np.asarray(rectangle.exterior.coords)
            measured=sorted(float(v) for v in np.linalg.norm(np.diff(ring,axis=0),axis=1)[:2])
            sizes.append(measured)
            if np.max(np.abs(np.subtract(measured,target)))>TOL:
                issues.append('Measured crossing plate width or length differs from HR')
            if selected.get('rectangular') and abs(face.area-target[0]*target[1])>TOL*max(target):
                issues.append('Actual plate face differs from the selected rectangle')
        facts['plate_face_sizes_in']=sizes
        if selected.get('horizontal_vertical'):
            up=basis[:2,2]
            if abs(normal[2])>TOL:
                issues.append('The selected vertical plate plane does not contain the building vertical')
            else:
                horizontal=np.array([up[1],-up[0]])
                for _,face in faces:
                    coords=np.asarray(face.exterior.coords)
                    spans=sorted([float(np.ptp(coords@up)),float(np.ptp(coords@horizontal))])
                    if np.max(np.abs(np.subtract(spans,target)))>TOL:
                        issues.append('The selected horizontal and vertical plate edges are rotated in the truss plane')
                        break
    for i,k in enumerate(keys):
        z,plate_face=faces[i]
        bar_z,bar_face=shape[k][1-i]
        gap=z-bar_z if i==0 else bar_z-z
        contact=plate_face.intersection(bar_face)
        if abs(gap)>TOL or contact.area<=TOL*TOL or contact.distance(Point(0,0))>TOL:
            issues.append(k+': bar does not meet its own plate face at the crossing')
        paths=[w for w in welds if w['member']==k]
        record={'steel_face_gap_in':float(gap),'contact_area_in2':float(contact.area),'weld_lengths_in':[]}
        facts['interfaces'][k]=record
        if 'member_faces' in selected:
            record['face_sign']=2*i-1
            if selected['member_faces'][k]!=record['face_sign']:
                issues.append(k+': bar is on the opposite side of the selected crossing plate')
        if len(paths)!=selected['per_bar_count']:
            issues.append(k+': missing or extra bar-to-plate fillets')
        source_axis=np.asarray(axes[k],dtype=float)
        bar_u=(source_axis[1]-source_axis[0])@basis[:2].T
        bar_u/=np.linalg.norm(bar_u)
        bar_v=np.array([-bar_u[1],bar_u[0]])
        lateral=(np.asarray(bar_face.exterior.coords)@bar_v) if bar_face.geom_type=='Polygon' else None
        if lateral is None:
            issues.append(k+': missing connected bar face')
            continue
        if 'min_lap_in' in selected:
            zone=contact.buffer(TOL)
            end_lim=np.asarray(plate_face.exterior.coords)@bar_u
            measured=[]
            for side in (min(lateral),max(lateral)):
                ray=LineString([bar_u*t+bar_v*side for t in (min(end_lim)-1.,max(end_lim)+1.)])
                clipped=ray.intersection(zone)
                if clipped.geom_type=='MultiLineString':
                    segments=list(clipped.geoms)
                    clipped=max(segments,key=lambda segment:segment.length)
                measured.append(float(clipped.length))
            record['edge_lap_in']=measured
            if min(measured)+TOL<selected['min_lap_in']:
                issues.append(k+': actual bar-to-plate lap length is below the selected minimum')
        sides=set()
        for w in paths:
            pts=(np.asarray(w['points_in'],dtype=float)-origin)@basis.T
            if len(pts)<2 or not np.isfinite(pts).all():
                issues.append(k+': missing finite IFC weld path')
                continue
            length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum())
            record['weld_lengths_in'].append(length)
            path=LineString(pts[:,:2])
            span=pts[:,:2]@bar_v
            if selected.get('centered') and abs((pts[0,:2]+pts[-1,:2])@bar_u/2)>TOL:
                issues.append(k+': weld is offset along the bar from its selected crossing station')
            if len(pts)>2 and abs(np.linalg.norm(pts[-1]-pts[0])-length)>TOL:
                issues.append(k+': required longitudinal weld is doglegged or retraced')
            if abs(length-selected['length_in'])>TOL or abs(w['size_in']-selected['size_in'])>TOL:
                issues.append(k+': measured IFC fillet size or length differs from HR')
            if np.max(np.abs(pts[:,2]-z))>TOL or not contact.buffer(TOL).covers(path):
                issues.append(k+': fillet extends past the actual plate/bar contact or lies on another plane')
            at_side=[side for side,extreme in enumerate((min(lateral),max(lateral))) if np.max(np.abs(span-extreme))<=TOL]
            if len(at_side)!=1:
                issues.append(k+': fillet lies off the longitudinal edge of its bar')
            sides.update(at_side)
        if selected['per_bar_count']==2 and sides!={0,1}:
            issues.append(k+': the two selected fillets do not occupy opposite bar edges')
    if any(w['member'] not in bars for w in welds):issues.append('Crossing has welds attributed to an unrelated member')
    return facts,issues


def plate_selection(source,record):
    groups=defaultdict(dict)
    for i in source['selected']:
        f=record['fields'][i]
        group=groups[f['role']]
        if f['field'] in group and group[f['field']]!=f['value']:
            raise ValueError('Ambiguous selected crossing value '+f['field'])
        group[f['field']]=f['value']
    plate=groups['flat_bar_crossing_plate']
    fillet=groups['flat_bar_crossing_fillet']
    pkeys=('length_in','width_in','thickness_in','material')
    wkeys=('count_per_bar','size_in','length_in','material','run')
    if (any(plate[k]!=source['plate'][k] for k in pkeys) or any(fillet[k]!=source['welds'][k] for k in wkeys)
            or fillet['run']!='longitudinal' or source['plate'].get('record_id')!=source['record_id']):
        raise ValueError('Crossing plate, weld or source record differs from the located HR selection')
    signs=source['member_faces']
    if (len(signs)!=2 or {f['member_id'] for f in signs}!=set(source['member_ids'])
            or {f['face_sign'] for f in signs}!={-1,1}):
        raise ValueError('HR crossing does not identify one bar for each face')
    alignment=record.get('crossing_plate',{}).get('value',{}).get('alignment','')
    return dict(plate_thickness_in=plate['thickness_in'],plate_width_in=plate['width_in'],plate_length_in=plate['length_in'],
                rectangular=True,centered=True,plate_normal=source['plate']['normal'],
                horizontal_vertical='horizontal/vertical in the truss plane' in alignment.lower(),
                member_faces={f['member_id']:f['face_sign'] for f in signs},
                plate_material=plate['material'],weld_material=fillet['material'],
                per_bar_count=fillet['count_per_bar'],size_in=fillet['size_in'],length_in=fillet['length_in'])


def delivered_plate_crossing(rb,source,record,template,parts,placements,curves,meshes,members,cid):
    from .joint_mesh_readback import TOL as CURVE_TOL,transform
    from .selected_plate_readback import grade
    inst,instance=placements
    selected=plate_selection(source,record)
    plates=[p for p in parts.values() if p['kind']=='plate' and (p.get('parameters',{}).get('source_role')=='flat_bar_crossing_plate'
            or p['id'].upper() in ('CROSSING-PLATE','CROSSING_PLATE'))]
    if len(plates)!=1 or plates[0]['id'] not in meshes:
        return {},['Expected one identified actual crossing plate in its IFC constituent face range']
    plate=plates[0]['id']
    steel=meshes[plate].transformed(instance)
    obj=rb.assemblies[cid]
    sets=[a.RelatingMaterial for a in obj.HasAssociations if a.is_a('IfcRelAssociatesMaterial') and a.RelatingMaterial.is_a('IfcMaterialConstituentSet')]
    if len(sets)!=1 or sets[0].Name!=template:
        return {},['Crossing has no uniquely identified IFC material constituent set']
    materials={x.Name:x.Material.Name for x in sets[0].MaterialConstituents}
    issues=[]
    target_grade=grade(selected['plate_material'])
    if not target_grade or grade(materials.get(plate,''))!=target_grade:
        issues.append('Actual IFC crossing plate material differs from the HR selection')
    mid=source['member_ids']
    welds=[]
    used=set()
    for part in (p for p in parts.values() if p['kind']=='weld'):
        connects=part.get('connects',[])
        ids={inst['bindings'].get(t) for t in connects}&set(mid)
        if len(connects)!=2 or plate not in connects or len(ids)!=1:
            issues.append('Crossing weld does not bind exactly one bar to the selected plate')
            continue
        p=part.get('parameters',{})
        if not isinstance(p.get('size_in'),(int,float)):
            issues.append('Crossing weld lacks a numeric leg size')
            continue
        if 'points' not in part.get('geometry',{}):
            issues.append('Crossing weld lacks a locatable path')
            continue
        ref=transform(part['geometry']['points'],instance)
        hits=[i for i,q in enumerate(curves) if q.shape==ref.shape and min(
            np.max(np.abs(q-ref)),np.max(np.abs(q[::-1]-ref)))<=CURVE_TOL]
        if len(hits)!=1 or hits[0] in used:
            issues.append('Expected one distinct actual IFC weld trajectory for '+part['id'])
            continue
        used.add(hits[0])
        spec=materials.get(part['id'],'').upper()
        target=str(selected['weld_material']).upper().replace(' ','')
        grades=re.findall(r'\bE(?:XX|\d{2})[A-Z0-9]{2}\b',spec)
        if target.endswith('XX'):
            matches=bool(grades) and all(g[:3]==target[:3] for g in grades)
        else:matches=set(grades)=={target}
        if not matches:issues.append('Actual IFC weld material differs from '+target+' on '+part['id'])
        welds.append(dict(member=next(iter(ids)),points_in=curves[hits[0]],size_in=p['size_in']))
    facts,problems=plate_interfaces(source['point_in'],{k:members[k]['axis'] for k in mid},
        {k:rb.member(k) for k in mid},steel,welds,selected)
    facts.update(crossing=source['id'],constituent=plate,plate_grade=materials.get(plate),checked_welds=len(welds))
    return facts,issues+problems
