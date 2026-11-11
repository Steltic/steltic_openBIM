"""Project corrected detail scenes through the saved, located HR receiver frames."""
import copy
import hashlib
import math
import re
from collections import defaultdict
from . import bim_assemblies
from .assembly_templates import build_scene
from .drawing_workflow import fingerprint
from .hr_detail_selections import beam_family, selected_fields, SelectionConflict
from .pilots.model import add,sub,mul,dot,unit


def material_for(part,kind,old,materials,record_ids):
    selected=part.get('selected_material')
    if kind=='grout':
        candidates=[m for m in materials.values() if 'grout' in m.get('source_item','').lower()]
        if len(candidates)==1:
            return candidates[0]['id']
        selected='Grout; source grade unspecified'
    if selected:
        spec=str(selected)
        candidates=[m for m in materials.values() if m.get('specification')==spec]
        if kind=='pin' and '4140' in spec:
            candidates += [m for m in materials.values() if 'pin' in m.get('source_item','').lower()
                           and '4140' in m.get('specification','') and 'A572' not in m['specification']]
        if candidates:
            return candidates[0]['id']
        mid='selected-'+kind+'-'+hashlib.sha256(spec.encode()).hexdigest()[:14]
        materials.setdefault(mid,dict(id=mid,specification=spec,source_item=kind,
            basis='S: HR selection for this constituent',source_record_ids=record_ids))
        return mid
    if old:
        return old['material_id']
    # New geometric constituents use the retained material selection for the
    # corresponding source role. A mixed catalog is not a single selection.
    candidates=[m for m in materials.values()
                if kind in m.get('source_item','').lower() and m['id'].startswith('gold-material-')]
    if len(candidates)==1:
        return candidates[0]['id']
    raise ValueError('No selected material for '+kind+' '+part['id'])


def native_parts(scene,old_template,materials):
    old_parts={p['id']:p for p in old_template['parts']}
    baseline_by_kind=defaultdict(list)
    for p in old_template['parts']:
        baseline_by_kind[p['kind']].append(p)
    result=[]
    for part in scene['parts']:
        if part.get('representation_role')=='context_only':
            continue
        if part.get('member') and part.get('representation_role')!='assembly_component':
            continue
        if part.get('bound_panel_id'):
            continue
        group=part['id']
        count=part.get('count',1)
        if count<=0 or len(part['faces'])%count:
            raise ValueError('Invalid constituent mesh count for '+group)
        span=len(part['faces'])//count
        for i in range(count):
            pid=group if count==1 else f'{group}:{i+1}'
            old=old_parts.get(pid)
            kind=part.get('functional_kind') or ('grout' if group.upper()=='GROUT' else None)
            if kind is None:
                kind=old['kind'] if old else ('screw' if part.get('screw') else 'bolt') if part['kind']=='fastener' else part['kind']
            predecessor=old
            if predecessor is None and kind=='plate':
                predecessor=old_parts.get('GUSSET') or old_parts.get('P1')
            if predecessor is None and len({p['material_id'] for p in baseline_by_kind[kind]})==1:
                predecessor=baseline_by_kind[kind][0]
            mid=material_for(part,kind,predecessor,materials,scene['source_record_ids'])
            parameters=dict(old.get('parameters',{})) if old else {}
            parameters.update(part.get('parameters',{}))
            parameters.update(description=part['description'],basis=part['basis'],source_group_id=group,group_count=count)
            for field in ('diameter','grip','thickness','holes','selected_material'):
                if field in part:parameters[field]=part[field]
            if part['kind']=='fastener':
                parameters.update(count=1,point=part['points'][i],axis=part['axis'])
            geometry={'type':'mesh','faces':part['faces'][i*span:(i+1)*span]}
            result.append(dict(id=pid,kind=kind,geometry=geometry,material_id=mid,parameters=parameters,
                               source_basis=part['basis'],connects=part.get('connects',[])))
    for weld in scene['welds']:
        old=old_parts.get(weld['id'])
        if old is None and weld['id'].endswith('-B'):old=old_parts.get(weld['id'][:-2])
        if old is None and baseline_by_kind['weld']:old=baseline_by_kind['weld'][0]
        mid=material_for(weld,'weld',old,materials,scene['source_record_ids'])
        params=dict(weld_type=weld['kind'],size_in=weld['size'] if weld['kind'] in ('fillet','PJP') else None,
                    basis=weld['basis'],description=weld['description'])
        params.update({k:weld[k] for k in ('source_weld_id','segment_index','selected_total_length_in','segment_count',
                                           'attachment_role','available_edge_length_in') if k in weld})
        result.append(dict(id=weld['id'],kind='weld',material_id=mid,connects=weld['connects'],
            geometry=dict(type='polyline',points=[weld['a'],weld['b']]),
            parameters=params))
    return result


def local_point(world,frame):
    v=sub(world,frame['origin'])
    return [dot(v,x) for x in (frame['x_axis'],frame['y_axis'],bim_assemblies.cross(frame['x_axis'],frame['y_axis']))]


