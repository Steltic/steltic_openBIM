"""Check both selected fillet runs on opposite faces of the actual gusset."""
import numpy as np
from shapely import line_merge,union_all
from shapely.geometry import LineString

from .joint_mesh_readback import TOL,plane_axes


def both_faces(plate,paths,length=None):
    normal=plate.plate_normal
    levels=plate.vertices@normal
    limits=[float(min(levels)),float(max(levels))]
    uv=np.array(plane_axes(normal)).T
    sides=[[],[]]
    issues=[]
    for pid,points in paths:
        positions=points@normal
        hits=[i for i,limit in enumerate(limits) if np.max(np.abs(positions-limit))<=TOL]
        if len(hits)!=1:
            issues.append(dict(part=pid,detail='Selected two-sided fillet is off both actual plate faces'))
            continue
        sides[hits[0]].append(LineString(points@uv))
    spans=[sum(line.length for line in side) for side in sides]
    facts=dict(face_lengths_in=spans,selected_per_side_in=length,segment_counts=[len(s) for s in sides])
    if not all(sides):
        issues.append(dict(detail='Selected fillets do not occupy both faces of the actual gusset',**facts))
        return facts,issues
    merged=[union_all(side) for side in sides]
    for i,s in enumerate(merged):
        # Segmenting along adjacent receivers is allowed provided both runs are continuous.
        joined=line_merge(s)
        if joined.geom_type!='LineString' or abs(s.length-spans[i])>TOL:
            issues.append(dict(detail='Gusset support fillet has a gap or a repeated segment on one side',side=i))
        if length is not None and abs(spans[i]-length)>TOL:
            issues.append(dict(detail='Actual per-side gusset fillet length differs from HR',side=i,**facts))
    if merged[0].hausdorff_distance(merged[1])>TOL:
        issues.append(dict(detail='Opposite-face gusset fillets do not occupy the same selected finite support edge'))
    return facts,issues


def selected_support_sides(parts,meshes,instance,actual_lines,fields,gussets):
    results=[]
    issues=[]
    for role in ('gusset_column_weld','gusset_base_weld','gusset_beam_weld'):
        side_counts=set(fields.get((role,'faces'),[]))
        if not side_counts:continue
        if side_counts!={2}:
            issues.append(dict(role=role,detail='Unresolved selected support fillet side count',selected=sorted(side_counts)))
            continue
        expected='WGC' if role=='gusset_column_weld' else 'WGB'
        lengths=set(fields.get((role,'length_in'),[]))
        if len(lengths)>1:
            issues.append(dict(role=role,detail='Conflicting selected per-side gusset support lengths'))
            continue
        groups={}
        for pid,p in parts.items():
            params=p.get('parameters',{})
            key=params.get('source_weld_id',pid)
            if p['kind']!='weld' or key!=expected:continue
            links=p.get('connects',[])
            if role=='gusset_base_weld' and not any(s in ('BASE','COLLAR','FOUNDATION') for s in links):continue
            if role=='gusset_beam_weld' and any(s in ('BASE','COLLAR','FOUNDATION') for s in links):continue
            candidates=gussets.intersection(links)
            if len(candidates)!=1 or pid not in actual_lines or str(params.get('weld_type','')).lower()!='fillet':
                issues.append(dict(role=role,part=pid,detail='Cannot locate a selected fillet path on one gusset'))
                continue
            groups.setdefault(next(iter(candidates)),[]).append((pid,actual_lines[pid]))
        if not groups:
            issues.append(dict(role=role,detail='No measured IFC trajectories for the selected two-sided gusset attachment'))
        for plate_id,paths in groups.items():
            if plate_id not in meshes:
                issues.append(dict(role=role,part=plate_id,detail='Actual gusset with two-sided fillets is missing'))
                continue
            facts,errors=both_faces(meshes[plate_id].transformed(instance),paths,next(iter(lengths),None))
            results.append(dict(role=role,gusset=plate_id,**facts))
            issues.extend(dict(row,role=role,gusset=plate_id) for row in errors)
    return results,issues
