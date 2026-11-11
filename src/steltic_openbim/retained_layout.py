"""Reapply an approved sheet register to a connection-only native revision."""
import copy
from .drawing_workflow import fingerprint


def compare_rows(table,before,after,fields):
    left={row['id']:row for row in before};right={row['id']:row for row in after}
    if len(left)!=len(before) or len(right)!=len(after) or set(left)!=set(right):
        raise ValueError(f'Connection-only revision changed {table} identities')
    for rid,row in left.items():
        for key in fields:
            if row.get(key)!=right[rid].get(key):
                raise ValueError(f'Connection-only revision changed {table} {rid} {key}')
    return len(left)


def bind_layout(prior,package,model,manifest):
    """Validate retained geometry, then update connection selections from the new job."""
    if (manifest['building_id']!=prior['building_id'] or manifest['model_sha256']!=fingerprint(model) or
            manifest['source_model_sha256']!=model['source_sha256']):
        raise ValueError('Approved drawing model is not bound to the prior job and register')
    native=package['physical'];old=prior['physical']
    fields={
        'members':('kind','axis','local_y','level','end_offsets','analysis_ids'),
        'panels':('kind','vertices','level','thickness','thickness_in','openings'),
        'openings':('kind','plane','vertices','level','host_id','width_ft','height_ft','confirmed'),
        'joints':('point','member_ends','attachments'),
    }
    counts={key:compare_rows(key,old[key],native[key],attrs) for key,attrs in fields.items()}
    old_members={m['id']:m for m in old['members']}
    crossings={mid for r in package.get('source_handoff',{}).get('crossing_interfaces',[])
               if r['kind'] in ('flat_bar_crossing','flat_bar_crossing_plate') for mid in r['member_ids']}
    old_profiles={p['id']:p for p in old['profiles']};profiles={p['id']:p for p in native['profiles']}
    changed={}
    for m in native['members']:
        old_id=old_members[m['id']]['profile_id'];pid=m['profile_id']
        if old_id==pid:continue
        if (m['id'] not in crossings or old_profiles[old_id]['family']!='flat' or
                profiles[pid]['family']!='flat' or not m.get('design_record_ids')):
            raise ValueError('Revised member section lacks a scoped flat-bar crossing selection: '+m['id'])
        changed[m['id']]={'prior':old_id,'revised':pid,'design_record_ids':m['design_record_ids']}
    existing={p for p in profiles if p in old_profiles}
    if set(profiles)-existing-{v['revised'] for v in changed.values()}:
        raise ValueError('New profile definition outside the crossing revision')
    compare_rows('profiles',[old_profiles[p] for p in existing],[profiles[p] for p in existing],
                 ('family','dimensions','components','lip_angle_deg'))
    counts['profiles']=len(existing)
    # The published composition may include declared drawing-only continuity
    # occurrences. Its structural member, panel and aperture identity is exact.
    for key,attrs in [('members',('kind','profile_id','axis','local_y','level')),
                      ('panels',('kind','vertices','level','thickness_in')),
                      ('openings',('kind','plane','level','x_ft','y_ft','z_ft','width_ft','height_ft','confirmed'))]:
        compare_rows('approved '+key,model[key],old[key],attrs)
    compare_rows('connections',old['connections'],native['connections'],('point','joint_id','member_ids'))
    previous={c['id']:c for c in old['connections']}
    drawing={c['id']:c for c in model['connections']}
    prior_records={r['id']:r for r in prior.get('design_records',[])}
    revised_records={r['id']:r for r in package.get('design_records',[])}
    revised_templates={t['id']:t for t in native.get('assemblies',[])}
    revised_connections=[]
    for c in native['connections']:
        target=drawing.get(c['id']);prev=previous[c['id']]
        if target is None:raise ValueError('Retained layout lacks required connection '+c['id'])
        if c.get('assembly_instance')!=prev.get('assembly_instance'):
            old_frame=prev.get('assembly_instance') or {};frame=c.get('assembly_instance') or {}
            locator=('origin','x_axis','y_axis','bindings')
            changed_records=[r for r in c['design_record_ids'] if revised_records.get(r)!=prior_records.get(r)]
            template=revised_templates.get(frame.get('template_id'),{})
            if (any(frame.get(k)!=old_frame.get(k) for k in locator) or not changed_records or
                    not template or template.get('revision')!=frame.get('revision')):
                raise ValueError('Revised connection lacks an authenticated change at its retained placement: '+c['id'])
            revised_connections.append(dict(connection_id=c['id'],record_ids=changed_records,template=frame['template_id']))
        target['parameters']=copy.deepcopy(c.get('parameters',{}))
        target['design_record_ids']=list(c['design_record_ids'])
        if 'source_record_selections' in c:
            target['source_record_selections']=copy.deepcopy(c['source_record_selections'])
    current={m['id']:m for m in native['members']}
    for m in model['members']:
        m['design_record_ids']=list(current[m['id']].get('design_record_ids',[]))
        m['profile_id']=current[m['id']]['profile_id']
    if changed:
        model['profiles']=copy.deepcopy(native['profiles'])
        members={m['id']:m for m in model['members']};schedule=[]
        for row in model['member_schedule']:
            groups={}
            for mid in row['member_ids']:groups.setdefault(members[mid]['profile_id'],[]).append(mid)
            for i,(pid,ids) in enumerate(sorted(groups.items(),key=lambda v:(v[0]!=row['profile_id'],v[0]))):
                mark=row['mark'] if i==0 else row['mark']+'-R'+str(i)
                for mid in ids:members[mid]['mark']=mark
                schedule.append(dict(row,mark=mark,profile_id=pid,member_ids=ids,count=len(ids),
                                     levels=sorted({members[mid]['level'] for mid in ids})))
        model['member_schedule']=schedule
    model['title']=package['building_id']
    return dict(unchanged=counts,revised_crossing_members=changed,revised_connection_templates=revised_connections,existing_physical_connections=len(previous),
                approved_drawing_occurrences=len(drawing),prior_building_id=prior['building_id'],
                approved_model_sha256=manifest['model_sha256'],prior_sheet_count=len(manifest['sheets']),
                prior_sheet_ids=[s['number'] for s in manifest['sheets']])