def receivers(scene,old_template,frame,members,c):
    old={r['id']:r for r in old_template['receivers']}
    result=[];bindings={}
    for part in scene['parts']:
        role=part['id']
        if part.get('representation_role') in ('assembly_component','context_only'):
            continue
        if not part.get('member'):
            if role in old and old[role]['kind']!='member':
                result.append(old[role]);bindings[role]=frame['bindings'][role]
            continue
        local=part['member']
        world=[bim_assemblies.transformed(q,frame) for q in local['axis']]
        candidates=list(dict.fromkeys([frame['bindings'].get(role),*frame['bindings'].values(),*c['member_ids']]))
        if part.get('located_extension'):
            candidates.extend(m['id'] for m in members.values() if m['profile_id']==local['profile_id'] and m['id'] not in candidates)
        options=[]
        for mid in candidates:
            m=members.get(mid)
            if not m or m['profile_id']!=local['profile_id']:continue
            ends=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
            axis=unit(sub(ends[1],ends[0]));length=math.dist(*ends)
            project=[dot(sub(q,ends[0]),axis) for q in world]
            off=max(math.dist(q,add(ends[0],mul(axis,s))) for q,s in zip(world,project))
            if off>.02:continue
            clipped=[max(0.,min(length,s)) for s in project]
            if abs(clipped[1]-clipped[0])<1e-5:continue
            score=off+sum(abs(a-b) for a,b in zip(project,clipped))
            options.append((score,mid,m,ends[0],axis,clipped))
        if not options:
            raise ValueError('No aligned physical receiver for '+c['id']+' '+role)
        _,mid,m,start,axis,stations=min(options,key=lambda row:row[0])
        if part.get('located_extension') and mid not in c['member_ids']:
            c['member_ids'].append(mid)
        points=[local_point(add(start,mul(axis,s)),frame) for s in stations]
        y=[dot(m['local_y'],v) for v in (frame['x_axis'],frame['y_axis'],bim_assemblies.cross(frame['x_axis'],frame['y_axis']))]
        bindings[role]=mid
        result.append(dict(id=role,kind='member',profile_id=m['profile_id'],axis=points,local_y=y,
                           source_context_axis=local['axis']))
    for role,receiver in old.items():
        if receiver['kind']!='member' and role not in bindings:
            result.append(receiver);bindings[role]=frame['bindings'][role]
    return result,bindings


def crop_existing_receivers(receivers,frame,members):
    result=[]
    for original in receivers:
        mid=frame['bindings'].get(original['id'])
        member=members.get(mid,{})
        if original['kind']!='member' or not member or not any(any(abs(v)>1e-8 for v in q) for q in member['end_offsets']):
            result.append(original)
            continue
        ends=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]
        axis=unit(sub(ends[1],ends[0]));length=math.dist(*ends)
        world=[bim_assemblies.transformed(q,frame) for q in original['axis']]
        stations=[max(0,min(length,dot(sub(q,ends[0]),axis))) for q in world]
        if abs(stations[0]-stations[1])<1e-6:
            raise ValueError('No receiving member length remains at '+mid)
        result.append(dict(original,axis=[local_point(add(ends[0],mul(axis,s)),frame) for s in stations]))
    return result


def rebuilt_scenes(model,package):
    """Keep existing sheet identity. Split only when a selected variant differs."""
    by_id={c['id']:c for c in model['connections']}
    records={r['id']:r['data'] for r in package['design_records']}
    changed={};out=[]
    next_number=max((int(s['sheet'][1:]) for s in model['connection_assemblies'] if re.fullmatch(r'C\d+',s['sheet'])),default=0)+1
    for original in model['connection_assemblies']:
        family=original['family']
        if family not in ('review_brace','review_brb','review_beam','review_pin_beam','review_base','review_wall_base','review_truss_node','review_truss_heel'):
            out.append(original);continue
        groups=defaultdict(list)
        for cid in original['occurrences']:
            c=by_id[cid];selected=selected_fields(package,c)
            variant=family
            if family=='review_pin_beam':
                source=next((records[r].get('components','') for r in c['design_record_ids'] if r in records),'')
                variant=beam_family(source) or family
                if variant=='review_beam':
                    c['detail_ref']['id']=variant;c['parameters']['joint']='shear_plate'
            token=(variant,selected.signature())
            groups[token].append(c)
        for group_index,group in enumerate(groups.values()):
            representative=group[0]
            unresolved=False
            try:
                scene=build_scene(model,package,representative)
            except SelectionConflict as issue:
                unresolved=True
                for occurrence in group:
                    issue.record(package,occurrence['id'])
                scene=dict(original,notes=list(original.get('notes',[]))+[
                    'REVIEW REQUIRED. Competing selected '+'.'.join(issue.key)+' values. Prior geometry retained.'])
            number=original['sheet'] if group_index==0 else f'C{next_number:03}'
            if group_index:next_number+=1
            sid=original['id'] if group_index==0 else 'CD'+number[1:]
            ids=[c['id'] for c in group]
            scene.update(id=sid,sheet=number,reference='1/'+number,occurrences=ids,occurrence_count=len(ids),
                         geometry_sha256=fingerprint([scene['parts'],scene['welds'],scene['interfaces']]))
            for c in group:
                c.update(assembly_id=sid,drawing_ref=scene['reference'])
                if not unresolved:
                    changed[c['id']]=scene
            out.append(scene)
    model['connection_assemblies']=out
    references=defaultdict(set)
    for c in model['connections']:
        for mid in c['member_ids']:references[mid].add(c['drawing_ref'])
    for m in model['members']:m['connection_refs']=sorted(references[m['id']])
    for row in model['member_schedule']:
        row['connection_refs']=sorted(set().union(*(references[mid] for mid in row['member_ids'])))
    return changed


