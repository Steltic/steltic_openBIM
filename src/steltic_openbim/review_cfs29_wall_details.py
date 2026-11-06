"""Actual track, bracing, collector and blocking connections for CFS29."""
import math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import extract,point,horizontal_frame,vector
from .review_cfs_occurrences import axis
from .review_cfs29_details import box,bend
from .review_cfs29_model import PT,TT,JT


def draw(ctx):
    purpose=ctx.params['purpose']
    if purpose not in ('stud_track','track_post','track_anchor','track_transfer','collector','strap_end','bridge_stud','bridge_post','blocking_end'):return False
    along=ctx.params['along'];u=[1,0,0] if along==0 else [0,1,0]
    if purpose in ('track_post','collector','blocking_end') and ctx.params['end']==1:u=mul(u,-1)
    axes=horizontal_frame(u);a=ctx.a
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),axes,24)
    if purpose=='stud_track':
        sg=1 if ctx.params['end']==0 else -1;outer=(6+2*TT+.0625)/2
        for side in (-1,1):
            tag='PACK'+str(side)
            box(a,tag,[.25,side*3,sg*.2],[1.25,side*(outer-TT),sg*1.2],'A1/32in flat packing at actual stud/track flange')
            a.fastener('SCREW'+str(side),[[.75,side*outer,sg*.65]],[0,-side,0],.19,outer-3+TT,['M0','M1',tag],'S oneNo10 each flange; A local gauge/packing',basis='S group / A fit',screw=True)
    elif purpose=='track_post':track_post(ctx,axes)
    elif purpose=='track_anchor':
        box(a,'SLAB',[-8,-8,-6],[8,8,0],'S6in existing slab / A local context','S thickness / A envelope');a.parts[-1]['kind']='concrete'
        box(a,'WASH',[-1,-1,TT],[1,1,TT+.25],'S2in square plate washer / A1/4in thickness')
        a.fastener('ANCHOR',[[0,0,-4]],[0,0,1],.5,4+TT+.25,['M0','SLAB','WASH'],'S1/2in adhesive track anchor at24in; A4in embedment and washer thickness',basis='S group / A fit')
    elif purpose in ('track_transfer','collector'):transfer(ctx,axes,purpose=='collector')
    elif purpose=='strap_end':strap(ctx,axes)
    elif purpose in ('bridge_stud','bridge_post'):bridge(ctx,axes,purpose=='bridge_post')
    elif purpose=='blocking_end':blocking(ctx,axes)
    a.front_axes=(0,2);a.section_axis=2;a.section_at=0
    if purpose=='strap_end':a.section_at=a.fasteners[0]['points'][5][2]
    return True


def track_post(ctx,axes):
    a=ctx.a;sg=-1 if ctx.params['top'] else 1;t=TT
    box(a,'FOOT',[-.125+t,-1.5,sg*TT/2],[1.75,1.5,sg*(TT/2+t)],'A54mil track-end formed clip')
    box(a,'POST-LEG',[-.125,-1.5,sg*(TT/2+t)],[-.125+t,1.5,sg*(TT/2+3)],'A clip leg on the actual finite post face')
    bend(a,'CLIP-BEND',['FOOT','POST-LEG'])
    a.fastener('TRACK',[[u,0,sg*(TT/2+t)] for u in (.5,1.25)],[0,0,-sg],.216,2*t,['FOOT','M0'],'A2No12 track-end retention',basis='A',screw=True)
    a.fastener('POST',[[t-.125,v,sg*1.5] for v in (-.75,.75)],[-1,0,0],.216,t+PT,['POST-LEG','M1'],'A2No12 actual post face',basis='A',screw=True)


def transfer(ctx,axes,collector):
    a=ctx.a;along=ctx.params['along'];host=ctx.ms[1]
    p=ctx.p[host['profile_id']]
    if p['family']=='built_up':p=ctx.p[p['components'][0]['profile_id']]
    ht=p['dimensions']['t']
    if collector and along==1:
        # Source collector is on the unbraced half, across the shared grid
        # post. A U-shaped plate passes around its actual6in face; a straight
        # plate would run through the column and falsely imply a load path.
        outline=[[-12,-4.25],[12,-4.25],[12,-.25],[3.2,-.25],[3.2,-3.2],[-3.2,-3.2],[-3.2,-.25],[-12,-.25]]
        a.polygon('BYPASS',[[u,v,-TT-.125] for u,v in outline],.125,normal=[0,0,1],basis='A',description='A1/8in U-shaped collector bypass clearing actual post and adjacent beam ends')
        box(a,'PACK',[-12,-2.25,-TT],[-4,-.25,0],'A54mil solid packing to actual single-C collector flange')
        for sign,label,joined,depth in ((1,'TRACK',['M0','BYPASS'],TT+.125),(-1,'COLLECTOR',['M1','BYPASS','PACK'],ht+TT+.125)):
            a.fastener(label,[[sign*u,v,-TT-.125] for u in (6,8,10) for v in (-.75,-1.75)],[0,0,1],.216,depth,joined,'S6No12 interface group / A bypass and exact set-out',basis='S group / A hardware',screw=True)
        a.notes.append('S end collector on source unbraced half. A U-shaped bypass carries it around the real grid post to the braced track; source6No12 groups retained at both receiving interfaces. Bypass bending/combined force capacity requires verification.')
        return
    if along==0:vs=(-1.25,1.25)
    else:
        sg=1 if dot(host['local_y'],axes[1])>0 else -1;vs=(sg*.75,sg*1.75)
    us=(6,8,10) if collector else (-5,5)
    a.fastener('TRANSFER',[[u,v,-TT] for u in us for v in vs],[0,0,1],.216,TT+ht,['M0','M1'],('S6No12 collector' if collector else 'S4No12 per24in,2per flange line')+'; A actual flange gauge',basis='S group / A gauge',screw=True)


