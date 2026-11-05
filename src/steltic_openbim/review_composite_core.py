"""Source-bound HR27 composite walls, through ties and embedded box beams.

The saved elastic wide columns are not the steel plate workpieces. Coordinates
below come from the source LEGS/CBS and the final pier/connection schedules.
Unspecified weld preparation, stud margins and slab closure fit remain A.
"""
import math,re
from .pilots.model import add,sub,mul,dot,cross,unit
from .pilots.geometry import part_faces
from .review_receiver_geometry import extract,point,horizontal_frame
from .assembly_scene import clip_part

Z=[0,0,1]


def stations(lo,hi,pitch,count=None):
    n=count or max(1,math.ceil((hi-lo)/pitch))
    start=(lo+hi-(n-1)*pitch)/2
    if start<lo-1e-6:raise ValueError('Source pattern does not fit its actual plate')
    return [start+i*pitch for i in range(n)]


def build(b,levels):
    c=b.config;walls={};closures={};slab=6.25
    for name,(direction,station,start,end,group) in c['LEGS'].items():
        along=0 if direction=='X' else 1;normal=1-along;length=end-start
        sx=1 if group[1]=='W' else -1;sy=1 if group[0]=='S' else -1
        toward=sx if along==0 else sy;outer=-sy if along==0 else -sx
        corner=start if toward==1 else end;free=end if toward==1 else start;centre=(start+end)/2
        ly=[0,0,0];ly[along]=1;n=cross(Z,ly)
        def at(u,z,trans=station):
            q=[0,0,z];q[along]=u;q[normal]=trans;return q
        for k in range(1,len(levels)):
            gi=next(i for i,(lo,hi) in enumerate(c['PLATE_GROUPS']) if lo<=k<=hi);t=c['PLATE'][group][gi]
            records=[]
            for rid,r in b.records.items():
                if not rid.startswith('members/pier-'+group+'-S'):continue
                lo,hi=map(int,r['data']['inputs']['stories'].split('-'))
                if lo<=k<=hi:records.append(rid)
            if len(records)!=1:raise ValueError('Missing exact pier tier '+name+str(k))
            pitch=10 if k>=16 else 12
            description=b.records[records[0]]['data']['inputs']['description']
            if f'at {pitch} in x {pitch} in' not in description:raise ValueError('Pier tie schedule changed')
            comps=[];face_rows=[]
            for side in (-1,1):
                is_outer=side==outer
                # X plates reach the outside corner; Y plates butt against
                # their edges. The two inside faces start at the inside corner.
                edge=corner+toward*((-9+(t if along==1 else 0)) if is_outer else 9)
                lo,hi=sorted((edge,free));width=hi-lo
                pid=b.custom(f'CORE-FACE-{width:g}-{t:g}','flat',dict(width=width,thickness=t),basis='S: actual L-pier face, source outside dimensions')
                offset=(station+side*(9-t/2)-station)*n[normal]
                comps.append(dict(profile_id=pid,offset=[(lo+hi)/2-centre,offset],rotation_deg=0))
                count=int(length/6)+(0 if is_outer else -2) if along==0 else int(length/6)+(1 if is_outer else -1)
                face_rows.append(dict(side=side,lo=lo-centre,hi=hi-centre,stud_columns=count))
            pid=b.custom(f'CORE-{name}-{t:g}','built_up',{},components=comps,basis='S: two actual L-pier faceplates; corner and free-end geometry')
            bottom=levels[k-1]+(slab if k>1 else 0);top=levels[k]+slab
            m=b.member(f'CORE-{name}-{k}',pid,'composite_wall',at(centre,bottom),at(centre,top),k,records=records,local_y=ly,
                core_plate_thickness=t,core_faces=face_rows,core_free=free,core_toward=toward,core_group=group)
            walls[name,k]=m
            # 1 in closures are selected explicitly in every source pier record.
            cp=b.custom(f'CORE-CLOSURE-{t:g}','flat',dict(width=18-2*t,thickness=1),basis='S: 1 in free-end closure between actual wall faces')
            close=b.member(f'CORE-CLOSURE-{name}-{k}',cp,'wall_closure',at(free-toward*.5,bottom),at(free-toward*.5,top),k,records=records,local_y=n)
            closures[name,k]=close
            common=dict(actual_composite_core=True,direction=direction,plate_thickness=t,face_rows=face_rows,leg_length=length)
            b.connection(m['id']+':CLOSURE','review_core_wall',at(free,(bottom+top)/2),[m,close],records,
                parameters=dict(common,purpose='closure',toward=toward))
            lo,hi=sorted((corner+toward*9,free-toward));xs=stations(lo,hi,pitch)
            # One complete row is a placed detail. Every source tie has a real
            # station; the picture is not an unplaced four-tie example.
            for j,z in enumerate(stations(bottom,top,pitch)):
                b.connection(m['id']+f':TIES-{j}','review_core_wall',at(centre,z),[m],
                    [b.record('connections','conn-tie-bar-to-plate')]+records,
                    parameters=dict(common,purpose='ties',tie_pitch=pitch,tie_stations=[x-centre for x in xs]))
            b.connection(m['id']+':DIAPHRAGM','review_core_wall',at(centre,levels[k]+slab/2),[m],
                [b.record('connections','conn-diaphragm-to-core-walls')],parameters=dict(common,purpose='diaphragm',slab_depth=slab))
            if k==1:
                m['end_offsets'][0][2]=-72;close['end_offsets'][0][2]=-72
                b.connection(m['id']+':BASE','review_core_base',at(centre,0),[m,close],[b.record('connections','conn-base-wall-'+group)],parameters=dict(common,purpose='base'))
        b.views.append(dict(title='Composite core '+name,direction=direction,station_in=station,range_in=[start,end]))
    # Concrete is a single L prism per pier/tier, with no overlapping corner.
    for group in ('SW','SE','NW','NE'):
        xd,ys,x0,x1,_=c['LEGS'][group+'-X'];yd,xs,y0,y1,_=c['LEGS'][group+'-Y']
        sx=1 if group[1]=='W' else -1;sy=1 if group[0]=='S' else -1;cx=x0 if sx==1 else x1;cy=y0 if sy==1 else y1
        for k in range(1,len(levels)):
            wx,wy=walls[group+'-X',k],walls[group+'-Y',k];t=wx['core_plate_thickness'];a=9-t
            poly=[[-a,-a],[x1-x0-1,-a],[x1-x0-1,a],[a,a],[a,y1-y0-1],[-a,y1-y0-1]]
            z=wx['axis'][0][2]+wx['end_offsets'][0][2];top=wx['axis'][1][2]
            vertices=[[cx+sx*x,cy+sy*y,z] for x,y in poly]
            if sx*sy<0:vertices.reverse()
            b.panel(f'CORE-{group}-{k}-CONCRETE','composite_core',vertices,top-z,k,'S',records=wx['design_record_ids'],concrete_specification="SCC f'c=6 ksi")
            b.connection(f'CORE-{group}-{k}:CORNER','review_core_wall',[cx,cy,(z+top)/2],[wx,wy],wx['design_record_ids'],
                parameters=dict(actual_composite_core=True,purpose='corner',direction='X',plate_thickness=t,sx=sx,sy=sy))
    for name,(direction,station,start,end) in c['CBS'].items():
        along=0 if direction=='X' else 1
        for k in range(1,len(levels)):
            group='Y' if name in ('2','4') else name;gi=next(i for i,(lo,hi) in enumerate(c['CB_GROUPS']) if lo<=k<=hi);tf,tw=c['CB_T'][group][gi]
            fp=b.custom(f'CB-FLANGE-{tf:g}','flat',dict(width=18,thickness=tf),basis='S')
            wp=b.custom(f'CB-WEB-{tf:g}-{tw:g}','flat',dict(width=24-2*tf,thickness=tw),basis='S')
            pid=b.custom(f'COUPLING-BOX-{tf:g}-{tw:g}','built_up',{},components=
                [dict(profile_id=fp,offset=[0,sg*(24-tf)/2],rotation_deg=0) for sg in (-1,1)]+
                [dict(profile_id=wp,offset=[sg*(18-tw)/2,0],rotation_deg=90) for sg in (-1,1)],basis='S: concrete-filled 18 x 24 in box, two side webs')
            a=[start,station,levels[k]-12] if along==0 else [station,start,levels[k]-12];d=[end,station,levels[k]-12] if along==0 else [station,end,levels[k]-12]
            lo,hi=c['CB_GROUPS'][gi];suffix='L1-20' if group=='B' else f'L{lo}-{hi}';rid=b.record('connections',f'conn-coupling-{group}-{suffix}')
            text=b.records[rid]['data']['components'];embed=float(re.search(r'continue (\d+) in into',text)[1])
            record=b.record('members',f'coupling-{group}-{suffix}')
            if not record or b.records[record]['data']['inputs']['section']!=text.split(' to the wall')[0]:raise ValueError('Exact coupling member tier is missing')
            m=b.member(f'COUPLING-{name}-{k}',pid,'coupling_beam',a,d,k,records=[rid,record] if record else [rid])
            for e,origin in enumerate((a,d)):
                candidates=[w for w in walls.values() if w['level']==k and abs(w['core_free']-origin[along])<.01 and abs(w['axis'][0][1-along]-station)<.01 and abs(w['local_y'][along])>.99]
                if len(candidates)!=1:raise ValueError('Coupling beam has no unique actual wall')
                wall=candidates[0];wallname=wall['id'][5:].rsplit('-',1)[0];close=closures[wallname,k];into=-1 if e==0 else 1
                # Source embedded flanges occupy fitted slots in both faces.
                centre=origin[along]+into*embed/2-wall['axis'][0][along]
                actual_bottom=wall['axis'][0][2]+wall['end_offsets'][0][2]
                for zlo in (levels[k]-24,levels[k]-tf):
                    wall.setdefault('slots',[]).append(dict(start_in=zlo-actual_bottom,end_in=zlo+tf-actual_bottom,width_in=embed,centre_in=centre,section_axis=0,basis='S flange embedment; A exact plate slot fit'))
                close.setdefault('slots',[]).append(dict(start_in=levels[k]-24-actual_bottom,end_in=levels[k]-actual_bottom,width_in=30,centre_in=0,section_axis=0,basis='S closure cut through coupling beam/infill opening'))
                b.connection(m['id']+':'+str(e),'review_coupling',origin,[m,wall,close],[rid],parameters=dict(actual_composite_core=True,purpose='coupling',direction=direction,
                    end=e,embedment=embed,flange_thickness=tf,web_thickness=tw,plate_thickness=wall['core_plate_thickness']))
            n=cross(unit(sub(d,a)),m['local_y']);verts=[add(a,add(mul(m['local_y'],y),mul(n,-12+tf))) for y in (-9+tw,9-tw)]
            verts += [add(d,add(mul(m['local_y'],y),mul(n,-12+tf))) for y in (9-tw,-9+tw)]
            b.panel(m['id']+'-INFILL','composite_coupling_infill',verts,24-2*tf,k,'S',records=[rid])
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for name,(direction,station,start,end,group) in c['LEGS'].items():
        close=closures[name,1]
        b.endpoint_links.append(dict(member_id=close['id'],end='start',connection_id=walls[name,1]['id']+':BASE',basis='Actual full-depth closure extension is joined by the located wall/base assembly.'))
        for k in range(1,len(levels)-1):
            low,high=walls[name,k],walls[name,k+1];lc,hc=closures[name,k],closures[name,k+1]
            cid=low['id']+':SPLICE';origin=low['axis'][1]
            b.connection(cid,'review_core_wall',origin,[low,high,lc,hc],parameters=dict(actual_composite_core=True,purpose='splice',direction=direction,
                plate_thickness=low['core_plate_thickness'],upper_thickness=high['core_plate_thickness']))
            for member,endname in ((low,'end'),(high,'start'),(lc,'end'),(hc,'start')):
                b.endpoint_links.append(dict(member_id=member['id'],end=endname,connection_id=cid,basis='A actual horizontal face/closure plate splice at the declared story-panel boundary; complete CJP seams, source plate thicknesses retained.'))
    for group in ('SW','SE','NW','NE'):
        k=len(levels)-1;wx,wy=walls[group+'-X',k],walls[group+'-Y',k];cx,cy=closures[group+'-X',k],closures[group+'-Y',k]
        x0,x1=c['LEGS'][group+'-X'][2:4];y0,y1=c['LEGS'][group+'-Y'][2:4];sx=1 if group[1]=='W' else -1;sy=1 if group[0]=='S' else -1
        origin=[x0 if sx==1 else x1,y0 if sy==1 else y1,wx['axis'][1][2]];cid='CORE-'+group+':ROOF-CAP'
        b.connection(cid,'review_core_wall',origin,[wx,wy,cx,cy],parameters=dict(actual_composite_core=True,purpose='cap',direction='X',plate_thickness=wx['core_plate_thickness'],sx=sx,sy=sy,lx=x1-x0,ly=y1-y0))
        for m in (wx,wy,cx,cy):b.endpoint_links.append(dict(member_id=m['id'],end='end',connection_id=cid,basis='A1/4 in non-loadbearing roof closure cap welded to the actual L-pier face and end plates; source structural wall design unchanged.'))
    b.note('CORE','S: actual L-pier outside dimensions, source faceplate tiers, 1 in free-end closures, .75 in A706 ties at12 in (L1-15) and10 in (L16-20), .625 in all-around E70 tie welds; source18x24 concrete-filled coupling boxes with two side webs and tier-specific24/30/36/42/54 in flange embedment. Source0.030 rad connection qualification and24 in protected zones remain requirements. A: continuous wall plates extend6.25 in above each TOS to contain the diaphragm stud row; segment boundaries, exact corner weld preparation, stud margins and2 in base bearing plate fit are adopted geometry, not new capacity checks. Base stud counts match the selected1920 SW/NE and1488 SE/NW. Mat reinforcement and slab chord/shear-friction design remain delegated source requirements.')
    b.note('CORE-PANEL-JOINTS','A: horizontal construction seams at the explicit story-panel boundaries use full CJP plate/closure splices, with outer wall faces aligned and thicker plate preparation to be qualified. Source files do not specify panelization or seam design. A1/4 in non-loadbearing top cap closes each L-pier. These are accepted fictional assembly proposals, not source-checked splice or construction-sequence designs.')


