"""Check brace gussets against the hardware owned by the located column base."""
from collections import defaultdict
import numpy as np

from .joint_mesh_readback import TOL, common_plate_section


def located(connection,joints):
    """Where a connection is and what it joins. The contract locates it by its joint and bindings;
    `point` and `member_ids` are optional copies of that."""
    frame=connection.get('assembly_instance',{})
    point=connection.get('point') or joints.get(connection.get('joint_id'),{}).get('point') or frame.get('origin')
    members=connection.get('member_ids') or list(frame.get('bindings',{}).values())
    if point is None:raise ValueError('Connection has no located joint: '+str(connection.get('id')))
    return tuple(point),members


def check(checker):
    near=defaultdict(list)
    joints={j['id']:j for j in checker.physical.get('joints',[])}
    for item in checker.owned_gussets:
        c=checker.connections[item.connection]
        if c.get('parameters',{}).get('joint')!='base':continue
        point,members=located(c,joints)
        for mid in members:
            if checker.members.get(mid,{}).get('kind')=='column':
                near[mid,point].append(item)
    checked=0;issues=[]
    for base in checker.connections.values():
        if not near:break
        point,members=located(base,joints)
        targets=[g for mid in members for g in near.get((mid,point),[])
                 if g.connection!=base['id']]
        instance=base.get('assembly_instance')
        if not targets or not instance:continue
        tid=instance['template_id'];parts={p['id']:p for p in checker.templates[tid]['parts']}
        hardware={p['id'] for p in parts.values() if p['kind']=='anchor' or
                  (p['kind']=='plate' and 'washer' in (p['id']+' '+p.get('parameters',{}).get('description','')).lower())}
        if not hardware:continue
        try:
            _,raw,matrix=checker.rb.mesh(checker.rb.assemblies[base['id']])
            locators={r['id']:r for r in checker.rb.ranges[tid]}
            for pid in sorted(hardware):
                locator=locators[pid];count=locator['face_count']
                if not count:raise ValueError('Missing actual steel for '+pid)
                mesh=raw.subset(locator['face_start'],count).transformed(matrix)
                lo,hi=mesh.vertices.min(0),mesh.vertices.max(0)
                for gusset in targets:
                    checked+=1
                    a,b=gusset.bounds
                    if np.min(np.minimum(b,hi)-np.maximum(a,lo))<=TOL:continue
                    hit=common_plate_section(gusset.world,mesh)
                    if hit:
                        issues.append(dict(code='base_hardware_intersects_gusset',connection=gusset.connection,
                            sheet=gusset.sheet,gusset=gusset.part,base_connection=base['id'],hardware=pid,**hit))
        except (ValueError,RuntimeError,KeyError,IndexError) as exc:
            issues.append(dict(code='base_hardware_clearance_unverified',base_connection=base['id'],detail=str(exc)))
    return checked,issues
