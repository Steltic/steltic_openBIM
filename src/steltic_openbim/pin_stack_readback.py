"""Check a source-selected common pin through its actual ordered plate/clevis stack."""
from collections import Counter
import re

import numpy as np
from shapely.geometry import LineString,Polygon

from .joint_mesh_readback import TOL,outer_polygon,plane_axes,projected,transform,unit


def material_key(value):
    name=re.sub(r'\b(?:ASTM|GRADE|GR\.?)(?=\b|\s)',' ',str(value).upper())
    return re.sub('[^A-Z0-9]','',name)


def actual_materials(product):
    groups=[a.RelatingMaterial for a in product.HasAssociations if a.is_a('IfcRelAssociatesMaterial') and a.RelatingMaterial.is_a('IfcMaterialConstituentSet')]
    if len(groups)!=1:return {}
    return {v.Name:v.Material.Name for v in groups[0].MaterialConstituents}


def selected_stack_record(handoff,cid):
    rows=[]
    for link in handoff.get('occurrences',{}).get(cid,{}).get('applications',[]):
        record=handoff['records'][link['record_id']]
        stack=record.get('data',{}).get('pin_stack')
        if stack and link.get('selected'):rows.append((link['record_id'],stack))
    return rows


def verify_pin_stack(record_id,source,parts,meshes,materials,curves,inverse):
    findings=[];counts=Counter(actual_selected_pin_stacks=1)
    def issue(code,**data):findings.append(dict(code=code,**data))
    pins=[id for id,p in parts.items() if p['kind']=='pin']
    if len(pins)!=1 or pins[0] not in meshes:
        issue('selected_common_pin_missing_or_duplicated',pins=pins)
        return counts,findings
    pin=pins[0];parameters=parts[pin]['parameters'];axis=unit(parameters['axis']);point=np.asarray(parameters['point'])
    axes=plane_axes(axis);center=projected(point,axes)
    shaft=meshes[pin];shaft_stations=shaft.vertices@axis
    if float(np.ptp(shaft_stations))+TOL<source['grip_in']:
        issue('selected_common_pin_too_short_for_grip',actual_shaft_span_in=float(np.ptp(shaft_stations)),selected_grip_in=source['grip_in'])
    if material_key(source['pin_material']) not in material_key(materials.get(pin,'')):
        issue('selected_common_pin_material_differs',actual=materials.get(pin),selected=source['pin_material'])
    positions={};by_role={};sections={};expected=source['selected_stack']
    mapping=[(p['parameters'].get('source_stack_role'),k) for k,p in parts.items() if p.get('parameters',{}).get('source_stack_role')]
    if len(mapping)!=len(expected) or len(dict(mapping))!=len(expected):
        issue('selected_pin_stack_role_count_differs',actual=[r for r,_ in mapping],selected=[r['role'] for r in expected])
    actual=dict(mapping)
    for i,ply in enumerate(expected):
        role=ply['role'];pid=actual.get(role)
        if pid not in meshes or pid not in parts[pin].get('connects',[]):
            issue('selected_pin_stack_ply_missing',stack_role=role);continue
        par=parts[pid]['parameters'];mesh=meshes[pid];by_role[role]=pid
        if par.get('source_stack_index')!=i or par.get('source_record_id')!=record_id:
            issue('pin_stack_ply_binding_differs',ply=pid,stack_role=role,selected_index=i)
        stations=mesh.vertices@axis;lo,hi=float(min(stations)),float(max(stations));mid=(lo+hi)/2
        positions[role]=(lo,hi)
        thickness=hi-lo
        if abs(thickness-ply['thickness_in'])>TOL or not mesh.closed:
            issue('selected_pin_stack_ply_thickness_or_closure_differs',ply=pid,actual_in=thickness,selected_in=ply['thickness_in'])
        if material_key(ply['material']) not in material_key(materials.get(pid,'')):
            issue('selected_pin_stack_ply_material_differs',ply=pid,actual=materials.get(pid),selected=ply['material'])
        if lo<min(shaft_stations)-TOL or hi>max(shaft_stations)+TOL:
            issue('selected_common_pin_does_not_engage_full_ply',ply=pid)
        section=mesh.section(axis,mid,axes);sections[role]=section
        holes=[Polygon(r) for r in getattr(section,'interiors',[]) if Polygon(r).covers(center)]
        if len(holes)!=1:
            issue('selected_pin_stack_bore_missing',ply=pid)
        else:
            radii=np.linalg.norm(np.asarray(holes[0].exterior.coords)-[center.x,center.y],axis=1)
            if np.max(np.abs(2*radii-source['pin_hole_diameter_in']))>4*TOL:
                issue('selected_pin_stack_bore_diameter_or_center_differs',ply=pid,selected_in=source['pin_hole_diameter_in'])
        pin_section=shaft.section(axis,mid,axes)
        if pin_section.geom_type!='Polygon' or not pin_section.covers(center):
            issue('selected_common_pin_absent_at_ply',ply=pid)
        else:
            radii=np.linalg.norm(np.asarray(pin_section.exterior.coords)-[center.x,center.y],axis=1)
            if np.max(np.abs(2*radii-source['pin_diameter_in']))>4*TOL:
                issue('selected_common_pin_diameter_or_center_differs',ply=pid,selected_in=source['pin_diameter_in'])
        counts['actual_ordered_pin_bearing_plies']+=1
    source_order=[v['role'] for v in expected]
    order=sorted(positions,key=lambda k:positions[k][0])
    if order:
        grip=positions[order[-1]][1]-positions[order[0]][0]
        if abs(grip-source['grip_in'])>TOL:
            issue('selected_common_pin_grip_differs',actual_stack_span_in=grip,selected_in=source['grip_in'])
    if order!=source_order and order!=list(reversed(source_order)):
        issue('selected_bearing_ply_order_differs',actual=order,selected=source_order)
    roles={r['role']:r for r in expected}
    for a,b in zip(order,order[1:]):
        moving=(roles[a]['connected_to']=='brace_end')!=(roles[b]['connected_to']=='brace_end')
        target=source['clearance_between_moving_groups_in'] if moving else 0.
        gap=positions[b][0]-positions[a][1]
        if abs(gap-target)>TOL:issue('selected_pin_stack_interface_clearance_differs',plies=[a,b],actual_in=gap,selected_in=target)
    actual_lines=[transform(line,inverse) for line in curves]
    for role,pid in by_role.items():
        if not role.startswith('cheek_'):continue
        primary=by_role.get(roles[role]['connected_to'])
        welds=[(k,p) for k,p in parts.items() if p['kind']=='weld' and {pid,primary}<=set(p.get('connects',[]))]
        if len(welds)!=4:
            issue('selected_cheek_perimeter_weld_count_differs',ply=pid,actual=len(welds),selected=4)
            continue
        outline=outer_polygon(sections[role]).exterior.simplify(TOL)
        perimeter=source['cheek_weld_perimeter_in'];target_length=source['cheek_side_in']
        if abs(outline.length-perimeter)>4*TOL:
            issue('selected_cheek_perimeter_differs',ply=pid,actual_in=outline.length,selected_in=perimeter)
        used=set();segments=[]
        for wid,weld in welds:
            expected_line=np.asarray(weld['geometry']['points'])
            matches=[i for i,line in enumerate(actual_lines) if i not in used and line.shape==expected_line.shape and
                     (np.max(np.abs(line-expected_line))<=TOL or np.max(np.abs(line[::-1]-expected_line))<=TOL)]
            if len(matches)!=1:
                issue('selected_cheek_weld_reference_missing',ply=pid,weld=wid);continue
            index=matches[0];used.add(index);line=actual_lines[index]
            length=float(np.linalg.norm(np.diff(line,axis=0),axis=1).sum())
            leg=weld['parameters'].get('size_in',weld['parameters'].get('size'))
            if leg is None or abs(float(leg)-source['cheek_weld_leg_in'])>TOL or abs(length-target_length)>TOL:
                issue('selected_cheek_weld_size_or_length_differs',ply=pid,weld=wid,actual_in=length,selected_in=target_length,actual_leg_in=leg)
            segments.append(LineString(np.column_stack((line@axes[0],line@axes[1]))))
            counts['actual_selected_cheek_perimeter_welds']+=1
        if segments:
            from shapely.ops import unary_union
            lines=unary_union(segments)
            if outline.difference(lines.buffer(2*TOL)).length>4*TOL or lines.difference(outline.buffer(2*TOL)).length>4*TOL:
                issue('selected_cheek_welds_do_not_cover_four_edges',ply=pid)
    return counts,findings