def frame(ctx):
    return horizontal_frame([1,0,0] if ctx.params['direction']=='X' else [0,1,0])


def weld_ring(a,label,centre,r,normal,connects,size,description):
    # A short seam marker carries the complete all-around requirement. Its
    # ends lie on the real bar/plate interface, not across an empty receiver.
    u=[1,0,0];v=Z
    if abs(normal[0])>.5:u=[0,1,0]
    q=lambda theta:add(centre,add(mul(u,r*math.cos(theta)),mul(v,r*math.sin(theta))))
    a.weld(label,q(math.pi/4),q(3*math.pi/4),connects,size,description=description+'; all around, schematic seam marker')


def bars(a,label,points,normal,dia,length,headed,description):
    faces=[]
    for q in points:
        faces+=part_faces(dict(geometry=dict(type='cylinder',origin=q,axis=normal,radius=dia/2,length=length)),a.profiles)
        if headed:faces+=part_faces(dict(geometry=dict(type='cylinder',origin=add(q,mul(normal,length-dia*.4)),axis=normal,radius=dia,length=dia*.4)),a.profiles)
    return a.part(label,description,faces,'S','headed_stud' if headed else 'reinforcement',count=len(points),diameter=dia,points=points,axis=normal,length=length)


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=frame(ctx);purpose=par['purpose'];t=par['plate_thickness']
    if purpose=='coupling':return coupling(ctx)
    if purpose in ('splice','cap'):return panel_joint(ctx)
    extent=76 if purpose=='base' else (max(math.dist(*m['axis']) for m in ctx.ms)+72 if purpose in ('corner','closure') else 7)
    for i,m in enumerate(ctx.ms):extract(ctx,m,'WALL' if i==0 else 'OTHER',axes,extent)
    if purpose=='ties':
        pts=[[x,-9,0] for x in par['tie_stations']];bars(a,'TIES',pts,[0,1,0],.75,18,False,'S .75 in A706 Gr60 through ties; no bolt nuts or heads')
        for i,q in enumerate(pts):
            for sg in (-1,1):weld_ring(a,f'TIE-{i}-{sg}',[q[0],sg*9,0],.375,[0,sg,0],['WALL','TIES'],.625,'S .625 in E70 fillet at each outside face')
        a.box('INFILL',[-par['leg_length']/2,-9+t,-6],[par['leg_length'],18-2*t,12],'S',"SCC f'c=6 ksi local core concrete context",kind='concrete')
        a.dim([pts[0][0],0,0],[pts[0][0]+par['tie_pitch'],0,0],f'{par["tie_pitch"]:g} in horizontal / vertical source tie spacing')
        a.section_axis=0;a.section_at=pts[len(pts)//2][0]
    elif purpose in ('base','diaphragm'):
        base=purpose=='base';zs=list(range(-3,-72,-6)) if base else [0];pitch=6 if base else 12;dia=.875 if base else .75;length=5 if base else 4
        for j,f in enumerate(par['face_rows']):
            # normal changes sign for a global Y leg in the right-handed frame.
            sg=f['side']*(1 if par['direction']=='X' else -1)
            xs=stations(f['lo'],f['hi'],pitch,f['stud_columns'] if base else None);pts=[[x,sg*9,z] for x in xs for z in zs]
            label='STUDS'+str(j);bars(a,label,pts,[0,sg,0],dia,length,True,f'S {len(pts)} headed studs, {dia:g} in dia; '+('5 in after weld,6 x6 in' if base else '12 in stations; A4 in after-weld length'))
            for i,q in enumerate(pts):weld_ring(a,label+'-'+str(i),q,dia/2,[0,sg,0],['WALL',label],.1875,'S automatic stud weld; A schematic collar size')
        width=par['leg_length']
        if base:
            a.box('BEARING',[-width/2-9,-11,-74],[width+18,22,2],'A','A2 in base bearing plate; foundation capacity delegated')
            a.box('MAT',[-width/2-18,-24,-84],[width+36,48,84],'A','Mat context; source reinforcement/breakout/pryout/punching handoff',kind='concrete')
            for j,f in enumerate(par['face_rows']):
                sg=f['side']*(1 if par['direction']=='X' else -1);a.weld('BASE'+str(j),[f['lo'],sg*9,-72],[f['hi'],sg*9,-72],['WALL','BEARING'],kind='CJP',basis='A',description='A wall/base development weld fit; no new capacity approval')
            a.dim([0,16,-72],[0,16,0],'72 in source embedment');a.section_axis=2;a.section_at=-36
        else:
            a.box('SLAB',[-width/2-9,-20,-par['slab_depth']/2],[width+18,40,par['slab_depth']],'S','Slab context at actual source TOS; chord/shear-friction reinforcing delegated',kind='concrete')
            a.dim([0,-9,0],[0,9,0],'18 in source wall');a.section_axis=0;a.section_at=xs[len(xs)//2]
    elif purpose=='closure':
        # Two vertical closure edges meet the inner faceplate surfaces.
        close=ctx.ms[1];ends=[point(add(q,o),ctx.c['point'],axes) for q,o in zip(close['axis'],close['end_offsets'])]
        sign=par['toward'];x=ends[0][0]+sign*.5
        # Skip the source coupling opening in the closure and wall edges.
        lo,hi=sorted(q[2] for q in ends);cut=[];actual_bottom=close['axis'][0][2]+close['end_offsets'][0][2]
        for slot in close.get('slots',[]):cut.append((actual_bottom+slot['start_in']-ctx.c['point'][2],actual_bottom+slot['end_in']-ctx.c['point'][2]))
        spans=[];cursor=lo
        for l,h in sorted(cut):
            if l>cursor:spans.append((cursor,l))
            cursor=max(cursor,h)
        if cursor<hi:spans.append((cursor,hi))
        for sg in (-1,1):
            for j,(l,h) in enumerate(spans):a.weld(f'CLOSE-{sg}-{j}',[x,sg*(9-t),l],[x,sg*(9-t),h],['WALL','OTHER'],kind='CJP',basis='A',description='A continuous closure-to-faceplate weld preparation; source closure retained')
        a.section_axis=2;a.section_at=0
    elif purpose=='corner':
        sx,sy=par['sx'],par['sy'];lo=max(q['bounds'][2][0] for q in a.parts);hi=min(q['bounds'][2][1] for q in a.parts)
        for j,(x,y) in enumerate(((-sx*(9-t/2),-sy*(9-t)),(sx*9,sy*9))):
            a.weld('CORNER'+str(j),[x,y,lo],[x,y,hi],['WALL','OTHER'],kind='CJP',basis='A',description='A continuous L-pier face corner weld; source wall section retained')
        a.section_axis=2;a.section_at=0;a.front_axes=(0,1)
    a.notes.append('S source plates, tie/stud diameters, counts and tier-specific spacing. A exact local stations, weld preparation and concrete context. No new capacity or connection qualification is inferred.')


def panel_joint(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=frame(ctx);purpose=par['purpose'];t=par['plate_thickness']
    for i,m in enumerate(ctx.ms):extract(ctx,m,'R'+str(i),axes,12)
    if purpose=='splice':
        low,high,lc,hc=ctx.ms
        for i,(f,g) in enumerate(zip(low['core_faces'],high['core_faces'])):
            y=f['side']*9*(1 if par['direction']=='X' else -1);lo=max(f['lo'],g['lo']);hi=min(f['hi'],g['hi'])
            a.weld('FACE'+str(i),[lo,y,0],[hi,y,0],['R0','R1'],kind='CJP',basis='A',description='A complete horizontal wall-face CJP splice; qualified thickness-transition preparation required')
        centre=point(lc['axis'][1],ctx.c['point'],axes);width=18-2*max(t,par['upper_thickness'])
        a.weld('CLOSURE',[centre[0],-width/2,0],[centre[0],width/2,0],['R2','R3'],kind='CJP',basis='A',description='A horizontal closure-plate CJP splice')
        a.section_axis=2;a.section_at=1;a.front_axes=(0,2)
        a.notes.append('A story-panel seam layout and full CJP splice proposal. Source wall dimensions and thickness tiers retained. This is a new assembly fit assumption; splice capacity, weld qualification, access and erection sequence are not certified.')
    else:
        sx,sy,lx,ly=[par[k] for k in ('sx','sy','lx','ly')]
        vertices=[[sx*x,sy*y,0] for x,y in ((-9,-9),(lx,-9),(lx,9),(9,9),(9,ly),(-9,ly))]
        if sx*sy<0:vertices.reverse()
        a.polygon('CAP',vertices,.25,normal=Z,basis='A',description='A1/4 in non-loadbearing L-pier roof closure')
        for i,wall in enumerate(ctx.ms[:2]):
            for j,f in enumerate(wall['core_faces']):
                u=wall['axis'][0][:2];along=0 if i==0 else 1;normal=1-along;coords=[]
                for off in (f['lo'],f['hi']):
                    q=list(wall['axis'][1]);q[along]+=off;q[normal]+=f['side']*9;coords.append(point(q,ctx.c['point'],axes))
                a.weld(f'FACE{i}-{j}',*coords,['R'+str(i),'CAP'],.1875,basis='A',description='A closure fillet at actual faceplate top edge')
        for i,close in enumerate(ctx.ms[2:],2):
            centre=point(close['axis'][1],ctx.c['point'],axes);v=close['local_y'];width=18-2*t
            a.weld('END'+str(i),add(centre,mul(v,-width/2)),add(centre,mul(v,width/2)),['R'+str(i),'CAP'],.1875,basis='A',description='A closure fillet at actual free-end plate top edge')
        a.front_axes=(0,1);a.section_axis=2;a.section_at=.125
        a.notes.append('A non-loadbearing roof cap closes the source concrete-filled wall. No roof plant, guarding or structural attachment capacity is implied.')


def coupling(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;beam,wall,closure=ctx.ms
    into=1 if par['end']==0 else -1;axes=horizontal_frame(mul(unit(sub(*beam['axis'][::-1])),into))
    extract(ctx,beam,'BEAM',axes,36);extract(ctx,wall,'WALL',axes,36);extract(ctx,closure,'CLOSURE',axes,36)
    le=par['embedment'];tf=par['flange_thickness'];tw=par['web_thickness']
    for label in ('WALL','CLOSURE'):
        part=next(x for x in a.parts if x['id']==label)
        clip_part(part,[1,0,0],-le-12);clip_part(part,[-1,0,0],.0)
    for j,z in enumerate((-12,12-tf)):
        label='EMBED'+str(j);a.box(label,[-le,-9,z],[le,18,tf],'S','Source continuous embedded flange plate')
        for sg in (-1,1):a.weld(f'DEVELOP{j}-{sg}',[-le,sg*9,z+tf],[0,sg*9,z+tf],['WALL',label],kind='CJP',description='S demand-critical embedded flange edge CJP')
        a.interfaces.append(dict(id='CONTINUOUS-FLANGE'+str(j),kind='continuous_material',connects=['BEAM',label],basis='S',description='Same continuous source flange plate through the wall face; no invented flange splice'))
    for sg in (-1,1):a.weld('WEB'+str(sg),[0,sg*9,-12+tf],[0,sg*9,12-tf],['WALL','BEAM'],kind='CJP',description='S demand-critical beam web butt weld to actual wall faceplate; thickness transition preparation by qualified detail')
    a.box('INFILL',[-le,-9+tw,-12+tf],[le+36,18-2*tw,24-2*tf],'S',"SCC f'c=6 ksi continuous concrete infill through source cut closure",kind='concrete')
    a.dim([-le,0,13],[0,0,13],f'{le:g} in source flange embedment');a.dim([0,0,-13],[24,0,-13],'24 in source protected end region')
    a.section_axis=0;a.section_at=-le/2
    a.notes.append('S18x24 concrete-filled box with two side webs, actual wall faceplates and1 in free-end closure cut through the beam. Tier-specific embedded flanges. Source tested0.030 rad connection rotation and demand-critical weld qualification remain required; the drawing does not certify qualification.')
