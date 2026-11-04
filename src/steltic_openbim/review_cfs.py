"""Physical wall, floor and roof reconstruction from completed CFS schedules."""
from __future__ import annotations
import math,re
from collections import defaultdict
from .review_model import add,sub,mul,unit,MIL
from .assembly_templates import number,NUMBER

SHAPE=r'(?:\d+\s*[xX]\s*)?\d{3,4}[STUZ]\d{3}-\d{2,3}'

def section(text,default='600S162-54'):
    match=re.search(SHAPE,str(text),re.I)
    if match:return re.sub(r'\s+','',match[0]).upper()
    match=re.search(r'(?:HSS[\d.]+[xX][\d.]+[xX][\d./]+|W\d+[xX][\d.]+)',str(text),re.I)
    return match[0].upper() if match else default

def story_value(record,k):
    for key in ('rows','rod_schedule','post_schedule'):
        row=next((r for r in record.get(key,[]) if r.get('story',r.get('level'))==k),None)
        if row:return dict(record,**row)
    result=dict(record);txt=record.get('section','');match=re.search(r'\b(?:L|s)'+str(k)+r'\s*:?\s+([^;]+)',txt)
    if match:result['section']=match[1]
    rod=re.search(r'\bL'+str(k)+r'\s+'+NUMBER+r'\s*in',record.get('selection',''))
    if rod:result['rod']=rod[1]+' in.'
    if not rod:
        hit=re.search(r'rods?(?: by story)?:?\s*((?:'+NUMBER+r' in\.?[, ]*)+)\s*\(story 1 to',record.get('selection',''))
        if hit:
            sizes=re.findall(NUMBER+r' in',hit[1])
            if k<=len(sizes):result['rod']=sizes[k-1]+' in.'
    for check in record.get('checks',[]):
        if check.get('story')!=k and not re.search(r'\bstory '+str(k)+r'\b',check.get('limit_state','')):continue
        if check.get('rod'):result['rod']=check['rod']
        if 'bracket' in check.get('limit_state','') and check.get('screws'):result['bracket_screws']=check['screws']
    return result

def physical_pack(b,text,label):
    parts=re.findall(r'(\d+)\s*[xX]\s*(\d{3,4}S\d{3}-\d{2,3})',text,re.I)
    if not parts:return b.profile(section(text))
    total=sum(int(n) for n,_ in parts)
    if len(parts)==1 and total%2==0:return b.pack(b.profile(parts[0][1]),total,'box',label=label,gap=.25)
    comps=[];i=0
    for count,pid in parts:
        pid=b.profile(pid)
        for _ in range(int(count)):
            comps.append(dict(profile_id=pid,offset=[(i-(total-1)/2)*2.25,0],rotation_deg=180 if i%2 else 0));i+=1
    return b.custom(label,'built_up',{},components=comps,basis='A: explicitly spaced mixed source chord plies; source count/sections retained')

def intersections(poly,axis,station):
    other=1-axis;intervals=[]
    # A re-entrant boundary can have floor/wall material on either side at
    # different stations. The first nonempty side alone omits the return leg.
    for offset in (1e-5,-1e-5):
        hits=[];s=station+offset
        for a,d in zip(poly,poly[1:]+poly[:1]):
            if (a[other]<=s<d[other]) or (d[other]<=s<a[other]):hits.append(a[axis]+(d[axis]-a[axis])*(s-a[other])/(d[other]-a[other]))
        hits.sort();intervals.extend(zip(hits[::2],hits[1::2]))
    result=[]
    for lo,hi in sorted(intervals):
        if result and lo<=result[-1][1]+1e-7:result[-1]=(result[-1][0],max(result[-1][1],hi))
        else:result.append((lo,hi))
    return result

def spaced_segments(lo,hi,widths,margin=None):
    spare=hi-lo-sum(widths)
    if spare<-.05:raise ValueError(f'Source segments exceed physical wall run {lo,hi,widths}')
    gap=spare/max(1,len(widths)-1) if margin==0 else spare/(len(widths)+1)
    x=lo+(0 if margin==0 else gap);result=[]
    for w in widths:result.append((x,x+w));x+=w+gap
    return result

