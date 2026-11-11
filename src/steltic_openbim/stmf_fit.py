"""Finite STMF truss members, selected gusset slots and welded flat-bar laps."""
import math
import re
from collections import defaultdict

from .assembly_scene import Assembly, bounds
from .bim_assemblies import transformed
from .drawing_workflow import fingerprint
from .hr_brace_fit import slot_for_gusset
from .pilots.geometry import strips,member_faces
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_assemblies import hull


def local(v,frame,point=False):
    v=sub(v,frame['origin']) if point else v
    return [dot(v,k) for k in (frame['x_axis'],frame['y_axis'],cross(frame['x_axis'],frame['y_axis']))]


def end_selection(records,profile,direction,vertical,existing,role):
    """Select the actual vertical/end-diagonal record for this section and plane."""
    for rid,row in records.items():
        typename=row.get('type','').lower();components=row.get('components','')
        if ('stmf '+direction.lower()+' trusses') not in typename or ('vertical' in typename)!=vertical:
            continue
        prior=next((w for w in existing['welds'] if role in w['connects']),None)
        if profile.startswith('PL'):
            clause=next((s['limit_state'] for s in row.get('checks',[])
                         if 'flat bar' in s.get('limit_state','').lower() and 'end connection' in s['limit_state'].lower()),'')
            m=re.search(r'two ([\d.]+)-in fillets x ([\d.]+) in',clause,re.I)
            section=re.search(r'flat bar ([\d.]+) x ([\d.]+)',clause,re.I)
            matches=section and tuple(map(float,section.groups()))==tuple(map(float,profile.removeprefix('PL').split('X')))
            if m and matches:return rid,dict(count=2,size=float(m[1]),length=float(m[2]),kind='lap',basis='S')
            if prior:return rid,dict(count=2,size=prior['size'],length=math.dist(prior['a'],prior['b']),kind='lap',
                                     basis='A retained coordination weld; governing bar is a different section')
        else:
            m=re.search(r'four (\d+)/(\d+) in E70 fillet welds x ([\d.]+) in',components,re.I)
            slot=re.search(r'slot width t_?g\s*\+\s*(\d+)/(\d+) in',components,re.I)
            if m and slot:
                exact=profile in components
                return rid,dict(count=4,size=int(m[1])/int(m[2]) if exact or not prior else prior['size'],
                                length=float(m[3]) if exact or not prior else math.dist(prior['a'],prior['b']),
                                clearance=int(slot[1])/int(slot[2]),kind='slot',
                                basis='S' if exact else 'A retained coordination weld; governing HSS is a different section')
    raise ValueError('Missing selected STMF weld/slot record for '+direction+' '+profile)