def repair(package,model):
    physical=package['physical']
    members={m['id']:m for m in physical['members']}
    source_members={m['id']:m for m in model['members']}
    if not set(members)<=set(source_members):
        raise ValueError('Saved drawing and native member identities disagree')
    for mid,m in members.items():
        source_members[mid]['material_id']=m['material_id']
    from .hr_boxed_plies import add_column_plies
    add_column_plies(package,model)
    from .review_hr_brace_ends import bind
    bind(model,package)
    for mid,m in members.items():
        corrected=source_members[mid]
        for field in ('end_offsets','slots'):
            if field in corrected:m[field]=copy.deepcopy(corrected[field])
    changed=rebuilt_scenes(model,package)
    from .terminal_planes import saved_cuts
    changed.update(saved_cuts(physical,model))
    from .stmf_fit import repair_stmf
    changed.update(repair_stmf(package,model))
    templates={t['id']:t for t in physical['assemblies']}
    drawing_connections={c['id']:c for c in model['connections']}
    materials={m['id']:m for m in physical['materials']}
    new_templates={};signature_by_id={};parts_cache={}
    for c in physical['connections']:
        frame=c.get('assembly_instance')
        if not frame:continue
        old=templates[frame['template_id']];scene=changed.get(c['id'])
        if scene:
            token=(old['id'],scene['id'])
            if token not in parts_cache:parts_cache[token]=native_parts(scene,old,materials)
            parts=parts_cache[token]
            rr,bindings=receivers(scene,old,frame,members,c)
            extras=dict(source_interfaces=scene['interfaces'])
            c['assembly_id']=scene['id'];c['drawing_ref']=scene['reference']
            c['design_record_ids']=sorted(set(c['design_record_ids'])|set(scene.get('source_record_ids',[])))
            c['detail_ref']=dict(c['detail_ref'],legacy_family=scene['family'],id=model['pilot']+'/'+scene['id'],source_drawing=scene['reference'],revision=scene['geometry_sha256'])
        else:
            drawing=drawing_connections.get(c['id'])
            if drawing:
                c.update(assembly_id=drawing['assembly_id'],drawing_ref=drawing['drawing_ref'])
                c['detail_ref']=dict(c['detail_ref'],source_drawing=drawing['drawing_ref'])
            rr,bindings=crop_existing_receivers(old['receivers'],frame,members),frame['bindings'];parts=old['parts'];extras={}
            token=(old['id'],None)
            if token not in parts_cache:
                for p in parts:
                    if p['id'].upper()=='GROUT':
                        p['kind']='grout';p['material_id']=material_for(p,'grout',p,materials,old['source_record_ids'])
                parts_cache[token]=parts
        # Repeated occurrences share identical local geometry and source roles.
        # Quantize only the cache signature. The actual saved coordinates and
        # revision digest retain full precision.
        key=(token,fingerprint([(r['id'],[[round(x,6) for x in q] for q in r.get('axis',[])]) for r in rr]))
        if key not in new_templates:
            tid=old['id']
            if tid in signature_by_id:tid+='-fit-'+str(len(new_templates)+1)
            built={k:v for k,v in old.items() if k!='revision'}
            built.update(id=tid,parts=parts,receivers=rr,**extras)
            if scene:
                built['source_detail']=scene['id']
                built['source_record_ids']=sorted(set(old['source_record_ids'])|set(scene.get('source_record_ids',[])))
            built['revision']=bim_assemblies.fingerprint(built)
            new_templates[key]=built;signature_by_id[tid]=key
        built=new_templates[key]
        frame.update(template_id=built['id'],revision=built['revision'],bindings=bindings)
    physical['assemblies']=list(new_templates.values())
    physical['materials']=list(materials.values())
    model['materials']=copy.deepcopy(physical['materials'])
    from .occurrence_materials import bind as bind_materials
    bind_materials(package,model)
    from .flat_bar_crossings import add_crossings
    added_crossings=add_crossings(package,model)
    references=defaultdict(set)
    for c in model['connections']:
        for mid in c['member_ids']:references[mid].add(c['drawing_ref'])
    for m in model['members']:m['connection_refs']=sorted(references[m['id']])
    for row in model['member_schedule']:
        row['connection_refs']=sorted(set().union(*(references[mid] for mid in row['member_ids'])))
    return dict(rebuilt_connections=len(changed),new_crossing_connections=added_crossings,
                templates=len(physical['assemblies']),members=len(members))
