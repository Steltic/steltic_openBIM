"""Located eave/valley strut ends in the three saved CFS portal examples.

Source strut sections remain unchanged. End clips, through-web bolts, packers
and cut clearances are accepted fictional detailing, not new capacity checks.
"""
import math
from .pilots.geometry import strips
from .pilots.model import add,sub,mul,unit,cross
from .review_receiver_geometry import extract

AXES=([1,0,0],[0,1,0],[0,0,1])


def section_points(member,profiles):
    u=unit(sub(*member['axis'][::-1]));y=member['local_y'];z=cross(u,y)
    return [[add(mul(y,p[0]),mul(z,p[1])) for p in poly] for poly in strips(profiles[member['profile_id']],profiles)]


def apply(b):
    if b.key not in ('cfs17','cfs19','cfs30'):return
    members={m['id']:m for m in b.members}
    roofs=[m for m in b.members if m['kind']=='rafter' and abs(m['axis'][0][1]-m['axis'][1][1])<.01]
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for c in b.connections:
        if c['detail_ref']['id']!='review_secondary':continue
        m=members[c['member_ids'][0]]
        if m['kind']!='eave_strut':continue
        end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']));into=1 if end==0 else -1
        x,y,z=c['point'];options=[]
        for h in roofs:
            if abs(h['axis'][0][1]-y)>.01:continue
            lo,hi=sorted(q[0] for q in h['axis'])
            for sx in (1,-1):
                if lo+.01<=min(x+sx*1.5,x+sx*5) and max(x+sx*1.5,x+sx*5)<=hi-.01:
                    options.append((0 if sx==1 else 1,h['id'],h,sx))
        if not options:raise ValueError('No actual rafter web for strut end '+c['id'])
        _,_,host,sx=min(options,key=lambda r:r[:2]);polys=section_points(host,b.profiles)
        webs=[]
        for poly in polys:
            yy=sorted(p[1] for p in poly);zz=sorted(p[2] for p in poly)
            if .001<yy[-1]-yy[0]<.5 and zz[-1]-zz[0]>4:
                face=yy[-1] if into>0 else yy[0]
                webs.append((into*face,face,yy[-1]-yy[0]))
        if not webs:raise ValueError('Actual rafter has no receiving web '+host['id'])
        _,face,thickness=max(webs)
        clear=max(into*p[1] for poly in polys for p in poly)+.25
        m['end_offsets'][end][1]=into*clear
        c['member_ids']=[m['id'],host['id']]
        c.setdefault('parameters',{})['actual_cfs_strut_end']=dict(into=into,clip_side=sx,
            host_face_y=face,host_web_thickness=thickness,end=end)
        b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],
            basis='The strut cut clears the real frame envelope; a located folded clip connects its actual web stack to the real outer rafter web.'))
        b.changes.append(dict(kind='actual_cfs_strut_end',member_id=m['id'],receiver_id=host['id'],
            connection_id=c['id'],end=end,end_offset=list(m['end_offsets'][end]),
            basis='S source eave/valley strut section. A1/4in folded clip, two1/2in bolts per leg, web-gap packers and1/4in frame clearance; attachment capacity unverified.'))
    b.note('ACTUAL-STRUT-ENDS','S: saved eave and valley strut sections. A: strut ends clear the actual frame by1/4in and use located1/4in bent clips with two1/2in bolts per leg. Through bolts and explicit packers engage both webs of built-up struts. Exact cutback, clip and receiving-web capacity remain accepted fictional fit decisions.')


def draw(ctx):
    a,p=ctx.a,ctx.p;m,h=ctx.ms;par=ctx.params['actual_cfs_strut_end'];into=par['into'];sx=par['clip_side'];t=.25
    extract(ctx,m,'STRUT',AXES,32);extract(ctx,h,'RAFTER',AXES,28)
    webs=[]
    for poly in section_points(m,p):
        xx=sorted(q[0] for q in poly);zz=sorted(q[2] for q in poly)
        if .001<xx[-1]-xx[0]<.5 and zz[-1]-zz[0]>4:webs.append((xx[0],xx[-1]))
    webs=sorted(webs)
    if not webs:raise ValueError('Strut detail has no actual broad web')
    face=webs[-1][1] if sx>0 else webs[0][0]
    cut=m['end_offsets'][par['end']][1];hy=par['host_face_y'];far=cut+into*6
    a.polygon('STRUT-LEG',[[face,yy,zz] for yy,zz in ((hy,-1.5),(far,-1.5),(far,1.5),(hy,1.5))],t,
        normal=[sx,0,0],basis='A',description='A quarter-inch clip web leg reaches the actual strut cut')
    a.polygon('FRAME-LEG',[[xx,hy,zz] for xx,zz in ((face+sx*t,-1.5),(face+sx*5,-1.5),(face+sx*5,1.5),(face+sx*t,1.5))],t,
        normal=[0,into,0],basis='A',description='A folded receiving leg against the actual outer rafter web')
    packers=[]
    for i,((_,left),(right,_)) in enumerate(zip(webs,webs[1:])):
        if right-left<1e-7:continue
        label='WEB-PACK'+str(i);packers.append(label)
        a.box(label,[left,min(cut,far),-1.5],[right-left,6,3],basis='A',description='A solid fit pack between actual strut webs')
    a.fastener('STRUT-BOLTS',[[face+sx*t,cut+into*y,0] for y in (1.5,4.5)],[-sx,0,0],.5,
        t+webs[-1][1]-webs[0][0],['STRUT','STRUT-LEG']+packers,'A two1/2in through bolts across every actual strut web and gap pack',basis='A')
    a.fastener('FRAME-BOLTS',[[face+sx*x,hy+into*t,0] for x in (1.5,3.5)],[0,-into,0],.5,
        t+par['host_web_thickness'],['RAFTER','FRAME-LEG'],'A two1/2in bolts at actual outer rafter web',basis='A')
    a.interfaces.append(dict(id='FOLD',kind='continuous_folded_clip',connects=['STRUT-LEG','FRAME-LEG'],basis='A',
        description='Continuous bent clip; bend radius omitted from design representation'))
    a.dim([face,cut,0],[face,far,0],'A6in clip beyond cut',basis='A')
    a.front_axes=(0,1);a.section_axis=1;a.section_at=cut+into*1.5
    a.notes.append('Source strut and real frame sections are shown in installed positions. The located cutback, folded clip, bolts and web packers are A accepted example details. Source strut design does not verify this receiving attachment.')
