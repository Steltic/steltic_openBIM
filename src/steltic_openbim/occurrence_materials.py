"""Resolve compound schedule descriptions to the grade of a selected constituent."""
import re
from collections import defaultdict
from .drawing_workflow import fingerprint
from .hr_detail_selections import selected_fields
from .saved_assemblies import material_for


def material_role(part):
    pid=part['id'].upper();kind=part['kind']
    desc=(part.get('description') or part.get('parameters',{}).get('description','')).upper()
    if pid=='GROUT' or kind=='grout':return 'grout'
    if pid=='PIN' or kind=='pin':return 'pin'
    if kind in ('bolt','anchor','rod','fastener'):
        if 'ERECTION' in pid or 'ERECTION' in desc:return None
        if pid.startswith(('ANCH', 'ROD')) and ('ANCHOR' in desc or kind=='anchor'):return 'anchor'
        if re.search(r'\bA(?:325|490)(?:\b|-)',desc) or kind=='bolt':return 'bolt'
    if pid=='GUSSET':return 'gusset'
    if pid in ('P1','BASE') and ('BASE PLATE' in desc or 'END BEARING/ANCHOR PLATE' in desc):return 'base_plate'
    if pid.startswith('CHEEK'):return 'cheek_plate'
    if pid.startswith('CLEVIS'):return 'clevis_plate'
    if pid=='KNIFE':return 'knife_plate'
    if pid.startswith('SPLICE') and kind=='plate':return 'splice_plate'
    if pid.startswith('REINF') and 'SLOT' in desc:return 'slot_reinforcement'
    if pid in ('P1','P2') and ('SHEAR PLATE' in desc or 'ERECTION TAB' in desc):return 'shear_plate'
    return None


