"""Complete, paginated parts and notes for assembled connection drawings."""


def weld_groups(scene):
    groups={}
    labels={p['id']:p.get('annotation_group',p['id']) for p in scene['parts']}
    for weld in scene['welds']:
        key=(weld['basis'],weld['kind'],weld['size'],weld['description'],tuple(labels.get(i,i) for i in weld['connects']))
        groups.setdefault(key,[]).append(weld)
    for key,welds in groups.items():
        label=welds[0]['id'] if len(welds)==1 else welds[0]['id']+'..'+welds[-1]['id']
        yield label,key,welds


def entries(scene):
    rows=[];groups={};part_labels={}
    for part in scene['parts']:
        label=part.get('annotation_group',part['id'])
        groups.setdefault(label,[]).append(part);part_labels[part['id']]=label
    def joined(ids):return ', '.join(dict.fromkeys(part_labels.get(i,i) for i in ids))
    for label,parts in groups.items():
        part=parts[0];description=part['description']
        if len(parts)>1 and part['kind']!='fastener':description+=f' | qty {len(parts)}; repeated group'
        if part.get('geometry',{}).get('type')=='box':description+=' | '+' x '.join(f'{v:g}' for v in part['geometry']['size'])+' in'
        if part['kind']=='fastener':
            description+=f" | qty {sum(p['count'] for p in parts)}; grip {part['grip']:g} in"
            if 'pattern' in part:
                pat=part['pattern'];description+=' | grid '+' / '.join(f'{n} at {d:g} in' for n,d in zip(pat['counts'],pat['spacing']) if n>1 and d is not None)
        basis=str(part['basis'])
        if basis not in ('S','A'):
            description+=' | Basis: '+basis
            basis='S/A' if 'S' in basis and 'A' in basis else 'S' if basis.startswith('S') else 'A'
        rows.append(dict(label=label,basis=basis,text=description,note=False))
    for label,(basis,kind,size,description,connects),welds in weld_groups(scene):
        spec=(f'{size:g} in ' if kind=='fillet' else '')+kind
        rows.append(dict(label=label,basis=basis,note=False,text=spec+' | '+description+' | '+joined(connects)+(f' | {len(welds)} weld lines' if len(welds)>1 else '')))
    rows.extend(dict(label=i['id'],basis=i['basis'],note=False,text=i['description']+' | '+joined(i['connects'])) for i in scene.get('interfaces',[]))
    rows.extend(dict(label='',basis='',note=True,text=t) for t in scene['notes'])
    for row in rows:
        basis=str(row['basis'])
        if basis not in ('S','A','S/A',''):
            row['text']+=' | Basis: '+basis
            row['basis']='S/A' if 'S' in basis and 'A' in basis else 'S' if basis.startswith('S') else 'A'
    return rows


def pages(sh,scene):
    """First page is the 584-point legend panel; later pages use full sheets."""
    source=entries(scene);result=[[]];used=0
    for row in source:
        width=1070 if row['note'] else 965
        # Reflow the next whole entry at the continuation sheet's wider width.
        if len(result)>1:width=2050 if row['note'] else 1952
        lines=sh.lines(row['text'],width,10);step=14 if row['note'] else 13;gap=10 if row['note'] else 6
        capacity=584 if len(result)==1 else 1250
        if used+len(lines)*step+gap>capacity and result[-1]:
            result.append([]);used=0;capacity=1250
            width=2050 if row['note'] else 1952;lines=sh.lines(row['text'],width,10)
        while lines:
            count=max(0,int((capacity-used-gap)//step))
            if not count:
                result.append([]);used=0;capacity=1250;continue
            chunk,lines=lines[:count],lines[count:]
            result[-1].append(dict(row,lines=chunk,step=step,gap=gap))
            used+=len(chunk)*step+gap
            if lines:
                result.append([]);used=0;capacity=1250
                row=dict(row,label=row['label']+' (cont.)' if row['label'] else '')
    return result


def number(scene,index):return f"{scene['sheet']}N{index:02}"


def draw(sh,scene,index=0):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    layout=pages(sh,scene);x,y=(1210,774) if index==0 else (80,sh.H-195)
    for row in layout[index]:
        if not row['note']:
            size=min(11,11*56/max(1,stringWidth(row['label'],'Helvetica-Bold',11)))
            sh.text(x,y,row['label'],size,font='Helvetica-Bold')
            sh.text(x+64,y,row['basis'],10,'#946320' if row['basis']=='A' else '#243d49')
        for line in row['lines']:
            sh.text(x+(0 if row['note'] else 98),y,line,10);y-=row['step']
        y-=row['gap']
    if y<190:raise ValueError('Assembly legend pagination overflow '+scene['id'])
    if index+1<len(layout):sh.text(x,186,'Parts and notes continue on '+number(scene,index+1),11,font='Helvetica-Bold')
    sh.text(x,170,'Source variant and exact assembly geometry: connection_assemblies.json / '+scene['id'],10)


def continuation_jobs(sh,scene):
    for index in range(1,len(pages(sh,scene))):
        yield number(scene,index),scene['sheet']+' / parts and notes continued',lambda index=index:draw(sh,scene,index)
