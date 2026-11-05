"""Wall-to-floor stacks, uplift paths and composite-pack attachments."""
import re,math
from .review_assemblies import *

def draw(ctx):
    {'review_pack_stitch':pack,'review_floor_strap':uplift,'review_post_collector':collector,'review_rod_transfer':rod_transfer,'review_roof_edge':roof_edge,'review_post_edge':post_edge}[ctx.family](ctx)

def rod_transfer(ctx):
    a,p=ctx.a,ctx.p;bp='W21X44';d=effective(p,bp);bf=effective(p,bp,'width');tf=p[bp]['dimensions']['tf'];tw=p[bp]['dimensions']['tw'];dia=p[ctx.pid]['dimensions']['d'];rx=6;ry=bf/4
    a.member('GIRDER',bp,[-12,0,-d/2],[36,0,-d/2]);a.member('ROD',ctx.pid,[rx,ry,-tf-3],[rx,ry,30]);a.box('WASHER',[rx-1.5,ry-1.5,-tf-.5],[3,3,.5],'S','Source 3 x 3 x 1/2 in plate washer below top flange');a.cylinder('NUT',[rx,ry,-tf-.5-dia],[0,0,1],dia*1.8,dia,'A','Heavy hex nut envelope')
    for j,sg in enumerate((-1,1)):
        y=tw/2 if sg>0 else -bf/2+.25;a.box('ST'+str(j),[rx+.75,y,-d+tf],[.375,bf/2-tw/2-.25,d-2*tf],'A','Source stiffener pair; A 3/8 in fit clear of nut');a.weld('W'+str(j),[rx+.75,y,-d+tf],[rx+.75,y,-tf],['ST'+str(j),'GIRDER'],.25,basis='A')
    a.weld('BEARING',[rx-1,ry,-tf],[rx+1,ry,-tf],['GIRDER','WASHER','NUT','ROD'],kind='BEARING',description='Source rod / nut bearing beneath girder flange; no rod weld');a.section_axis=0;a.section_at=rx;a.dim([rx,ry,-tf-.5],[rx,ry,-tf],'1/2 in washer')

def roof_edge(ctx):
    a,p=ctx.a,ctx.p;cp=next(m['profile_id'] for m in ctx.ms if m['kind']=='truss_chord');bp='W8X18';d=effective(p,bp);cd=effective(p,cp)
    a.member('EDGE',bp,[-24,0,-d/2],[24,0,-d/2]);a.member('HEEL',cp,[0,-6,cd/2],[0,30,cd/2],y=[1,0,0]);faces=web_faces(p,cp);xx,sg,web=faces[-1];x=xx if sg>0 else xx-.375
    a.box('TAB',[x,-2,0],[.375,4,11],'S','Source 3/8 x 4 x 11 in truss heel tab');a.fastener('BOLTS',[[x+.375,0,z] for z in (2,5,8)],[-1,0,0],.5,.375+.0566,['TAB','VERT'],'Source three 1/2 in A325 bolts at 3 in pitch into heel vertical')
    vp=channel(p,'ASSEMBLY-HEEL600',6,2,.0566,.625);a.member('VERT',vp,[x-.0283,0,.1],[x-.0283,0,12],y=[1,0,0],basis='A',description='A supplier heel vertical, minimum source 54 mil');a.weld('SUPPLIER',[x,0,cd/2],[x,2,cd/2],['VERT','HEEL'],kind='SUPPLIER',basis='A',description='A truss supplier heel-node attachment; companion truss node detail')
    for j,sg in enumerate((-1,1)):a.weld('W'+str(j),[x if sg<0 else x+.375,-2,0],[x if sg<0 else x+.375,2,0],['TAB','EDGE'],.1875,description='Source two 3/16 in shop fillets');
    a.section_axis=2;a.section_at=5;a.dim([x,0,2],[x,0,8],'2 @ 3 in pitch')

def post_edge(ctx):
    a,p=ctx.a,ctx.p;d=effective(p,ctx.pid);sp=channel(p,'ASSEMBLY-EDGE600',6,2,.0713,.625)
    a.member('POST',ctx.pid,[0,0,-18],[0,0,24]);a.member('EDGE',sp,[d/2+.03565,0,-18],[d/2+.03565,0,24],y=[1,0,0],basis='A',description='Source WSP edge stud; A 68 mil fit')
    a.fastener('SCREWS',[[d/2+.0713,y,z] for y in (-1,1) for z in (-12,-8,-4,0,4,8,12,16)],[-1,0,0],.25,.0713+p[ctx.pid]['dimensions']['t'],['POST','EDGE'],'Source two rows No.14 at 4 in pitch; A transverse 2 in gauge',screw=True)
    a.section_axis=2;a.section_at=0;a.dim([d/2,0,0],[d/2,0,4],'4 in pitch')