def build(b):
    if b.key in ('cfs10','cfs18','cfs25','cfs27','cfs28'):
        from .review_next_cfs_frames import build as frames
        frames(b);return
    if b.key in ('cfs17','cfs19','cfs26','cfs30'):
        from .review_cfs_frames import build as frames
        frames(b);return
    from .review_next_cfs_walls import KEYS as next_keys,prepare,locations as next_locations,depth as next_depth,stud as next_stud,floors as next_floors
    from . import review_final_cfs as final
    if b.key in final.KEYS:final.prepare(b)
    if b.key in next_keys:prepare(b)
    cfg=b.cfg;lx,ly=cfg['plan_ft'];base=180 if b.key in ('cfs3','cfs4') else 288 if b.key=='cfs9' else 0
    heights=cfg['heights_ft'];levels=[base]
    for h in heights:levels.append(round(levels[-1]+12*h,3))
    b.levels=[(k,'PODIUM TOP' if k==0 and base else ('BASE' if k==0 else ('ROOF BEARING' if k==len(heights) else 'L'+str(k+1)+' FFL')),z) for k,z in enumerate(levels)]
    if b.key=='cfs29':b.levels=[(0,'EXISTING SLAB',0),(1,'MEZZANINE FFL',levels[1])]
    outline=cfg.get('plan_outline_ft',[[0,0],[lx,0],[lx,ly],[0,ly]])
    bystory=cfg.get('plan_outline_by_story',{})
    if b.key=='cfs14':bystory['1']=[[0,0],[120,0],[120,35],[0,35]]
    ordinary=next((r for r in b.raw['studs'] if r['id'].startswith('stud-typ')),b.raw['studs'][0])
    rawwalls={r['id']:r for r in b.raw['wall_lines']};chords={r['id']:r for r in b.raw['studs'] if r['id'].startswith('chord-')};holds={r['id']:r for r in b.raw['holddowns']}
    line_configs=[]
    for d in ('X','Y'):
        for line in cfg.get('lines_'+d.lower(),[]):line_configs.append((d,line))
    for d,line in line_configs:
        name=line['name'];axis=0 if d=='X' else 1;normal=1-axis;pos=cfg.get('line_plan_pos_ft',{}).get(d+'-'+name,line['pos'])
        for sk,segs in line['segments'].items():
            k=int(sk)
            if not segs:continue
            poly=bystory.get(str(k),outline);ranges=intersections(poly,axis,pos)
            widths=[x[0] for x in segs]
            if not ranges:raise ValueError(f'{b.key} source wall {name} outside physical footprint')
            lo,hi=ranges[0][0],ranges[-1][1]
            if b.key=='cfs3':
                if name in ('XS','XN'):locations=[(13+14*j,21+14*j) for j in range(14)]
                elif name in ('XCS','XCN'):locations=[(14+12*j,22+12*j) for j in range(16)]
                else:
                    half=len(widths)//2;locations=spaced_segments(0,29,widths[:half],0)+spaced_segments(35,64,widths[half:],0)
            elif b.key=='cfs7':
                if name=='XM':lo,hi=90,150
                elif name.startswith('YN'):lo,hi=58,116
                elif name.startswith('YS'):lo,hi=0,58
                locations=spaced_segments(lo,hi,widths,0 if len(widths)==1 else None)
            elif b.key=='cfs11':
                if name.startswith('XW'):lo,hi=0,26
                elif name in ('XB70','XB96'):lo,hi=0,160
                elif name=='Y0':lo,hi=0,96
                elif name=='Y26':lo,hi=0,96;pos=26
                else:lo,hi=70,96
                if name in ('Y0','Y26'):
                    n=5;locations=spaced_segments(0,70,widths[:n])+spaced_segments(70,96,widths[n:],0)
                else:locations=spaced_segments(lo,hi,widths,0 if len(widths)==1 else None)
                if k==1 and name in ('XB70','XB96'):
                    # Reserve the source breezeway between P80 and P93.
                    left=[w for j,w in enumerate(widths) if j<len(widths)//2];right=widths[len(left):]
                    locations=spaced_segments(0,80,left)+spaced_segments(93.333,160,right)
            elif b.key=='cfs13':
                rs={'SW':(0,72.5),'SE':(97.5,130),'SEE':(130,170),'NB':(72.5,97.5),'NW':(0,130),'NE':(130,170)}
                if name in rs:lo,hi=rs[name]
                elif name.startswith('NC'):lo,hi=0,20
                elif name=='P85':lo,hi=20,64
                locations=spaced_segments(lo,hi,widths,0 if name in rs else None)
            elif b.key=='cfs14':
                if name.endswith('S') and d=='Y':lo,hi=0,35
                elif name.endswith('N') and d=='Y':lo,hi=35,70
                raw=rawwalls[f'wall-{d}-{name}-s{k}'];txt=raw.get('selection','');match=re.search(r'at\s+[xy]\s*=\s*(.*)',txt)
                locations=[tuple(map(float,m)) for m in re.findall(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)',match[1])] if match else []
                if len(locations)!=len(widths):locations=spaced_segments(lo,hi,widths)
            elif b.key in next_keys:locations=next_locations(b,d,line,k,ranges)
            elif b.key in final.KEYS:locations=final.locations(b,d,line,k,ranges)
            else:
                # CFS29's end-wall bay is 16 ft in the checked design. Keep the
                # adopted centre at Y=16 ft, but derive its width from the actual
                # selected segment rather than copying the 12 ft X-wall width.
                if d=='X':
                    if len(widths)!=2:raise ValueError('Mezzanine X wall requires its two selected bay lengths')
                    locations=[(0,widths[0]),(60-widths[1],60)]
                else:
                    if len(widths)!=1:raise ValueError('Mezzanine Y wall requires its selected bay length')
                    locations=[(16-widths[0]/2,16+widths[0]/2)]
            record=rawwalls.get(f'wall-{d}-{name}-s{k}',{});props=dict(line.get('wall_props') or {});props.update(props.get('by_story',{}).get(str(k),{}))
            floor_depth=14 if b.key=='cfs3' else (14.25 if b.key=='cfs13' else (16.25 if b.key=='cfs14' else 12))
            z0=levels[k-1];zt=levels[k]-(floor_depth if k<len(heights) or b.key=='cfs3' else 0)
            if b.key in next_keys:floor_depth=next_depth(b,k);zt=levels[k]-floor_depth
            if b.key in final.KEYS:floor_depth=final.depth(b,k);zt=levels[k]-floor_depth
            if b.key=='cfs7':
                from .review_cfs7 import depth as bar_depth,finish as bar_finish
                floor_depth=bar_depth(k==len(heights));zt=levels[k]-floor_depth
                z0=levels[k-1]-(bar_finish() if k>1 else 0)
            if b.key=='cfs29':floor_depth=14 if name=='XM' else 12;zt=levels[k]-floor_depth
            # This line is a geometric physical wall, not its fitted tributary line.
            runs=[]
            for j,(a,dend) in enumerate(locations):
                actual_pos=26.667 if b.key=='cfs11' and name=='Y26' and a>=70 else pos
                runs.append(dict(start_in=a*12,end_in=dend*12,position_in=actual_pos*12))
            wall=dict(id=f'{name}-L{k}',line=name,direction=d,level=k,base_z_in=z0,top_z_in=zt,runs=runs,basis='A: source lengths; adopted physical bay set-out',source_record=b.record('wall_lines',record.get('id')))
            b.walls.append(wall)
            rstud=story_value(ordinary,k)
            if b.key=='cfs3':
                wanted='stud-segments-97-ext' if name in ('XS','XN') else ('stud-segments-97-cor' if name in ('XCS','XCN') else 'stud-demising')
                rstud=story_value(next((r for r in b.raw['studs'] if r['id']==wanted),ordinary),k)
            elif b.key=='cfs7':rstud=story_value(next((r for r in b.raw['studs'] if r['id']=='stud-cross-segments'),ordinary),k)
            elif b.key in next_keys:rstud=next_stud(b,d,name,k,props,ordinary)
            elif b.key in final.KEYS:rstud=final.stud(b,d,name,k,props,ordinary)
            studpid=b.profile(section(rstud.get('section')));spacing=float(rstud.get('spacing_in',12 if b.key=='cfs14' else 16));trackpid=b.profile('600T150-'+str(int(round(props.get('t_stud_in',.054)*1000))))
            if b.key=='cfs29':spacing=12 if name=='XM' else 24
            if b.key=='cfs5':trackpid=b.profile('600T125-97')
            chordrec=story_value(chords.get(f'chord-{d}-{name}',{}),k);hold=story_value(holds.get(f'hd-{d}-{name}',{}),k)
            if b.key=='cfs14' and ((name in ('S','M','N') and k>=3) or (name in ('C1S','C2S') and k>=2)):
                hold=story_value(holds[f'hd-{d}-{name}-above'],k)
            chordpid=physical_pack(b,chordrec.get('section',hold.get('section','2x600S200-68')),f'CH-{name}-L{k}')
            bracket=next((r for r in b.raw['connections'] if r['id']==f'conn-rod-bracket-{d}-{name}'),{})
            bracket_text=bracket.get('selection',hold.get('selection',''))
            cm=re.search(r'(\d+(?:-\d+/\d+|/\d+|\.\d+)?)\s*in\. clear between',bracket_text)
            clear=number(cm[1]) if cm else 4
            pp=b.profiles[chordpid]
            if pp['family']=='built_up' and b.key!='cfs29':
                # Open rod space: source pack count retained, explicit adopted arrangement.
                for ci,component in enumerate(pp['components']):
                    cp=b.profiles[component['profile_id']];sign=-1 if ci%2==0 else 1
                    layer=ci//2;web=cp['dimensions']['t'];flange=cp['dimensions']['b']
                    shift=0 if layer==0 else web+.02 if layer==1 else web+.02+2*flange-.25
                    component['offset']=[sign*(clear/2+web/2+shift),0]
                    inward=layer!=1
                    component['rotation_deg']=(0 if sign<0 else 180) if inward else (180 if sign<0 else 0)
            if b.key=='cfs14' and ((name in ('S','M') and k<=2) or name=='N' and k==2 or name in ('C1S','C2S') and k==1):chordpid=b.profile('HSS6X6X5/16')
            for j,run in enumerate(runs):
                a,dend,posin=run['start_in'],run['end_in'],run['position_in'];label=f'{name}-L{k}-B{j+1}'
                def pt(u,z):return [u,posin,z] if axis==0 else [posin,u,z]
                local_y=[1,0,0] if axis==0 else [0,1,0]
                bottom=b.member(label+'-BT',trackpid,'bottom_track',pt(a,z0),pt(dend,z0),k,'A',local_y=[0,0,1],records=[wall['source_record']]);top=b.member(label+'-TT',trackpid,'top_track',pt(a,zt),pt(dend,zt),k,'A',local_y=[0,0,-1],records=[wall['source_record']])
                b.connection(bottom['id'],'review_cfs_sill',pt(a+6,z0),[bottom], [b.record('anchorage',f'anch-{d}-{name}')],parameters={'podium':base>0,'slab_thickness':12 if base else (6 if b.key=='cfs29' else 10)})
                b.connection(top['id'],'review_cfs_floor',pt(a,zt),[top],[b.record('connections',f'conn-floor-{d}-{name}')],parameters={'concrete_slab':b.key=='cfs3','floor_depth':floor_depth})
                for side,u in enumerate((a,dend) if b.key=='cfs29' else (a+3,dend-3)):
                    if b.key=='cfs5' and d=='Y':
                        continuous_left=j>0 and abs(runs[j-1]['end_in']-a)<.1
                        continuous_right=j<len(runs)-1 and abs(runs[j+1]['start_in']-dend)<.1
                        if side==0 and continuous_left:continue
                        if side==1 and continuous_right:
                            postrec=story_value(next(r for r in b.raw['studs'] if r['id']==f'post-Y-{name}'),k)
                            post=b.member(label+'-INTERMEDIATE',physical_pack(b,postrec['section'],f'POST-{name}-{k}'),'chord',pt(dend,z0+.1),pt(dend,zt-.1),k,'A',local_y=local_y,records=[b.record('studs',postrec['id'])]);b.ends(post,'cfs_stud');continue
                    typeii=b.key=='cfs13' and name in ('SW','SE','SEE','NB','NW','NE');is_end=not typeii or (j==0 and side==0) or (j==len(runs)-1 and side==1)
                    cp=chordpid if is_end else b.profile('2X600S162-54')
                    chord_top=levels[k] if b.key=='cfs29' else zt-.1
                    chord=b.member(label+'-CH'+str(side),cp,'chord' if is_end else 'opening_jamb',pt(u,z0+.1),pt(u,chord_top),k,'A',local_y=local_y,records=[b.record('studs',chordrec.get('id'))])
                    if is_end:
                        rtext=str(hold.get('rod',hold.get('selection','5/8 in.')));dia=number(re.search(NUMBER+r'\s*in',rtext)[1]) if re.search(NUMBER+r'\s*in',rtext) else .625
                        if b.key=='cfs29':b.connection(chord['id']+':0','review_cfs_post',chord['axis'][0],[chord],[b.record('holddowns',hold.get('id'))],parameters={'at_base':True,'embedment':4})
                        elif b.profiles[cp]['family']=='rhs':b.ends(chord,'review_cfs_post',[b.record('holddowns',hold.get('id'))],parameters={'at_base':k==1 or name=='N' and k==2,'embedment':12})
                        else:
                            if not .375<=dia<=3:raise ValueError(f'{b.key} {label}: invalid source rod diameter {dia}; use the story-specific rod record')
                            rodpid=b.custom(f'ROD-{dia:g}','round',{'d':dia},basis='S: scheduled tie rod');rod=b.member(label+'-ROD'+str(side),rodpid,'hold_down_rod',pt(u,z0-2),pt(u,zt+4),k,'A',records=[b.record('holddowns',hold.get('id'))])
                            refs=[b.record('holddowns',hold.get('id')),b.record('connections',f'conn-rod-bracket-{d}-{name}'),b.record('studs',chordrec.get('id'))]
                            count=hold.get('bracket_screws') or (re.search(r'(\d+) No\.?\s*14',bracket_text)[1] if re.search(r'(\d+) No\.?\s*14',bracket_text) else 8)
                            b.connection(chord['id']+'-HD','review_cfs_hold_down',pt(u,zt),[chord,rod,top],refs,parameters={'rod_diameter':dia,'story':k,'bracket_screws':count,'bracket_clear':clear,'floor_depth':floor_depth})
                            if k==1:b.connection(chord['id']+'-FOUND','review_rod_foundation',pt(u,z0),[chord,rod],[b.record('holddowns',hold.get('id')),b.record('anchorage',f'anch-{d}-{name}')],parameters={'rod_diameter':dia,'embedment':8 if b.key=='cfs3' else 12,'podium':b.key=='cfs3'})
                    else:b.ends(chord,'cfs_stud')
                for n,u in enumerate(frange(a+spacing,dend-6,spacing)):
                    m=b.member(label+f'-S{n}',studpid,'stud',pt(u,z0+.1),pt(u,zt-.1),k,'A',local_y=local_y,records=[b.record('studs',rstud.get('id'))]);b.ends(m,'cfs_stud',[b.record('connections','conn-stud-to-track')])
                bridge=b.custom('CRC1.5X.5-54','channel',dict(d=1.5,b=.5,t=.0566,lip=0),basis='S: source bridging section')
                for row,z in enumerate(frange(z0+float(ordinary.get('bridging_in',48)),zt-1,float(ordinary.get('bridging_in',48)))):
                    m=b.member(label+f'-BR{row}',bridge,'stud_bridging',pt(a,z),pt(dend,z),k,'A');b.ends(m,'cfs_stud_bridging',parameters={'screw_count':2})
                if props.get('sheathing')=='strap' or 'strap' in record.get('sheathing','').lower():
                    txt=record.get('selection','');w=number(re.search(r'(\d+(?:\.\d+)?)\s*(?:in\.)?\s*x\s*(?:0\.|\d+\s*mil)',txt,re.I)[1]) if re.search(r'(\d+(?:\.\d+)?)\s*(?:in\.)?\s*x\s*(?:0\.|\d+\s*mil)',txt,re.I) else 2.5
                    tm=re.search(r'\bx\s*(0\.\d+)\s*in',txt,re.I)
                    mil=re.search(r'\bx\s*(\d+)\s*mil',txt,re.I)
                    t=float(tm[1]) if tm else MIL[int(mil[1])] if mil else .0451
                    # Ex2 selection includes strap area in in2, not a plate thickness.
                    if b.key=='cfs2':t=MIL[68 if w==8 else 54]
                    if b.key=='cfs5':t=MIL[int(mil[1])]
                    strap=b.custom(f'STRAP-{w:g}X{t:g}','flat',dict(width=w,thickness=t),basis='S: source strap schedule')
                    for face in (-1,1):
                        for diagonal,(u,v) in enumerate(((a,dend),(dend,a))):
                            aa,dd=pt(u,z0),pt(v,zt);aa[normal]+=face*(3+(t/2 if b.key=='cfs29' else 0));dd[normal]+=face*(3+(t/2 if b.key=='cfs29' else 0))
                            m=b.member(label+f'-X{face}-{diagonal}',strap,'strap',aa,dd,k,'A',records=[wall['source_record']],local_y=local_y)
                            b.ends(m,'review_cfs_strap',[wall['source_record'],b.record('connections',f'conn-strap-{d}-{name}')],parameters={'story':k,'line':name})
                else:
                    thick=props.get('t_sheathing_in',.5);faces=int(props.get('faces',2 if 'gypsum' in record.get('sheathing','').lower() else 1))
                    for face in range(faces):
                        verts=[pt(a,z0),pt(dend,z0),pt(dend,zt),pt(a,zt)]
                        for q in verts:q[normal]+=3*(1 if face==0 else -1)
                        b.panel(label+f'-SHEATH{face}','sheathing',verts,thick,k,'S',records=[wall['source_record']],material=record.get('sheathing'))
                    fs=re.search(r'No\.?\s*(\d+)',record.get('selection') or record.get('sheathing',''))
                    b.connection(label+'-SHEATH','review_sheathing',pt(a,z0),[bottom,top],[wall['source_record']],parameters={'thickness':thick,'faces':faces,'edge_spacing':props.get('s_in',6),'field_spacing':12,'fastener_number':int(fs[1]) if fs else 8,'material':props.get('sheathing',record.get('sheathing','WSP')),'stud_profile':studpid})
            # Gaps between source braced segments receive explicit, dimensioned openings.
            for j,(left,right) in enumerate(zip(runs,runs[1:])):
                gap=right['start_in']-left['end_in']
                if 30<=gap<=240 and abs(left['position_in']-right['position_in'])<.1:
                    width=min(gap-6,72);u=(left['end_in']+right['start_in']-width)/2;door=name.startswith('XC') or name=='NB' and k==1
                    sill=0 if door else 36;h=84 if door else min(48,zt-z0-sill-10)
                    if h>0:opening(b,f'{name}-{k}-O{j}',axis,left['position_in'],u,z0+sill,width,h,k)
    from .review_supplements import complete_walls
    complete_walls(b,outline,bystory,levels)
    if b.key in next_keys:next_floors(b,outline,levels)
    elif b.key in final.KEYS:final.floors(b,outline,levels)
    elif b.key=='cfs7':
        from .review_cfs7 import floors as bar_floors
        bar_floors(b,outline,levels)
    else:floors_and_roofs(b,outline,bystory,levels)
    if b.key=='cfs11':walkways(b,levels)
    if b.key=='cfs29':mezzanine(b,levels)
    if b.key=='cfs3':b.panel('PODIUM-CONTEXT','foundation_context',[[0,0,168],[2592,0,168],[2592,768,168],[0,768,168]],12,0,'A',scope='Podium design by others; source handoff forces retained')
    if b.key in ('cfs4','cfs9'):
        b.panel('PODIUM-CONTEXT','foundation_context',[[x*12,y*12,base-12] for x,y in outline],12,0,'A',scope='Source concrete podium / A 12 in slab envelope; design by others')
        b.note('PODIUM','S: CFS superstructure is supported by a separately designed concrete podium. '+('S: podium top +15 ft.' if b.key=='cfs4' else 'A: two podium levels at +12/+24 ft; source specifies two podium levels without elevations.')+' Source handoff forces and embed requirements remain; slab/support dimensions are A coordination context.')
    b.grids={'x':[(str(i+1),v*12) for i,v in enumerate(sorted({0,lx}|{round(l['pos'],3) for d,l in line_configs if d=='Y'}))],
             'y':[(chr(65+i),v*12) for i,v in enumerate(sorted({0,ly}|{round(cfg.get('line_plan_pos_ft',{}).get(d+'-'+l['name'],l['pos']),3) for d,l in line_configs if d=='X'}))]}
    b.note('WALL-SETOUT','A: source braced-segment lengths, sections, story schedules and rod sizes are retained. The dimensioned physical bay positions replace any tributary-fitted analysis coordinates. Openings occupy the scheduled gaps; ordinary studs and bridging stop at framed openings. Floor/roof datums are reconciled in the model. Type II hold-downs occur only at complete wall ends.')

def frange(a,b,step):
    while a<b-.01:yield round(a,6);a+=step

def opening(b,label,axis,pos,u,z,w,h,k):
    def pt(v,zz):return [v,pos,zz] if axis==0 else [pos,v,zz]
    pid=b.profile('2X800S162-68');jamb=b.profile('2X600S162-54');header=b.member('OPEN-'+label+'-H',pid,'opening_header',pt(u-3,z+h+4),pt(u+w+3,z+h+4),k,'A');b.ends(header,'test_wall_opening')
    floor=next((wall['base_z_in'] for wall in b.walls if wall['level']==k),z)
    for side,v in enumerate((u-3,u+w+3)):
        m=b.member('OPEN-'+label+'-J'+str(side),jamb,'opening_jamb',pt(v,floor),pt(v,z+h+8),k,'A');b.ends(m,'test_wall_opening')
    if z>floor+1:
        m=b.member('OPEN-'+label+'-S',pid,'opening_sill',pt(u-3,z-4),pt(u+w+3,z-4),k,'A');b.ends(m,'test_wall_opening')
    loc=pt(u,z);b.openings.append(dict(id=label,kind='door' if abs(z-floor)<1 else 'window',plane='xz' if axis==0 else 'yz',x_ft=loc[0]/12,y_ft=loc[1]/12,z_ft=z/12,width_ft=w/12,height_ft=h/12,level=k,basis='A',query_id=b.key.upper()+'-OPENINGS',confirmed=True))

def floors_and_roofs(b,outline,bystory,levels):
    cfg=b.cfg;framing=b.raw.get('framing',b.raw.get('gravity_framing',[]));records={r['id']:r for r in framing}
    for k,z in enumerate(levels[1:],1):
        poly=bystory.get(str(k),outline);roof=k==len(levels)-1
        finish=19/32 if b.key=='cfs3' and roof else 3 if b.key=='cfs3' else .75
        surface=z+finish if b.key=='cfs3' and roof else z
        refs=[rid for rid,row in b.records.items() if b.key=='cfs3' and rid.startswith('diaphragms/') and row['data'].get('level')==k]
        b.panel(f'FLOOR-{k}','roof' if b.key=='cfs3' and roof else 'floor',[[x*12,y*12,surface] for x,y in poly],finish,k,'A',records=refs,
                **(dict(reference_line='top surface; source roof steel datum is below by 19/32 in' if roof else 'top surface of the source 3 in concrete floor',thickness_direction='negative_global_z') if b.key=='cfs3' else {}))
        if b.key=='cfs29':continue
        if b.key in ('cfs11','cfs13','cfs14') and roof:
            # Explicit delegated roof members and interfaces, with adopted truss layout.
            regions=[(0,160,70,104),(0,34,0,70)] if b.key=='cfs11' else [(0,130,0,64)] if b.key=='cfs13' else [(0,120,0,70)]
            for ri,(x0,x1,y0,y1) in enumerate(regions):
                along=0 if b.key=='cfs11' and ri==1 else 1
                for station in frange((y0 if along==0 else x0)*12,(y1 if along==0 else x1)*12+.1,24):
                    lo=(x0 if along==0 else y0)*12;hi=(x1 if along==0 else y1)*12
                    if b.key=='cfs13' and 72.5*12<station<97.5*12:lo=20*12
                    # Roof level is the wall bearing datum. The six-inch
                    # delegated chord needs its centroid above that surface,
                    # not buried halfway inside the top track.
                    simple_truss(b,f'ROOF-{ri}-{station}',along,station,lo,hi,z+3.125,(hi-lo)/8,k,'2X600S162-68','2X600S162-54',24*4)
            b.changes.append(dict(kind='delegated_roof_chord_bearing_datum',level=k,chord_centroid_shift_in=3.125,
                basis='A: place the six-inch delegated bottom chord underside 1/8 in above the wall bearing workpoint; local bearing pack fits the actual track web. Source spacing/sections and analysis remain unchanged; supplier capacity and final roof-cover geometry remain separately required.'))
            continue
        direction=1 if b.key=='cfs14' else 0;normal=1-direction
        # Physical bearing lines subdivide the irregular footprint into real spans.
        bearing=sorted({run['position_in'] for wall in b.walls if wall['level']==k and wall['direction']==('Y' if direction==0 else 'X') for run in wall['runs']})
        if b.key=='cfs14':bearing=[0,210,420,630,840]
        if b.key=='cfs3':bearing=[x*12 for x in (0,28,56,84,112,140,168,196,216)]
        low=min(q[normal] for q in poly)*12;high=max(q[normal] for q in poly)*12
        rec=records.get('joist-roof' if roof else 'joist-typ') or records.get('joist-unit') or records.get('joist-clinic') or records.get('joist-room-bar') or {}
        pid=b.profile(section(rec.get('section'),'1200S200-68'));spacing=float(rec.get('spacing_in',12 if b.key=='cfs14' else 16))
        if b.key=='cfs3':spacing=16 if roof else 48
        for station in frange(low,high+.1,spacing):
            ranges=intersections(poly,direction,station/12)
            for run,(lo,hi) in enumerate(ranges):
                supports=sorted({lo*12,hi*12}|{x for x in bearing if lo*12<x<hi*12})
                for j,(a,d) in enumerate(zip(supports,supports[1:])):
                    if d-a<12:continue
                    if b.key=='cfs3':
                        simple_truss(b,f'OW-{k}-{station}-{run}-{j}',direction,station,a,d,z-14+1.25,11.5 if roof else 8.5,k,'250S162-68','250S137-43',24,flat=True)
                        continue
                    if b.key=='cfs11' and ((direction==0 and station>96*12) or (station<70*12 and a>=26*12)):
                        # Walkway joists span normal to their edge beam, not along the open edge.
                        continue
                    finish=2.25 if b.key in ('cfs13','cfs14') and not roof else .75
                    def pt(u):return [u,station,z-finish-b.depth(pid)/2] if direction==0 else [station,u,z-finish-b.depth(pid)/2]
                    m=b.member(f'JOIST-{k}-{station}-{run}-{j}',pid,'joist',pt(a),pt(d),k,'A',records=[b.record('framing',rec.get('id'))]);b.ends(m,'review_cfs_joist',[b.record('framing',rec.get('id'))],parameters={'spacing':spacing,'floor_depth':b.depth(pid)+.75})
    b.note('DELEGATED-ROOF','A: the pictured roof truss internals, node gussets and supplier floor-joist arrangements are explicit fictional inputs. Use the source sections where scheduled; source delegated reactions, diaphragm conditions and capacity approval requirements remain attached. The drawing is not a supplier certification.')
    if b.key=='cfs3':
        # Wall levels are bearing surfaces, while track geometry uses a web
        # centreline. Account for that half-thickness rather than burying the
        # truss bottom chord in the track. Analysis workpoints remain unchanged.
        for m in b.members:
            if m['kind'] not in ('top_track','bottom_track','ordinary_track','tier_track'):continue
            if abs(m['local_y'][2])<.999:continue
            half=b.profiles[m['profile_id']]['dimensions']['t']/2
            for off in m['end_offsets']:off[2]+=half*m['local_y'][2]
        b.changes.append(dict(kind='cfs3_truss_bearing_datums',chord_centre_shift_in=1.25,
                              roof_truss_outside_depth_in=14,roof_sheathing_in=19/32,floor_topping_in=3,
                              basis='S: 14 in roof truss and 19/32 in Structural I roof sheathing; 3 in concrete floor topping. A: retain the existing 11 in delegated floor-truss envelope, place bottom-chord underside on the wall bearing datum, and offset track web centrelines by half their actual thickness. Source analysis workpoints and selected sections retained; supplier capacity remains unverified.'))

def simple_truss(b,label,along,station,start,end,base,rise,k,chord,web,panel,flat=False,heel=0):
    cp=b.profile(chord);wp=b.profile(web);span=end-start;n=max(2,math.ceil(span/panel));n=n if flat else math.ceil(n/2)*2;step=span/n
    def pt(u,z):return [start+u,station,z] if along==0 else [station,start+u,z]
    nodes=defaultdict(list);ly=[0,1,0] if along==0 else [1,0,0]
    for j in range(n):
        a,d=j*step,(j+1)*step
        for edge in ('B','T'):
            zz=lambda u:base+(rise if flat else heel+rise*(1-abs(2*u/span-1))) if edge=='T' else base
            m=b.member(f'{label}-{edge}{j}',cp,'truss_chord',pt(a,zz(a)),pt(d,zz(d)),k,'A',local_y=ly);nodes[j,edge].append(m);nodes[j+1,edge].append(m)
        first,last=('B','T') if j%2==0 else ('T','B')
        def znode(u,edge):return base+(rise if flat else heel+rise*(1-abs(2*u/span-1))) if edge=='T' else base
        aa,dd=pt(a,znode(a,first)),pt(d,znode(d,last))
        if math.dist(aa,dd)>.01:
            m=b.member(f'{label}-W{j}',wp,'truss_web',aa,dd,k,'A',local_y=ly);nodes[j,first].append(m);nodes[j+1,last].append(m)
    if not flat and not heel:
        for j in (0,n):
            nodes[j,'B']+=nodes.pop((j,'T'),[])
    if flat or heel:
        for j in (0,n):
            vertical=b.member(f'{label}-END{j}',wp,'truss_web',pt(j*step,base),pt(j*step,base+(rise if flat else heel)),k,'A',local_y=ly)
            nodes[j,'B'].append(vertical);nodes[j,'T'].append(vertical)
    for (j,edge),ms in nodes.items():
        u=j*step;z=base+(rise if flat else heel+rise*(1-abs(2*u/span-1))) if edge=='T' else base
        family='review_truss_heel' if j in (0,n) and edge=='B' else 'review_truss_node'
        if len(ms)<2:
            # End vertical completes a flat open-web joist; both chords have a real node.
            other=base+rise if edge=='B' else base
            vertical=b.member(f'{label}-END{j}{edge}',wp,'truss_web',pt(u,z),pt(u,other),k,'A',local_y=ly);ms.append(vertical)
        b.connection(f'{label}-N{j}{edge}',family,pt(u,z),ms,parameters={'flat':flat,'node_type':edge,'angle':round(math.degrees(math.atan2(rise,span/2)),3),'along':along})
        if j in (0,n) and edge=='B':b.connection(f'{label}-SEAT{j}','review_roof_seat',pt(u,z),ms,parameters={'flat':flat})

def walkways(b,levels):
    for axis,pos,lo,hi in ((0,104*12,0,160*12),(1,34*12,0,70*12)):
        def pt(u,z):return [u,pos,z] if axis==0 else [pos,u,z]
        stations=list(frange(lo,hi,160 if axis==0 else 168))+[hi]
        for i,u in enumerate(stations):
            post=b.member(f'WALKPOST-{axis}-{i}','HSS4X4X1/4','walkway_post',pt(u,0),pt(u,levels[-1]),1,'A');b.ends(post,'review_cfs_post',[b.record('connections','conn-walkway-post-base')])
        for k,z in enumerate(levels[1:],1):
            for j,(a,d) in enumerate(zip(stations,stations[1:])):
                m=b.member(f'WALKBEAM-{axis}-{k}-{j}','W8X18' if k==len(levels)-1 else 'W8X10','walkway_edge_beam',pt(a,z-4),pt(d,z-4),k,'A');b.ends(m,'review_beam',[b.record('connections','conn-edge-beam-post')])
            if k<len(levels)-1:
                for u in frange(lo,hi+.1,16):
                    aa=pt(u,z-.75-3);dd=aa.copy();aa[1-axis]-=96
                    m=b.member(f'WALKJOIST-{axis}-{k}-{u}','600S162-54','joist',aa,dd,k,'A');b.ends(m,'review_cfs_joist',[b.record('connections','conn-walkway-joist')],parameters={'clip':True,'screws':4,'screw_size':10})
                for u in sorted(set(frange(lo,hi+.1,48))|{hi}):
                    m=b.member(f'WALKGUARD-{axis}-{k}-{u}','2X362S162-54','guard_post',pt(u,z-10),pt(u,z+42),k,'A');b.ends(m,'review_guard_connection')
                m=b.member(f'WALKRAIL-{axis}-{k}','362S162-54','guard_rail',pt(lo,z+42),pt(hi,z+42),k,'A');b.ends(m,'review_guard_connection',parameters={'rail':True})
    for x in (80*12,93.333*12):
        for y in (70*12,96*12):
            m=b.member(f'BREEZEPOST-{x}-{y}','HSS5X5X5/16','column',[x,y,0],[x,y,levels[1]],1,'A');b.ends(m,'review_cfs_post',[b.record('connections','conn-post-base')])
    for x in (80*12,93.333*12):
        m=b.member('BREEZEGIRDER-'+str(x),'W21X44','girder',[x,70*12,levels[1]-10.5],[x,96*12,levels[1]-10.5],1,'A');b.ends(m,'review_beam',[b.record('connections','conn-girder-post')])
    for y in (70*12,96*12):
        m=b.member('BREEZEHEADER-'+str(y),'W8X18','girder',[80*12,y,levels[1]-4],[93.333*12,y,levels[1]-4],1,'A');b.ends(m,'review_beam',[b.record('connections','conn-header-post')])
    b.note('BREEZEWAY','A: the source Level-1 breezeway remains open between P80 and P93. Source steel posts/girders support the walls above; exterior walkway edge beams and posts are drawn at the actual open edges. Their local fit and footing context are fictional coordination answers.')

def mezzanine(b,levels):
    for x in range(0,721,144):
        for y in (0,192,384):
            if any(m['kind']=='chord' and math.dist(m['axis'][0][:2],[x,y])<.1 for m in b.members):continue
            pid=b.pack(b.profile('600S250-97'),2,'box');m=b.member(f'MEZZPOST-{x}-{y}',pid,'column',[x,y,0],[x,y,144],1,'S');b.connection(m['id']+':0','review_cfs_post',m['axis'][0],[m],[b.record('connections','conn-post-base')],parameters={'slab_thickness':6,'embedment':4})
    for y in (0,192,384):
        pid=b.pack(b.profile('1400S300-118' if y==192 else '1200S300-97'),2,'box')
        for x in range(0,720,144):
            m=b.member(f'MEZZBEAM-{x}-{y}',pid,'girder',[x,y,144-b.depth(pid)/2],[x+144,y,144-b.depth(pid)/2],1,'S');b.ends(m,'review_cfs_beam_clip',[b.record('connections','conn-beam-post')],parameters={'count':2,'diameter':.75,'post_count':4})
    for x in range(0,721,16):
        for y in (0,192):
            m=b.member(f'MEZZJOIST-{x}-{y}','1200S250-68','joist',[x,y,138],[x,y+192,138],1,'S');b.ends(m,'review_cfs_joist',[b.record('connections','conn-joist-clip')],parameters={'clip':True,'screws':4,'screw_size':10})
    for axis,pos,limit in ((0,0,720),(0,384,720),(1,0,384),(1,720,384)):
        def at(u,z):return [u,pos,z] if axis==0 else [pos,u,z]
        for u in sorted(set(frange(0,limit+.1,48))|({300,384} if axis==0 and pos==0 else {limit})):
            if axis==0 and pos==0 and 300<u<384:continue
            m=b.member(f'GUARD-{axis}-{pos}-{u}','2X362S162-54','guard_post',at(u,132),at(u,186),1,'A');b.ends(m,'review_guard_connection',[b.record('connections','conn-guard-post')])
        for j,(aa,dd) in enumerate([(0,300),(384,limit)] if axis==0 and pos==0 else [(0,limit)]):
            m=b.member(f'GUARDRAIL-{axis}-{pos}-{j}','362S162-54','guard_rail',at(aa,186),at(dd,186),1,'A');b.ends(m,'review_guard_connection',[b.record('connections','conn-guard-post')],parameters={'rail':True})
    for j,x in enumerate((312,360)):
        m=b.member(f'STAIR-STRINGER-{j}','2X1000S250-97','stair_stringer',[x,-216,0],[x,0,144],1,'A')
        for side,point in enumerate(m['axis']):b.connection(m['id']+':'+str(side),'review_stair_clip',point,[m],[b.record('connections','conn-stair-stringer')],parameters={'lower_landing':side==0})
    for j in range(1,18):
        y=-216+j*12;z=j*8;m=b.member(f'STAIR-TREAD-{j}','L2X2X1/4','tread_angle',[312,y,z],[360,y,z],1,'A');b.ends(m,'review_angle_clip',parameters={'count':2,'diameter':.375})
        b.panel(f'TREAD-{j}','stair_tread',[[312,y-6,z],[360,y-6,z],[360,y+6,z],[312,y+6,z]],1,1,'A')
    b.note('STAIR-GUARD','A: external 4 ft stair at the south edge, 18 rises of 8 in and 12 in tread pitch, paired 1000S250-97 stringers and L2x2x1/4 tread seats. Source 42 in guards use paired 362S162-54 posts at 4 ft maximum, source through-bolts/crush tubes. Treads, stringer sizes and local base fitting are fictional coordination inputs, with no egress or capacity approval inferred.')
    b.note('HOST','A: the existing host warehouse is shown only as coordination context. The mezzanine remains freestanding. Source 6 in slab, 4 in anchor embedment, sawcut clearance and bolt/base-plate variants remain explicit; no connection to the host frame is introduced.')
