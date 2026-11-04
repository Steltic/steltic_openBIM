"""Locate the floor joists explicitly selected on parallel wall lines.

The regular sixteen-inch floor grid does not necessarily land on a wall line.
Use the saved schedule for the wall-line section and the actual adjacent floor
span for its endpoints. This is physical set-out, not a new joist design.
"""
import copy,re


def apply(b,*,adopt_roof_wall_joists=False):
    if b.key not in ('cfs5','cfs7'):return
    record=b.record('framing','chord-squash-floor')
    if not record:return
    rows=b.records[record]['data'].get('rows',[])
    selections={}
    for row in rows:
        text=row.get('floor_member','')
        match=re.search(r'(\d{3,4}S\d{3}-\d{2,3}) joist on the wall line',text)
        if not match:continue
        _,direction,line=row['member'].split('-',2)
        key=(direction,line,int(row['level']))
        if key in selections and selections[key]!=match[1]:raise ValueError('Conflicting source wall-line joist sections')
        selections[key]=match[1]
    source_joists=[m for m in b.members if m['kind']=='joist']
    existing={m['id']:m for m in b.members}
    for wall in b.walls:
        k=wall['level'];direction=wall['direction'];line=wall['line'];ax=0 if direction=='X' else 1;other=1-ax
        pid=selections.get((direction,line,k));is_roof=False
        # A floor-only row cannot silently become a roof selection.
        if not pid:
            is_roof=adopt_roof_wall_joists and k==max(w['level'] for w in b.walls) and any(d==direction and name==line for d,name,_ in selections)
            if not is_roof:continue
        for position in sorted({round(r['position_in'],6) for r in wall['runs']}):
            candidates=[m for m in source_joists if m['level']==k and abs(m['axis'][0][other]-m['axis'][1][other])<.001
                        and abs(m['axis'][0][other]-position)<=16.001]
            groups={}
            for m in candidates:
                lo,hi=sorted(p[ax] for p in m['axis']);key=(round(lo,6),round(hi,6),round(m['axis'][0][2],6))
                if key not in groups or abs(m['axis'][0][other]-position)<abs(groups[key]['axis'][0][other]-position):groups[key]=m
            for span,reference in sorted(groups.items()):
                selected_pid=reference['profile_id'] if is_roof else pid
                refs=list(reference.get('design_record_ids',[])) if is_roof else [record]
                # Only a span physically covered by this wall line is eligible;
                # nearby corridors/steps are not extrapolated across voids.
                tracks=[m for m in b.members if m['kind'] in ('top_track','ordinary_track') and m['level']==k
                        and m['local_y'][2]<-.99 and all(abs(p[other]-position)<.001 for p in m['axis'])
                        and min(max(p[ax] for p in m['axis']),span[1])-max(min(p[ax] for p in m['axis']),span[0])>.5]
                if not tracks:continue
                target=next((m for m in source_joists if m['level']==k and all(abs(p[other]-position)<.001 for p in m['axis'])
                             and tuple(round(v,6) for v in (*sorted(p[ax] for p in m['axis']),m['axis'][0][2]))==span),None)
                label=f'WALL-J-{direction}-{line}-{k}-{span[0]:g}-{span[1]:g}'
                if label in existing:continue
                if target and is_roof:continue
                if target and target.get('physical_fit_basis','').startswith('S: source wall-line joist section') and target['profile_id']==pid and target['design_record_ids']==[record]:continue
                if target:
                    previous=dict(profile_id=target['profile_id'],design_record_ids=list(target['design_record_ids']))
                    target.setdefault('source_context_records',[]).extend(r for r in target['design_record_ids'] if r!=record)
                    target['profile_id']=b.profile(pid);target['design_record_ids']=[record]
                    b.used_records.add(record)
                    for c in b.connections:
                        if target['id'] in c['member_ids']:
                            c.setdefault('source_context_records',[]).extend(c['design_record_ids']);c['design_record_ids']=[record]
                else:
                    endpoints=copy.deepcopy(reference['axis'])
                    for q in endpoints:q[other]=position
                    target=b.member(label,selected_pid,'joist',*endpoints,k,'A' if is_roof else 'S',records=refs,local_y=reference['local_y'])
                    b.ends(target,'review_cfs_joist',refs,parameters=dict(spacing=16,wall_line_joist=True))
                    previous=None;existing[label]=target
                target['physical_fit_basis']=('A: accepted extra roof joist on the wall line, matching the actual adjacent roof member and support span; no floor-only section or capacity is applied at the roof.' if is_roof else
                    'S: source wall-line joist section. A: exact wall axis and adjacent physical support span; chord-pack interruptions and their clips are separate required details.')
                b.changes.append(dict(kind='adopted_roof_wall_joist' if is_roof else 'source_wall_line_joist',member_id=target['id'],source_record_ids=refs,
                                      source_row=None if is_roof else dict(direction=direction,line=line,level=k),reference_span_member_id=reference['id'],
                                      previous=previous,axis=copy.deepcopy(target['axis']),basis=target['physical_fit_basis']))
