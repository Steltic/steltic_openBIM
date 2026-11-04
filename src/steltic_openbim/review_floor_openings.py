"""Actual header/trimmer receivers and explicit fictional opening clips."""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .pilots.geometry import strips
from .review_receiver_geometry import point,vector,extract


def physical_axis(m):return [add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]


def section(m,profiles,origin,axes):
    a,b=physical_axis(m);u=unit(sub(b,a));y=m['local_y'];z=cross(u,y)
    return [[point(add(a,add(mul(y,q[0]),mul(z,q[1]))),origin,axes) for q in poly]
            for poly in strips(profiles[m['profile_id']],profiles)]


def frame(primary,origin):
    a,b=primary['axis'];x=unit(sub(max((a,b),key=lambda q:math.dist(q,origin)),origin));x[2]=0;x=unit(x)
    return x,cross([0,0,1],x),[0,0,1]


def bind(model):
    members={m['id']:m for m in model['members']};profiles={p['id']:p for p in model['profiles']}
    candidates=[m for m in model['members'] if m['kind'] in ('opening_trimmer','opening_header','joist','girder','beam')]
    for c in model['connections']:
        if c['detail_ref']['id']!='test_floor_opening' or c.get('parameters',{}).get('physical_floor_opening'):continue
        primary=members[c['member_ids'][0]];origin=c['point'];axes=frame(primary,origin);choices=[]
        for host in candidates:
            if host['id']==primary['id']:continue
            a,b=physical_axis(host);u=unit(sub(b,a));length=math.dist(a,b)
            if abs(dot(u,axes[0]))>.01:continue
            station=dot(sub(origin,a),u)
            if not -.01<=station<=length+.01:continue
            near=add(a,mul(u,station))
            if math.dist(near[:2],origin[:2])>.01 or abs(near[2]-origin[2])>16:continue
            choices.append((abs(near[2]-origin[2]),host['id'],host))
        if not choices:continue
        host=min(choices,key=lambda q:(q[0],q[1]))[2]
        face=max(q[0] for poly in section(host,profiles,origin,axes) for q in poly)
        end=min(range(2),key=lambda i:math.dist(primary['axis'][i],origin));old=list(primary['end_offsets'][end])
        primary['end_offsets'][end]=add(old,mul(axes[0],max(0,face+.125-dot(old,axes[0]))))
        c['member_ids']=[primary['id'],host['id']]
        c.setdefault('parameters',{})['physical_floor_opening']=dict(cutback_in=face+.125)
        model.setdefault('connection_endpoint_links',[]).append(dict(member_id=primary['id'],end='start' if end==0 else 'end',connection_id=c['id'],
            basis='A header/joist cut stops 1/8 in clear of the actual supporting flange; the located clip joins this cut end to the same physical support.'))
        model.setdefault('changes',[]).append(dict(kind='opening_clip_actual_receiver',connection_id=c['id'],support_id=host['id'],previous_end_offset=old,
            end_offset=primary['end_offsets'][end],basis='A accepted opening face fit; source profiles, joist reference axes and calculations unchanged.'))
    # Group only equivalent section orientation and datums; member IDs stay on
    # the occurrence but do not multiply otherwise identical drawing variants.
    for c in model['connections']:
        if not c.get('parameters',{}).get('physical_floor_opening'):continue
        axes=frame(members[c['member_ids'][0]],c['point'])
        from .review_cfs_wall_bindings import local_member,signature
        c['parameters']['physical_floor_opening']['receivers']=[signature(local_member(members[mid],c['point'],axes,28)) for mid in c['member_ids']]


def draw(ctx):
    a,p=ctx.a,ctx.p;primary,host=ctx.ms[:2];axes=frame(primary,ctx.c['point'])
    beam=extract(ctx,primary,'JOIST',axes,28);support=extract(ctx,host,'SUPPORT',axes,28)
    prim=section(primary,p,ctx.c['point'],axes);sec=section(host,p,ctx.c['point'],axes)
    bounds=lambda poly:[[min(q[i] for q in poly),max(q[i] for q in poly)] for i in range(3)]
    webs=[bounds(poly) for poly in prim if max(q[1] for q in poly)-min(q[1] for q in poly)<.5 and max(q[2] for q in poly)-min(q[2] for q in poly)>2]
    hostwebs=[bounds(poly) for poly in sec if max(q[0] for q in poly)-min(q[0] for q in poly)<.5 and max(q[2] for q in poly)-min(q[2] for q in poly)>2]
    if not webs or not hostwebs:raise ValueError('Opening clip needs actual vertical channel webs: '+ctx.c['id'])
    t=.125;face=max(bb[0][1] for bb in hostwebs);back=min(bb[0][0] for bb in hostwebs)
    start=min(q[0] for q in beam['member']['axis']);bolt_x=start+1
    for i,bb in enumerate(webs):
        centre=sum(bb[1])/2
        sign=1 if centre>=0 else -1
        if len(webs)==1:
            ymin=min(q[1] for poly in prim for q in poly);ymax=max(q[1] for poly in prim for q in poly)
            sign=1 if ymax-centre>=centre-ymin else -1
        web=bb[1][1 if sign>0 else 0];yy=web if sign>0 else web-t
        low=max(bb[2][0],max(q[2][0] for q in hostwebs))+.5
        high=min(bb[2][1],min(q[2][1] for q in hostwebs))-.5
        if high-low<3:raise ValueError('Opening clip lacks usable overlapping web depth: '+ctx.c['id'])
        height=min(8,high-low);lo=(low+high-height)/2;leg=bolt_x+2-face;label='CLIP'+str(i)
        a.box(label,[face,yy,lo],[leg,t,height],'A','A 1/8 in opening clip leg at the actual supported web')
        foot=yy if sign>0 else yy-3+t
        a.box(label+'R',[face,foot,lo],[t,3,height],'A','A 3 in return leg against actual supporting web')
        zs=[lo+1+r*(height-2)/3 for r in range(4)]
        pts=[[xx,web+sign*t,zz] for xx in (bolt_x,bolt_x+1) for zz in zs]
        a.fastener('J'+str(i),pts,[0,-sign,0],.25,t+bb[1][1]-bb[1][0],['JOIST',label],
            'A eight No.14 supported-web screws per ply; exact face fit and edge stations',basis='A',screw=True)
        pts=[[face+t,web+sign*d,zz] for d in (.75,1.75) for zz in zs]
        a.fastener('S'+str(i),pts,[-1,0,0],.25,t+face-back,['SUPPORT',label+'R'],
            'A eight No.14 receiving-web screws per clip through the actual receiving plies; grip includes their spacing',basis='A',screw=True)
        a.weld('BEND'+str(i),[face+t,yy,lo],[face+t,yy,lo+height],[label,label+'R'],kind='BEND',basis='A',description='A single formed angle; no site weld')
    a.section_axis=0;a.section_at=bolt_x;a.dim([face,0,lo],[face,0,lo+height],basis='A')
    a.notes.append('A accepted fictional opening assembly: actual header/trimmer/joist centroids, plies and roll retained. The supported end is clear of the receiving flange and each ply has its own formed clip. Trimmer bearing is shown separately. These added opening members and attachments have no new capacity verification.')
