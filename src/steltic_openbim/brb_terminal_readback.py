"""Measure both HR-selected enlarged core transitions and their actual full-section fused heads."""
import numpy as np
from .brb_core_readback import end_face
from .joint_mesh_readback import TOL,plane_axes,unit
from .selected_plate_readback import grade


def check_transitions(core_info,spec):
    intervals=core_info.get('actual_intervals',[]);yielding=core_info.get('measured_yielding_intervals_in',[])
    end_area=spec['area_in2']*spec['terminal']['end_area_ratio']
    minimum=spec['terminal']['minimum_transition_length_in'];errors=[];measured=[]
    if len(yielding)!=1 or not intervals:return {},['No unique finite yielding segment for transition measurement']
    for end in (0,1):
        boundary=yielding[0][end]
        rows=([r for r in intervals if r['end_in']<=boundary+TOL] if not end else
              list(reversed([r for r in intervals if r['start_in']>=boundary-TOL])))
        if not rows:errors.append('No enlarged terminal at end '+str(end));continue
        epsilon=TOL*max(1.,end_area)
        near=rows[0]['area_range_in2']
        if max(abs(a-end_area) for a in near)>epsilon:
            errors.append('Actual end stock fails to retain its full selected area at end '+str(end))
        changing=[r for r in rows if max(abs(a-end_area) for a in r['area_range_in2'])>epsilon]
        if not changing:errors.append('Actual core lacks a machined transition at end '+str(end));continue
        first=changing[0]['start_in' if not end else 'end_in']
        length=abs(boundary-first)
        if length+2*TOL<minimum:errors.append('Actual gradual transition is shorter than selected at end '+str(end))
        prior=end_area
        for r in changing:
            low,high=r['area_range_in2']
            if high>prior+epsilon or low<spec['area_in2']-epsilon or high>end_area+epsilon:
                errors.append('Actual machined section reverses, undercuts or overshoots its permitted area at end '+str(end));break
            prior=low
        measured.append(dict(end_index=end,actual_terminal_area_in2=near,required_terminal_area_in2=end_area,
                             measured_transition_in=length,required_minimum_transition_in=minimum))
    return {'machined_end_transitions':measured},errors


def check_cjp(shapes,parts,materials,axis,spec):
    source=spec['terminal'];required=spec['area_in2']*source['end_area_ratio'];ids=['END-CAP','HEAD-CJP','CORE-END']
    if any(k not in shapes or k not in parts for k in ids):return {},['A constituent of the selected complete-joint-penetration head is missing']
    cap,seam,core=[shapes[k] for k in ids]
    normal=unit(axis);axes=plane_axes(normal)
    cap_back=float(max(cap.vertices@normal));front=float(min(seam.vertices@normal));back=float(max(seam.vertices@normal))
    core_front=float(min(core.vertices@normal));errors=[]
    if not all(shape.closed for shape in (cap,seam,core)) or abs(front-cap_back)>TOL or abs(core_front-back)>TOL or back-front<=TOL:
        errors.append('The selected CJP has a missing face, gap, penetration or zero fusion thickness')
    frontw=end_face(seam,normal,front,axes);backw=end_face(seam,normal,back,axes)
    head_face=end_face(cap,normal,cap_back,axes);core_face=end_face(core,normal,core_front,axes)
    face_tol=TOL*max(1.,head_face.length,core_face.length,frontw.length,backw.length)
    if (min(frontw.area,backw.area)+face_tol<required or frontw.difference(head_face.buffer(TOL)).area>face_tol or
            backw.difference(core_face.buffer(TOL)).area>face_tol or core_face.difference(backw.buffer(TOL)).area>face_tol):
        errors.append('The deposited groove weld fails to fuse the complete selected net terminal face')
    for f in (.1,.5,.9):
        sec=seam.section(normal,front+f*(back-front),axes)
        if sec.area+face_tol<required:errors.append('The actual groove weld contains an undersized internal throat');break
    actual=str(materials.get('HEAD-CJP','')).upper()
    if (source['head_joint_electrode'].upper() not in actual or parts['HEAD-CJP'].get('kind')!='weld' or
            parts['HEAD-CJP'].get('parameters',{}).get('weld_type')!='CJP'):
        errors.append('The actual complete-joint-penetration weld process or consumable differs from HR')
    if grade(materials.get('CORE-END',''))!=grade(spec['material']) or grade(materials.get('END-CAP',''))!=grade(source['head_material']):
        errors.append('The actual core/head parent steel grade differs from HR')
    return dict(actual_electrode=actual,required_end_area_in2=required,measured_weld_faces_in2=[frontw.area,backw.area],
                actual_core_face_in2=core_face.area,measured_fused_head_contact_in2=frontw.intersection(head_face).area,
                measured_fused_core_contact_in2=backw.intersection(core_face).area,measured_fusion_zone_in=back-front),errors
