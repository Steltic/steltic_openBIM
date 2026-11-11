"""Bind a BRB's restraint to its member record and keep its moving core unbonded."""
import copy
import hashlib
import math
import re
from collections import defaultdict
from fractions import Fraction


HSS = r'HSS\s*(\d+(?:\.\d+)?|\d+/\d+)\s*[Xx]\s*(\d+(?:\.\d+)?|\d+/\d+)\s*[Xx]\s*(\d+/\d+|\d+(?:\.\d+)?)'
DELEGATED_MATERIAL = 'Steel BRB restraint casing; grade delegated to BRB supplier'
MORTAR = 'Mortar for BRB casing infill'


def hss_dimensions(section):
    match = re.fullmatch(HSS, section.strip(), re.I)
    if not match:
        raise ValueError('Unsupported source-selected BRB casing section '+section)
    height, width, wall = (float(Fraction(term)) for term in match.groups())
    if wall <= 0 or min(width, height) <= 2 * wall:
        raise ValueError('Selected casing has no hollow interior: '+section)
    return dict(h=height, b=width, t=wall)


def requirements(members, handoff, records, materials):
    """Resolve located controls. The material schedule and member checks remain independent."""
    specs = {row['id']: row['data'] for row in records if row['id'].startswith('members/')}
    schedules = [m for m in materials if re.search(r'buckling.restrained brace', m.get('source_item',''), re.I)]
    result = {}
    for member in members:
        row = handoff.get('member_selections',{}).get(member['id'],{})
        fields = {}
        for f in row.get('fields',[]):
            if f['role'] not in ('brb_casing','brb_infill'):
                continue
            key = f['role'],f['field']
            if key in fields and fields[key] != f['value']:
                raise ValueError('Conflicting located BRB casing controls for '+member['id'])
            fields[key] = f['value']
        bindings = member.get('design_record_ids',[])
        if fields and row['record_id'] not in bindings:
            raise ValueError('BRB casing record is not bound to '+member['id'])
        bound = [rid for rid in bindings if rid in specs and
                 ('BRB' in str(member.get('source_profile_id',member.get('profile_id',''))).upper() or fields)]
        if not fields and not bound:
            continue
        section = fields.get(('brb_casing','section'))
        material = fields.get(('brb_casing','material'))
        mode = fields.get(('brb_casing','design_mode'))
        infill = fields.get(('brb_infill','material')) or fields.get(('brb_casing','infill_material'))
        sources = list(bound or [row['record_id']])
        for rid in bound:
            for check in specs[rid].get('checks',[]):
                text = check.get('limit_state','')
                if not re.search(r'\bcasing\b',text,re.I):
                    continue
                match = re.search(r'\b('+HSS+r')\s+(?:ASTM\s+)?A500\s+Gr(?:ade)?\.?\s*([A-D])\b',text,re.I)
                if match:
                    label = re.sub(r'\s','',match[1]).upper()
                    alloy = 'ASTM A500 Grade '+match[5].upper()
                    if section and hss_dimensions(section) != hss_dimensions(label):
                        raise ValueError('Typed BRB casing differs from its member stability check for '+member['id'])
                    if material:
                        typed_grade=re.fullmatch(r'(?:ASTM\s+)?A500\s+Gr(?:ade)?\.?\s*([A-D])',material.strip(),re.I)
                        if not typed_grade or typed_grade[1].upper()!=match[5].upper():
                            raise ValueError('Typed casing grade differs from its member stability check for '+member['id'])
                    section,material = label,alloy
        for schedule in schedules:
            text = schedule.get('specification','')
            if re.search(r'\bmortar.filled steel casing\b',text,re.I):
                if infill and 'mortar' not in str(infill).lower():
                    raise ValueError('BRB infill differs from the original material schedule for '+member['id'])
                infill = infill or MORTAR
                sources.append(schedule['id'])
            if not section and not material and re.search(r'\bcasing\b[^;]*?\bby the BRB (?:supplier|manufacturer)\b',text,re.I):
                mode = mode or 'supplier_delegated'
                sources.append(schedule['id'])
        if not (section or material or mode or infill):
            continue
        if not material and mode == 'supplier_delegated':
            material = DELEGATED_MATERIAL
        if not material:
            raise ValueError('BRB casing material or supplier delegation is missing for '+member['id'])
        result[member['id']] = dict(section=section,material=material,infill_material=infill,
            design_mode=mode or 'selected',source_ids=list(dict.fromkeys(sources)))
    return result


