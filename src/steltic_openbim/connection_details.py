"""Occurrence-to-assembled-detail mapping; no silent unsupported-detail fallback."""
from collections import defaultdict
import hashlib
import json
from .assembly_templates import build_scene


def subtype(connection,members):
    family=connection['detail_ref']['id'];kinds={m['kind'] for m in members}
    if family in ('review_cfs_post','review_sliding_post'):
        return 'base' if abs(connection['point'][2]-min(p[2] for p in members[0]['axis']))<.1 else 'top'
    if family=='review_cfs_sill':return 'ground' if members[0].get('level',1)==1 else 'floor'
    if family=='test_guard':return 'rail-joint' if 'guard_rail' in kinds or connection['point'][2]>min(p[2] for m in members for p in m['axis'])+.1 else 'post-base'
    if family=='test_walkway_support':return 'beam-seat' if 'walkway_edge_beam' in kinds or connection['point'][2]>1 else 'post-base'
    if family=='hr_column_base':return 'embedded' if any(m['profile_id'].startswith('W36') for m in members) else 'exposed'
    if family=='cfs_scheduled_endwall_post':return 'post-base' if connection['point'][2]<1 else 'post-top'
    if family=='test_wall_opening':
        if kinds=={'opening_jamb'}:return 'jamb-base' if abs(connection['point'][2]-min(p[2] for m in members for p in m['axis']))<.1 else 'jamb-head'
    return ''