def bind(package,model):
    physical=package['physical']
    catalog={m['id']:m for m in physical['materials']}
    templates={t['id']:t for t in physical['assemblies']}
    scenes={s['id']:s for s in model['connection_assemblies']}
    drawing_connections={c['id']:c for c in model['connections']}
    native_connections={c['id']:c for c in physical['connections']}
    template_cache={};scene_cache={};scene_variants=defaultdict(list)
    next_sheet=max((int(s['sheet'][1:]) for s in scenes.values() if re.fullmatch(r'C\d+',s['sheet'])),default=0)
    for c in physical['connections']:
        frame=c.get('assembly_instance')
        if not frame:continue
        template=templates[frame['template_id']]
        selected=selected_fields(package,c);roles={}
        for role in set(filter(None,(material_role(p) for p in template['parts']))):
            key=(role,'material')
            origin=selected
            if role=='base_plate':
                related={p.get('parameters',{}).get('referenced_connection_id') for p in template['parts']
                         if material_role(p)==role}-{None}
                if len(related)==1 and next(iter(related)) in native_connections:
                    origin=selected_fields(package,native_connections[next(iter(related))])
            if key in origin.conflicts:continue
            grade=origin.get(key)
            if grade:roles[role]=(str(grade),origin.sources[key])
        spec=tuple(sorted((role,grade) for role,(grade,_) in roles.items()))
        if not spec:continue
        c.setdefault('parameters',{})['source_material_fields']={role:refs for role,(_,refs) in roles.items()}
        token=(template['id'],spec)
        if token not in template_cache:
            parts=[]
            for old in template['parts']:
                role=material_role(old)
                if role not in roles:
                    parts.append(old);continue
                grade,provenance=roles[role];kind=old['kind']
                selection=dict(id=old['id'],selected_material=grade)
                mid=material_for(selection,kind,old,catalog,[r['record_id'] for r in provenance])
                params=dict(old.get('parameters',{}),selected_material=grade,
                            source_material_id=old.get('material_id'),source_material_role=role)
                parts.append(dict(old,material_id=mid,parameters=params))
            tid=template['id']+'-material-'+fingerprint(spec)[:10]
            built=dict(template,id=tid,parts=parts);built.pop('revision',None)
            built['revision']=fingerprint(built);template_cache[token]=built
        built=template_cache[token]
        frame.update(template_id=built['id'],revision=built['revision'])
        source_scene=scenes.get(c.get('assembly_id'))
        if not source_scene:continue
        stoken=(source_scene['id'],spec)
        if stoken not in scene_cache:
            parts=[]
            for part in source_scene['parts']:
                role=material_role(part)
                if role not in roles:parts.append(part);continue
                grade=roles[role][0]
                description=part['description']
                if grade.upper() not in description.upper():
                    description+='; selected '+grade
                parts.append(dict(part,description=description,selected_material=grade))
            scene=dict(source_scene,parts=parts,occurrences=[])
            variants=scene_variants[source_scene['id']]
            if variants:
                next_sheet+=1;scene.update(id=f'CD{next_sheet:03}',sheet=f'C{next_sheet:03}',reference=f'1/C{next_sheet:03}')
            variants.append(scene);scene_cache[stoken]=scene
        scene=scene_cache[stoken];scene['occurrences'].append(c['id'])
        c.update(assembly_id=scene['id'],drawing_ref=scene['reference'])
        c['detail_ref']=dict(c['detail_ref'],source_drawing=scene['reference'],id=model['pilot']+'/'+scene['id'])
        if c['id'] in drawing_connections:drawing_connections[c['id']].update(assembly_id=scene['id'],drawing_ref=scene['reference'])
    used={c['assembly_instance']['template_id'] for c in physical['connections'] if c.get('assembly_instance')}
    physical['assemblies']=[t for t in [*templates.values(),*template_cache.values()] if t['id'] in used]
    out=[]
    for original in model['connection_assemblies']:
        variants=scene_variants.get(original['id'])
        if not variants:out.append(original);continue
        consumed={cid for s in variants for cid in s['occurrences']}
        remaining=[cid for cid in original['occurrences'] if cid not in consumed]
        if remaining:
            # A shared unselected detail keeps its original content and page.
            # A grade selected on a neighboring occurrence cannot replace it.
            retained=dict(original,occurrences=remaining,occurrence_count=len(remaining))
            next_sheet+=1;first=variants[0]
            first.update(id=f'CD{next_sheet:03}',sheet=f'C{next_sheet:03}',reference=f'1/C{next_sheet:03}')
            out.append(retained)
        for scene in variants:
            scene['occurrence_count']=len(scene['occurrences'])
            scene['geometry_sha256']=fingerprint([scene['parts'],scene['welds'],scene['interfaces']])
            for cid in scene['occurrences']:
                c=native_connections[cid]
                c.update(assembly_id=scene['id'],drawing_ref=scene['reference'])
                c['detail_ref']=dict(c['detail_ref'],id=model['pilot']+'/'+scene['id'],source_drawing=scene['reference'],
                                     revision=scene['geometry_sha256'])
                if cid in drawing_connections:
                    drawing_connections[cid].update(assembly_id=scene['id'],drawing_ref=scene['reference'])
        out.extend(variants)
    model['connection_assemblies']=out
    current={t['id']:t for t in physical['assemblies']}
    for c in native_connections.values():
        frame=c.get('assembly_instance')
        if not frame or not c.get('assembly_id'):continue
        template=current[frame['template_id']]
        if template.get('source_detail')!=c['assembly_id']:
            tid=template['id']+'-detail-'+fingerprint(c['assembly_id'])[:10]
            if tid not in current:
                revised=dict(template,id=tid,source_detail=c['assembly_id'])
                revised['revision']=fingerprint({k:v for k,v in revised.items() if k!='revision'})
                current[tid]=revised
            frame.update(template_id=tid,revision=current[tid]['revision'])
    used={c['assembly_instance']['template_id'] for c in native_connections.values() if c.get('assembly_instance')}
    physical['assemblies']=[template for tid,template in current.items() if tid in used]
    physical['materials']=list(catalog.values());model['materials']=physical['materials']