def material_id(catalog,role,spec,refs,basis):
    key = 'brb-'+role+'-'+hashlib.sha256(spec.encode()).hexdigest()[:14]
    item = catalog.setdefault(key,dict(id=key,source_item='BRB '+role,specification=spec,
                                        source_record_ids=[],source_material_ids=[],basis=basis))
    item['source_record_ids'] = sorted(set(item['source_record_ids']) | {rid for rid in refs if rid.startswith('members/')})
    item['source_material_ids'] = sorted(set(item.get('source_material_ids',[])) | {rid for rid in refs if not rid.startswith('members/')})
    return key


def prepare_casings(package,model,core_ids):
    if not core_ids:
        return
    physical=package['physical']
    selections=requirements(model['members'],package.get('source_handoff',{}),
                            package.get('design_records',[]),physical['materials'])
    active=set(core_ids)&set(selections)
    if not active:
        return
    catalog={m['id']:m for m in physical['materials']}
    originals={p['id']:p for p in model['profiles']}
    members={m['id']:m for m in physical['members']}
    groups=defaultdict(set)
    for m in model['members']:
        spec=selections.get(m['id'])
        if m['id'] in active:
            groups[m.get('source_profile_id',m['profile_id'])].add(spec['section'])
    profile_rows={key:[] for key in groups}
    for m in model['members']:
        spec=selections.get(m['id'])
        if m['id'] not in active:
            continue
        base=m.get('source_profile_id',m['profile_id'])
        old=originals[base]
        section=spec['section']
        pid=base if len(groups[base])==1 else base+' / '+(section or 'supplier casing')
        selected=copy.deepcopy(old)
        selected['id']=pid
        if section:
            selected.update(family='rhs',dimensions=hss_dimensions(section),casing_section=section,
                            basis='S: nominal HSS casing from the located HR member; sharp corners in the coordination representation')
        if pid not in [p['id'] for p in profile_rows[base]]:
            profile_rows[base].append(selected)
        for target in (m,members[m['id']]):
            target.update(source_profile_id=base,profile_id=pid,brb_casing=copy.deepcopy(spec),
                          material_id=material_id(catalog,'casing',spec['material'],spec['source_ids'],
                            'S: supplier-delegated casing; A: coordination envelope' if spec['material']==DELEGATED_MATERIAL
                            else 'S: selected casing steel'))
        if spec['infill_material']:
            material_id(catalog,'infill',spec['infill_material'],spec['source_ids'],'S: HR casing infill material')
    for dest in (model,physical):
        if 'profiles' not in dest:
            continue
        current={p['id']:p for p in dest['profiles']}
        for rows in profile_rows.values():
            current.update((p['id'],copy.deepcopy(p)) for p in rows)
        dest['profiles']=list(current.values())
    physical['materials']=list(catalog.values())
    # One mark may previously have combined two same-area BRBs with different
    # specified casings. Split that mark and its schedule through the located IDs.
    by_id={m['id']:m for m in model['members']}
    schedule=[]
    for old in model.get('member_schedule',[]):
        if active.isdisjoint(old['member_ids']):
            schedule.append(old)
            continue
        variants=defaultdict(list)
        for mid in old['member_ids']:
            variants[by_id[mid]['profile_id']].append(mid)
        for i,(pid,ids) in enumerate(variants.items(),1):
            mark=old['mark'] if len(variants)==1 else old['mark']+'-'+str(i)
            item=dict(old,mark=mark,profile_id=pid,member_ids=ids,count=len(ids))
            chosen=by_id[ids[0]].get('brb_casing',{})
            if chosen.get('section'):item['casing_section']=chosen['section']
            schedule.append(item)
            for mid in ids:
                if len(variants)>1:by_id[mid]['mark']=members[mid]['mark']=mark
    if 'member_schedule' in model:model['member_schedule']=schedule


