"""Measure an HR-selected straight fold line against the actual brace cap and restrained IFC edges."""
import numpy as np

from .joint_mesh_readback import TOL,unit


def measure_fold_line(member,axis,origin,restraints,thickness,ratio):
    """The normal to the fold line points from this workpoint into the brace."""
    if not restraints or thickness<=0 or ratio<=0:
        raise ValueError('A selected fold line needs a positive gusset thickness, ratio and finite restraint')
    origin=np.asarray(origin,dtype=float)
    u=unit(axis)
    stations={part:float(np.max((np.asarray(points)-origin)@u)) for part,points in restraints.items()}
    governing=max(stations,key=stations.get)
    cap=float(np.min((member.vertices-origin)@u))
    line=stations[governing]
    return dict(controlling_restraint=governing,restraint_stations_in=stations,brace_end_in=cap,
                fold_line_in=line,clearance_in=cap-line,plate_thickness_in=float(thickness),
                selected_multiplier=float(ratio),required_in=float(ratio*thickness))


def selected_clearances(members,braces,member_fields,parts,placements,meshes,lines,rb,interfaces):
    inst,world=placements
    origin=world[:3,3]
    results=[]
    issues=[]
    for role,mid in braces.items():
        ratios=set(member_fields.get(mid,{}).get(('brace_end_clearance','depths'),[]))
        if not ratios:continue
        if len(ratios)!=1:
            issues.append(dict(member=mid,detail='No unique selected linear clearance at this occurrence'))
            continue
        ratio=next(iter(ratios))
        # An explicit center-crossing or other multibrace assembly can name its
        # own controlling welds. On an end connection identify the restrained
        # edges by their finite supporting weld and the other connected receiver.
        named=[s for s in interfaces if s.get('kind')=='linear_gusset_clearance' and s.get('brace')==role]
        attached={p for w in parts.values() if role in w.get('connects',[])
                  and w['kind'] in ('weld','bolt','pin') for p in w.get('connects',[])
                  if p in meshes and parts[p]['kind'] in ('plate','gusset') and
                  'gusset' in (p+' '+parts[p].get('parameters',{}).get('description','')).lower()}
        if named:
            attached.update(s['gusset'] for s in named)
        if not attached:
            issues.append(dict(member=mid,detail='The actual connected gusset with selected fold clearance is unlocated'))
        work=np.asarray(members[mid]['axis'],dtype=float)
        closest=int(np.argmin(np.linalg.norm(work-origin,axis=1)))
        axis=work[1-closest]-work[closest]
        for pid in sorted(attached):
            specified=[s for s in named if s['gusset']==pid]
            ids={key for key,p in parts.items() if p['kind']=='weld' and pid in p.get('connects',[])
                 and any((r in inst['bindings'] and r not in braces and inst['bindings'][r] in members) or
                         r.upper() in ('BEAM','COLUMN','BASE','SEAT','COLLAR','FOUNDATION')
                         for r in p.get('connects',[]) if r!=pid)}
            ids.update(k for s in specified for k in s['restrained_welds'])
            if (not ids or not ids.issubset(lines) or pid not in meshes or
                    any(parts[k]['kind']!='weld' or pid not in parts[k].get('connects',[]) or role in parts[k]['connects'] for k in ids)):
                issues.append(dict(member=mid,part=pid,detail='The IFC lacks a located restrained attachment or gusset for the selected fold line'))
                continue
            plate=meshes[pid]
            thickness=float(np.ptp(plate.vertices@plate.plate_normal))
            facts=measure_fold_line(rb.member(mid),axis,origin,{k:lines[k] for k in sorted(ids)},thickness,ratio)
            facts.update(member=mid,part=pid)
            results.append(facts)
            if facts['clearance_in']+TOL<facts['required_in']:
                issues.append(dict(facts,detail='Actual brace end lacks its selected linear fold clearance'))
    return results,issues
