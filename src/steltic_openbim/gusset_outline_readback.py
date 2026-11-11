"""Compare the free edge and transfer section with actual IFC attachments."""
from collections import defaultdict
import numpy as np
from shapely import union_all
from shapely.geometry import LineString,MultiPoint,Point,Polygon

from .joint_mesh_readback import TOL,cross_section,frame,transform,unit


def measure_outline(plate,arms,support):
    contour,_,axes,lo,hi=cross_section(plate,plate.plate_normal)
    if contour.geom_type!='Polygon':raise ValueError('Actual gusset lacks a single finite planar contour')
    outer=Polygon(contour.exterior)
    projection=np.asarray(axes).T
    t=hi-lo
    available=[]
    findings=[]
    envelopes=[]
    for arm in arms:
        u=unit(arm['axis'])
        v=unit(np.cross(plate.plate_normal,u))
        if abs(u@plate.plate_normal)>TOL:
            raise ValueError('Brace workline is outside the plate plane')
        uv_u,uv_v=u@projection,v@projection
        runs=arm['paths']
        if not runs:raise ValueError('Selected brace has no actual finite attachment curves')
        all_points=np.vstack(runs)
        ends=[]
        for run in runs:
            at=np.asarray(run)@u
            ends.append(run[int(np.argmin(at))])
        if np.ptp(np.asarray(ends)@u)>TOL:
            raise ValueError('Selected slotted transfer has no common joint-side weld-end station')
        centre=np.mean(ends,axis=0)@projection
        witnesses=list(np.asarray(support)@projection) if len(support) else []
        if arm['fitted'] and not witnesses:
            raise ValueError('Fitted free contour has no measured finite support edge or contact')
        for p in all_points@projection:
            witnesses.extend((p+t*uv_u,p-t*uv_u,p+t*uv_v,p-t*uv_v))
        if arm.get('width') is not None:
            width=arm['width']
            span=max(outer.bounds[2]-outer.bounds[0],outer.bounds[3]-outer.bounds[1],width)*2+1
            cut=outer.intersection(LineString([centre-span*uv_v,centre+span*uv_v]))
            segments=list(cut.geoms) if hasattr(cut,'geoms') else [cut]
            at=[s for s in segments if s.geom_type=='LineString' and s.distance(Point(centre))<=TOL]
            sides=[0.,0.]
            if len(at)==1:
                coordinates=(np.asarray(at[0].coords)-centre)@uv_v
                sides=[float(-min(coordinates)),float(max(coordinates))]
            available.append(dict(member=arm['member'],width_in=width,available_sides_in=sides))
            left,right=centre-width*uv_v/2,centre+width*uv_v/2
            if min(sides)+TOL<width/2:
                findings.append(dict(member=arm['member'],detail='Selected Whitmore width exceeds the available material at the transfer section',
                                     selected_width_in=width,available_sides_in=sides))
            witnesses.extend((left,right))
        if arm['fitted']:envelopes.append(MultiPoint(witnesses).convex_hull)
    metrics=dict(transfer_sections=available,plate_area_in2=float(outer.area))
    if envelopes:
        if len(envelopes)!=len(arms):
            raise ValueError('Shared free-edge policy does not account for all connected arms')
        allowed=union_all(envelopes)
        excess=float(outer.difference(allowed.buffer(TOL)).area)
        metrics.update(unsupported_area_in2=excess,arm_count=len(arms))
        if excess>TOL*max(1.,outer.length):
            extension=max(Point(p).distance(allowed) for p in outer.exterior.coords)
            findings.append(dict(detail='Actual adopted free contour extends past its supporting and transfer regions',
                                 unsupported_area_in2=excess,maximum_extra_projection_in=float(extension)))
    return metrics,findings