def make_scene(source,rows,profiles,records,direction):
    a=Assembly(source['title'],profiles);webs=[r for r in rows if r['kind']=='truss_web']
    chords=[r for r in rows if r['kind']=='truss_chord']
    column=next((r for r in rows if r['kind']=='column'),None)
    if not chords:raise ValueError('STMF node has no bound chord')
    references=set(source.get('source_record_ids',[]))
    material_specs=set()
    for record in records.values():
        if ('STMF '+direction+' trusses').lower() not in record.get('type','').lower():
            continue
        material_specs.update(re.findall(r'slotted for a ([\d.]+) in (.*?) gusset',record.get('components',''),re.I))
    if len(material_specs)!=1:
        raise ValueError('STMF gusset thickness or grade is missing or ambiguous for '+direction)
    selected_t,grade=material_specs.pop()
    t=float(selected_t)
    # A single gusset position serves all webs in one node. Opposite flat bars
    # meet directly at their selected crossing weld and lap their own end gussets.
    flat=next((r for r in webs if profiles[r['pid']]['family']=='flat'),None)
    gy=flat['near'][1]-flat['side']*(profiles[flat['pid']]['dimensions']['thickness']+t)/2 if flat else 0.
    starts={};slots={};outline=[];pending=[];chord_edges=[]
    if column:
        q=column['near'];v=column['axis']
        a.member(column['role'],column['pid'],add(q,mul(v,-24)),add(q,mul(v,24)),y=column['y'],
                 **({'section_plies':column['plies']} if column.get('plies') else {}))
    def support_distance(r,host):
        v=r['away'];h=host['axis'];n=sub(v,mul(h,dot(v,h)))
        if math.dist(n,[0,0,0])<1e-7:return 0.
        n=unit(n)
        def cross_values(row):
            z=cross(row['axis'],row['y'])
            return [u*dot(row['y'],n)+w*dot(z,n) for poly in strips(profiles[row['pid']],profiles) for u,w in poly]
        support=dot(host['near'],n)+max(cross_values(host))
        return (support-dot(r['near'],n)-min(cross_values(r)))/dot(v,n)
    for r in chords:
        d=max(0.,support_distance(r,column)) if column else 0.
        q=add(r['near'],mul(r['away'],d));starts[r['role']]=q
        a.member(r['role'],r['pid'],q,add(q,mul(r['away'],min(35,r['length']-d))),y=r['y'])
        if column:
            profile=profiles[r['pid']]['dimensions']
            for j,sg in enumerate((-1,1)):
                z=cross(r['axis'],r['y'])
                flange=add(q,mul(z,sg*(profile['d']-profile['tf'])/2))
                a.weld(r['role']+'-FLANGE'+str(j),add(flange,mul(r['y'],-profile['bf']/2)),
                       add(flange,mul(r['y'],profile['bf']/2)),[r['role'],column['role']],kind='CJP',
                       description='Source chord flange CJP to column')
        if webs:
            toward=1 if sum(w['away'][2] for w in webs)>0 else -1
            webface=r['near'][2]+toward*profiles[r['pid']]['dimensions']['tw']/2
            edge=[q[0],gy,webface];other=add(edge,mul(r['away'],min(10.,r['length']-d)))
            chord_edges.append((r['role'],edge,other))
            outline.extend([(edge[0],edge[2]),(other[0],other[2])])
    if not webs and not column:
        # Adjacent chord webs need not be at the same elevation or have the
        # same thickness. Fit the lower/upper edge of one splice gusset to
        # the two real web surfaces and preserve each adopted weld length.
        old_gusset=next(p for p in source['parts'] if p['id']=='GUSSET')
        depth=old_gusset['bounds'][2][1]-old_gusset['bounds'][2][0]
        toward=-1 if sum(r['near'][2] for r in chords)>0 else 1
        edges=[]
        for r in chords:
            q=starts[r['role']]
            old_weld=next(w for w in source['welds'] if r['role'] in w['connects'] and 'GUSSET' in w['connects'])
            length=math.dist(old_weld['a'],old_weld['b'])
            z=q[2]+toward*profiles[r['pid']]['dimensions']['tw']/2
            start=[q[0],gy-t/2,z]
            finish=add(start,mul(r['away'],length))
            a.weld(old_weld['id'],start,finish,old_weld['connects'],old_weld['size'],
                   kind=old_weld['kind'],basis='A retained chord splice weld',
                   description='Retained splice weld on the actual horizontal chord web')
            edges.append((min(q[0],finish[0]),max(q[0],finish[0]),z))
        edges.sort()
        outline=[]
        for lo,hi,z in edges:
            for pt in ((lo,z),(hi,z)):
                if not outline or math.dist(outline[-1],pt)>1e-7:
                    outline.append(pt)
        face_z=(max if toward>0 else min)(z for _,_,z in edges)+toward*depth
        outline.extend([(edges[-1][1],face_z),(edges[0][0],face_z)])
        gusset=a.polygon('GUSSET',[[x,gy-t/2,z] for x,z in outline],t,
                        basis='S thickness and grade; A chord-web fit',
                        description='Stepped splice gusset fitted to both chord webs')
        gusset['selected_material']=grade
    for r in webs:
        v=r['away'];pid=r['pid'];pr=profiles[pid];d=max([2.]+[support_distance(r,h)+.125 for h in chords+([column] if column else [])])
        zaxis=cross(r['axis'],r['y'])
        section=[add(mul(r['y'],u),mul(zaxis,z)) for poly in strips(pr,profiles) for u,z in poly]
        for other in webs:
            if other is r:continue
            diff=sub(v,other['away'])
            if math.dist(diff,[0,0,0])<.01:continue
            n=unit(diff);d=max(d,(.125-min(dot(q,n) for q in section)-dot(r['near'],n))/dot(v,n))
        rid,selected=end_selection(records,pid,direction,abs(v[2])>.999,source,r['role'])
        references.add(rid);wl=selected['length'];q=add(r['near'],mul(v,d))
        if d+wl>=r['length']:
            raise ValueError('STMF cutback consumes source weld length at '+r['role'])
        starts[r['role']]=q
        part=a.member(r['role'],pid,q,add(q,mul(v,min(wl+12,r['length']-d))),y=r['y'])
        across=unit([-v[2],0.,v[0]])
        extent=pr['dimensions'].get('h',pr['dimensions'].get('width'))/2
        if selected['kind']=='slot':
            for side in (-1,1):
                for face in (-1,1):
                    start=add(q,mul(across,side*extent));start[1]=gy+face*t/2
                    finish=add(start,mul(v,wl))
                    a.weld(r['role']+f'-S{side}-{face}',start,finish,[r['role'],'GUSSET'],
                           selected['size'],basis=selected['basis'],description='Slotted HSS weld, four lines')
                    outline.extend([(start[0],start[2]),(finish[0]+v[0]*t,finish[2]+v[2]*t)])
            pending.append((r,part,selected))
        else:
            for side in (-1,1):
                start=add(q,mul(across,side*extent));start[1]=gy+r['side']*t/2
                finish=add(start,mul(v,wl))
                a.weld(r['role']+f'-L{side}',start,finish,[r['role'],'GUSSET'],selected['size'],
                       basis=selected['basis'],description='Flat-bar lap fillet along the actual bar edge')
                outline.extend([(start[0],start[2]),(finish[0]+v[0]*t,finish[2]+v[2]*t)])
    if webs:
        for role,edge,other in chord_edges:
            a.weld('G-'+role,edge,other,[role,'GUSSET'],.3125,basis='A',
                   description='Gusset to actual chord web; openBIM fit weld path')
        poly=hull(outline)
        gusset=a.polygon('GUSSET',[[x,gy-t/2,z] for x,z in poly],t,
                         basis='S thickness and grade; A located perimeter',description='Source STMF node gusset')
        gusset['selected_material']=grade
        for r,part,selected in pending:
            slot=slot_for_gusset(a,part,gusset,t,t+selected['clearance'])
            # Map the plate mid-plane to the true local section coordinates.
            local_y=part['member']['local_y'];v=r['away']
            axes=(local_y,cross(v,local_y));idx=max(range(2),key=lambda i:abs(axes[i][1]))
            slot.update(section_axis=idx,centre_in=(gy-part['member']['axis'][0][1])*axes[idx][1])
            part['member']['slots']=[slot];part['faces']=member_faces(part['member'],profiles);part['bounds']=bounds(part['faces'])
            slots[r['role']]=slot
    a.notes.append('Explicit source welds and slot widths follow the selected vertical, diagonal or flat-bar detail; remaining terminal stations and gusset perimeter are openBIM fits.')
    scene=dict(source,**{k:v for k,v in a.result().items() if k not in ('id','reference','sheet')})
    scene['source_record_ids']=sorted(references)
    return scene,starts,slots


