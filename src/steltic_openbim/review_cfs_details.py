"""CFS assembled interfaces with real ply, support, rod and movement geometry."""
import math,re,copy
from .review_assemblies import *

def draw(ctx):
    f=ctx.family
    if f in ('review_pack_stitch','review_floor_strap','review_post_collector','review_rod_transfer','review_roof_edge','review_post_edge'):
        from .review_wall_details import draw
        draw(ctx)
    elif f in ('review_kicker','review_guard_connection','review_stair_clip'):
        from .review_detail_extras import draw
        draw(ctx)
    elif f in ('review_portal_base','review_cfs_post'):post(ctx)
    elif f in ('review_portal_joint','review_canopy_knee'):portal(ctx)
    elif f in ('review_canopy_brace','review_angle_clip'):angle(ctx)
    elif f in ('review_endpost_base','review_endpost_top'):endpost(ctx,f.endswith('base'))
    elif f=='review_cfs_beam_clip':
        from .review_detail_extras import beam_clip
        beam_clip(ctx)
    elif f in ('review_secondary','review_ledger'):secondary(ctx)
    elif f=='review_roof_seat':
        from .review_detail_extras import roof_seat
        roof_seat(ctx)
    elif f=='review_cfs_joist' and ctx.params.get('clip'):
        if ctx.params.get('physical_joist_end') and re.search(r'L\s*3\s*x\s*3\s*x\s*54 mil',ctx.text,re.I):
            from .review_wall_occurrence_details import joist
            joist(ctx)
        else:
            from .review_detail_extras import joist_clip
            joist_clip(ctx)
    elif f in ('review_cfs_sill','review_cfs_floor','review_cfs_joist'):floor(ctx)
    elif f=='review_cfs_hold_down':hold_down(ctx)
    elif f=='review_cfs_strap':strap(ctx)
    elif f=='review_sheathing':sheathing(ctx)
    elif f=='review_thermal_clip':thermal(ctx)
    elif f in ('review_hanger_plate','review_hanger_pin'):hanger(ctx)
    elif f=='review_platform_seat':platform(ctx)
    elif f=='review_rod_foundation':rod_foundation(ctx)
    else:raise ValueError(f)

