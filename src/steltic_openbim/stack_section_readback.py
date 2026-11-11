"""Independently measure the HR pin-eye breadth, extensions, transfer strips and head contact in STEP."""
from collections import Counter
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from .brb_core_readback import end_face,inside_core
from .joint_mesh_readback import TOL,plane_axes,unit


def check_head_contact(tongue,head,axis):
    direction=unit(axis);axes=plane_axes(direction)
    leaf_stations=tongue.vertices@direction
    head_stations=head.vertices@direction
    far=float(max(leaf_stations));mouth=float(min(head_stations))
    leaf=end_face(tongue,direction,far,axes);root=end_face(head,direction,mouth,axes)
    touch=float(leaf.intersection(root).area)
    errors=[]
    if (not tongue.closed or not head.closed or abs(mouth-far)>TOL or leaf.area<=TOL or
            leaf.difference(root.buffer(TOL)).area>TOL*max(1.,leaf.length)):
        errors.append('Integral supplier tongue and moving head do not share the complete finite end face')
    return dict(actual_terminal_gap_in=mouth-far,tongue_face_area_in2=float(leaf.area),contact_in2=touch),errors


def _line_spans(outer,point,direction,span):
    a=np.asarray(point);v=np.asarray(direction)
    cut=outer.intersection(LineString([a-v*span,a+v*span]))
    if cut.is_empty:return None
    lines=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
    touching=[p for p in lines if p.geom_type=='LineString' and p.distance(Point(a))<=TOL]
    if len(touching)!=1:return None
    vals=(np.asarray(touching[0].coords)-a)@v
    return float(min(vals)),float(max(vals))


def _clipped_projection(mesh,normal,low,high,axes):
    """Projection of the solid clipped to a slab; retain its initial cap and swept boundary."""
    stations=mesh.vertices@normal
    low=max(float(min(stations))+TOL/4,low+TOL/4)
    high=min(float(max(stations))-TOL/4,high-TOL/4)
    if high-low<=TOL:return Polygon()
    pieces=[mesh.section(normal,(low+high)/2,axes)]
    for face in mesh.polygons:
        values=face@normal
        if max(values)<low or min(values)>high:continue
        ring=list(face)
        for station,sign in ((low,1.),(high,-1.)):
            new=[]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                da,db=(a@normal-station)*sign,(b@normal-station)*sign
                if da>=0:new.append(a)
                if da*db<0:new.append(a+(b-a)*da/(da-db))
            ring=new
            if len(ring)<3:break
        if len(ring)<3:continue
        shape=Polygon(np.asarray(ring)@np.asarray(axes).T)
        if shape.area>TOL*TOL:pieces.append(shape if shape.is_valid else shape.buffer(0))
    return unary_union(pieces)