def needs_completion(physical,required):
    profiles={p['id']:p for p in physical['profiles']}
    mats={m['id']:m['specification'] for m in physical['materials']}
    for member in physical['members']:
        spec=required.get(member['id'])
        if not spec:continue
        if member.get('brb_casing')!=spec or mats.get(member['material_id'])!=spec['material']:
            return True
        if spec['section'] and profiles[member['profile_id']]['dimensions']!=hss_dimensions(spec['section']):
            return True
        if spec['infill_material']:
            fill=[p for p in member.get('section_plies',[]) if p.get('constituent_id')=='MORTAR-INFILL']
            if not fill or any(mats.get(p['material_id'])!=spec['infill_material'] for p in fill):return True
    return False


def bind_receiver_profiles(physical):
    """Keep the located member identity when a shared core label has two casing selections."""
    from .bim_assemblies import fingerprint
    templates={t['id']:t for t in physical.get('assemblies',[])}
    casings={m['id']:m['profile_id'] for m in physical['members'] if m.get('brb_casing')}
    changed=set()
    for connection in physical.get('connections',[]):
        placement=connection.get('assembly_instance',{})
        original=templates.get(placement.get('template_id'))
        if original is None:continue
        replacements={}
        for receiver in original.get('receivers',[]):
            mid=placement['bindings'].get(receiver['id'])
            if mid in casings and receiver.get('profile_id')!=casings[mid]:
                replacements[receiver['id']]=casings[mid]
        if not replacements:continue
        tid=original['id']+'-brb-'+fingerprint(replacements)[:14]
        if tid not in templates:
            revised=copy.deepcopy(original);revised.pop('revision',None);revised['id']=tid
            for receiver in revised['receivers']:
                if receiver['id'] in replacements:receiver['profile_id']=replacements[receiver['id']]
            revised['revision']=fingerprint(revised);templates[tid]=revised
        placement.update(template_id=tid,revision=templates[tid]['revision'])
        if 'detail_ref' in connection:
            connection['detail_ref']['revision']=templates[tid]['revision']
        changed.add(original['id'])
    if changed:
        located={c.get('assembly_instance',{}).get('template_id') for c in physical['connections']}
        physical['assemblies']=[row for tid,row in templates.items() if tid not in changed or tid in located]


def infill_plies(member,profile,core,length,catalog):
    """Fill the fixed interior around the entire swept steel envelope."""
    spec=member.get('brb_casing',{})
    if not spec.get('infill_material'):
        return []
    # The restrained core moves relative to the casing. A constant unbonded
    # opening encloses the largest actual section at every longitudinal station.
    # The 1/16-in lateral radial allowance is an adopted coordination dimension.
    gap=float(spec.get('core_clearance_in',1/16))
    if not math.isfinite(gap) or gap<=0:
        raise ValueError('BRB infill requires a positive unbonded interface for '+member['id'])
    y=max(abs(p[0]) for _,ring in core['sections'] for p in ring)+gap
    z=max(abs(p[1]) for _,ring in core['sections'] for p in ring)+gap
    d=profile['dimensions'];width=d['b']/2-d['t'];height=d['h']/2-d['t']
    if y>=width or z>=height:
        raise ValueError('Selected BRB core and unbonded interface exceed the actual casing for '+member['id'])
    mid=material_id(catalog,'infill',spec['infill_material'],spec['source_ids'],'S: HR casing infill material')
    rows=[]
    for name,(a,b,c,e) in zip(('BOTTOM','TOP','LEFT','RIGHT'),(
            (-width,-height,width,-z),(-width,z,width,height),(-width,-z,-y,z),(y,-z,width,z))):
        ring=[[a,b],[c,b],[c,e],[a,e]]
        rows.append(dict(id='MORTAR-'+name,constituent_id='MORTAR-INFILL',material_id=mid,
                         sections=[[0.,ring],[length,ring]],source_record_ids=spec['source_ids'],
                         basis='S: mortar-filled casing; A: continuous unbonded core opening and sliding allowance'))
    return rows