def floor(ctx):
    from . import review_wall_occurrence_details as located
    if ctx.params.get('physical_sill') and (ctx.ms[0].get('level',1)==1 or abs(ctx.c['point'][2])<.1):return located.sill(ctx)
    if ctx.params.get('physical_joist_end') and ctx.params.get('clip') and re.search(r'L\s*3\s*x\s*3\s*x\s*54 mil',ctx.text,re.I):return located.joist(ctx)
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;k=ctx.ms[0].get('level',1);base=ctx.family=='review_cfs_sill' and k==1;concrete=ctx.model['pilot']=='cfs3'
    track=pid if p[pid]['family']=='channel' and 'T' in pid else channel(p,'ASSEMBLY-TRACK600',6.2,2,.0713,0)
    sp=ctx.select(('stud',));jp=pid if ctx.family=='review_cfs_joist' else ctx.select(('joist',),channel(p,'ASSEMBLY-J1000',10,2,.0713,.5));jd=effective(p,jp);sd=effective(p,sp)
    a.member('UPPER',sp,[0,0,.15],[0,0,24],y=[1,0,0]);a.member('BOTTOM-TRACK',track,[-24,0,.05],[24,0,.05],y=[0,0,1])
    if base or concrete:
        slab=par.get('slab_thickness',12) if base else 3
        a.box('SLAB',[-28,-16,-slab],[56,32,slab],'A' if base else 'S','Foundation / source concrete floor slab',kind='concrete')
        dia=ctx.n(NUMBER+r' in\. (?:F1554|anchor)',.625 if base else .5);embed=min(slab-1,7 if base else 2)
        a.fastener('ANCH',[[-12,0,-embed],[12,0,-embed]],[0,0,1],dia,embed+.15,['BOTTOM-TRACK','SLAB'],'Source anchor size; A local end offsets / embedment where delegated',basis='A')
        if not base:
            a.member('LOWER',sp,[0,0,-slab-24],[0,0,-slab-.15],y=[1,0,0]);a.member('TOP-TRACK',track,[-24,0,-slab],[24,0,-slab],y=[0,0,-1])
            for sg in (-1,1):a.fastener('LOWER-S'+str(sg),[[0,sg*sd/2,-slab-.5]],[0,-sg,0],.216,.2,['LOWER','TOP-TRACK'],'A stud/track attachment',basis='A',screw=True)
    else:
        a.member('LOWER',sp,[0,0,-jd-24],[0,0,-jd-.15],y=[1,0,0]);a.member('TOP-TRACK',track,[-24,0,-jd],[24,0,-jd],y=[0,0,-1])
        for j,sg in enumerate((-1,1)):
            a.member('JOIST'+str(j),jp,[0,sg*.125,-jd/2],[0,sg*28,-jd/2],y=[1,0,0]);a.box('DECK'+str(j),[-24,3.3 if sg>0 else -24,0],[48,20.7,.75],'A','Subfloor held back from stacked bearing wall')
            stiff=channel(p,'ASSEMBLY-STIFF362',3.625,1.625,.0566,.5);a.member('STIFF'+str(j),stiff,[-1.625,sg*1.5,-jd+.1],[-1.625,sg*1.5,-.1],y=[1,0,0],basis='A',description='Source bearing stiffener; A local alignment')
            a.fastener('STIFF-S'+str(j),[[-.05,sg*1.5,z] for z in (-jd+1.5,-1.5)],[-1,0,0],.19,.2,['JOIST'+str(j),'STIFF'+str(j)],'A stiffener flange screws to joist web',basis='A',screw=True)
            a.fastener('SHEAR'+str(j),[[x,sg*1.5,-.15] for x in (.5,1.25)],[0,0,1],.216,.3,['JOIST'+str(j),'BOTTOM-TRACK'],'A source transfer-station attachment; spacing in source record',basis='A',screw=True)
        a.fastener('LOWER-S',[[0,sd/2,-jd-.5]],[0,-1,0],.216,.2,['LOWER','TOP-TRACK'],'A stud-to-top-track screw',basis='A',screw=True)
        # Local compression path is steel-to-steel, without compressible flooring.
        a.notes.append('Subfloor/underlayment is held back from the stacked wall bearing strip. Upper wall bears through stiffened joist ends onto the lower wall top track. Source diaphragm shear-transfer spacing applies along the complete wall, not just this extract.')
    for j,sg in enumerate((-1,1)):a.fastener('UP-S'+str(j),[[0,sg*sd/2,.6]],[0,-sg,0],.216,.2,['UPPER','BOTTOM-TRACK'],'A stud-to-track flange screw',basis='A',screw=True)
    a.section_axis=0;a.section_at=.5;a.dim([24,0,-(slab if base or concrete else jd)],[24,0,0],basis='A');a.notes.append('Source story and line shear/uplift schedules are attached. The local fit is A where unprovided; foundation reinforcement and supplier approval remain delegated.')

