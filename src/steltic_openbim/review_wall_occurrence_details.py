"""Located sill anchorage and joist clips using the actual receiving framing."""
import math,re
from .review_assemblies import NUMBER,number,effective


def cripple(ctx):
    from .review_receiver_geometry import extract,point
    from .pilots.model import unit,cross,add,sub
    a,p=ctx.a,ctx.p;stud=ctx.ms[0];edge=next(m for m in ctx.ms if m['id']==ctx.params['physical_stud_support']['member_id'])
    x=unit([*stud['local_y'][:2],0]);axes=(x,cross([0,0,1],x),[0,0,1]);origin=ctx.c['point']
    extract(ctx,stud,'STUD',axes,18);extract(ctx,edge,'OPENING',axes,24)
    far=max(stud['axis'],key=lambda q:math.dist(q,origin));direction=1 if far[2]>origin[2] else -1
    d=effective(p,stud['profile_id']);t=.0566;leg=1.5
    ez=sum(q[2]+o[2] for q,o in zip(edge['axis'],edge['end_offsets']))/2-origin[2]
    face=ez+direction*effective(p,edge['profile_id'])/2
    for sign in (-1,1):
        side='CLIP'+str(sign);yy=sign*d/2
        z0=min(0,direction*leg)
        a.box(side,[.1,yy if sign>0 else yy-t,z0],[leg,t,leg],'A','A 1-1/2 x 1-1/2 x 54 mil formed cripple-stud clip')
        a.box(side+'F',[.1,yy-leg if sign>0 else yy,face if direction>0 else face-t],[leg,leg,t],'A','A clip foot on actual header/sill flange')
        a.fastener('S'+str(sign),[[.75,yy+sign*t,direction*.65]],[0,-sign,0],.19,t+p[stud['profile_id']]['dimensions']['t'],['STUD',side],'A No.10 stud flange screw',basis='A',screw=True)
        a.fastener('F'+str(sign),[[.75,yy-sign*.75,face+direction*t]],[0,0,-direction],.19,t+.15,['OPENING',side+'F'],'A No.10 header/sill flange screw; verify actual grip',basis='A',screw=True)
        a.weld('BEND'+str(sign),[.1,yy,face],[.1+leg,yy,face],[side,side+'F'],kind='BEND',basis='A',description='A continuous formed clip')
    a.section_axis=2;a.section_at=direction*.65
    a.notes.append('Cripple stud at an actual opening header/sill. A formed clip proposal replaces the erroneous generic track. The source opening and stud geometry are unchanged; attachment capacity is not checked.')


def sill(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;selected=par['physical_sill'];text=ctx.text
    a.member('TRACK',selected['profile_id'],*selected['axis'],y=selected['local_y'])
    lo,hi=sorted(q[0] for q in selected['axis']);z=selected['axis'][0][2];depth=effective(p,selected['profile_id'])
    anchor=re.search(NUMBER+r' in\.?\s*(?:post-installed adhesive |F1554[-\w ]*|cast-in )?anchors?(?: bolts?)? at '+NUMBER+r' in\.?\s*o\.?c',text,re.I)
    dia,pitch=map(number,anchor.groups()) if anchor else (.625,24)
    slab=par.get('slab_thickness',12);embed=min(slab-1,7);margin=min(6,(hi-lo)/4)
    stations=[lo+margin+i*pitch for i in range(int((hi-lo-2*margin)/pitch)+1)]
    if not stations:stations=[(lo+hi)/2]
    a.box('CONCRETE',[lo-6,-depth/2-6,z-slab],[hi-lo+12,depth+12,slab],'A','Foundation/slab interface context; reinforcement delegated',kind='concrete')
    a.fastener('ANCHORS',[[x,0,z-embed] for x in stations],[0,0,1],dia,embed+.15,['TRACK','CONCRETE'],
        f'{len(stations)} x {dia:g} in anchor rods at {pitch:g} in source pitch; A end margin and embedment',basis='S diameter/pitch; A end margin/embedment' if anchor else 'A')
    washer=re.search(NUMBER+r' in\.? square plate washers',text,re.I)
    if washer:
        width=number(washer[1])
        for j,x in enumerate(stations):a.box('WASHER'+str(j),[x-width/2,-width/2,z+.15],[width,width,.25],'S plan size; A thickness','Source anchor plate washer; A 1/4 in thickness')
    a.section_axis=0;a.section_at=stations[0];a.dim([lo,0,z],[hi,0,z],basis='S')
    a.notes.append('Anchorage covers the complete actual track span. Stud-to-track screws are separate located occurrences; no arbitrary stud is introduced at this anchor station. A embedment requires the source foundation review.')


def joist(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;data=par['physical_joist_end'];j=data['joist'];s=data['support']
    a.member('JOIST',j['profile_id'],*j['axis'],y=j['local_y'])
    a.member('SUPPORT',s['profile_id'],*s['axis'],y=s['local_y'])
    d=effective(p,j['profile_id']);sd=effective(p,s['profile_id']);z=sum(q[2] for q in j['axis'])/2;sz=sum(q[2] for q in s['axis'])/2
    # Selected L3x3 clip is shown at the actual beam web and joist end. The
    # source worklines are retained; cutbacks and hole stations are A fit data.
    t=.0566;leg=3.;height=min(6,d-1,sd-1);lo=max(z-d/2,sz-sd/2)+.5
    x=sum(q[0] for q in s['axis'])/2;web=p[j['profile_id']]['dimensions'].get('t',.0713)
    a.box('CLIP-J',[x+.125,web/2,lo],[leg,t,height],'S 3x3x54 mil legs; A height/fit','Joist-web leg of source angle')
    a.box('CLIP-S',[x+.125,web/2+t,lo],[t,leg-t,height],'S 3x3x54 mil legs; A height/fit','Supporting-web leg of source angle')
    count=par.get('screws',4);size=par.get('screw_size',10);diameter={10:.19,12:.216,14:.25}.get(size,.19)
    rows=math.ceil(count/2);pts=[[x+.75+(i%2)*1.5,web/2+t,lo+.75+(i//2)*(height-1.5)/max(1,rows-1)] for i in range(count)]
    a.fastener('JOIST-SCREWS',pts,[0,-1,0],diameter,t+web,['JOIST','CLIP-J'],f'{count} No.{size} source joist web screws; A stations',screw=True)
    pts=[[x+.125+t,web/2+.75+(i%2)*1.5,lo+.75+(i//2)*(height-1.5)/max(1,rows-1)] for i in range(count)]
    a.fastener('SUPPORT-SCREWS',pts,[-1,0,0],diameter,t+.125,['SUPPORT','CLIP-S'],f'{count} No.{size} source support web screws; A stations/grip',screw=True)
    a.section_at=x+1.5;a.dim([x,0,lo],[x,0,lo+height],basis='A')
    a.notes.append('Actual joist and receiving member profiles, axes and orientation are shown. Source angle legs, thickness and screws remain attached; local angle height, end cutback and hole layout are A fit requiring engineering review.')