def verify_outlines(check,connections):
    from .ifc_assembly_verification import selected
    inventory={(r.connection,r.part):r for r in check.owned_gussets}
    templates={c['id']:check.templates[c['assembly_instance']['template_id']] for c in connections if c.get('assembly_instance')}
    canonical_parts={key:next(p for p in templates[key[0]]['parts'] if p['id']==key[1]) for key in inventory}
    groups=defaultdict(lambda:dict(arms=[],support=[]))
    failures=[]
    for c in connections:
        inst=c.get('assembly_instance')
        if not inst:continue
        template=check.templates[inst['template_id']]
        parts={p['id']:p for p in template['parts']}
        owners={k:(c['id'],k) for k,p in parts.items() if p.get('parameters',{}).get('free_contour_rule')=='slotted_attachment_hull'}
        for ref in (c.get('parameters') or {}).get('shared_constituents',[]):
            key=(ref['owner_connection_id'],ref['owner_part_id'])
            if key in inventory:owners[ref['role']]=key
        receivers={k:m for k,m in inst['bindings'].items() if m in check.members and
                   check.members[m]['kind'] in ('brace','truss_web','diagonal','lateral_strut')}
        if not receivers:continue
        matrix=frame(inst['origin'],inst['x_axis'],inst['y_axis'])
        actual=None
        def trajectory(part):
            nonlocal actual
            if actual is None:actual=check.rb.curves(c['id'])
            ref=transform(part['geometry']['points'],matrix)
            matches=[q for q in actual if q.shape==ref.shape and
                     min(np.max(np.abs(q-ref)),np.max(np.abs(q[::-1]-ref)))<=TOL]
            if len(matches)!=1:raise ValueError('Missing or duplicated finite IFC weld '+part['id'])
            return matches[0]
        try:
            for role,mid in receivers.items():
                m=check.members[mid]
                fields=selected(check.handoff,c['id'],mid,check.profiles.get(m['profile_id']))
                widths=set(fields.get(('gusset','whitmore_effective_width_in'),[]))
                if len(widths)>1:raise ValueError('Unresolved selected effective widths for '+mid)
                # Some primary shared assemblies also bind the second brace for
                # the overall component. Its originating end owns its welds.
                welds=[p for p in parts.values() if p['kind']=='weld' and role in p.get('connects',[])
                       and ('GUSSET' in p['connects'] or any(t in owners for t in p['connects']))]
                if not welds:continue
                pids={t for p in welds for t in p['connects'] if t in owners or (t=='GUSSET' and widths)}
                for pid in pids:
                    key=owners.get(pid,(c['id'],pid))
                    if key not in inventory:raise ValueError('No actual owner of gusset '+str(key))
                    entity=inventory[key]
                    canonical=canonical_parts[key]
                    fitted=canonical.get('parameters',{}).get('free_contour_rule')=='slotted_attachment_hull'
                    if not fitted and not widths:continue
                    axes=np.asarray(m['axis'],dtype=float)
                    i=int(np.argmin(np.linalg.norm(axes-c.get('point',inst['origin']),axis=1)))
                    paths=[trajectory(p) for p in welds if pid in p['connects']]
                    groups[key]['arms'].append(dict(member=mid,axis=axes[1-i]-axes[i],paths=paths,
                        width=next(iter(widths),None),fitted=fitted))
                    support=[p for p in parts.values() if p['kind']=='weld' and pid in p.get('connects',[])
                             and p.get('parameters',{}).get('source_weld_id',p['id']) in ('WGB','WGC')]
                    groups[key]['support'].extend(q for p in support for q in trajectory(p))
                    for s in template.get('source_interfaces',[]):
                        if s.get('kind')!='contact' or pid not in s.get('connects',[]) or not s.get('segment_in'):continue
                        bound=[inst['bindings'].get(v) for v in s['connects'] if v!=pid]
                        if len(bound)!=1 or bound[0] not in check.rb.members:raise ValueError('Unlocated supporting contact')
                        line=transform(s['segment_in'],matrix)
                        host=check.rb.member(bound[0])
                        if any(max(host.point_distance(q),entity.world.point_distance(q))>TOL for q in line):
                            raise ValueError('Selected outline support contact is unseated')
                        groups[key]['support'].extend(line)
        except (KeyError,ValueError,RuntimeError,IndexError,AttributeError,TypeError) as exc:
            failures.append(dict(code='gusset_free_contour_unverified',connection=c['id'],sheet=c.get('drawing_ref'),detail=str(exc)))
    results=[]
    for key,items in groups.items():
        placed=inventory[key]
        context=dict(connection=placed.connection,part=placed.part,sheet=placed.sheet)
        try:
            facts,issues=measure_outline(placed.world,items['arms'],items['support'])
            results.append(dict(context,**facts))
            failures.extend(dict(context,code='gusset_attachment_outline_differs',**row) for row in issues)
        except (ValueError,RuntimeError,IndexError,AttributeError) as exc:
            failures.append(dict(context,code='gusset_free_contour_unverified',detail=str(exc)))
    return results,failures