def pack(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);w=effective(p,pid,'width');a.member('PACK',pid,[0,0,-18],[0,0,18],y=[1,0,0]);a.member('CONT',pid,[0,0,18],[0,0,24],y=[1,0,0])
    # Continuous cover strips provide an explicit A seam fit for the boxed arrangement.
    for j,sg in enumerate((-1,1)):
        y=sg*d/2;label='SEAM'+str(j);a.box(label,[-1.5,y if sg>0 else y-.0566,-18],[3,.0566,36],'A','A 54 mil continuous seam cover at opposing flange tips')
        a.fastener('F'+str(j),[[x,y+(.0566 if sg>0 else -.0566),z] for x in (-1,1) for z in (-12,0,12)],[0,-sg,0],.19,.2,['PACK',label],'Source pairs No.10 at 12 in; A flange-seam fit',basis='A',screw=True)
    a.section_axis=2;a.section_at=0;a.dim([0,0,-12],[0,0,0],'12 in source stitching pitch');a.notes.append('The source count, section and steel thickness of every chord ply is retained. Box arrangement/clear rod cavity and seam-cover fit are A; stitching is repeated through all adjacent pack interfaces. This is not a new built-up-column capacity check.')

def uplift(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;d=effective(p,pid);foundation=par.get('foundation');width=1.5 if foundation else 2;t=.0566;count=4
    a.member('UPPER',pid,[0,0,0],[0,0,30],y=[1,0,0]);strap=flat(p,width,t)
    if foundation:a.box('CONC',[-16,-16,-18],[32,32,18],'A','Foundation anchorage context',kind='concrete');low=-12
    else:a.member('LOWER',pid,[0,0,-42],[0,0,-12],y=[1,0,0]);low=-30
    a.member('STRAP',strap,[0,d/2+t/2,low],[0,d/2+t/2,18],y=[1,0,0]);a.fastener('UP',[[0,d/2+t,z] for z in (3,6,9,12)],[0,-1,0],.216,t+.08,['STRAP','UPPER'],'Source four No.12 per end; A set-out',screw=True)
    if not foundation:a.fastener('LOW',[[0,d/2+t,z] for z in (-15,-18,-21,-24)],[0,-1,0],.216,t+.08,['STRAP','LOWER'],'Source four No.12 per end; A set-out',screw=True)
    else:a.weld('EMBED',[0,d/2,-12],[0,d/2,0],['STRAP','CONC'],kind='EMBED',basis='A',description='Foundation engineer designs cast-in anchorage; 12 in shown A')
    a.section_axis=2;a.section_at=6;a.dim([0,0,0],[0,0,12],'12 in adopted lap',basis='A');a.notes.append('Uplift bypasses bottom-track bending. Source straps repeat at 32 in centres; this is one typical occurrence. Foundation breakout/pullout verification remains delegated.')

def collector(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;d=effective(p,pid);w=effective(p,pid,'width');a.member('POST',pid,[0,0,-24],[0,0,24]);track=channel(p,'ASSEMBLY-COLLECTOR600',6,2,.0713,0)
    for j,sg in enumerate((-1,1)):
        a.member('TRACK'+str(j),track,[sg*(d/2+.125),0,0],[sg*(d/2+24),0,0],y=[0,0,1]);a.member('NEST'+str(j),track,[sg*(d/2+.125),0,.08],[sg*(d/2+24),0,.08],y=[0,0,1]);x=d/2 if sg>0 else -d/2-12
        a.box('PL'+str(j),[x,-2.75,.16],[12,5.5,.25],'S','Source 1/4 x 5-1/2 x 12 in collector splice plate');n=par['screws'];pts=[[sg*(d/2+1.5+(r//2)*1.5),(-1 if r%2 else 1)*1.5,.41] for r in range(n)]
        a.fastener('F'+str(j),pts,[0,0,-1],.25,.41,['PL'+str(j),'TRACK'+str(j),'NEST'+str(j)],f'{n} No.14 each side; two rows at 1-1/2 in source pitch',screw=True);a.weld('W'+str(j),[sg*d/2,-2.75,.16],[sg*d/2,2.75,.16],['POST','PL'+str(j)],.1875,description='Source shop fillets above and below splice plate')
    a.section_axis=2;a.section_at=.2;a.dim([d/2,0,0],[d/2+12,0,0],'12 in plate length');a.notes.append('HSS post is continuous through the Level 1 floor. No post splice or rod coupler is introduced at this level. Rim ends butt the post and the floor joist provides the source point brace.')
