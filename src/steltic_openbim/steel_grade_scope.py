"""Apply a report-bound above-grade steel publication scope after the original layout is validated."""
import re

def apply(package,model,manifest):
    scope_records={r['id']:r['data']['steel_delivery_scope'] for r in package['design_records'] if 'steel_delivery_scope' in r['data']}
    scopes=list(scope_records.values())
    if not scopes:return None
    scope=scopes[0]
    if any(s!=scope for s in scopes[1:]):raise ValueError('Competing steel delivery scopes')
    grade=float(scope['grade_in']);cols=set(scope['clipped_columns']);removed=set(scope['excluded_connections'])
    ph=package['physical'];old={c['id']:c for c in ph['connections']}
    below={c['id'] for c in ph['connections'] if c['point'][2]<grade-.001}
    if not below or below!=removed:raise ValueError('Scope does not identify every below-grade joint')
    if any(old[c]['detail_ref']['legacy_family']!='review_base' or len(old[c]['member_ids'])!=1 for c in below):
        raise ValueError('Exclusion includes steel other than a below-grade column base')
    if {old[c]['member_ids'][0] for c in below}!=cols:raise ValueError('Column scope and base scope disagree')
    below_joints={old[c]['joint_id'] for c in below}
    clipped={}
    for table in (model,ph):
        trimmed=set()
        for m in table['members']:
            ends=[q[2]+d[2] for q,d in zip(m['axis'],m['end_offsets'])]
            if min(ends)>=grade-.001:continue
            i=ends.index(min(ends))
            if (m['id'] not in cols or m['kind']!='column' or min(ends)>=grade or
                max(ends)<=grade or abs(m['axis'][i][2]-grade)>.001 or
                any(abs(a-b)>.001 for a,b in zip(m['axis'][0][:2],m['axis'][1][:2]))):
                raise ValueError('Unsupported below-grade member in the steel scope: '+m['id'])
            clipped[m['id']]=min(ends);trimmed.add(m['id'])
            m['end_offsets'][i][2]=grade-m['axis'][i][2]
            if 'joint_workpoints' in m:m['joint_workpoints'][i][2]=grade
            m['setout_basis']='Source column section and splice stations, with steel terminating at the issued grade datum.'
        if trimmed!=cols:raise ValueError('Scope includes an unclipped column')
        table['connections']=[c for c in table['connections'] if c['id'] not in below]
    underground=[j for j in ph['joints'] if j['id'] in below_joints]
    ph['joints']=[j for j in ph['joints'] if j['id'] not in below_joints]
    ph['joint_dispositions']=[j for j in ph.get('joint_dispositions',[]) if j.get('joint_id') not in below_joints]
    at_grade={tuple(j['point']):j for j in ph['joints'] if abs(j['point'][2]-grade)<.001}
    for joint in underground:
        point=(*joint['point'][:2],grade);ends=joint['member_ends']
        if len(ends)!=1 or ends[0]['member_id'] not in cols:raise ValueError('Unresolved column end at the steel delivery limit')
        end=dict(ends[0],joint_offset=[0.,0.,0.])
        if point in at_grade:
            at_grade[point]['member_ends'].append(end)
        else:
            joint.update(point=list(point),member_ends=[end],basis='Steel delivery boundary at the grade slab')
            ph['joints'].append(joint);at_grade[point]=joint
            ph['joint_dispositions'].append(dict(joint_id=joint['id'],kind='scope_boundary',design_record_ids=sorted(scope_records),
                reason='End of published steel at grade. Supporting construction is outside the steel delivery scope.'))
    used={c['assembly_instance']['template_id'] for c in ph['connections'] if c.get('assembly_instance')}
    ph['assemblies']=[t for t in ph['assemblies'] if t['id'] in used]
    records={r for c in ph['connections'] for r in c['design_record_ids']}
    retired={r for cid in below for r in old[cid]['design_record_ids']}-records
    for rid in sorted(retired):
        ph['record_dispositions'].append(dict(record_id=rid,status='not_applicable',evidence_member_ids=sorted(cols),
            reason='Below-grade column base lies outside the issued steel delivery scope. The full HR record is archived.'))
    sheets=[];scenes=[]
    for sc in model['connection_assemblies']:
        keep=[cid for cid in sc['occurrences'] if cid not in below]
        if not keep and sc['occurrences']:sheets.append(sc['sheet']);continue
        sc['occurrences']=keep;sc['occurrence_count']=len(keep);scenes.append(sc)
    model['connection_assemblies']=scenes
    model['levels']=[r for r in model['levels'] if r[2]>=grade-.001]
    refs={}
    for c in model['connections']:
        for mid in c['member_ids']:refs.setdefault(mid,set()).add(c['drawing_ref'])
    for m in model['members']:m['connection_refs']=sorted(refs.get(m['id'],set()))
    for row in model['member_schedule']:row['connection_refs']=sorted(set().union(*(refs.get(mid,set()) for mid in row['member_ids'])))
    model['connection_endpoint_links']=[r for r in model.get('connection_endpoint_links',[]) if r['connection_id'] not in below]
    superseded=set(scope.get('superseded_assumptions',[]))
    model['assumptions']=[r for r in model['assumptions'] if r['id'] not in superseded]
    model['assumptions'].append(dict(id='STEEL-GRADE-LIMIT',answer=f'Steel scope ends at slab grade {grade:g} in. Grade receiver reactions are given at the steel interface.'))
    old_numbers=[r['number'] for r in manifest['sheets']]
    withdrawn=[n for n in old_numbers if any(n==s or re.fullmatch(re.escape(s)+r'N\d+',n) for s in sheets)]
    result=dict(grade_in=grade,clipped_columns=clipped,excluded_connections=sorted(below),
                withdrawn_detail_sheets=sorted(withdrawn),retired_records=sorted(retired))
    model['steel_delivery_scope']=result
    if 'bounds' in model:model['bounds'][2][0]=max(grade,model['bounds'][2][0])
    return result
