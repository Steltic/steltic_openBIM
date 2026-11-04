"""Physical occurrences of explicit member-level selections in saved golds.

Only explicit numerical source selections are read. These fixture helpers never
calculate member or connection capacity. Missing fit dimensions remain A.
"""
from collections import defaultdict
import json,math,re
from .assembly_templates import NUMBER,number,effective
from .pilots.model import sub,add,mul


def apply(builder):
    if not builder.key.startswith('hr'):return
    members={m['id']:m for m in builder.members};roof=max(m.get('level',1) for m in builder.members)
    # Envelope records sometimes use a broader role name than the frame layout.
    # Bind an otherwise-unused check only when the saved member schedule proves
    # its selected section AND governing axial demand, at the printed precision.
    used={r for m in builder.members for r in m.get('design_record_ids',[])}
    for rid,record in builder.records.items():
        data=record['data'];inputs=data.get('inputs',{})
        if record['table']!='members' or rid in used or inputs.get('kind') not in ('col','column'):continue
        selected=inputs.get('section');demand=inputs.get('P_comp_kip')
        if not selected or not isinstance(demand,(float,int)) or demand<=0:continue
        matches=[]
        for m in builder.members:
            if m['kind']!='column' or m['profile_id']!=selected:continue
            try:force=float(m.get('source_forces',{})['P_comp_kip'])
            except (KeyError,TypeError,ValueError):continue
            if abs(force-demand)<=.11:matches.append(m)
        for m in matches:
            m['design_record_ids'].append(rid);builder.used_records.add(rid)
            m.setdefault('design_mapping_evidence',[]).append(dict(record_id=rid,basis='Exact source section and governing axial demand at source schedule precision',P_comp_kip=demand))
    # A directional check can qualify a selected section without putting that
    # section at the end of its ID (for example floor-W27X94-X-lines).
    directional=[]
    for rid,record in builder.records.items():
        match=re.search(r'-([XY])-lines$',rid);inputs=record['data'].get('inputs',{})
        if record['table']=='members' and match and inputs.get('section') and inputs.get('role') in ('floor','roof'):
            directional.append((rid,inputs['section'],inputs['role'],match[1]))
    for m in builder.members:
        if m['kind'] not in ('beam','girder','moment_beam'):continue
        v=sub(m['axis'][1],m['axis'][0]);direction='X' if abs(v[0])>abs(v[1]) else 'Y'
        role='roof' if m['level']==roof else 'floor'
        for rid,section,selected_role,selected_direction in directional:
            if (m['profile_id'],role,direction)==(section,selected_role,selected_direction) and rid not in m['design_record_ids']:
                m['design_record_ids'].append(rid);builder.used_records.add(rid)
        # The roof-diaphragm chord check applies to perimeter roof beams.
        if role=='roof':
            roof_columns=[q for col in builder.members if col['kind']=='column' for q in col['axis']]
            edge=any(all(abs(q[i]-bound)<.01 for q in m['axis']) for i in (0,1) for bound in (min(q[i] for q in roof_columns),max(q[i] for q in roof_columns))) if roof_columns else False
            rid=builder.record('members','chord-roof-'+m['profile_id'])
            if edge and rid and rid not in m['design_record_ids']:m['design_record_ids'].append(rid);builder.used_records.add(rid)
    for c in builder.connections:
        if not c.get('parameters',{}).get('collector'):continue
        m=members[c['member_ids'][0]];v=sub(m['axis'][1],m['axis'][0]);direction='X' if abs(v[0])>abs(v[1]) else 'Y'
        rid=builder.record('members',f"collector-{direction}-{'roof' if m['level']==roof else 'floor'}-{m['profile_id']}")
        if rid and rid not in m['design_record_ids']:m['design_record_ids'].append(rid);builder.used_records.add(rid)
    # Existing explicitly modelled shear-stud schemes remain their own source.
    if any(m['kind']=='shear_stud' for m in builder.members) or any(c['detail_ref']['id'] in ('review_deck_studs','review_selected_studs') for c in builder.connections):return
    groups=defaultdict(list)
    for m in builder.members:
        if m['kind'] not in ('beam','girder','moment_beam','infill'):continue
        groups[m.get('original_physical_member_id',m['id'])].append(m)
    added=0
    for original,ms in groups.items():
        refs=sorted({r for m in ms for r in m.get('design_record_ids',[])})
        selections=[];count_only=[]
        for rid in refs:
            record=builder.records[rid]['data']
            text=json.dumps({k:record.get(k) for k in ('selection','design_note','checks')})
            for match in re.finditer(r'(\d+)\s*x\s*'+NUMBER+r'\s*in\.?\s+(?:headed\s+)?studs',text,re.I):
                selections.append((int(match[1]),number(match[2]),rid))
            for match in re.finditer(r'(\d+)\s+studs per beam',text,re.I):count_only.append((int(match[1]),rid))
        if not selections:continue
        diameters={d for _,d,_ in selections}
        if len(diameters)!=1:raise ValueError('Conflicting explicit stud diameters on '+original)
        total=max([n for n,_,_ in selections]+[n for n,_ in count_only]);diameter=next(iter(diameters))
        selected_refs=sorted({r for _,_,r in selections}|{r for _,r in count_only})
        lengths=[math.dist(*m['axis']) for m in ms];length=sum(lengths)
        counts=[int(total*l/length) for l in lengths]
        for i in sorted(range(len(ms)),key=lambda i:total*lengths[i]/length-counts[i],reverse=True)[:total-sum(counts)]:counts[i]+=1
        for m,count in zip(ms,counts):
            if not count:continue
            mid=[(a+b)/2 for a,b in zip(*m['axis'])]
            builder.connection(m['id']+':selected-studs','review_selected_studs',mid,[m],selected_refs,
                parameters=dict(count=count,total_source_count=total,diameter=diameter,length_in=5.5,original_physical_member_id=original,
                    piece_length_in=math.dist(*m['axis']),beam_offset_z=sum(q[2] for q in m['end_offsets'])/2),basis='S count/diameter; A stations and length')
            added+=count
    if added:builder.note('SELECTED-STUDS',f'S: {added} explicitly selected headed studs are located on their actual beams. A: centred one-row stations with 6 in end margins and 5-1/2 in shaft length. Cut fictional infill pieces share the original count, apportioned by retained length; no revised composite-capacity verification is claimed.')


