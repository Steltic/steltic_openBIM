"""Wall-supported joists, scheduled header clips and lower-roof interfaces."""
import math
from .review_assemblies import effective,channel,web_faces,screw_diameter
FAMILIES={'review_final_cfs_joist','review_final_header','review_final_guard','review_final_roof_transfer'}

def draw(ctx):
    if ctx.family=='review_final_header':header(ctx)
    elif ctx.family=='review_final_guard':guard(ctx)
    elif ctx.family=='review_final_roof_transfer':roof_transfer(ctx)
    else:joist(ctx)

def header(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;hp=ctx.pid;hd=effective(p,hp);jp=ctx.select(('opening_jamb',),channel(p,'ASSEMBLY-JAMB',6,1.625,.0566,.5));jd=effective(p,jp);t=par['source_header_clip_t'];count=par['source_header_screws'];dia=screw_diameter(par['source_header_screw_size']);face=jd/2
    a.member('JAMB',jp,[0,0,-hd-18],[0,0,12]);a.member('HEADER',hp,[face+.125,0,-hd/2],[face+30,0,-hd/2]);faces=web_faces(p,hp)
    for j,(yy,sg,web) in enumerate(faces):
        n=count//len(faces)+(j<count%len(faces));h=hd-1;leg=3;tag='CLIP'+str(j);y=yy if sg>0 else yy-t
        a.box(tag,[face,y,-hd+.5],[leg,t,h],'A','S 54 mil clip; A 3 in legs and fitted length')
        a.box(tag+'R',[face,yy-3 if sg<0 else yy,-hd+.5],[t,3,h],'A','A clip return to jamb flange')
        rows=math.ceil(n/2)
        a.fastener('H'+str(j),[[face+.75+(r%2)*1.5,yy+sg*t,-hd+1+(r//2)*(hd-2)/max(1,rows-1)] for r in range(n)],[0,-sg,0],dia,t+web,['HEADER',tag],f'S {n} of {count} No.12 screws to header; A distribution',screw=True)
        a.fastener('J'+str(j),[[face+t,yy+sg*(.5+(r%2)*.625),-hd+1+(r//2)*(hd-2)/max(1,rows-1)] for r in range(n)],[-1,0,0],dia,t+.0566,['JAMB',tag+'R'],f'S {n} of {count} No.12 screws to jamb; A distribution',screw=True)
    a.dim([face,0,-hd+.5],[face,0,-.5],'A fitted clip height',basis='A');a.section_axis=0;a.section_at=face+1

def joist(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;jp=ctx.pid;jd=effective(p,jp);sp=ctx.select(('stud',),channel(p,'ASSEMBLY-STUD600',6,1.625,.0566,.5));sd=effective(p,sp);tp=channel(p,'ASSEMBLY-TRACK600',6.2,1.5,.0713,0);packer=max(0,par.get('bearing_packer_in',0));bottom=-jd-packer
    a.member('STUD',sp,[0,0,bottom-30],[0,0,bottom-.1],y=[1,0,0]);a.member('TRACK',tp,[-24,0,bottom],[24,0,bottom],y=[0,0,-1]);a.member('JOIST',jp,[0,0,-jd/2],[0,32,-jd/2],y=[1,0,0])
    if packer>.01:a.box('PACKER',[-3,-3,bottom],[6,6,packer],'A','A steel bearing packer for source shorter joist depth')
    stiff=channel(p,'ASSEMBLY-STIFF362',3.625,1.625,.0566,.5);a.member('STIFF',stiff,[-1.625,1,-jd+.1],[-1.625,1,-.1],y=[1,0,0],basis='A',description='S 362S162 bearing stiffener; A cut-to-fit length')
    jt=p[jp]['dimensions']['t'];clip_x=jt/2;stud_t=p[sp]['dimensions'].get('t',.0566)
    a.fastener('STIFF-S',[[jt/2,1+3.625/2-.0566/2,z] for z in (-jd+1.5,-jd/2,-1.5)],[-1,0,0],.19,.0566+jt,['JOIST','STIFF'],'S three No.10 where scheduled; A fit through joist web and stiffener flange',basis='A',screw=True)
    a.interfaces.append(dict(id='BEAR',kind='compression_bearing',connects=['JOIST','STIFF','TRACK','STUD']+(['PACKER'] if packer>.01 else []),basis='A',description='A direct steel bearing stack; no compressible floor finish under the bearing strip.'))
    n=par.get('screws',2);size=par.get('screw_size',10);t=.0566;zlo=-jd+1
    a.box('CLIP-J',[clip_x,0,zlo],[t,3,jd-2],'A','S 54 mil uplift clip where specified; A outline')
    a.box('CLIP-S',[stud_t/2,0,bottom-10],[t,3,10],'A','A lower clip leg fastened to in-line stud; top track bypassed')
    a.box('LINK',[min(clip_x,stud_t/2),0,bottom],[t+abs(clip_x-stud_t/2),3,max(.1,zlo-bottom)],'A','A bent clip transition')
    a.fastener('FJ',[[clip_x+t,1.5,zlo+1+j*(jd-4)/max(1,n-1)] for j in range(n)],[-1,0,0],screw_diameter(size),t+jt,['CLIP-J','JOIST'],f'{n} No.{size} uplift screws; source where scheduled',basis='S' if par.get('screws') else 'A',screw=True)
    a.fastener('FS',[[stud_t/2+t,1.5,bottom-8+j*4/max(1,n-1)] for j in range(n)],[-1,0,0],screw_diameter(size),t+stud_t,['CLIP-S','STUD'],f'{n} No.{size} receiving screws; A local fit',basis='A',screw=True)
    a.dim([0,0,bottom],[0,0,0],'A bearing stack height',basis='A');a.section_axis=1;a.section_at=1
    a.notes.append('S: joist section and span are unchanged. A: bent-clip shape, bearing packer and end fit. Source floor shear/diaphragm schedules remain separate from the local uplift attachment.')

def guard(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;pid=ctx.pid;d=effective(p,pid);h=par.get('height_in',48);bp=channel(p,'ASSEMBLY-BLOCK600',6,2,.0713,.5)
    a.member('POST',pid,[0,0,-12],[0,0,h],y=[1,0,0]);n=6
    post=p[pid];base=p[post['components'][0]['profile_id']] if post['family']=='built_up' else post;pt=base['dimensions']['t'];bt=.0713;t=.0566
    for side in (-1,1):
        block='BLOCK'+str(side);a.member(block,bp,[-24,side*(d/2+bt/2),-6],[24,side*(d/2+bt/2),-6],y=[0,side,0],basis='A',description='A paired blocking channel outside post flange')
        a.box('CLIP'+str(side),[-3,side*(d/2+bt)-(t if side<0 else 0),-9],[6,t,6],'A','A 54 mil blocking/post clip')
        pts=[[.4+(j%2)*.8,side*(d/2+bt+t),-8+(j//2)*2] for j in range(n)]
        a.fastener('F'+str(side),pts,[0,-side,0],.216,t+bt+pt,['POST',block,'CLIP'+str(side)],'S six No.12 each side for terrace guard; A parapet fit' if not par.get('continuous_parapet') else 'A six No.12 blocking attachment; source parapet stud is continuous',basis='A' if par.get('continuous_parapet') else 'S',screw=True)
    a.dim([0,0,-12],[0,0,0],'Backspan',basis='A' if par.get('continuous_parapet') else 'S',offset=24);a.dim([0,0,0],[0,0,h],'Roof to top',basis='A',offset=50);a.section_axis=2;a.section_at=-6
    a.notes.append('Source parapet studs continue through the roof line. The drawing shows local roof blocking, not a splice at the roof. Terrace guard is 48 in above roof / 42 in above the adopted paver finish.')

def roof_transfer(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;tp=ctx.pid;sp=ctx.select(('stud',),channel(p,'ASSEMBLY-STUD600',6,1.625,.0566,.5));cp=ctx.select(('truss_chord',),channel(p,'ASSEMBLY-CHORD600',6,1.625,.0713,.5));slip=par.get('vertical_slip',False);cd=effective(p,cp)
    td=p[tp]['dimensions'];face=td['d']/2;tt=td['t'];bt=.0713;top=24
    a.member('STUD',sp,[0,0,-30],[0,0,-.1],y=[1,0,0]);a.member('TRACK',tp,[-27,0,0],[45 if slip else 27,0,0],y=[0,0,-1])
    block=channel(p,'ASSEMBLY-BLOCK-TOP',6,2,bt,.5)
    a.member('BLOCK-TOP',block,[-27,face,top-3],[27,face,top-3],y=[0,-1,0],basis='A',description='A top rail of supplier blocking panel, 6 x 2 in / 68 mil')
    a.box('BLOCKING',[-27,face,-1.25],[54,.75,top+1.25],'A','A plywood shear-blocking infill between trusses; local 24 in height')
    a.box('ROOF',[-27,face-4,top],[54,6,.46875],'S','S 15/32 in roof sheathing; A local horizontal cut envelope',kind='panel')
    size=12 if par.get('step_line') else 10;dia=screw_diameter(size)
    a.fastener('BASE',[[x,face+.75,-.75] for x in (-24,0,24)],[0,-1,0],dia,.75+tt,['TRACK','BLOCKING'],f'S No.{size} at 24 in to double top track; A local edge fit',screw=True)
    a.fastener('PANEL',[[x,face+.75,top-2] for x in range(-24,25,6)],[0,-1,0],.19,.75+bt/2,['BLOCK-TOP','BLOCKING'],'A No.10 blocking-panel attachment at 6 in; supplier fit',basis='A',screw=True)
    a.fastener('EDGE',[[x,face-1,top+.46875] for x in range(-24,25,6)],[0,0,-1],.19,.46875+bt,['BLOCK-TOP','ROOF'],'S roof sheathing No.10 at 6 in edges; A local fit',screw=True)
    if slip:
        # Crossing truss bottom chord is independent of the between-truss blocking.
        chord=channel(p,'ASSEMBLY-SLIP-CHORD',cd,1.625,.0713,.5)
        a.member('TRUSS',chord,[36,-18,cd/2+2],[36,18,cd/2+2],y=[1,0,0],basis='A',description='A crossing truss bottom-chord envelope; supplier section and fit')
        cx=36+.0713/2;t=.0566
        a.box('SLIP',[cx,-2,.1],[t,4,12],'A','A vertical-slot guide; no truss gravity bearing on corridor wall')
        a.box('SLIP-FOOT',[cx,-2,.1],[3,4,t],'A','A guide bent foot seated on top-track web')
        a.fastener('SLIP-F',[[cx+t,0,cd/2+2]],[-1,0,0],.25,t+.0713,['SLIP','TRUSS'],'A guide screw in 1-1/2 in vertical slot; slip washer, no clamping of slot',basis='A',screw=True)
        slot=dict(direction=[0,0,1],length_in=1.5,basis='A');a.fasteners[-1]['slot']=slot;a.parts[-1]['slot']=slot
        a.fastener('FOOT',[[cx+1,y,.1+t] for y in (-1,1)],[0,0,-1],.19,t+.1+tt/2,['SLIP-FOOT','TRACK'],'A two No.10 guide-foot screws to top-track web',basis='A',screw=True)
        a.dim([36,-8,0],[36,-8,2],'A clear below crossing truss',basis='A')
        a.notes.append('S: corridor wall blocking transfers in-plane shear only. The truss crosses on vertical-slip clips and bears at the exterior walls. A slot travel and clip outline require supplier coordination.')
    a.dim([-24,0,0],[0,0,0],'S 24 in transfer spacing');a.section_axis=0;a.section_at=0