def portal(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;point=ctx.c['point'];ms=[m for m in ctx.ms if m['kind'] in ('column','rafter')];dirs=[]
    for m in ms:
        far=max(m['axis'],key=lambda q:math.dist(q,point));dirs.append(unit([far[0]-point[0],0,far[2]-point[2]]))
    if len(dirs)!=2:raise ValueError('Portal node requires both source members')
    # Mirror right knees into a readable local frame without changing the source pitch.
    if dirs[1][0]<0:dirs=[[ -v[0],v[1],v[2]] for v in dirs]
    canopy=ctx.family=='review_canopy_knee';t=.375;bisector=unit(sub(*dirs))
    for i,(m,v) in enumerate(zip(ms,dirs)):
        part=a.member('M'+str(i+1),m['profile_id'],mul(v,-8 if i==0 else -18) if canopy else [0,0,0],mul(v,38),description=m['kind']+' '+m['profile_id'])
        if not canopy:clip_part(part,mul(bisector,1 if i==0 else -1),.1875)
    if canopy:
        # Actual box column and paired rafter webs, with internal pipe spacers.
        rp=ms[1]['profile_id'];cp=ms[0]['profile_id'];w=effective(p,cp,'width');pts=[[x,-w/2,z] for x in (-3,3) for z in (-3,3)]
        for i,q in enumerate(pts):a.cylinder('SP'+str(i),q,[0,1,0],1.25,w,'A','3/4 in bolt pipe spacer envelope')
        a.fastener('F1',pts,[0,1,0],.75,w,['M1','M2']+[f'SP{i}' for i in range(4)],'4 x 3/4 in A325 on 6 in square; source through-box spacer detail')
        a.section_axis=2;a.section_at=3;a.dim([-3,0,-3],[3,0,-3],'6 in gauge');a.notes.append('Source four-bolt through-box lap, with pipe spacers through the actual box width. A 8 in column-head extension and 18 in rafter-tail envelope; local flange notches and installation sequence require shop fitting.');return
    n=par['across'];rows=par['rows'];gauge=4 if n==3 else 3.5;half=(n-1)*gauge/2+2;length=(rows-1)*3+4
    pairs=len(p[ms[1]['profile_id']].get('components',[]))//2 or 1;pairgap=p[ms[1]['profile_id']].get('pair_spacing_in',6.375)
    for j in range(pairs):
        yy=(j-(pairs-1)/2)*pairgap;points=[]
        for v in dirs:
            across=[-v[2],0,v[0]]
            points.extend((q[0],q[2]) for q in [add(mul(v,end),mul(across,side)) for end in (0,length) for side in (-half,half)])
        if par.get('prop'):points.extend([(-3,-13),(3,-13)])
        if par.get('hanger'):points.extend([(-5,-17),(5,-17)])
        plate='P'+str(j);a.polygon(plate,[[x,yy-t/2,z] for x,z in hull(points)],t,basis='A',description='Source 3/8 in continuous bracket; A perimeter')
        for i,v in enumerate(dirs):
            across=[-v[2],0,v[0]];webt=p[p[ms[i]['profile_id']]['components'][0]['profile_id']]['dimensions']['t'] if p[ms[i]['profile_id']]['family']=='built_up' else .1017
            pts=[add(mul(v,2+r*3),add(mul(across,(g-(n-1)/2)*gauge),[0,yy-t/2-webt,0])) for r in range(rows) for g in range(n)]
            a.fastener(f'F{j}{i}',pts,[0,1,0],.75,t+2*webt,['M'+str(i+1),plate],f'{rows*n} x 3/4 in A325 per leg per pair; source grade, pitch/gauge')
    if par.get('prop'):
        pp=next(m['profile_id'] for m in ctx.ms if m['kind']=='prop');a.member('PROP',pp,[0,0,-40],[0,0,-13.75]);a.box('CAP',[-8,-11,-13.75],[16,22,.75],'A','Source 3/4 in cap; A footprint')
        for j in range(pairs):a.weld('WP'+str(j),[-3,(j-(pairs-1)/2)*pairgap,-13],[3,(j-(pairs-1)/2)*pairgap,-13],['P'+str(j),'CAP'],.25,basis='A',description='Bracket-to-cap weld, A local fit')
        a.weld('WC',[-3,-3,-13.75],[3,-3,-13.75],['PROP','CAP'],.1875,description='Source cap-to-HSS fillet all around')
    a.section_at=6;a.dim([0,0,-2],[0,0,-11],'3 @ 3 in pitch');a.notes.append(f'{pairs} actual bracket planes; {2*pairs*rows*n} total joint bolts. Source 2 in edge/end distances, {gauge:g} in gauge; A 3/8 in joint gap and convex bracket outline.')

def post(ctx):
    a,p,pid,txt,par=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params
    if ctx.family=='review_cfs_post' and ctx.c['point'][2]>min(q[2] for q in ctx.ms[0]['axis'])+.1:
        if ctx.model['pilot']=='cfs14' and p[pid]['family']=='rhs':
            rods=[m for m in ctx.model['members'] if m['kind']=='hold_down_rod'];pt=ctx.c['point'];near=min(rods,key=lambda m:math.dist(m['axis'][0],pt));rp=near['profile_id'];dia=p[rp]['dimensions']['d']
            a.member('POST',pid,[0,0,-24],[0,0,0]);a.box('CAP',[-3,-3,0],[6,6,1.5],'S','Source 1-1/2 x 6 x 6 in post cap');a.member('ROD',rp,[0,0,-4],[0,0,30]);a.cylinder('NUT',[0,0,-dia*1.5],[0,0,1],dia*1.8,dia*1.5,'A','Heavy hex nut under cap / A envelope')
            a.weld('CAP-WELD',[-3,-3,0],[3,-3,0],['POST','CAP'],.3125,description='Source 5/16 in fillet all around post flats');a.weld('BEARING',[-1,0,0],[1,0,0],['ROD','NUT','CAP'],kind='BEARING',description='Source upper-storey rod anchored below post cap; no rod weld');a.section_axis=2;a.section_at=.75;a.dim([3,0,0],[3,0,1.5],'1-1/2 in cap');return
        bp=ctx.select(('girder','walkway_edge_beam','joist'),ctx.default_w());d=effective(p,bp);a.member('POST',pid,[0,0,-26],[0,0,0]);a.box('CAP',[-8,-6,0],[16,12,.75],'A','A cap/seat plate');a.member('BEAM',bp,[-24,0,.75+d/2],[24,0,.75+d/2]);a.weld('WP',[-3,-3,0],[3,-3,0],['POST','CAP'],.25,basis='A');a.fastener('FB',[[x,y,.75] for x in (-4,4) for y in (-2,2)],[0,0,1],.625,.75+p[bp]['dimensions'].get('tf',.125),['BEAM','CAP'],'A cap-to-beam attachment',basis='A');a.section_at=4;return
    interior=par.get('interior') or p[pid]['family']=='rhs';canopy=ctx.model['pilot']=='cfs26';d=effective(p,pid);w=effective(p,pid,'width')
    if interior:t,bx,by,dia,n=.75,max(12,d+6),max(12,w+6),.75,4
    elif canopy:t,bx,by,dia,n=1.25,24,16,.75,4
    elif ctx.model['pilot']=='cfs30':t,bx,by,dia,n=1.25,24,18,1,6
    elif ctx.model['pilot']=='cfs17':t,bx,by,dia,n=.75,22,16,.75,4
    elif ctx.model['pilot']=='cfs19':t,bx,by,dia,n=.75,20,16,.75,4
    else:t,bx,by,dia,n=.375,max(8,d+2),max(10,w+4),.625,2
    if ctx.model['pilot']=='cfs14' and interior:t,bx,by,dia,n=2.5,6,24,1.5,2
    grout=-t if ctx.model['pilot']=='cfs14' and interior else 1.5;embed=par.get('embedment',4 if ctx.model['pilot']=='cfs29' else 12)
    a.box('CONC',[-bx/2-6,-by/2-6,-embed-6],[bx+12,by+12,embed+6],'A','Foundation/slab context',kind='concrete');a.box('GROUT',[-bx/2,-by/2,grout-1.5],[bx,by,1.5],'S','Non-shrink grout / recessed flush base where scheduled');a.box('BASE',[-bx/2,-by/2,grout],[bx,by,t],'S','Source base plate');a.member('POST',pid,[0,0,grout+t],[0,0,grout+t+30])
    if n==2:pts=[[0,y,-embed] for y in (-by/2+2,by/2-2)]
    else:pts=[[x,y,-embed] for x in (-bx/2+2,bx/2-2) for y in ([-by/2+2,by/2-2] if n==4 else [-by/2+2,0,by/2-2])]
    a.fastener('ANCH',pts,[0,0,1],dia,embed+grout+t,['CONC','BASE'],f'{n} x {dia:g} in F1554 anchors; source grade retained; A embedment where delegated')
    if interior:a.weld('W1',[-d/2,-w/2,grout+t],[d/2,-w/2,grout+t],['POST','BASE'],.1875,description='3/16 in source HSS base fillet all around')
    else:
        pairs=len(p[pid].get('components',[]))//2 or 1;sep=p[pid].get('pair_spacing_in',6.375)
        for j in range(pairs):
            yy=(j-(pairs-1)/2)*sep;thick=.5 if canopy else .375;label='G'+str(j);a.box(label,[-6,yy-thick/2,grout+t],[12,thick,18 if canopy else 10],'A','Source base gusset; A width/height fit');a.weld('W'+str(j),[-6,yy,grout+t],[6,yy,grout+t],['BASE',label],.375 if canopy else .25,description='Base gusset fillet both sides')
            pts=[[x,yy-thick/2-.13,grout+t+z] for x in (-3,3) for z in ((3,6,9,12) if canopy else (3,6))]
            a.fastener('B'+str(j),pts,[0,1,0],.75,thick+.26,['POST',label],f'{len(pts)} x 3/4 in A325 web bolts per bracket')
    a.section_axis=2;a.section_at=grout+t/2;a.dim([-bx/2,0,grout],[bx/2,0,grout],f'{bx:g} in plate');a.notes.append('Source anchor embedment, edge distances and concrete handoff requirements govern. Foundation reinforcement is retained as a delegated scope; A concrete block only shows the interface.')

def endpost(ctx,base=False):
    from .review_detail_extras import endpost as fitted
    return fitted(ctx,base)

def secondary(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;d=effective(p,pid);kind=par.get('kind','beam');receiver=ctx.select(('rafter','column','prop','girder','opening_jamb','chord'),ctx.default_w());rd=effective(p,receiver)
    a.member('M1',receiver,[-24,0,-rd/2],[24,0,-rd/2]);a.member('M2',pid,[0,-24,d/2+.125],[0,24,d/2+.125],y=[1,0,0]);lap=par.get('lap',0)
    if lap:
        offset=.125+p[pid]['dimensions'].get('t',.1);a.member('M3',pid,[offset,-min(24,lap),d/2+.125],[offset,min(24,lap),d/2+.125],y=[1,0,0],description='Nested same-section lap; A ply separation')
    web=p[pid]['dimensions'].get('t',.1017);t=par.get('clip_t',.25);height=min(d-1,8);z=1
    a.box('CLIP-W',[web/2,-3,z],[t,6,height],'A','Web leg of source bolted clip');a.box('CLIP-F',[web/2,-3,.125],[4,6,t],'A','Clip foot on receiving flange')
    pts=[[web/2+t,y,z+height/2] for y in (-1.5,1.5)];a.fastener('F1',pts,[-1,0,0],.5,t+web+(.125+web if lap else 0),['CLIP-W','M2']+(['M3'] if lap else []),'2 x 1/2 in A325 web bolts / source support clip')
    a.fastener('F2',[[2,y,-p[receiver]['dimensions'].get('tf',.13)] for y in (-1.5,1.5)],[0,0,1],.5,p[receiver]['dimensions'].get('tf',.13)+.125+t,['M1','CLIP-F'],'A: two 1/2 in receiving-flange bolts; source attachment retained in specification',basis='A')
    a.section_axis=1;a.section_at=1.5;a.dim([0,-3,z],[0,3,z],'6 in clip length (A)',basis='A');a.notes.append(f'Source {kind} section retained; lap extension {lap:g} in each side where scheduled. A clip fit and nested-Z offset; join every actual source ply. Source anti-roll/bridging requirements remain in associated record.')

def floor(ctx):
    from .review_wall_details import floor as fitted
    return fitted(ctx)

def hold_down(ctx):
    a,p,pid,par,txt=ctx.a,ctx.p,ctx.pid,ctx.params,ctx.text;dia=par['rod_diameter'];w=effective(p,pid,'width');d=effective(p,pid);t=.5
    match=re.search(r'(?:bearing|bracket) plate\s*(?:PL\s*)?'+NUMBER,txt,re.I)
    if match:t=number(match[1])
    if par.get('bearing_thickness'):t=par['bearing_thickness']
    a.member('CHORD',pid,[0,0,-24],[0,0,24],y=[1,0,0]);rp=rod(p,dia);a.member('ROD',rp,[0,0,-30],[0,0,30],basis='S',description=f'Source story {par["story"]} tie rod dia {dia:g}')
    # Plate spans actual pack; side returns fasten to every physical outer web.
    a.box('BEARING',[-w/2-1,-d/2,-t/2],[w+2,d,t],'A','Source bearing plate thickness / A fit envelope')
    faces=web_faces(p,pid);count=int(re.search(r'\d+',str(par.get('bracket_screws') or 16))[0]);h=max(6,math.ceil(count/max(1,len(faces))/2)+2)
    for j,(xx,sg,web) in enumerate(faces):
        per=count//len(faces)+(1 if j<count%len(faces) else 0)
        side='SIDE'+str(j);x=xx if sg>0 else xx-.25;a.box(side,[x,-d/2,-h],[.25,d,h],'A','A bracket return at actual chord web')
        pts=[[x+( .25 if sg>0 else 0),yy,-1.5-r] for r in range(math.ceil(per/2)) for yy in (-d/4,d/4)][:per]
        a.fastener('F'+str(j),pts,[-sg,0,0],.25,.25+web,[side,'CHORD'],f'{per} No.14 at this return; {count} total source bracket screws / A distribution',basis='A',screw=True);a.weld('W'+str(j),[x,-d/2,0],[x,d/2,0],[side,'BEARING'],.1875,basis='A')
    a.cylinder('NUT',[0,0,t/2],[0,0,1],dia*1.8,dia*.8,'A','A heavy nut / take-up envelope');a.weld('BEAR',[0,0,t/2],[dia,0,t/2],['NUT','BEARING'],kind='BEARING',basis='A',description='Nut/washer bearing interface; no weld to rod')
    if not par.get('separate_coupler'):
        cp=tube(p,dia*2,dia*2,.2);a.member('COUPLER',cp,[0,0,12],[0,0,12+4*dia],basis='A',representation_role='assembly_component',description='A proprietary coupler envelope')
    a.notes.append('Source rod grade, diameter and cumulative story force remain unchanged. Coupler/take-up envelope and bracket local layout are A, with no supplier capacity approval. All chord plies receive a shown attachment. Actual floor couplers are separate located details when so scheduled.')
    a.section_axis=2;a.section_at=-2;a.dim([-w/2-1,0,0],[w/2+1,0,0],basis='A')

def strap(ctx):
    if ctx.params.get('physical_strap_end'):
        from .review_cfs_frame_straps import draw
        return draw(ctx)
    a,p,pid,txt,par=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params;level=par.get('story',ctx.ms[0].get('level',1))
    story=re.search(r'story '+str(level)+r':\s*(.*?)(?=; story|\n|$)',txt,re.I);txt=story[1] if story else txt
    count=int(par.get('screws') or findnum(r'(\d+) No\.?\s*(?:10|12|14)',txt,10));size=int(par.get('screw_size') or findnum(r'\d+ No\.?\s*(\d+)',txt,14));dia=screw_diameter(size)
    cp=par.get('host_profile') or ctx.select(('chord','column','endwall_post','stud'))
    receiver=ctx.receiver(('top_track','bottom_track','ordinary_track','tier_track','eave_strut','rim_track','floor_rim'))
    if receiver is None:raise ValueError('Strap needs an actual receiving track/member selection: '+ctx.c['id'])
    tp=receiver['profile_id'];cd=effective(p,cp);width=p[pid]['dimensions']['width'];t=p[pid]['dimensions']['thickness'];gusset=.1017 if ctx.model['pilot'] in ('cfs14','cfs29') else .1875
    if ctx.model['pilot']=='cfs2':gusset=.1423
    if ctx.model['pilot']=='cfs5':gusset=.1242 if width==8 else .1017
    a.member('CHORD',cp,[0,0,-6],[0,0,30]);a.member('TRACK',tp,[0,0,0],[34,0,0],y=[0,0,1]);y=cd/2+.25
    a.polygon('GUSSET',[[0,y,0],[26,y,0],[26,y,14],[14,y,26],[0,y,26]],gusset,basis='A',description='Source gusset thickness / A corner outline')
    angle=math.atan2(abs(ctx.ms[0]['axis'][1][2]-ctx.ms[0]['axis'][0][2]),math.dist(ctx.ms[0]['axis'][0][:2],ctx.ms[0]['axis'][1][:2]));v=[math.cos(angle),0,math.sin(angle)];across=[-v[2],0,v[0]]
    a.member('STRAP',pid,add(mul(v,4),[0,y+gusset+t/2,0]),add(mul(v,42),[0,y+gusset+t/2,0]),y=across);cols=max(1,min(4,int(width-1)))
    if ctx.model['pilot']=='cfs2':cols={3:2,4:3,5:3,8:5}[width]
    if ctx.model['pilot']=='cfs5':cols={3:2,4:3,5:3,6:4,8:5}[width]
    rows=math.ceil(count/cols)
    pts=[add(mul(v,6+(i//cols)),add(mul(across,(i%cols-(cols-1)/2)),[0,y+gusset+t,0])) for i in range(count)]
    a.fastener('FS',pts,[0,-1,0],dia,t+gusset,['STRAP','GUSSET'],f'{count} No.{size} source strap-end screws'+(' stainless bi-metal' if par.get('stainless') else ''),screw=True)
    counts={3:(5,6),4:(7,8),5:(8,10),8:(17,19)}.get(width,(6,6)) if ctx.model['pilot']=='cfs2' else (6,6)
    if ctx.model['pilot']=='cfs5':counts={3:(5,6),4:(7,8),5:(8,10),6:(13,13) if t>.06 else (9,12),8:(15,19)}[width]
    for name,host,n in [('FC','CHORD',counts[0]),('FT','TRACK',counts[1])]:
        pts=[[1+(j//12),y,2+j%12] if host=='CHORD' else [2+j%20,y,1+(j//20)] for j in range(n)]
        a.fastener(name,pts,[0,-1,0],.25,gusset+.125,[host,'GUSSET'],f'{n} No.14 gusset-to-host screws; A local fit',basis='S' if ctx.model['pilot'] in ('cfs2','cfs5') else 'A',screw=True)
    a.section_at=8;a.dim(mul(v,6),mul(v,6+rows-1),f'{rows-1} @ 1 in (A)',basis='A')

def sheathing(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;sp=par['stud_profile'];tp=ctx.pid;d=effective(p,sp);t=par['thickness'];edge=float(par.get('edge_spacing',6));edge=max(edge,1)
    a.member('STUD',sp,[0,0,0],[0,0,30],y=[1,0,0]);a.member('TRACK',tp,[-12,0,0],[24,0,0],y=[0,0,1]);a.box('SHEET',[-12,d/2,0],[36,t,30],'S',str(par.get('material','Sheathing'))+' source thickness')
    fs=par.get('fastener_number',8);dia=screw_diameter(fs)
    a.fastener('EDGE',[[0,d/2+t,z] for z in frange(.5,30,edge)],[0,-1,0],dia,t+.08,['STUD','SHEET'],f'No.{fs} source screws at {edge:g} in edges; A end offsets',basis='S',screw=True)
    a.fastener('TRACK-S',[[x,d/2+t,.5] for x in frange(-11.5,24,edge)],[0,-1,0],dia,t+.08,['TRACK','SHEET'],'Panel-to-track source edge screws; A local pattern origin',basis='S',screw=True)
    a.section_axis=2;a.section_at=12;a.dim([0,0,.5],[0,0,.5+edge],f'{edge:g} in edge fasteners');a.notes.append(f'{par["faces"]} source sheathing face(s); reverse-face fastening repeats where specified. Type II walls use continuous sheathing over/under openings and end-only hold-downs; do not add intermediate hold-downs.')

def frange(a,b,s):
    while a<b:yield a;a+=s

def angle(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;host=ctx.select(('column','rafter','beam'));d=effective(p,host);a.member('HOST',host,[0,0,-24],[0,0,24]);v=[.8,0,.6];a.member('BRACE',pid,[d/2+2,0,0],[d/2+26,0,18]);a.box('GUSSET',[d/2,-.1875,-6],[16,.375,18],'A','A brace end gusset')
    n=par.get('count',4);dia=par.get('diameter',.625);a.fastener('F',[[d/2+4+r*3,-.5,1.5+r*2.25] for r in range(n)],[0,1,0],dia,1,['BRACE','GUSSET'],f'{n} x {dia:g} in source bolt group / A local fit');a.weld('W',[d/2,0,-6],[d/2,0,12],['GUSSET','HOST'],.25,basis='A');a.section_at=d/2+7

def thermal(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);a.member('PURLIN',pid,[-24,0,-d/2],[24,0,-d/2]);panel=channel(p,'ASSEMBLY-SKIN-PANEL',2,12,.024,0);a.member('SKIN',panel,[0,-20,4],[0,20,4],y=[1,0,0],basis='A')
    a.box('ISO',[-4,-3,0],[8,6,1],'A','Thermal isolation pad, A supplier envelope');a.box('CLIP',[-3,-2,1],[6,4,.125],'A','Sliding clip base, A supplier envelope');a.box('SLIDE',[-3,-2,1.125],[6,4,.125],'A','Moving plate / source +/-3/4 in travel')
    a.fastener('BASE',[[-2,0,-.1],[2,0,-.1]],[0,0,1],.25,1.225,['PURLIN','ISO','CLIP'],'A stainless bi-metal clip anchors',basis='A',screw=True);a.fastener('SHOULDER',[[0,0,1]],[0,0,1],.25,.5,['CLIP','SLIDE'],'A shoulder screw through 1-3/4 in longitudinal slot; do not clamp sliding plate',basis='A')
    a.weld('ATTACH',[-2,0,1.25],[2,0,1.25],['SKIN','SLIDE'],kind='CLIP',basis='A',description='A supplier panel-lock interface (no welded field attachment)');a.section_at=0;a.dim([-.75,0,3],[.75,0,3],'1-1/2 in total free travel');a.notes.append('S: +/-3/4 in slots isolate skin movement. Central structural bracing and exterior panel fixed-point layout are separate. A clip geometry requires supplier approval; no steel frame expansion joint is invented.')

def hanger(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;bp=par.get('beam_profile',ctx.select(('hanger_beam','monorail','beam')));d=effective(p,bp);dia=par.get('diameter',.875);gauge=par.get('gauge',3.5)
    if ctx.family=='review_hanger_pin':
        rp=ctx.select(('rafter',));rd=effective(p,rp);rr=rod(p,dia)
        a.member('RAFTER-L',rp,[-30,0,rd/2-3],[0,0,rd/2]);a.member('RAFTER-R',rp,[0,0,rd/2],[30,0,rd/2-3])
        for j,y in enumerate((-6.375,0,6.375)):
            a.box('EXT'+str(j),[-6,y-.1875,-10],[12,.375,rd],'S','Three source ridge-gusset extensions / 10 in below rafter')
            a.fastener('RIDGE'+str(j),[[x,y-.33,2] for x in (-4,4)],[0,1,0],.75,.66,['EXT'+str(j),'RAFTER-L','RAFTER-R'],'A local extract: complete source ridge bolt pattern on companion apex detail',basis='A')
        links=[]
        for j,y in enumerate((-4.5,4.5)):
            a.member('ROD'+str(j),rr,[0,y,-40],[0,y,-15]);links.append('ROD'+str(j))
            for side in (-1,1):
                name=f'CLEVIS{j}{side}';yy=y+side*.8-.375;a.box(name,[-2,yy,-15],[4,.75,12],'A','A forged clevis jaw envelope');links.append(name)
            a.box('CLEVIS-BODY'+str(j),[-2,y-1.175,-17],[4,2.35,3],'A','A forged threaded clevis body')
            a.weld('THREAD'+str(j),[-.5,y,-16],[.5,y,-16],['ROD'+str(j),'CLEVIS-BODY'+str(j)],kind='THREAD',basis='A',description='Threaded forged clevis engagement; no welded rod')
        a.fastener('PIN',[[0,-7,-6]],[0,1,0],1,14,['EXT0','EXT1','EXT2']+[n for n in links if n.startswith('CLEVIS')],'Source 1 in A325 transverse hanger pin; A forged jaw fit / retaining envelope')
        a.section_axis=2;a.section_at=-6;a.dim([0,-4.5,-15],[0,4.5,-15],'9 in adopted rod centres');a.notes.append('Three actual ridge-gusset extensions support both forged clevises on a common pin. Companion apex sheet gives the complete rafter bolt groups. Clevis forging profile, thread engagement and pin procurement length are A supplier assumptions.');return
    a.member('BEAM',bp,[-24,0,-d/2],[24,0,-d/2]);a.box('PLATE',[-4,-6,0],[8,12,1],'S' if dia==.875 else 'A','Hanger plate 1 x 8 x 12 in')
    a.fastener('FLANGE',[[x,y,-p[bp]['dimensions'].get('tf',.125)] for x in (-1.5,1.5) for y in (-gauge/2,gauge/2)],[0,0,1],.625,1+p[bp]['dimensions'].get('tf',.125),['BEAM','PLATE'],'Four 5/8 in A325 pretensioned flange bolts; source gauge')
    rp=rod(p,dia)
    for j,y in enumerate((-4.5,4.5)):
        a.member('ROD'+str(j),rp,[0,y,-4],[0,y,30],basis='S');a.cylinder('NUT'+str(j),[0,y,-dia*1.5],[0,0,1],dia*1.8,dia*1.5,'A','Double nuts / washer envelope');a.weld('BEAR'+str(j),[-dia,y,0],[dia,y,0],['ROD'+str(j),'NUT'+str(j),'PLATE'],kind='BEARING',basis='A',description='Thread/nut bearing; no welded rod attachment')
    if par.get('top'):
        # Upper hanger plate bears beneath the W bottom flange; invert the entire
        # local assembly so rods descend and the plate is not perched above it.
        for part in a.parts:
            for face in part['faces']:
                for q in face:q[2]=-q[2]
            from .assembly_scene import bounds
            part['bounds']=bounds(part['faces'])
        for fastener in a.fasteners:
            for q in fastener['points']:q[2]=-q[2]
            fastener['axis'][2]*=-1
        for weld in a.welds:weld['a'][2]*=-1;weld['b'][2]*=-1
    a.section_axis=0;a.section_at=1.5;a.dim([0,-4.5,1],[0,4.5,1],'9 in rod centres');a.notes.append('Use source bevelled F436 washers on the S-section 1:6 flange; normal hardened washers at W-section. Source pretension and cyclic-load requirements apply. Rod lengths and clevis envelope are A.')

def platform(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;rp=ctx.params['rafter_profile'];d=effective(p,rp);a.member('RAFTER',rp,[-24,0,-d/2],[24,0,-d/2]);a.box('BASE',[-4,-10,0],[8,20,.5],'S','Source 1/2 x 20 x 8 in platform leg plate');a.member('LEG',pid,[0,0,.5],[0,0,24],basis='A');a.weld('W1',[-2,-2,.5],[2,-2,.5],['LEG','BASE'],.25,basis='A');a.fastener('F1',[[x,y,-.125] for x in (-2,2) for y in (-8,8)],[0,0,1],.5,.625,['RAFTER','BASE'],'4 x 1/2 in bolts through source outer rafter flanges');a.section_at=2

def rod_foundation(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;dia=par['rod_diameter'];embed=par['embedment'];rp=rod(p,dia)
    a.member('CHORD',pid,[0,0,0],[0,0,24],y=[1,0,0]);a.member('ROD',rp,[0,0,-embed],[0,0,26],basis='S')
    a.box('CONC',[-18,-18,-embed-4],[36,36,embed+4],'A','Podium / foundation interface',kind='concrete');a.box('ANCHOR-PL',[-3,-3,-embed],[6,6,1],'A','A embedded rod-end plate; foundation design delegated')
    a.cylinder('NUT',[0,0,-embed-1],[0,0,1],dia*1.8,1,'A','A rod-end nut envelope');a.weld('THREAD',[0,0,-embed],[dia,0,-embed],['ROD','NUT','ANCHOR-PL'],kind='BEARING',basis='A',description='Thread/nut bearing; no rod weld')
    a.section_axis=2;a.section_at=-embed+.5;a.dim([4,0,-embed],[4,0,0],f'{embed:g} in illustrative anchorage depth (A)',basis='A');a.notes.append('Source tie-rod force and diameter retained. Foundation breakout/pullout reinforcement and rod-end anchorage remain delegated; displayed plate/embedment are explicit fictional review inputs, not a verified anchor design.')