def draw(ctx):
    a=ctx.a;par=ctx.params;pid=ctx.pid;depth=effective(ctx.p,pid);length=par['piece_length_in'];z=par['beam_offset_z'];top=z+depth/2
    a.member('BEAM',pid,[-length/2,0,z],[length/2,0,z])
    # Context is already represented by the physical floor panels in the model.
    a.box('SLAB',[-length/2,-18,top],[length,36,6.25],'A','Floor/deck context; actual build-up is in the floor schedule',kind='concrete')
    a.parts[-1]['representation_role']='context_only'
    count=par['count'];margin=min(6,length/4);pitch=(length-2*margin)/(count-1) if count>1 else 0
    points=[[-length/2+margin+i*pitch if count>1 else 0,0,top+par['length_in']] for i in range(count)]
    a.fastener('STUDS',points,[0,0,-1],par['diameter'],par['length_in'],['BEAM','SLAB'],
               f"{count} source headed studs; source diameter {par['diameter']:g} in; A length/stations, illustrative head envelope",screw=True)
    a.weld('STUD-WELDS',[-length/2+margin,0,top],[length/2-margin,0,top],['BEAM','STUDS'],kind='STUD_WELD',description='Stud-weld stations coincide with the individual shafts; no continuous seam weld')
    a.dim([-length/2,0,top],[length/2,0,top],basis='S')
    a.notes.append('Source count is preserved per original beam. Local stations and shaft length are A; source deck rib, stud-strength and installation requirements remain authoritative.')