def prepare(model,package):
    """Build each distinct source/profile/story variant and remap every occurrence.

    Same geometry repeated at many locations shares a detail. A story-dependent
    bracket/rod or floor-shear connection cannot borrow another story's parameters.
    """
    from .review_cfs_occurrences import bind
    if model['pilot'].startswith('cfs'):
        # Opening face cuts change actual member endpoints. Take the floor and
        # wall receiver extracts after those cuts, not from a stale workpiece.
        from .review_floor_openings import bind as opening_bind
        opening_bind(model)
        from .review_cfs_wall_bindings import bind as wall_bind
        wall_bind(model)
    bind(model)
    if model['pilot'].startswith('cfs'):
        from .review_source_clauses import apply as source_clauses
        source_clauses(model,package)
    members={m['id']:m for m in model['members']};groups=defaultdict(list)
    truss_nodes=defaultdict(set)
    for m in model['members']:
        if 'truss' in m['kind']:
            for point in m['axis']:truss_nodes[tuple(round(v,4) for v in point)].add(m['id'])
    if model.get('pilot')=='cfs8' and not any(c['detail_ref']['id']=='test_roof_hanger' for c in model['connections']):
        girders=[m for m in model['members'] if m['kind']=='girder_truss' and all(abs(p[2]-468)<.01 for p in m['axis'])]
        for point,mids in sorted(truss_nodes.items()):
            if abs(point[1]-1008)>.01 or abs(point[2]-468)>.01 or not 564<=point[0]<=1116:continue
            heads=[mid for mid in mids if 'TEST-HEAD-' in mid]
            support=next((m for m in girders if min(p[0] for p in m['axis'])-.01<=point[0]<=max(p[0] for p in m['axis'])+.01),None)
            if not heads or support is None:continue
            model['connections'].append(dict(id='TEST-ROOF-HANGER-'+str(point[0]),point=list(point),member_ids=heads+[support['id']],detail_ref={'id':'test_roof_hanger'},design_record_ids=[],parts=[],basis='A',assumption_id='CFS8-ROOF-INTERFACE'))
    for c in model['connections']:
        if c['detail_ref']['id']=='test_roof_truss':
            primary=members[c['member_ids'][0]];delta=[primary['axis'][1][i]-primary['axis'][0][i] for i in (0,1)]
            plane=1 if abs(delta[0])>=abs(delta[1]) else 0
            adjacent=truss_nodes[tuple(round(v,4) for v in c['point'])]
            prefix=primary['id'].rsplit('-',1)[0]
            c['member_ids']=sorted(set(c['member_ids'])|{mid for mid in adjacent if mid.rsplit('-',1)[0]==prefix})
        ms=[members[i] for i in c['member_ids']];family=c['detail_ref']['id']
        story=ms[0].get('level',1) if any(t in family for t in ('chord','hold_down','collector','squash','rim','floor_stack')) or family in ('review_cfs_floor','review_cfs_sill') else 0
        angles=()
        if family in ('test_roof_truss','review_truss_node','review_truss_heel','review_stmf_node','review_stmf_end','review_portal_joint','review_canopy_knee','review_canopy_brace','review_transfer_truss','review_brace_crossing'):
            vectors=[]
            for m in ms:
                far=max(m['axis'],key=lambda p:sum((p[i]-c['point'][i])**2 for i in range(3)))
                vector=[far[i]-c['point'][i] for i in range(3)];length=sum(v*v for v in vector)**.5
                if length>1e-8:vectors.append(tuple(round(v/length,5) for v in vector))
            angles=tuple(sorted(vectors))
        # Occurrence identity is provenance, not a shape parameter. In particular,
        # equal stud layouts on different beams share a drawing detail while the
        # source-beam identity remains on every actual connection occurrence.
        shape_parameters={k:v for k,v in c.get('parameters',{}).items() if k not in ('original_physical_member_id','source_releases')}
        if family in ('test_roof_truss','review_truss_node','review_truss_heel'):
            from .truss_node_geometry import receivers
            # A piece trimmed at a nearby opening cannot borrow the longer
            # standard node's screw stations or local member extent.
            from .review_cfs_wall_bindings import signature as receiver_shape
            shape_parameters['physical_truss_receivers']=receiver_shape(receivers(ms,c['point']))
        if family=='review_splice':
            # Equal W designations do not imply that both actual shafts have
            # full-height boxing. This changes the receiver list itself.
            shape_parameters['actual_shaft_boxing']=[dict(profile=m['profile_id'],thickness=m.get('boxing_thickness_in'),width=m.get('boxing_width_in')) for m in ms if m['kind']=='column']
        if family=='review_chamfer':
            # Opposite corners can be reflections, not rotations about global
            # up. Preserve beam direction in the actual column frame so sharing
            # a detail cannot require turning its below-TOS beam upside down.
            from .pilots.model import sub,unit,dot,cross
            column=next(m for m in ms if m['kind']=='column')
            ray=unit(sub(max(ms[0]['axis'],key=lambda p:sum((p[i]-c['point'][i])**2 for i in range(3))),c['point']))
            cy=column['local_y'];cx=cross(cy,[0,0,1])
            shape_parameters['chamfer_direction']=[round(dot(ray,v),6) for v in (cx,cy)]
        from .review_cfs_wall_bindings import signature
        for name in ('physical_opening_joint','physical_wall_attachment','physical_floor_stack','physical_jamb_base','physical_wall_strap'):
            if name in shape_parameters:shape_parameters[name]=signature(shape_parameters[name])
        if 'physical_stud_support' in shape_parameters:
            shape_parameters['physical_stud_support']={k:v for k,v in shape_parameters['physical_stud_support'].items() if k!='member_id'}
        if 'physical_hr_kicker' in shape_parameters:
            shape_parameters['physical_hr_kicker']={k:v for k,v in shape_parameters['physical_hr_kicker'].items() if not k.endswith('_id')}
        if shape_parameters.get('physical_plan_brace'):
            from .review_plan_bracing import shape
            shape_parameters['physical_plan_receivers']=shape(ms,c['point'])
        if 'core_face_attachment' in shape_parameters:
            shape_parameters['core_face_attachment']={k:v for k,v in shape_parameters['core_face_attachment'].items() if k!='wall_id'}
        if family in ('review_beam','review_existing_joint','review_crane_bracket','review_pin_beam','hr_simple_shear_plate'):
            from .pilots.model import sub,unit,dot
            column=next((m for m in ms if m['kind'] in ('column','walkway_post','prop')),None)
            if column:
                beam_axis=unit(sub(ms[0]['axis'][1],ms[0]['axis'][0]))
                shape_parameters['support_weak_axis']=abs(dot(beam_axis,column['local_y']))>.7
        parameters=json.dumps(shape_parameters,sort_keys=True,separators=(',',':'))
        if family=='test_floor_opening':
            # Equal section names do not imply equal connection datums. A
            # centroid-based perimeter and a TOS-based infill need distinct fits.
            parameters+=json.dumps([(m['id']==ms[0]['id'],m['kind'],m['profile_id'],
                round(m['axis'][0][2]+m.get('end_offsets',[[0,0,0]])[0][2]-c['point'][2],6)) for m in ms])
        key=(family,subtype(c,ms),tuple(sorted((m['kind'],m['profile_id']) for m in ms)),tuple(sorted(c.get('design_record_ids',[]))),story,angles,parameters)
        groups[key].append(c)
    assemblies=[];details=[];refs=defaultdict(set)
    for i,(key,cs) in enumerate(sorted(groups.items())):
        representative=max(cs,key=lambda c:len(c.get('parts',[])))
        scene=build_scene(model,package,representative,key[1]);number=f'C{i+1:03}';ref='1/'+number
        scene.update(id=f'CD{i+1:03}',sheet=number,reference=ref,occurrences=[c['id'] for c in cs],occurrence_count=len(cs))
        scene['geometry_sha256']=hashlib.sha256(json.dumps(scene,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        assemblies.append(scene);details.append(dict(id=scene['id'],family=key[0],number=1,sheet=number,reference=ref,variant=i+1,occurrences=len(cs)))
        for c in cs:
            c['drawing_ref']=ref;c['assembly_id']=scene['id']
            for mid in c['member_ids']:refs[mid].add(ref)
    for m in model['members']:m['connection_refs']=sorted(refs[m['id']])
    for row in model['member_schedule']:row['connection_refs']=sorted({r for mid in row['member_ids'] for r in refs[mid]})
    model['details']=details;model['connection_assemblies']=assemblies
    model['connection_detailing']='assembled members, plates, fastener groups and weld interfaces; source-bound variants'
    return assemblies
