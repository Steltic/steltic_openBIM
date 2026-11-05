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
    from .review_cfs6_endpoint_links import bind as cfs6_endpoint_links
    cfs6_endpoint_links(model)
    if model['pilot'].startswith('cfs'):
        from .review_source_clauses import apply as source_clauses
        source_clauses(model,package)
        from .review_cfs6_floor_references import apply as source_floor_references
        source_floor_references(model)
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
        if family=='review_sbmf_floor':
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters['actual_floor_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),64 if shape_parameters['purpose']=='transfer' else 18) for m in ms])
        if family=='review_sbmf_deck':
            from .review_cfs_wall_bindings import local_member,signature
            import math
            extent=max(math.sqrt(sum(v*v for v in f['point_relative'])) for f in shape_parameters['fasteners'])+2
            shape_parameters['actual_folded_deck_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),extent) for m in ms])
        if family in ('review_deck_screws','review_deck_block_link','review_wsp_block','review_wsp_screws','review_roof_bottom_strap'):
            from .review_cfs_wall_bindings import local_member,signature
            import math
            extent=max((math.sqrt(sum(v*v for v in q)) for q in shape_parameters.get('points_relative',[])),default=8)+2
            shape_parameters['actual_deck_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),extent) for m in ms])
        if family in ('review_collector_bond','review_collector_lap'):
            from .review_cfs_wall_bindings import local_member,signature
            from .review_receiver_geometry import horizontal_frame
            from .pilots.model import sub
            import math
            frame=horizontal_frame(sub(ms[0]['axis'][1],ms[0]['axis'][0]))
            extent=shape_parameters.get('context_extent_in',shape_parameters['lap_in']/2+12 if family=='review_collector_lap' else math.dist(*ms[0]['axis'])/2+.01)
            shape_parameters['actual_reinforcement_receivers']=signature([local_member(m,c['point'],frame,extent) for m in ms])
        if any(shape_parameters.get(k) for k in ('actual_sbmf_wall','actual_sbmf_girt','actual_sbmf_restraint','actual_sbmf_roof','actual_sbmf_header','actual_cfs_strut_end','actual_cfs_endwall_girt','actual_cfs_door_header','actual_cfs_cross_plate','actual_cfs_endwall_head')) or family=='review_sbmf_joint':
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters['actual_cfs_endwall_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),30) for m in ms])
        if shape_parameters.get('actual_cfs_kicker'):
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters['actual_cfs_kicker']={k:v for k,v in shape_parameters['actual_cfs_kicker'].items() if k not in ('foot_face_x','foot_centre_y')}
            shape_parameters['actual_cfs_kicker_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),50) for m in ms])
        if family=='review_roof_seat' and model['pilot'].startswith('hr'):
            from .review_cfs_wall_bindings import local_member,signature
            from .pilots.model import sub,unit,cross
            import math
            chord=next(m for m in ms if m['kind']=='truss_chord')
            away=sub(max(chord['axis'],key=lambda q:math.dist(q,c['point'])),c['point'])
            y=unit([away[0],away[1],0]);frame=(cross(y,[0,0,1]),y,[0,0,1])
            shape_parameters['actual_hr_roof_seat_receivers']=signature([local_member(m,c['point'],frame,30 if m is chord else 24) for m in ms if m is chord or m['kind'] in ('beam','girder','moment_beam','rafter')])
        if shape_parameters.get('actual_composite_core'):
            from .review_cfs_wall_bindings import local_member,signature
            from .review_receiver_geometry import horizontal_frame
            from .pilots.model import unit,sub,mul
            import math
            purpose=shape_parameters['purpose']
            direction=[1,0,0] if shape_parameters['direction']=='X' else [0,1,0]
            frame=horizontal_frame(mul(unit(sub(*ms[0]['axis'][::-1])),1 if shape_parameters['end']==0 else -1)) if purpose=='coupling' else horizontal_frame(direction)
            extent=76 if purpose=='base' else (max(math.dist(*m['axis']) for m in ms)+72 if purpose in ('corner','closure') else 36 if purpose=='coupling' else 12 if purpose in ('splice','cap') else 7)
            core_receivers=[]
            for m in ms:
                item=local_member(m,c['point'],frame,extent)
                # Slot positions are relative to the actual start, including
                # the embedded base. Two equal wall profiles can have different
                # coupling-flange cuts in this extract.
                actual_start=[x+y for x,y in zip(m['axis'][0],m['end_offsets'][0])]
                u=unit(sub(*m['axis'][::-1]));station=sum((x-y)*z for x,y,z in zip(c['point'],actual_start,u))
                item['source_slots']=[dict(slot,start_in=slot['start_in']-station,end_in=slot['end_in']-station) for slot in m.get('slots',[]) if slot['start_in']<station+extent and slot['end_in']>station-extent]
                core_receivers.append(item)
            shape_parameters['actual_core_receivers']=signature(core_receivers)
        if shape_parameters.get('actual_double_top_track'):
            from .review_cfs_wall_bindings import local_member,signature
            from .review_receiver_geometry import horizontal_frame
            frame=horizontal_frame([1,0,0] if shape_parameters['direction']==0 else [0,1,0])
            shape_parameters['actual_track_receivers']=signature([local_member(m,c['point'],frame,24) for m in ms])
        if shape_parameters.get('actual_crc'):
            from .review_cfs_wall_bindings import local_member,signature
            from .review_receiver_geometry import horizontal_frame
            from .pilots.model import sub,unit,dot,add
            frame=horizontal_frame([1,0,0] if shape_parameters['direction']==0 else [0,1,0])
            extent=150 if shape_parameters['purpose']=='anchor' else 8
            data=[]
            for m in ms:
                row=local_member(m,c['point'],frame,extent)
                station=dot(sub(c['point'],add(m['axis'][0],m['end_offsets'][0])),unit(sub(*m['axis'][::-1])))
                row['slots']=[dict(slot,start_in=slot['start_in']-station,end_in=slot['end_in']-station) for slot in m.get('slots',[]) if slot['start_in']<station+extent and slot['end_in']>station-extent]
                for slot in row['slots']:slot.pop('connection_id',None)
                data.append(row)
            shape_parameters['actual_crc_receivers']=signature(data)
        if shape_parameters.get('actual_source_floor') or shape_parameters.get('actual_chord_floor'):
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters['actual_floor_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),24) for m in ms])
        if shape_parameters.get('actual_diaphragm') or shape_parameters.get('actual_roof_distribution'):
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters['actual_diaphragm_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),40) for m in ms])
        if shape_parameters.get('actual_gable_brace') or shape_parameters.get('actual_gable_secondary'):
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters.pop('primary_origin',None)
            shape_parameters['actual_gable_brace_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),70) for m in ms])
        if shape_parameters.get('actual_rod_end') or shape_parameters.get('actual_rod_adjuster'):
            from .review_cfs_wall_bindings import local_member,signature
            shape_parameters['actual_rod_receivers']=signature([local_member(m,c['point'],([1,0,0],[0,1,0],[0,0,1]),70) for m in ms])
        if shape_parameters.get('actual_crane_joint'):
            from .review_cfs_wall_bindings import local_member,signature
            from .review_receiver_geometry import horizontal_frame
            from .pilots.model import sub
            frame=horizontal_frame(sub(*ms[0]['axis'][::-1])) if shape_parameters['actual_crane_joint']=='bracket' else ([1,0,0],[0,1,0],[0,0,1])
            shape_parameters['actual_crane_receivers']=signature([local_member(m,c['point'],frame,48) for m in ms])
        if shape_parameters.get('actual_gable_knee') or shape_parameters.get('actual_bearing_cap'):
            from .review_receiver_geometry import horizontal_frame
            from .review_cfs_wall_bindings import local_member,signature
            from .pilots.model import sub
            direction=ms[0] if shape_parameters.get('actual_gable_knee') else ms[1]
            frame=horizontal_frame(sub(*direction['axis'][::-1]))
            shape_parameters['actual_gable_receivers']=signature([local_member(m,c['point'],frame,60) for m in ms])
        if shape_parameters.get('actual_endwall_head') or shape_parameters.get('actual_endwall_base'):
            from .review_cfs_wall_bindings import local_member,signature
            from .pilots.model import cross
            n=shape_parameters.get('actual_endwall_head',{}).get('normal',ms[0]['local_y'])
            frame=(cross(n,[0,0,1]),n,[0,0,1])
            shape_parameters['actual_endwall_receivers']=signature([local_member(m,c['point'],frame,48) for m in ms])
        if shape_parameters.get('actual_parapet'):
            from .review_cfs_wall_bindings import local_member,signature
            frame=([1,0,0],[0,1,0],[0,0,1])
            shape_parameters['actual_parapet_receivers']=signature([local_member(m,c['point'],frame,44) for m in ms])
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
