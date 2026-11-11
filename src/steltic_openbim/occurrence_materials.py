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
    if pid.startswith('REINF') and 'SLOT' in desc:return 'slot_reinforcement'
    if pid in ('P1','P2') and ('SHEAR PLATE' in desc or 'ERECTION TAB' in desc):return 'shear_plate'
    return None


def bind(package,model):
    physical=package['physical']
    catalog={m['id']:m for m in physical['materials']}
    templates={t['id']:t for t in physical['assemblies']}
    scenes={s['id']:s for s in model['connection_assemblies']}
    drawing_connections={c['id']:c for c in model['connections']}
    template_cache={};scene_cache={};scene_variants=defaultdict(list)
    next_sheet=max((int(s['sheet'][1:]) for s in scenes.values() if re.fullmatch(r'C\d+',s['sheet'])),default=0)
    for c in physical['connections']:
        frame=c.get('assembly_instance')
        if not frame:continue
        template=templates[frame['template_id']]
        selected=selected_fields(package,c);roles={}
        for role in set(filter(None,(material_role(p) for p in template['parts']))):
            key=(role,'material')
            if key in selected.conflicts:continue
            grade=selected.get(key)
            if grade:roles[role]=(str(grade),selected.sources[key])
        spec=tuple(sorted((role,grade) for role,(grade,_) in roles.items()))
        if not spec:continue
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
                            source_material_id=old.get('material_id'),source_material_fields=provenance)
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
            # Drawing-only continuity occurrences still point to the original
            # page and retain their own source bindings.
            variants[0]['occurrences'].extend(remaining)
        for scene in variants:
            scene['occurrence_count']=len(scene['occurrences'])
            scene['geometry_sha256']=fingerprint([scene['parts'],scene['welds'],scene['interfaces']])
        out.extend(variants)
    model['connection_assemblies']=out
    physical['materials']=list(catalog.values());model['materials']=physical['materials']