def check_plate_sections(source,receiver,parts,meshes,axis,casing=None,required_travel=0.,hosts=None):
    counts=Counter();issues=[];evidence=[]
    v=unit(axis);pin=next((k for k,p in parts.items() if p['kind']=='pin'),None)
    if pin is None or pin not in meshes:return counts,[dict(code='ordered_stack_common_pin_body_missing')],evidence
    y=unit(parts[pin]['parameters']['axis']);n=unit(np.cross(v,y))
    if abs(float(y@v))>TOL:return counts,[dict(code='ordered_stack_pin_not_transverse_to_source_brace')],evidence
    pin_point=np.asarray(parts[pin]['parameters']['point']);center=np.array([pin_point@v,pin_point@n])
    roles={p['parameters']['source_stack_role']:k for k,p in parts.items() if 'source_stack_role' in p.get('parameters',{})}
    ufm=receiver.get('ufm_for_one_primary_leaf',{});station=ufm.get('whitmore_clear_station_in')
    fixed=[];sections={};moving=[]
    for row in source['selected_stack']:
        role=row['role'];k=roles.get(role);connected=row['connected_to']
        if k not in meshes:continue
        mesh=meshes[k];lo,hi=np.min(mesh.vertices@y),np.max(mesh.vertices@y)
        section=mesh.section(y,(lo+hi)/2,(v,n))
        if section.geom_type!='Polygon' or section.is_empty:continue
        shape=Polygon(section.exterior);sections[k]=(lo,hi,shape)
        if connected!='brace_end':fixed.append((k,lo,hi,section))
        else:moving.append(k)
        if connected not in ('host','brace_end'):continue
        counts['actual_selected_bearing_widths']+=1
        transverse=_line_spans(shape,center,[0.,1.],10000.)
        width=None if transverse is None else transverse[1]-transverse[0]
        nominal=source['primary_width_at_pin_in']
        if width is None or abs(width-nominal)>4*TOL or abs(sum(transverse))>4*TOL:
            issues.append(dict(code='selected_eye_breadth_at_pin_differs',ply=k,width_in=width,required_in=nominal))
        ext=[];hole=source['pin_hole_diameter_in'];advance=1 if connected=='host' else -1
        for shift in (-hole/2,0.,hole/2):
            bounds=_line_spans(shape,center+[0.,shift],[1.,0.],10000.)
            distance=None if bounds is None else (bounds[1] if advance==1 else -bounds[0])-hole/2
            ext.append(distance)
        if any(x is None or abs(x-source['extension_in'])>4*TOL for x in ext):
            issues.append(dict(code='selected_pin_end_extension_differs',ply=k,measured_in=ext,required_in=source['extension_in']))
        item=dict(ply=k,actual_breadth_in=width,actual_edge_extensions_in=ext)
        if connected=='host' and station is not None:
            required=ufm['whitmore_effective_width_in']
            bounds=_line_spans(shape,[station,center[1]],[0.,1.],10000.)
            measures=None if bounds is None else [-bounds[0],bounds[1]]
            if measures is None or min(measures)+2*TOL<required/2:
                issues.append(dict(code='selected_whitmore_width_not_contained_by_primary',ply=k,half_widths_in=measures,required_in=required))
            else:counts['actual_full_structured_whitmore_sections']+=1
            item.update(transfer_station_in=station,half_widths_in=measures)
        evidence.append(item)
    if 'free_edge_stiffener_thickness_in' in ufm:
        thickness=ufm['free_edge_stiffener_thickness_in']
        for k,p in parts.items():
            par=p.get('parameters',{})
            if not par.get('free_edge_bar') or k not in meshes:continue
            mesh=meshes[k];lo,hi=np.min(mesh.vertices@y),np.max(mesh.vertices@y)
            sec=mesh.section(y,(lo+hi)/2,(v,n));parent=par.get('source_primary_gusset')
            if (parent not in sections or not mesh.closed or abs(hi-lo-thickness)>TOL or sec.is_empty or
                    min(abs(hi-sections[parent][0]),abs(lo-sections[parent][1]))>TOL or
                    sec.intersection(sections[parent][2]).area<=TOL):
                issues.append(dict(code='selected_free_edge_stock_lacks_required_face_or_thickness',ply=k,source_plate=parent))
            else:counts['actual_fitted_free_edge_bars']+=1
            fixed.append((k,lo,hi,sec))
        for row in source['selected_stack']:
            if row['connected_to']!='host':continue
            parent=roles.get(row['role'])
            if parent not in sections:continue
            entries=[p for k,p in parts.items() if p.get('parameters',{}).get('source_primary_gusset')==parent and k in meshes]
            for side in (-1,1):
                face=sections[parent][0 if side<0 else 1]
                if not any(abs((np.max(meshes[p['id']].vertices@y) if side<0 else np.min(meshes[p['id']].vertices@y))-face)<=TOL for p in entries):
                    issues.append(dict(code='selected_primary_free_edge_stiffening_face_absent',ply=parent,face=side))
    for k in moving:
        lo,hi,shape=sections[k]
        for host,mesh in (hosts or {}).items():
            projection=_clipped_projection(mesh,y,lo,hi,(v,n))
            intrudes=shape.intersection(projection.buffer(-TOL)).area
            if intrudes>TOL*max(1.,shape.length):
                issues.append(dict(code='selected_moving_tongue_intrudes_receiving_member',ply=k,host=host,overlap_in2=intrudes))
    if casing is not None and required_travel>0:
        start=float(min(casing.vertices@v));limit=min(float(max(casing.vertices@v)),start+24.)
        cuts=sorted({round(float(s),6) for s in casing.vertices@v if start+TOL<s<limit-TOL}|{start,limit})
        material=[]
        for a,b in zip(cuts,cuts[1:]):
            if b-a<=TOL:continue
            # A mortar relief has a finite depth and may leave another real hole
            # in the annular stock. Locate the steel core at the source workline
            # and use all other measured material at each actual interval.
            fixed_sections=[]
            for ratio in (.15,.5,.85):
                section=casing.section(v,a+(b-a)*ratio,(y,n))
                pieces=list(section.geoms) if section.geom_type=='MultiPolygon' else [section]
                central=[p for p in pieces if p.covers(Point(0,0))]
                if len(central)!=1 or len(pieces)<2:
                    issues.append(dict(code='actual_supplier_casing_section_unresolved',interval_in=[a,b]));break
                fixed_sections.append(unary_union([p for p in pieces if p is not central[0]]))
            if len(fixed_sections)!=3:continue
            shell=fixed_sections[1]
            if any(shell.symmetric_difference(other).area>4*TOL*max(1.,shell.length) for other in fixed_sections):
                issues.append(dict(code='actual_fixed_casing_changes_inside_finite_interval',interval_in=[a,b]));continue
            material.append((a,b,shell))
        for k,lo,hi,section in fixed:
            for role in ('END-CAP','CORE-END','HEAD-CJP'):
                if role not in meshes:continue
                projection=_clipped_projection(meshes[role],y,lo,hi,(v,n))
                intrusion=section.intersection(projection.buffer(-TOL)).area
                if intrusion>TOL*max(1.,section.length):
                    issues.append(dict(code='actual_moving_head_or_core_intersects_stationary_pin_steel',part=role,stationary_part=k,overlap_in2=intrusion))
            for a,b,shell in material:
                projection=_clipped_projection(meshes[k],v,a-required_travel,b+required_travel,(y,n))
                overlap=shell.intersection(projection.buffer(-TOL)).area
                if overlap>TOL*max(1.,shell.length):
                    issues.append(dict(code='actual_stationary_pin_steel_intersects_swept_casing',part=k,
                        full_travel_in=required_travel,axial_material_interval_in=[a-start,b-start],overlap_in2=overlap))
            counts['actual_stationary_pin_stock_travel_checks']+=1
    return counts,issues,evidence
