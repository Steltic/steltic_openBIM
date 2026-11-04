"""Accepted fictional seat fit at the actual HR roof-member datums."""
import math
from .review_assemblies import effective,sub,unit,dot,cross
from .review_receiver_geometry import extract,horizontal_frame,nearest_beam,point,vector


def roof(ctx):
    a,p=ctx.a,ctx.p;chord=next(m for m in ctx.ms if m['kind']=='truss_chord')
    support=next((m for m in ctx.ms if m['kind'] in ('beam','girder','moment_beam','rafter')),None)
    if support is None:support=nearest_beam(ctx.model,ctx.c['point'],[m['id'] for m in ctx.ms])
    away=sub(max(chord['axis'],key=lambda q:math.dist(q,ctx.c['point'])),ctx.c['point'])
    y=unit([away[0],away[1],0]);axes=(cross(y,[0,0,1]),y,[0,0,1])
    host=extract(ctx,support,'SUPPORT',axes,24);joist=extract(ctx,chord,'CHORD',axes,30)
    cd=effective(p,chord['profile_id']);sd=effective(p,support['profile_id']);tw=p[support['profile_id']]['dimensions'].get('tw',.3)
    cz=joist['member']['axis'][0][2];sz=sum(q[2] for q in host['member']['axis'])/2
    seat=cz-cd/2-.25;face=tw/2
    a.box('SEAT',[-4,face,seat],[8,8,.25],'A','Fictional supplier bottom-chord bearing seat at the actual joist datum')
    low=min(seat-8,sz-sd/2+.5);high=max(seat+.25,sz+sd/2-.5)
    a.box('RISER',[-4,face,low],[8,.375,high-low],'A','A fitted vertical hanger plate to the actual girder web; supplier capacity review retained')
    for j,x in enumerate((-3,3)):
        a.polygon('ST'+str(j),[[x,face+.375,seat],[x,face+7,seat],[x,face+.375,seat-8]],.375,
                  normal=[1,0,0],basis='A',description='A seat bracket stiffener')
        a.weld('SEAT-W'+str(j),[x,face+.375,seat],[x,face+7,seat],['SEAT','ST'+str(j)],.25,basis='A')
        a.weld('RISER-W'+str(j),[x,face,sz-sd/2+1],[x,face,sz-sd/2+3],['RISER','SUPPORT'],.25,
               basis='S size/length; A fitted hanger location' if ctx.model['pilot']=='hr33' else 'A',
               description='Two 1/4 x 2 in seat uplift welds; A actual hanger fit, no new supplier capacity approval')
    a.weld('CHORD-SEAT',[-2,face+1,seat+.25],[2,face+1,seat+.25],['CHORD','SEAT'],.1875,basis='A')
    a.interfaces.append(dict(id='BEARING',kind='supplier_seat',connects=['CHORD','SEAT','RISER','SUPPORT'],basis='A',
        description='Accepted fictional bottom-chord hanger arrangement; actual source worklines retained. Supplier joist/seat capacity and fit remain delegated.'))
    a.dim([0,0,seat],[0,0,sz+sd/2],'Actual seat-to-support datum',basis='A');a.section_axis=0;a.section_at=3
    a.notes.append('A: a deep seat/hanger resolves the saved joist bottom-chord and girder elevations without moving the source worklines. This replaces the earlier disconnected typical seat. Supplier connection design remains explicitly unverified.')


def step(ctx):
    a,p=ctx.a,ctx.p;column=ctx.ms[0];axes=([1,0,0],[0,1,0],[0,0,1]);extract(ctx,column,'COLUMN',axes,42)
    cd=effective(p,column['profile_id']);cw=effective(p,column['profile_id'],'width')
    for j,beam in enumerate(ctx.ms[1:]):
        away=sub(max(beam['axis'],key=lambda q:math.dist(q,ctx.c['point'])),ctx.c['point']);u=unit([away[0],away[1],0]);v=cross([0,0,1],u)
        depth=effective(p,beam['profile_id']);width=effective(p,beam['profile_id'],'width');name='EDGE'+str(j)
        actual=extract(ctx,beam,name,axes,36);bottom=actual['member']['axis'][0][2]-depth/2
        strong=abs(dot(u,column['local_y']))<.5;face=(cd if strong else cw)/2;origin=[q*face for q in u];origin[2]=bottom-1
        seat='SEAT'+str(j);st='ST'+str(j)
        a.box(seat,[origin[i]-v[i]*(width/2+1) for i in range(3)],[10,width+2,1],'A','A fitted stiffened seat at actual roof level',x=u,y=v)
        tri=[[origin[i]+u[i]*t for i in range(3)] for t in (0,9,0)];tri[2][2]-=11
        a.polygon(st,[[q[i]-v[i]*.375 for i in range(3)] for q in tri],.75,normal=v,basis='A',description='A 3/4 in seat stiffener at actual beam azimuth')
        top=[origin[0],origin[1],bottom];a.weld('SEAT-W'+str(j),[top[i]-v[i]*width/2 for i in range(3)],[top[i]+v[i]*width/2 for i in range(3)],[name,seat],.25,basis='A')
        a.weld('ST-W'+str(j),[origin[0],origin[1],bottom-12],origin,['COLUMN',st],.375,basis='A')
    a.dim([0,0,0],[0,0,24],'Source 2 ft roof step');a.section_axis=2;a.section_at=-12
    a.notes.append('Source roof elevations and actual perpendicular edge-member directions retained. A seat/stiffener dimensions and welds are explicit coordination proposals; no new capacity approval.')
