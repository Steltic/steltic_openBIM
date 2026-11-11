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
    if ctx.params.get('joist_bearing_setout_in'):
        return paired_seat(ctx,joist,host,seat,face)
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


def paired_seat(ctx,chord,support,elevation,web):
    """Reach the fitted joist without passing the hanger through a girder flange."""
    from shapely.geometry import Polygon,box
    from shapely.ops import unary_union
    a=ctx.a;t=.375;dims=ctx.p[support['profile_id']]['dimensions']
    centre=sum(p[2] for p in support['member']['axis'])/2
    lo=centre-dims['d']/2+dims['tf'];hi=centre+dims['d']/2-dims['tf']
    attach=min(max(elevation,lo+.0625),hi-2-t-.0625)
    if attach<lo+.0624:raise ValueError('Support clear web cannot receive the selected two-inch seat welds')
    back=max(web,ctx.params['bearing_flange_face_in']+.0625);front=back+t
    # The web pad and horizontal return remain in the clear web depth. The
    # outer hanger leg passes the flange tips and continues to the bearing.
    lip=unary_union([box(web,attach,web+t,attach+t+2),box(web,attach,front,attach+t),
                     box(back,min(elevation-8,attach),front,max(elevation+.25,attach+t))])
    riser=a.polygon('RISER',[[-4,y,z] for y,z in list(lip.exterior.coords)[:-1]],8,normal=[1,0,0],
                    basis='A',description='3/8-in folded hanger, 8 in wide, fitted around the girder flange to its clear web')
    riser['parameters']={'stock_thickness_in':t,'formed_width_in':8}
    cap=min(q[1] for q in chord['member']['axis'])
    end=max(front,cap)+8
    a.box('SEAT',[-4,front,elevation],[8,end-front,.25],'A','Independent joist bearing seat with an 8-in fitted landing')
    for j,x in enumerate((-3,3)):
        label='ST'+str(j)
        a.polygon(label,[[x,front,elevation],[x,end-1,elevation],[x,front,elevation-8]],.375,
                  normal=[1,0,0],basis='A',description='Adopted seat bracket stiffener on the hanger outer leg')
        a.weld('SEAT-W'+str(j),[x,front,elevation],[x,end-1,elevation],[label,'SEAT'],.25,basis='A')
        a.weld('ST-RISER'+str(j),[x,front,elevation-8],[x,front,elevation],[label,'RISER'],.25,basis='A')
        a.weld('RISER-W'+str(j),[x,web,attach+t],[x,web,attach+t+2],['RISER','SUPPORT'],.25,
               basis='S size/length; A hanger position' if ctx.model['pilot']=='hr33' else 'A',
               description='Girder-web seat uplift fillet')
    sole=elevation+.25
    bearing=unary_union([Polygon([(q[0],q[1]) for q in f]) for f in chord['faces']
                         if all(abs(q[2]-sole)<1e-5 for q in f)]).intersection(box(-4,front,4,end))
    if bearing.is_empty or bearing.area<=1e-4:raise ValueError('Fitted joist has no physical seat contact')
    regions=bearing.geoms if bearing.geom_type=='MultiPolygon' else [bearing]
    edges=[(math.dist(q,r),q,r) for shape in regions for q,r in
           zip(list(shape.exterior.coords),list(shape.exterior.coords)[1:]) if abs(q[0]-r[0])<1e-6]
    length,start,finish=max(edges)
    use=min(4,length);mid=(start[1]+finish[1])/2
    a.weld('CHORD-SEAT',[start[0],mid-use/2,sole],[start[0],mid+use/2,sole],['CHORD','SEAT'],.1875,
           basis='A',description='Bottom-chord fillet along the actual edge of bearing')
    a.interfaces.append(dict(id='BEARING',kind='supplier_seat',connects=['CHORD','SEAT','RISER','SUPPORT'],
        basis='A',description='Independent supplier joist and bearing seat at the original support line'))
    a.dim([0,front,sole],[0,end,sole],'Fitted seat projection',basis='A')
    a.section_axis=0;a.section_at=3
    a.notes.append('A: separate joist end and hanger fitted at the common support. Supplier seat geometry and capacity remain delegated.')


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
