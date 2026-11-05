"""Actual end-wall girt clips for the three source portal examples."""
import math
from .pilots.model import add,sub,mul,unit,dot,cross
from .pilots.geometry import strips
from .review_receiver_geometry import extract

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key not in ('cfs17','cfs19','cfs30'):return
    members={m['id']:m for m in b.members}
    hosts=[m for m in b.members if m['kind'] in ('column','endwall_post','opening_jamb')]
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for c in b.connections:
        if c['detail_ref']['id']!='review_secondary':continue
        m=members[c['member_ids'][0]]
        if m['kind']!='girt' or abs(m['axis'][1][0]-m['axis'][0][0])<1:continue
        q=c['point'];end=min(range(2),key=lambda i:math.dist(m['axis'][i],q));side=1 if end==0 else -1
        options=[h for h in hosts if abs(h['axis'][0][0]-q[0])<.01 and abs(h['axis'][0][1]-q[1])<.01
                 and min(p[2] for p in h['axis'])-.01<=q[2]<=max(p[2] for p in h['axis'])+.01]
        # Upper triangular end-wall pieces may terminate at a sloping roof
        # member instead. They require their own roof receiver; this vertical
        # clip must not pretend an end-wall post extends above its real head.
        if not options:continue
        h=min(options,key=lambda r:r['id']);hu=unit(sub(*h['axis'][::-1]));hy=h['local_y'];hz=cross(hu,hy)
        polygons=[[[dot(add(mul(hy,p[0]),mul(hz,p[1])),v) for v in AXES] for p in poly]
                  for poly in strips(b.profiles[h['profile_id']],b.profiles)]
        candidates=[]
        for poly in polygons:
            x0,x1=min(p[0] for p in poly),max(p[0] for p in poly)
            y0,y1=min(p[1] for p in poly),max(p[1] for p in poly)
            # A broad web/flange face, never the unsupported tip of a lip.
            if .001<x1-x0<.5 and y1-y0>1.5:
                y=max(y0+.65,min(y1-.65,0.))
                if abs(y)>b.profiles[m['profile_id']]['dimensions']['d']/2-1:continue
                candidates.append((side*(x1 if side>0 else x0),-abs(y),x0,x1,y))
        if not candidates:raise ValueError('No actual broad receiving face for '+c['id'])
        _,_,x0,x1,y=max(candidates)
        face=x1 if side>0 else x0;clear=max(side*p[0] for poly in polygons for p in poly)+.25
        m['end_offsets'][end][0]=side*clear
        c['member_ids']=[m['id'],h['id']]
        c.setdefault('parameters',{})['actual_cfs_endwall_girt']=dict(side=side,host_face=face,host_thickness=x1-x0,clip_y=y)
        b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],
            basis='Actual girt cut clears the finite column/post/jamb section; the located clip joins its web to the real receiving face.'))
        b.changes.append(dict(kind='actual_endwall_girt_clip',member_id=m['id'],connection_id=c['id'],receiver_id=h['id'],
            end='start' if end==0 else 'end',end_offset=list(m['end_offsets'][end]),
            basis='S source girt and supporting section; A1/4in bent clip, two1/2in bolts per leg and local cut/fit. No attachment capacity inferred.'))


def draw(ctx):
    a,p=ctx.a,ctx.p;m,h=ctx.ms;par=ctx.params['actual_cfs_endwall_girt'];side=par['side'];t=.25
    extract(ctx,m,'GIRT',AXES,28);extract(ctx,h,'RECEIVER',AXES,24)
    d=p[m['profile_id']]['dimensions'];web=d['t'];z=web/2;face=par['host_face'];y=par['clip_y']
    end=min(range(2),key=lambda i:math.dist(m['axis'][i],ctx.c['point']));cut=m['end_offsets'][end][0]
    far=cut+side*5.;a.polygon('GIRT-LEG',[[x,yy,z] for x,yy in ((face,y-1),(far,y-1),(far,y+1),(face,y+1))],t,
        normal=[0,0,1],basis='A',description='A quarter-inch girt-web clip leg, fitted to the real cut end')
    a.polygon('HOST-LEG',[[face,yy,zz] for yy,zz in ((y-1,z-4),(y+1,z-4),(y+1,z),(y-1,z))],t,
        normal=[side,0,0],basis='A',description='A quarter-inch receiving leg against the actual broad column/post/jamb face')
    a.fastener('GIRT-BOLTS',[[cut+side*x,y,-web/2] for x in (1.5,3.5)],[0,0,1],.5,web+t,
        ['GIRT','GIRT-LEG'],'A two1/2in girt-web bolts; actual web contact',basis='A')
    a.fastener('HOST-BOLTS',[[face+side*t,y,z-zz] for zz in (1.,3.)],[-side,0,0],.5,t+par['host_thickness'],
        ['RECEIVER','HOST-LEG'],'A two1/2in receiving-face bolts; local attachment capacity not checked',basis='A')
    a.interfaces.append(dict(id='FOLD',kind='continuous_folded_clip',connects=['GIRT-LEG','HOST-LEG'],basis='A',
        description='A bent quarter-inch clip; bend radius omitted'))
    a.dim([cut,y,z],[far,y,z],'A5in girt clip projection',basis='A')
    a.front_axes=(0,1);a.section_axis=0;a.section_at=cut+side*1.5
    a.notes.append('The source girt and actual column, end-wall post or opening jamb are shown in their installed orientations. A local clip, bolt groups and end clearance are explicit fictional fit selections. Source girt member checks do not verify the added receiving attachment.')
