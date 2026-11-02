"""Source transition pieces and explicit fictional erection fit at CJP splices."""
import re
from .assembly_scene import clip_part
from .assembly_templates import NUMBER,number,effective,findnum
from .pilots.geometry import strips


def transition(ctx,lower):
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text
    upper=p[pid];bottom=p[lower];d=effective(p,pid);ld=effective(p,lower)
    # Grouped source records can describe multiple section pairs. Select this pair.
    marker=pid+' on '+lower+':'
    if marker in txt:txt=txt.split(marker,1)[1].split('; also ',1)[0]
    elif upper['family']=='rhs' or bottom['family']=='rhs':
        if pid==lower:return
        if pid+' over '+lower not in txt and pid+' on '+lower not in txt:return
    division=re.search(r'division plate PL '+NUMBER+r'(?: x '+NUMBER+r' x '+NUMBER+r')? in',txt)
    part=next(q for q in a.parts if q['id']=='M1')
    if division:
        t=number(division[1]);sx=number(division[2]) if division[2] else ld;sy=number(division[3]) if division[3] else effective(p,lower,'width')
        clip_part(part,[0,0,-1],t)
        a.box('DIVISION',[-sx/2,-sy/2,-t],[sx,sy,t],'S','Source full-section division plate; original grade/through-thickness requirements retained')
        a.weld('DIV-LOW',[-ld/2,0,-t],[ld/2,0,-t],['M1','DIVISION'],kind='CJP',description='Source lower shaft walls to division plate')
        next(w for w in a.welds if w['id']=='SPLICE')['connects']=['DIVISION','M2']
        a.dim([-sx/2,0,-t],[-sx/2,0,0],'Division plate thickness',offset=40)
        if upper['family']=='i' and bottom['family']=='rhs':
            web=findnum(r'(?:internal web plate|web diaphragm) PL '+NUMBER,txt,0)
            height=findnum(NUMBER+r' in deep',txt,24)
            clear=ld-2*bottom['dimensions']['t']
            if web:
                a.box('WEB-DIAPH',[-clear/2,-web/2,-t-height],[clear,web,height],'A','Source internal web diaphragm thickness/depth; A fitted width to box walls')
                a.weld('W-WEB-D',[-clear/2,0,-t],[clear/2,0,-t],['WEB-DIAPH','DIVISION'],kind='CJP',description='Source web diaphragm CJP to division plate; full connected thickness')
                for side in (-1,1):a.weld('W-WEB-'+str(side),[side*clear/2,0,-t-height],[side*clear/2,0,-t],['WEB-DIAPH','M1'],.5,basis='A',description='Source attachment to box walls; A fillet size where unstated')
            ft=findnum(r'flange diaphragms PL '+NUMBER,txt,0)
            if ft:
                for j,side in enumerate((-1,1)):
                    x=side*(d-upper['dimensions']['tf'])/2
                    a.box('FLANGE-D'+str(j),[x-ft/2,-clear/2,-t-height],[ft,clear,height],'A','Source flange diaphragm thickness/depth; A fitted width')
                    a.weld('W-FD'+str(j),[x,-clear/2,-t],[x,clear/2,-t],['FLANGE-D'+str(j),'DIVISION'],kind='CJP',description='Source flange diaphragm CJP to division plate')
                    for edge in (-1,1):a.weld(f'W-FD{j}{edge}',[x,edge*clear/2,-t-height],[x,edge*clear/2,-t],['FLANGE-D'+str(j),'M1'],kind='CJP',description='Source diaphragm CJP to box wall')
            double=re.search(r'web doubler plates 2 PL '+NUMBER+r' x '+NUMBER+r' in, '+NUMBER+r' in long',txt)
            if double:
                dt,dw,dh=map(number,double.groups());tw=upper['dimensions']['tw']
                for j,side in enumerate((-1,1)):
                    y=tw/2 if side>0 else -tw/2-dt
                    a.box('DOUBLER'+str(j),[-dw/2,y,0],[dw,dt,dh],'S','Source upper web doubler plate')
                    a.weld('W-DB'+str(j),[-dw/2,y,0],[dw/2,y,0],['DOUBLER'+str(j),'DIVISION'],kind='CJP',description='Source doubler CJP to division plate')
        if 'fishplate' in txt:
            for j,(shape,za,zb) in enumerate(((lower,-30,0),(pid,.0625,30))):
                face=effective(p,shape)/2;end=ld/2+4
                a.box('FISH'+str(j),[face,-.1875,za],[max(4,end-face),.375,zb-za],'A','Source 3/8 in wall fishplate; A aligned free edge, source width/overlap requirements retained')
                a.weld('W-FISH'+str(j),[face,0,za],[face,0,zb],['M1' if j==0 else 'M2','FISH'+str(j)],.25,description='Source fishplate attachment; wall panel lap detailed separately')
        return
    if upper['family']!=bottom['family'] or upper['family'] not in ('i','rhs') or upper['dimensions']==bottom['dimensions']:return
    segment=re.search(r'transition segment \(?'+NUMBER+r'(?: in\)?|\)? in) high',txt)
    changes=[abs(effective(p,pid,which)-effective(p,lower,which))/2 for which in ('depth','width')]
    dims=upper['dimensions'];lo=bottom['dimensions'];changes.extend(abs(dims[k]-lo[k]) for k in ('t',) if k in dims)
    changes.extend(abs(dims[k]-lo[k]) for k in ('tf','tw') if k in dims)
    height=number(segment[1]) if segment else max(1,2.5*max(changes))
    if not segment:
        specific=re.search(r'tapered 1:2.5 over \(?'+NUMBER+r' in',txt)
        if specific:height=number(specific[1])
    clip_part(part,[0,0,-1],height)
    low=strips(bottom,p);high=strips(upper,p);faces=[]
    for below,above in zip(low,high):
        rings=[[[ -v,u,z] for u,v in poly] for poly,z in ((below,-height),(above,0))]
        faces += [rings[0][::-1],rings[1]]+[[rings[0][i],rings[0][(i+1)%len(below)],rings[1][(i+1)%len(below)],rings[1][i]] for i in range(len(below))]
    a.part('TRANSITION','Source section transition; A interpolated fit envelope, source taper/weld preparation requirements retained',faces,'A','member',transition_height_in=height,lower_profile=lower,upper_profile=pid)
    a.weld('TRANS-LOW',[-ld/2,0,-height],[ld/2,0,-height],['M1','TRANSITION'],kind='CJP' if segment else 'CONTINUOUS',description='Source shop-welded transition' if segment else 'Continuous shaft; A start of tapered fit envelope')
    next(w for w in a.welds if w['id']=='SPLICE')['connects']=['TRANSITION','M2']
    a.dim([-max(d,ld)/2,0,-height],[-max(d,ld)/2,0,0],'Transition height',basis='S' if segment else 'A',offset=40)
    diaphragm=findnum(r'kink diaphragms PL \(?'+NUMBER,txt,0)
    if segment and diaphragm:
        for j,(shape,z) in enumerate(((lower,-height),(pid,0))):
            sh=p[shape]['dimensions'];clear=sh['h']-2*sh['t'];cw=sh['b']-2*sh['t']
            a.box('KINK'+str(j),[-clear/2,-cw/2,z-diaphragm],[clear,cw,diaphragm],'A','Source kink diaphragm thickness; A fitted inside outline')
            a.weld('W-KINK'+str(j),[-clear/2,0,z],[clear/2,0,z],['KINK'+str(j),'TRANSITION'],kind='CJP',basis='A',description='Source internal diaphragm; A all-around attachment')


