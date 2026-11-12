"""Measure HR-selected plate constituents in the located assembly."""
import re

import numpy as np
from shapely.geometry import MultiPoint

from .anchor_pattern_readback import solid_faces


def grade(value):
    """Retain every plate grade declared by a material, including conditional alternatives."""
    grades=set()
    for match in re.finditer(r'\bA\s*(36|242|514|572|588|709|992)\b(?:\s*[- ,/]?\s*(?:GR(?:ADE)?\.?\s*)?(36|42|46|50|55|60|65|70|80|100)\b)?',str(value),re.I):
        spec,number=match.groups()
        grades.add('A'+spec+(' GR '+number if number else ''))
    return grades


def plate_group(role,parts):
    def belongs(p):
        name=p['id'].upper()
        desc=p.get('parameters',{}).get('description','').lower()
        if role=='grout':return p['kind']=='grout' or name=='GROUT'
        if p['kind']!='plate':return False
        if role=='base_plate':return name in ('P1','BP','BASE','BASE-PLATE','BASE_PLATE') or desc.strip()=='base plate'
        if role=='shear_plate':return name in ('P1','P2','TAB','TAB1','TAB2') or 'shear plate / erection tab' in desc
        if role=='cheek_plate':return 'CHEEK' in name or 'cheek plate' in desc
        if role=='clevis_plate':return 'CLEVIS' in name or 'clevis plate' in desc
        if role=='knife_plate':return 'KNIFE' in name or 'knife plate' in desc
        if role=='gusset':
            if p.get('parameters',{}).get('free_edge_bar'):return False
            return 'GUSSET' in name or desc.strip()=='gusset plate'
        return False
    return [p for p in parts if belongs(p)]


def dimensions(part):
    faces=solid_faces(part.get('geometry',{}))
    if not faces:return None
    points=np.vstack(faces)
    normals=[]
    for face in faces:
        n=np.cross(face,np.roll(face,-1,axis=0)).sum(axis=0)
        if (length:=np.linalg.norm(n))>1e-8:
            n=n/length
            if n[np.argmax(np.abs(n))]<0:n=-n
            normals.append(n)
    if not normals:return None
    directions=np.unique(np.round(normals,8),axis=0)
    spans=np.ptp(points@directions.T,axis=0)
    index=np.argmin(spans)
    normal=directions[index]
    seed=np.eye(3)[np.argmin(np.abs(normal))]
    u=np.cross(normal,seed)
    u=u/np.linalg.norm(u)
    v=np.cross(normal,u)
    rectangle=MultiPoint(points@np.array([u,v]).T).minimum_rotated_rectangle
    if rectangle.geom_type!='Polygon':return None
    quad=list(rectangle.exterior.coords)
    sizes=sorted(float(np.linalg.norm(np.subtract(a,b))) for a,b in zip(quad[:2],quad[1:3]))
    return dict(thickness=float(spans[index]),in_plane=sizes,local_points=np.unique(np.round(points,8),axis=0))


def verify_plates(fields,variants,parts,instance,materials,cache,template,check,tongues=()):
    roles=set()
    if 'base_plate_anchors' in variants:roles.update(('base_plate','grout'))
    if variants&{'single_plate_shear','two_plate_shear','two_plate_bolted','two_plate_beam_end'}:roles.add('shear_plate')
    if 'beam_pin_hinge' in variants:roles.update(('knife_plate','clevis_plate'))
    if 'brb_pinned' in variants:roles.add('cheek_plate')
    if variants&{'brb_pinned','brb_bolted','slotted_hss_gusset'}:roles.add('gusset')
    for role in sorted(roles):
        relevant={field:entries for (source_role,field),entries in fields.items() if source_role==role and entries}
        if not relevant:continue
        selected=plate_group(role,parts)
        ids=[p['id'] for p in selected]
        for rid,n in relevant.get('count',[]):
            check('selected_'+role+'_count',len(selected)==n,n,ids,rid)
        dims=[]
        for p in selected:
            key=(template,p['id'])
            if key not in cache:cache[key]=dimensions(p)
            dims.append(cache[key])
        for rid,target in relevant.get('thickness_in',[]):
            values=[row['thickness'] if row else None for row in dims]
            check('selected_'+role+'_thickness',bool(values) and all(v is not None and abs(v-target)<1e-4 for v in values),target,values,rid)
        if role=='base_plate':
            for rw,width in relevant.get('width_in',[]):
                for rl,length in relevant.get('length_in',[]):
                    target=sorted([width,length])
                    if tongues:
                        from shapely.geometry import Polygon
                        from shapely.ops import unary_union
                        from .base_tongue_readback import measure_polygon
                        evidence=[]
                        for p in selected:
                            faces=solid_faces(p.get('geometry',{}))
                            pieces=[q for face in faces if (q:=Polygon(face[:,:2])).is_valid and q.area>1e-8]
                            evidence.append(measure_polygon(unary_union(pieces),width,length,tongues))
                        check('selected_base_plate_plan_size',len(evidence)==1 and all(ok for _,ok in evidence),
                              {'stock_in':target,'tongues':tongues},[row for row,_ in evidence],rw if rw==rl else [rw,rl])
                        continue
                    measured=[row['in_plane'] if row else None for row in dims]
                    check('selected_base_plate_plan_size',bool(measured) and all(v is not None and np.allclose(v,target,rtol=0,atol=1e-4) for v in measured),
                          target,measured,rw if rw==rl else [rw,rl])
        if role=='shear_plate':
            x,y=np.asarray(instance.get('x_axis',[1.,0,0])),np.asarray(instance.get('y_axis',[0,1.,0]))
            up=np.array([x[2],y[2],np.cross(x,y)[2]])
            for rid,target in relevant.get('depth_in',[]):
                vals=[float(np.ptp(row['local_points']@up)) if row else None for row in dims]
                check('selected_shear_plate_depth',bool(vals) and all(v is not None and abs(v-target)<1e-4 for v in vals),
                      target,vals,rid)
        for rid,target in relevant.get('material',[]):
            desired=grade(target)
            if not desired:continue
            values=[grade(materials.get(p.get('material_id'),{}).get('specification','')) for p in selected]
            check('selected_'+role+'_steel_grade',bool(values) and all(v==desired for v in values),
                  sorted(desired),[sorted(v) for v in values],rid)
