"""Source-specific SBMF, single-channel and open-front assembled details."""
import math
from .review_assemblies import effective,flat,channel,rod,web_faces,add,sub,mul,unit,hull,clip_part
FAMILIES={'review_next_portal_joint','review_next_portal_base','review_next_secondary','review_skin_fastener','review_screwed_flybrace','review_sbmf_joint','review_sbmf_header','review_sbmf_strut','review_sbmf_wall_slide','review_sbmf_hold_down'}

def draw(ctx):
    f=ctx.family
    if f=='review_next_portal_joint':portal(ctx)
    elif f=='review_next_portal_base':base(ctx)
    elif f=='review_next_secondary':secondary(ctx)
    elif f=='review_skin_fastener':skin(ctx)
    elif f=='review_screwed_flybrace':flybrace(ctx)
    elif f=='review_sbmf_joint':sbmf(ctx)
    elif f=='review_sbmf_header':header(ctx)
    elif f=='review_sbmf_strut':strut(ctx)
    elif f=='review_sbmf_wall_slide':wall_slide(ctx)
    elif f=='review_sbmf_hold_down':hold_down(ctx)

def portal(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;point=ctx.c['point'];directions=[];existing=par.get('existing_context');single=ctx.model['pilot']=='cfs27'
    if existing:
        cp,rp=ctx.ms[0]['profile_id'],ctx.ms[1]['profile_id'];d=effective(p,cp);a.member('HOST',cp,[0,0,-32],[0,0,12]);a.member('RAFTER',rp,[d/2+1,0,0],[d/2+44,0,4]);a.box('END',[d/2,-10,-12],[1,20,24],'A','Assumed existing end plate');a.fastener('B',[[d/2-1,y,z] for y in (-7,7) for z in (-8,0,8)],[1,0,0],.875,2,['HOST','END'],'A six 7/8 in existing joint bolts','A');a.weld('W',[d/2+1,-8,-8],[d/2+1,8,-8],['END','RAFTER'],.375,basis='A');a.notes.append('A assumed existing survey joint. Source retrofit scope explicitly excludes primary frame connections; this graphic is coordination context and has no source design check.');return
    for m in ctx.ms:
        far=max(m['axis'],key=lambda q:math.dist(q,point));directions.append(unit([far[0]-point[0],0,far[2]-point[2]]))
    if directions[1][0]<0:directions=[[-v[0],v[1],v[2]] for v in directions]
    bisector=unit(sub(*directions));t=.25 if single else .375;rows=par['rows'];pitch=2.5 if single else 3;dia=.625 if single else .75;gauge=3.5;leg1=48 if par['joint']=='knee' and single else 36 if par['joint']=='knee' else 24;leg2=36 if par['joint']=='knee' else 24
    for j,(m,v) in enumerate(zip(ctx.ms,directions)):
        part=a.member('M'+str(j),m['profile_id'],[0,0,0],mul(v,max(leg1,leg2)+12));clip_part(part,mul(bisector,1 if j==0 else -1),.1875)
    pair_count=1 if single else 3;pair_spacing=6.375
    for pair in range(pair_count):
        centre=(pair-(pair_count-1)/2)*pair_spacing;coords=[]
        for v,L in zip(directions,(leg1,leg2)):
            cross=[-v[2],0,v[0]]
            for station in (0,L+2):
                for sg in (-1,1):q=add(mul(v,station),mul(cross,sg*6.5));coords.append((q[0],q[2]))
        offsets=[-.1242/2-t,.1242/2] if single else [centre-t/2]
        plates=[]
        for j,yy in enumerate(offsets):
            name=f'G{pair}{j}';a.polygon(name,[[x,yy,z] for x,z in hull(coords)],t,basis='A',description='S source gusset thickness / 13 in leg depth; A node outline');plates.append(name)
        for leg,(m,v,L) in enumerate(zip(ctx.ms,directions,(leg1,leg2))):
            across=[-v[2],0,v[0]];tw=p[m['profile_id']]['dimensions']['t'] if single else .1242 if m['kind']=='column' else .1017;start=L-(rows-1)*pitch
            yy=-tw/2-t if single else centre-t/2-tw;pts=[add(mul(v,start+r*pitch),add(mul(across,(g-1.5)*gauge),[0,yy,0])) for r in range(rows) for g in range(4)]
            a.fastener(f'B{pair}{leg}',pts,[0,1,0],dia,2*t+tw if single else t+2*tw,['M'+str(leg)]+plates,f'S {4*rows} bolts per leg'+(' each pair' if not single else '')+'; A station datum')
            if single:
                q=mul(v,L+2);a.box('ST'+str(leg),[q[0]-1,-.1242/2-1,q[2]-1],[2,2,2],'A','Source 1/4 in end stiffener; A folded clip envelope');a.fastener('S'+str(leg),[[q[0],-.1242/2-1,q[2]]],[0,1,0],.625,1.1242,['M'+str(leg),'ST'+str(leg)],'A stiffener bolts','A')
    a.section_axis=0;a.section_at=6;a.dim(mul(directions[1],leg2-(rows-1)*pitch),mul(directions[1],leg2),f'{rows-1} @ {pitch:g} in source pitch')
    a.notes.append('S: bolt groups at the bracket leg ends; single-channel twin plates fit each face of its web, or one plate between each of three channel pairs. A: full node perimeter, ply spacing, cutbacks and stiffener fit. No single-channel assembly is replaced with a paired-channel detail.')

def base(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;key=ctx.model['pilot'];d=effective(p,pid);w=effective(p,pid,'width');existing=par.get('existing_context')
    t,bx,by,dia=(.75,20,20,.75) if key=='cfs10' else (.75,18,18,.75) if key=='cfs18' else (.5,16,8,.625) if key=='cfs27' else (.875,16,22,.875) if key=='cfs28' else (1,24,24,1)
    basis='A' if existing else 'S';a.box('CONC',[-bx/2-6,-by/2-6,-18],[bx+12,by+12,18],'A','Foundation context',kind='concrete');a.box('GROUT',[-bx/2,-by/2,0],[bx,by,1.5],basis,'1.5 in grout');a.box('BASE',[-bx/2,-by/2,1.5],[bx,by,t],basis,'Source base plate' if not existing else 'A existing base');a.member('COL',pid,[0,0,1.5+t],[0,0,38],basis=basis)
    edge=1.5 if key in ('cfs10','cfs18') else 1.75;pts=[[x,y,-12] for x in (-bx/2+edge,bx/2-edge) for y in (-by/2+edge,by/2-edge)];a.fastener('ANCH',pts,[0,0,1],dia,13.5+t,['CONC','BASE'],f'{basis}: 4 x {dia:g} in F1554-36; A embedment',basis)
    if key in ('cfs10','cfs18','cfs25'):a.weld('W',[-d/2,-w/2,1.5+t],[d/2,-w/2,1.5+t],['COL','BASE'],.25,basis=basis,description='All-around HSS fillet')
    else:
        count=1 if key=='cfs27' else 3;tw=.1242
        for j in range(count):
            centre=(j-(count-1)/2)*6.375;offsets=[-tw/2-.375,tw/2] if key=='cfs27' else [centre-.1875];parts=[]
            for n,y in enumerate(offsets):
                label=f'G{j}{n}';a.box(label,[-6,y,1.5+t],[12,.375,10],'A','S 3/8 in base gusset; A outline');a.weld('W'+label,[-6,y,1.5+t],[6,y,1.5+t],['BASE',label],.25,basis='A');parts.append(label)
            a.fastener('B'+str(j),[[x,offsets[0],z+1.5+t] for x in (-3,3) for z in (3,6)],[0,1,0],.625 if key=='cfs27' else .75,.75+tw if key=='cfs27' else .375+2*tw,['COL']+parts,'S four A325 web bolts per pair; A set-out')
    a.section_axis=2;a.section_at=1.5+t/2;a.dim([-bx/2,0,1.5],[bx/2,0,1.5],basis=basis);a.notes.append('Source plate/rod sizes retained; foundation block, anchor embedment and reinforcement are A delegated coordination geometry.' if not existing else 'A existing survey base. Original retrofit excludes the column base and anchor design.')

def secondary(ctx):
    from .review_cfs_details import secondary as ordinary
    ordinary(ctx);a=ctx.a;par=ctx.params;t=par.get('clip_t',.25)
    if t!=.25:
        for part in a.parts:
            if part['id'] in ('CLIP-W','CLIP-F'):part['description']='S 3/8 in anti-roll bent plate; A fit';part['basis']='S'
        a.notes.append('S: retrofit anti-roll clip is 3/8 in; graphic envelope includes the source thickness in the parts schedule.')
    if par.get('support_bolts')==4:
        f=next(f for f in a.fasteners if f['id']=='F2');a.fasteners.remove(f);a.parts[:]=[part for part in a.parts if part['id']!='F2'];pts=[[x,y,-.13] for x in (1,3) for y in (-1.5,1.5)];a.fastener('F2',pts,[0,0,1],.5,.13+.125+t,['M1','CLIP-F'],'S four 1/2 in support bolts at interior eave purlins; A gauge')

def skin(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);a.member('PURLIN',pid,[-24,0,-d/2],[24,0,-d/2]);skin=flat(p,24,.024);a.member('PANEL',skin,[-24,0,.012],[24,0,.012],y=[0,1,0],basis='A',description='A local sheet strip; source through-fastened option');spacing=ctx.params['spacing'];a.fastener('SCREWS',[[x,0,.024] for x in range(-18,19,spacing)],[0,0,-1],.216,.024+p[pid]['dimensions']['t'],['PURLIN','PANEL'],f'S No.12-14 at {spacing} in, 1/2 in sealing washer',screw=True);a.dim([-18,0,0],[-18+spacing,0,0],f'{spacing} in source spacing');a.section_at=0

def flybrace(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;host=ctx.ms[1]['profile_id'] if len(ctx.ms)>1 else ctx.select(('column','rafter'));d=effective(p,host);a.member('HOST',host,[-24,0,0],[24,0,0]);a.member('BRACE',pid,[0,0,-d/2],[0,20,-d/2+20],y=[1,0,0]);clip=flat(p,4,.105);a.member('CROSS',clip,[-2,-9.5,-d/2-.0525],[-2,9.5,-d/2-.0525],y=[1,0,0],basis='S' if ctx.params.get('cross_plate') else 'A');n=ctx.params.get('screws',2);a.fastener('SCREWS',[[x,1,-d/2] for x in [(-n+1)*.5+j for j in range(n)]],[0,0,-1],.216,.23,['BRACE','CROSS','HOST'],f'S {n} No.12 screws each end; A set-out',screw=True);a.section_axis=0;a.section_at=0;a.notes.append('Source angle section and screw count; A receiving-member clip and local fit. Companion building view locates each torsion/flange restraint.')

def sbmf(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;bp=ctx.pid;cp=ctx.ms[1]['profile_id'];d=effective(p,bp);cd=effective(p,cp);ct=p[cp]['dimensions']['t'];beam_t=p[p[bp]['components'][0]['profile_id']]['dimensions']['t'];bearing=par.get('bearing_plates');t=.25 if bearing else 0
    a.member('COLUMN',cp,[0,0,-30],[0,0,22]);a.member('BEAM',bp,[-cd/2,0,0],[42,0,0]);parts=['COLUMN','BEAM']
    if bearing:
        for j,sg in enumerate((-1,1)):
            name='BP'+str(j);y=cd/2+beam_t if sg>0 else -cd/2-beam_t-.25;a.box(name,[-5.625,y,-8],[11.75,.25,16],'S','Source 1/4 x 11.75 x 16 in bolt-bearing plate');a.weld('W'+str(j),[-5.625,y,-8],[6.125,y,-8],['BEAM',name],.125,description='Source 1/8 in E70 all around bearing plate');parts.append(name)
    a.fastener('BOLTS',[[x,-cd/2-beam_t-t,z] for x in (-3.125,3.125) for z in (-6,-3,3,6)],[0,1,0],1,cd+2*(beam_t+t),parts,'S eight 1 in A325 snug-tight; 1-1/16 in holes; hardened washers both sides')
    a.dim([-3.125,0,-6],[3.125,0,-6],'6-1/4 in gauge');a.dim([3.125,0,-6],[3.125,0,6],'3 / 6 / 3 in vertical pattern',offset=40);a.section_axis=2;a.section_at=3
    a.notes.append('S: channel webs straddle the HSS. Full-depth through bolts use the prescribed snug-tight joint; no welded moment connection or pretension is substituted. '+('Source bearing plates weld to channel webs, never to the HSS faying faces.' if bearing else 'Source explicitly has no bolt-bearing plates.')+' Gravity roof framing is separate; no slab/deck attachment is added to this beam.')

def header(ctx):
    a,p=ctx.a,ctx.p;pid=ctx.pid;cp=ctx.ms[1]['profile_id'];cd=effective(p,cp);d=effective(p,pid);tw=p[p[pid]['components'][0]['profile_id']]['dimensions']['t'];face=cd/2
    a.member('COLUMN',cp,[0,0,-24],[0,0,16]);a.member('HEADER',pid,[face+.5,0,-d/2],[face+36,0,-d/2]);a.box('TAB',[face,-.1875,-d/2-3],[6,.375,6],'S','Source 3/8 in shear plate, 6 in long');a.fastener('B',[[face+3,-.1875-tw,z] for z in (-d/2-1.5,-d/2+1.5)],[0,1,0],.625,.375+2*tw,['HEADER','TAB'],'S 2 x 5/8 in A325 double shear / A pitch');a.weld('W',[face,0,-d/2-3],[face,0,-d/2+3],['COLUMN','TAB'],.25,description='Source two 1/4 in fillets');a.section_at=face+3

def strut(ctx):
    a,p=ctx.a,ctx.p;bp=ctx.ms[1]['profile_id'];d=effective(p,bp);width=effective(p,bp,'width');a.member('BEAM',bp,[-24,0,d/2],[24,0,d/2]);a.member('STRUT',ctx.pid,[0,width/2-2,0],[0,width/2+22,0],y=[1,0,0]);vp=channel(p,'A-TRUSS-VERTICAL',6,1.625,.0566,.5);a.member('TRUSS',vp,[0,width/2+22,-12],[0,width/2+22,30],y=[1,0,0],basis='A');a.fastener('SCREWS',[[x,width/2-1,.0566] for x in (-.5,.5)],[0,0,-1],.216,.1808,['BEAM','STRUT'],'S 2 No.12 into bottom flange',screw=True);a.fastener('SLIDE',[[0,width/2+22-.0566,0]],[0,1,0],.5,.1132,['STRUT','TRUSS'],'S 1/2 in bolt; A 2 in vertical slot, free to slide');a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=2,travel_in=1.5,basis='A');a.dim([0,width/2,0],[0,width/2+24,0],'24 in source strut',view='plan');a.notes.append('S: this is a lateral flange restraint only. Vertical slot transfers no gravity reaction to the SBMF beam. A slot travel and supplier vertical fit; source minimum 54 mil truss web.')

def wall_slide(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);tp=channel(p,'A-DEEP-TRACK',d,2,.0713,0);a.member('STUD',pid,[0,0,-30],[0,0,-.5],y=[1,0,0]);a.member('TRACK',tp,[-18,0,0],[18,0,0],y=[0,0,-1],basis='A');a.box('CLIP',[-2,-.125,-8],[4,.125,8],'A','A supplier slide clip');a.fastener('SCREWS',[[0,-.125,z] for z in (-2,-5)],[0,1,0],.216,.125+.0713,['STUD','CLIP'],'S two No.12 through 2 in vertical slots',screw=True);a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=2,travel_in=1.5,basis='S');a.fastener('FIX',[[x,-.125,-.5] for x in (-1,1)],[0,1,0],.216,.1963,['CLIP','TRACK'],'A clip to track screws','A',screw=True);a.notes.append('S: wall racks in plane on single-line fasteners; source panel clips accommodate drift. This is a vertical stud slip clip, not a horizontal brace for the SBMF frame. A clip envelope and fixed-end pattern.')

def hold_down(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;dia=par['rod_diameter'];rp=rod(p,dia);d=effective(p,pid);w=effective(p,pid,'width');a.member('CHORD',pid,[0,0,0],[0,0,32],y=[1,0,0]);a.member('ROD',rp,[0,0,-12],[0,0,16]);a.box('BRACKET',[-w/2-1,-.375,0],[w+2,.375,12],'A','S 3/8 in bent bracket at continuous wall / A bracket fit');a.box('SEAT',[-w/2-1,-d/2,0],[w+2,d,.375],'A','A folded bearing leg');a.fastener('BOLTS',[[x,-.375,z] for x in (-w/4,w/4) for z in (3,8)],[0,1,0],.75,.375+.25,['CHORD','BRACKET'],'S four 3/4 in A325 at continuous chord; A geometry','S' if par.get('continuous') else 'A');a.cylinder('NUT',[0,0,.375],[0,0,1],dia*1.8,dia,'A','Take-up/nut envelope');a.interfaces.append(dict(id='ROD-BEARING',kind='thread_bearing',connects=['ROD','NUT','SEAT'],basis='A',description='A supplier take-up device / source rod diameter'));a.weld('FOLD',[-w/2-1,0,0],[w/2+1,0,0],['BRACKET','SEAT'],kind='FOLD',basis='A',description='Bent bracket continuous corner; no field seam');a.section_axis=2;a.section_at=3
    if par.get('foundation'):a.box('CONC',[-18,-18,-18],[36,36,18],'A','Slab interface',kind='concrete')
    a.notes.append('Source continuous chord or story-specific tie-rod diameter retained. A supplier bracket fit, coupler/take-up and anchor embedment where not dimensioned. Ordinary track shear anchors have their own connection callouts.')