def strap(ctx,axes):
    a=ctx.a;m,post=ctx.ms;end=ctx.params['end'];along=ctx.params['along'];face=ctx.params['face']
    n=[0,face,0] if along==0 else [face,0,0];normal=vector(n,axes)
    direction=unit(sub(axis(m)[1-end],axis(m)[end]));u=vector(direction,axes);v=vector(m['local_y'],axes);origin=ctx.c['point']
    positions=[add(mul(u,.6+.6*j),mul(v,.2 if j%2 else -.2)) for j in range(10)]
    # Connection point is the actual extended strap end. Measure the real
    # receiving face along the outward normal, independent of section labels.
    centre=point(post['axis'][0],origin,axes);h=3 if along==1 else (5+PT)/2
    receiver=dot(centre,normal)+h;strap_inner=-.0451/2;gap=strap_inner-receiver
    if gap<0:raise ValueError('Strap penetrates actual post')
    from .review_assemblies import hull
    flat=hull([(q[0]+du,q[2]+dz) for q in positions for du,dz in ((-.4,-.4),(-.4,.4),(.4,-.4),(.4,.4))])
    sign=normal[1]
    a.polygon('PACK',[[x,sign*receiver,z] for x,z in flat],gap,normal=normal,basis='A',description='A solid strap-end packing to actual boxed-post face')
    a.fastener('STRAP',positions,mul(normal,-1),.19,.0451/2+gap+PT,['M0','PACK','M1'],'S10No10 staggered,one screw per strap cross-section; A0.6in pitch and crossing-plane packing',basis='S count / A fit',screw=True)
    a.notes.append('S pretensioned ST50H43mil strap; continuous at crossing without centre splice. A3.3in end extensions,0.6in staggered pitch and end packing. The actual post face may be a web for the orthogonal strap direction; original flange attachment checks are not reassigned to this arrangement.')


def bridge(ctx,axes,post):
    a=ctx.a;face=ctx.params['face'];along=ctx.params['along'];sign=face if along==0 else -face
    height=(3 if along==1 else (5+PT)/2) if post else 3
    # origin lies at source stud flange for the intermediate connection, and
    # at strap centre for an end. Use actual member positions in both cases.
    centre=point(ctx.ms[1]['axis'][0],ctx.c['point'],axes);outer=centre[1]+sign*height
    mcentre=point(axis(ctx.ms[0])[0],ctx.c['point'],axes)[1];inner=mcentre-sign*TT/2;gap=sign*(inner-outer)
    into=1 if not post or ctx.params['end']==0 else -1
    pts=[[into*u,mcentre+sign*TT/2,0] for u in (.5,1.2)];joined=['M0','M1']
    if gap>1e-8:
        box(a,'PACK',[min(p[0] for p in pts)-.3,outer,-.6],[max(p[0] for p in pts)+.3,inner,.6],'A packing between source bridge strap and actual post face');joined.append('PACK')
    a.fastener('BRIDGE',pts,[0,-sign,0],.216,TT+max(gap,0)+(PT if post else TT),joined,'A2No12 bridge retention; source strap/blocking at48in',basis='A group / S restraint condition',screw=True)


def blocking(ctx,axes):
    a=ctx.a;t=TT
    box(a,'FOOT',[-.125+t,-1.5,-t/2-t],[2,1.5,-t/2],'A54mil blocking end clip')
    box(a,'WEB',[-.125,-1.5,-3],[-.125+t,1.5,-t/2-t],'A vertical clip leg on actual stud/post')
    bend(a,'CLIP-BEND',['FOOT','WEB'])
    a.fastener('BLOCK',[[u,0,-t/2-t] for u in (.75,1.5)],[0,0,1],.216,2*t,['FOOT','M0'],'A2No12 to blocking web',basis='A',screw=True)
    ht=PT if ctx.ms[1]['kind'] in ('chord','column') else TT
    a.fastener('HOST',[[t-.125,v,-1.5] for v in (-.75,.75)],[-1,0,0],.216,t+ht,['WEB','M1'],'A2No12 to actual stud/post web',basis='A',screw=True)