def repair_stmf(package,model):
    physical=package['physical'];members={m['id']:m for m in physical['members']}
    profiles={r['id']:r for r in physical['profiles']};source={m['id']:m for m in model['members']}
    original={s['id']:s for s in model['connection_assemblies']}
    records={r['id']:r['data'] for r in package['design_records']}
    crossing_plies={}
    for interface in package.get('source_handoff',{}).get('crossing_interfaces',[]):
        if interface['kind']!='flat_bar_crossing_plate':continue
        normal=unit(interface['plate']['normal'])
        for face in interface['member_faces']:
            mid=face['member_id'];sign=face['face_sign'];thick=interface['plate']['thickness_in']
            if sign not in (-1,1) or not thick>0:raise ValueError('Invalid crossing plate face or thickness at '+interface['id'])
            crossing_plies[mid]=(normal,sign,thick)
    connections={c['id']:c for c in model['connections']};cache={};variants=defaultdict(list);changed={};edits=defaultdict(dict)
    for c in physical['connections']:
        scene=original.get(c.get('assembly_id'));frame=c.get('assembly_instance',{})
        if not scene or scene['family'] not in ('review_stmf_node','review_stmf_end'):continue
        direction=c['parameters']['direction'];along=0 if direction=='X' else 1;other=1-along
        normal=[float(i==other) for i in range(3)];rows=[]
        for role,mid in frame['bindings'].items():
            m=members.get(mid)
            if not m:continue
            e=m['axis'];axis=unit(sub(e[1],e[0]));near_i=min(range(2),key=lambda i:math.dist(e[i],frame['origin']))
            sign=1 if axis[along]*axis[2]>0 else -1
            is_flat=profiles[m['profile_id']]['family']=='flat' and m['kind']=='truss_web'
            offset=mul(normal,sign*profiles[m['profile_id']]['dimensions']['thickness']/2) if is_flat else [0,0,0]
            if mid in crossing_plies:
                selected_normal,face,thick=crossing_plies[mid]
                offset=mul(selected_normal,face*(thick+profiles[m['profile_id']]['dimensions']['thickness'])/2)
                sign=face*(1 if dot(selected_normal,normal)>0 else -1)
            y=unit(cross(normal,axis)) if is_flat else m['local_y']
            near=add(e[near_i],offset)
            if m['kind']=='column':near=add(e[0],mul(axis,dot(sub(frame['origin'],e[0]),axis)))
            rows.append(dict(role=role,mid=mid,pid=m['profile_id'],kind=m['kind'],end=near_i,local_y=y,
                side=sign*dot(local(normal,frame),[0,1,0]),near=local(near,frame,True),axis=local(axis,frame),
                away=local(mul(axis,1 if near_i==0 else -1),frame),y=local(y,frame),length=math.dist(*e)))
            if m.get('section_plies'):
                from .hr_boxed_plies import cropped_plies
                station=dot(sub(near,add(e[0],m['end_offsets'][0])),axis)
                rows[-1]['plies']=cropped_plies(m['section_plies'],station-24,station+24)
        rows.sort(key=lambda r:r['role'])
        key=(scene['id'],direction,tuple((r['role'],r['pid'],r['kind'],round(r['length'],5),fingerprint(r.get('plies',[])),
            *(round(x,5) for attr in ('near','away','y') for x in r[attr])) for r in rows))
        if key not in cache:
            made,starts,slots=make_scene(scene,rows,profiles,records,direction)
            made['occurrences']=[];variants[scene['id']].append(made);cache[key]=(made,starts,slots)
        made,starts,slots=cache[key];made['occurrences'].append(c['id']);changed[c['id']]=made
        for r in rows:
            if r['role'] not in starts:continue
            m=members[r['mid']];m['local_y']=r['local_y']
            q=transformed(starts[r['role']],frame);end=r['end']
            offset=sub(q,m['axis'][end]);previous=edits[m['id']].get(end)
            if previous and math.dist(previous[0],offset)>1e-4:raise ValueError('Conflicting STMF terminal placements for '+m['id'])
            slot=slots.get(r['role'])
            if slot:
                # Local receiver axis points away from this joint; the global
                # member orientation can reverse section-axis 1.
                if slot['section_axis']==1 and end:slot=dict(slot,centre_in=-slot['centre_in'])
            edits[m['id']][end]=(offset,c['id'],slot)
    for mid,ends in edits.items():
        m=members[mid];m['end_offsets']=[ends[i][0] if i in ends else v for i,v in enumerate(m['end_offsets'])]
        length=math.dist(*[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])])
        slots=[s for s in m.get('slots',[]) if s.get('connection_id') not in {r[1] for r in ends.values()}]
        for end,(_,cid,slot) in ends.items():
            if slot:
                depth=slot['end_in']-slot['start_in']
                if depth>=length:raise ValueError('STMF slot consumes member '+mid)
                slots.append(dict(slot,connection_id=cid,start_in=length-depth if end else 0.,end_in=length if end else depth))
        if slots:m['slots']=slots
        for field in ('local_y','end_offsets','slots'):
            if field in m:source[mid][field]=m[field]
    number=max((int(s['sheet'][1:]) for s in original.values() if re.fullmatch(r'C\d+',s['sheet'])),default=0)
    revised=[]
    for sid,old in original.items():
        if sid not in variants:revised.append(old);continue
        for i,made in enumerate(variants[sid]):
            if i:
                number+=1;made['id']=f'CD{number:03}';made['sheet']=f'C{number:03}';made['reference']='1/'+made['sheet']
            made['occurrence_count']=len(made['occurrences']);made['geometry_sha256']=fingerprint([made['parts'],made['welds'],made['interfaces']])
            for cid in made['occurrences']:
                connections[cid].update(assembly_id=made['id'],drawing_ref=made['reference'])
            revised.append(made)
    model['connection_assemblies']=revised
    return changed