def erection(ctx,lower):
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text
    if 'erection plate' not in txt.lower():return
    hit=re.search(r'erection plates? with (\d+) x '+NUMBER+r'(?: in)? A325',txt,re.I)
    count,dia=(int(hit[1]),number(hit[2])) if hit else (4,.875)
    explicit='Source' if hit else 'A adopted';d=max(effective(p,pid),effective(p,lower));x=d/2+2;plate_t=.375
    lower_top=next(q for q in a.parts if q['id']=='M1')['bounds'][2][1]
    a.box('ERECT',[x-1.5,plate_t/2,lower_top-12],[3,plate_t,24-lower_top],'A','Temporary erection plate; A external lugs, set-out and size; remove before completing field CJP')
    for end,shape in enumerate((lower,pid)):
        side=1 if end else -1;n=count//2+(count%2 if end else 0);face=effective(p,shape)/2;tag='ERECT-LUG'+str(end)
        z0,z1=(2,12) if end else (lower_top-12,lower_top-2)
        a.box(tag,[face,-plate_t/2,z0],[x+1.5-face,plate_t,z1-z0],'A','A temporary exterior erection lug; no holes through the permanent shaft')
        a.weld('W-EL'+str(end),[face,0,z0],[face,0,z1],['M2' if end else 'M1',tag],.25,basis='A',description='A temporary erection lug attachment; remove/grind after field CJP')
        a.fastener('ERECT-B'+str(end),[[x,plate_t*1.5,4+i*3 if end else lower_top-4-i*3] for i in range(n)],[0,-1,0],dia,2*plate_t,['ERECT',tag],f'{explicit} {count} x {dia:g} in A325 erection bolts total; A set-out','A')
