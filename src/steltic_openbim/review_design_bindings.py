"""Bind saved checks by their explicit source demand, line and selected section.

These bindings retain the gold calculation's scope; they do not verify a newly
extended physical piece or extrapolate a governing check to another section.
"""
import math,re


def apply(b):
    if not b.key.startswith('hr'):return
    roof=max(m.get('level',0) for m in b.members)
    grid={i:sorted({q[i] for m in b.members if m['kind']=='column' for q in m['axis']}) for i in (0,1)}
    frames=b.config.get('FRAMES',[])
    for rid,record in b.records.items():
        if record['table']!='members':continue
        data=record['data'];inputs=data.get('inputs',{});section=inputs.get('section')
        if not section:continue
        matches=[];basis=None
        if b.key=='hr28' and ('STMF-truss-' in rid or '/truss-' in rid):
            direction=rid[-1] if 'STMF-truss-' in rid else rid.split('/truss-',1)[1][0]
            scope=re.search(r'levels (\d+)-(\d+)',inputs.get('basis',''))
            wanted=section.replace(' ','').replace('flatbar','').upper()
            for m in b.members:
                if not m['id'].startswith('STMF-'+direction+'-'):continue
                if 'STMF-truss-' in rid:
                    if ('roof-' in rid)!=(m['level']==roof):continue
                else:
                    if m['profile_id']!=wanted:continue
                    if scope and not int(scope[1])<=m['level']<=int(scope[2]):continue
                    vertical=abs(m['axis'][1][2]-m['axis'][0][2])>.01 and math.dist(m['axis'][0][:2],m['axis'][1][:2])<.01
                    if '-vertical-' in rid and not vertical:continue
                    if '-diagonal-' in rid and (vertical or m['kind']!='truss_web'):continue
                matches.append(m)
            basis='Source STMF direction, physical constituent section, member function and stated level range; equivalent truss check applies to its complete constituent assembly'
        elif b.key=='hr25' and '/boxed-col-4A4E-' in rid:
            pid=section.split(' +',1)[0];scope=re.search(r'stories (\d+)-(\d+)',inputs.get('basis',''))
            matches=[m for m in b.members if m['kind']=='column' and m['profile_id']==pid and m['axis'][0][0]==1008 and m['axis'][0][1] in (0,1440) and (not scope or int(scope[1])<=m['level']<=int(scope[2]))]
            basis='Source boxed column 4A/4E, selected W core and explicit story range; boxing plates remain separate physical pieces'
        elif b.key=='hr25' and '/smf-chord-' in rid:
            scope=re.search(r'levels (\d+)-(\d+)',inputs.get('basis',''))
            for m in b.members:
                if m['kind'] not in ('beam','girder','moment_beam') or m['profile_id']!=section:continue
                a,z=m['axis'];outer_x=a[0]==z[0] and a[0] in (0,2016);outer_y=a[1]==z[1] and a[1] in (0,1440)
                if scope and not int(scope[1])<=m['level']<=int(scope[2]):continue
                if '-lid-' in rid and m['level']!=7:continue
                if '-A-E-' in rid or '-lid-' in rid:match=outer_y
                elif '-1-7-' in rid:match=outer_x
                else:match=outer_x or outer_y
                if match:matches.append(m)
            basis='Source diaphragm chord: named perimeter grids, exact section and specified levels; source force check retained alongside beam design'
        elif b.key=='hr25' and rid=='members/infill-atrium-W18X35':
            matches=[m for m in b.members if m['profile_id']==section and m['level']<=6 and m['kind'] in ('infill','beam','girder') and any(abs(q[0]-v)<112.01 and 360<=q[1]<=1080 for q in m['axis'] for v in (672,1344))]
            basis='Source infill/corner beams beside the atrium: levels 1-6, selected section and 112 in balcony band'
        elif b.key=='hr13' and 'roof-flexible-check' in rid:
            matches=[m for m in b.members if m['kind']=='brace' and m['profile_id']==section and (m['level']==6 if 'office' in rid else m['level']==4 and all(q[0]==2400 for q in m['axis']))]
            basis='Source flexible roof envelope: all office story-6 braces or Grid-9 workshop upper-storey brace, matching source section'
        elif b.key=='hr13' and rid in ('members/collector-office-W18X35','members/collector-workshop-W24X76'):
            office='office' in rid
            matches=[m for m in b.members if m['kind'] in ('beam','girder','moment_beam') and m['profile_id']==section and (m['level']==5 and all(q[0]==1200 for q in m['axis']) if office else m['level']==2 and all(q[1]==0 for q in m['axis']) and min(q[0] for q in m['axis'])>=1200)]
            basis='Source governing collector line and level: Y5 at 38 ft or workshop XAw at 20 ft'
        elif b.key=='hr19' and rid=='members/transfer-support-col-W36X925':
            matches=[m for m in b.members if m['kind']=='column' and m['profile_id']=='W36X925' and all(q[1]==0 and q[0] in (0,1080) for q in m['axis'])]
            basis='Source A1/A4 transfer support columns, exact W36X925 section; source check includes girder seat/collar reactions'
        elif b.key=='hr16' and rid=='members/library-girder-W24X68':
            matches=[m for m in b.members if m['profile_id']==section and m['level']==1 and m['kind'] in ('beam','girder','moment_beam') and all(1008<=q[0]<=1344 and 336<=q[1]<=1008 for q in m['axis'])]
            basis='Source library floor at 12 ft, Grids 4-5/B-D; exact selected girder section'
        elif b.key.startswith('hr34') and rid in ('members/chord-L2-W21X93','members/chord-L2-Grid9-W24X76','members/floor-W27X84-Y-lines','members/infill-roof-drift-W21X44'):
            edge=max(q[0] for m in b.members if m['kind']=='column' for q in m['axis'])
            for m in b.members:
                if m['profile_id']!=section:continue
                a,z=m['axis']
                if rid=='members/chord-L2-W21X93' and m['level']==2 and a[1]==z[1] and a[1] in (0,1200):matches.append(m)
                if rid=='members/chord-L2-Grid9-W24X76' and m['level']==2 and a[0]==z[0]==edge:matches.append(m)
                if rid=='members/floor-W27X84-Y-lines' and m['level'] in (1,2) and a[0]==z[0] and a[1]!=z[1]:matches.append(m)
                if rid=='members/infill-roof-drift-W21X44' and m['level']==roof and m['kind']=='infill' and a[0]==z[0]==120:matches.append(m)
            basis=f'Source tower local grids: A/D podium chords, outer Grid 9 at local X={edge:g}, Y collectors, or first roof infill 120 in from the inter-tower face'
            if b.key=='hr34b' and rid=='members/floor-W27X84-Y-lines' and not matches:
                actual=[m for m in b.members if m['profile_id']==section and m['kind'] in ('beam','girder','moment_beam')]
                if len(actual)==4 and all(m['level'] in (1,2) and m['axis'][0][1]==m['axis'][1][1] and abs(m['axis'][1][0]-m['axis'][0][0]-441)<.01 for m in actual):
                    reason='Retained unused gold Y-line check for W27X84. All four final W27X84 members run in X over the 441 in podium extension at Levels 1 and 2, with their X-line design records. No W27X84 member runs along a 400 in Y bay. Do not apply this Y-line check or invent its bottom-flange bracing on the X members.'
                    b.record_dispositions=getattr(b,'record_dispositions',[])+[dict(record_id=rid,status='not_applicable',reason=reason,evidence_member_ids=[m['id'] for m in actual])]
                    b.note('UNUSED-Y-COLLECTOR-VARIANT','S: '+reason)
        elif inputs.get('kind') in ('col','column'):
            demand=data.get('engine_P_comp_kip',inputs.get('P_comp_kip'))
            if not isinstance(demand,(int,float)) or demand<=0:continue
            for m in b.members:
                if m['kind']!='column' or m['profile_id']!=section:continue
                try:actual=float(m.get('source_forces',{})['P_comp_kip'])
                except (KeyError,TypeError,ValueError):continue
                if abs(actual-demand)<=.11:matches.append(m)
            basis='Exact saved analysis section and governing axial demand at printed precision'
        elif inputs.get('role')=='collector':
            name=rid.split('/',1)[1];text=inputs.get('basis','')
            hit=re.search(r'collector-(?:setback-L\d+-)?([XY])-',name)
            level=re.search(r'collector-(?:setback-)?L(\d+)-',name)
            line=re.search(r'\bGrid ([A-Z]|\d+)\b',text)
            if not hit:
                hit=re.search(r'\(([XY])\)',text)
            if not hit:continue
            along='XY'.index(hit[1]);normal=1-along;lines=[]
            if line:
                label=line[1];index=int(label)-1 if label.isdigit() else ord(label)-ord('A')
                if 0<=index<len(grid[normal]):lines.append(grid[normal][index])
            if not lines:
                for f in frames or b.config.get('BRACES',[]):
                    direction=f.get('dir') if isinstance(f,dict) else f[0]
                    if direction!='XY'[along]:continue
                    index=f['line'] if isinstance(f,dict) else f[1]
                    if index<len(grid[normal]):lines.append(grid[normal][index])
            if not lines:continue
            for m in b.members:
                if m['kind'] not in ('beam','girder','moment_beam') or m['profile_id']!=section:continue
                a,z=m['axis']
                if abs(a[normal]-z[normal])>.01 or abs(a[along]-z[along])<.01:continue
                if not any(abs(a[normal]-v)<.01 for v in lines):continue
                if level and m['level']!=int(level[1]):continue
                if '-roof-' in name and m['level']!=roof:continue
                if '-floor-' in name and m['level']==roof:continue
                matches.append(m)
            basis='Source collector direction, named grid line, selected section and stated level scope'
        elif b.key=='hr15' and rid=='members/infill-terrace-girder-W24X76':
            for m in b.members:
                if m['profile_id']!=section or m['kind'] not in ('beam','girder','moment_beam'):continue
                x,y=[sum(q[i] for q in m['axis'])/2 for i in (0,1)]
                if m['level']==7 and (x>1800 or y>1440) or m['level']==14 and (x<360 or y<360):matches.append(m)
            basis='Source terrace girder selection at the L7 east/north and L14 west/south setbacks'
        elif b.key=='hr23' and rid=='members/roof-zone-girder-W24X68':
            for m in b.members:
                if m['profile_id']!=section or m['level']!=roof or m['kind'] not in ('beam','girder','moment_beam'):continue
                if all(336-.01<=q[0]<=1344+.01 and 300-.01<=q[1]<=900+.01 for q in m['axis']):matches.append(m)
            basis='Source roof equipment zone: central three by two bays, matching selected girder section'
        for m in matches:
            if rid not in m['design_record_ids']:m['design_record_ids'].append(rid)
            b.used_records.add(rid)
            m.setdefault('design_mapping_evidence',[]).append(dict(record_id=rid,basis=basis))
