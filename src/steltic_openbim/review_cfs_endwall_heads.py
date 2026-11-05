"""Saved CFS wind-post clips at their actual post and sloping roof flanges."""
import copy, math
from .pilots.model import add, sub, mul, unit, dot, cross
from .pilots.geometry import strips
from .review_receiver_geometry import extract, point
from .review_endwall_posts import lower_surface
from .review_cfs_frame_straps import face_intervals

AXES=([1,0,0],[0,1,0],[0,0,1])


def roof_at(roofs, profiles, x, y):
    options=[]
    for m in roofs:
        ends=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
        lo,hi=sorted(q[0] for q in ends)
        if lo-1e-7<=x<=hi+1e-7:options.append((lower_surface(m,profiles,[x,y]),m['id'],m))
    if not options:raise ValueError('Wind-post head has no actual roof flange at this station')
    return min(options,key=lambda v:v[:2])


def apply(b):
    if b.key not in ('cfs17','cfs19','cfs30'):return
    lookup={m['id']:m for m in b.members};rafters=[m for m in b.members if m['kind']=='rafter'
        and abs(m['axis'][0][1]-m['axis'][1][1])<.01 and abs(m['axis'][0][0]-m['axis'][1][0])>.01]
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for c in b.connections:
        if c['detail_ref']['id']!='review_endpost_top':continue
        post=lookup[c['member_ids'][0]];origin=c['point'];polygons=strips(b.profiles[post['profile_id']],b.profiles)
        u=unit(sub(*post['axis'][::-1]));y=post['local_y'];z=cross(u,y)
        corners=[add(origin,add(mul(y,q[0]),mul(z,q[1]))) for poly in polygons for q in poly]
        low,high=min(q[0] for q in corners),max(q[0] for q in corners)
        roofs=[m for m in rafters if abs(m['axis'][0][1]-origin[1])<.01
               and min(q[0] for q in m['axis'])<high and max(q[0] for q in m['axis'])>low]
        if not roofs:raise ValueError('No actual end-frame rafter above '+post['id'])
        top=min(roof_at(roofs,b.profiles,q[0],q[1])[0] for q in corners)-1.
        end=max(range(2),key=lambda i:post['axis'][i][2]);previous=list(post['end_offsets'][end])
        post['end_offsets'][end][2]=top-post['axis'][end][2]
        c['member_ids']=[post['id']]+[m['id'] for m in sorted(roofs,key=lambda m:m['axis'][0][0])]
        c.setdefault('parameters',{})['actual_cfs_endwall_head']=dict(post_top_relative=top-origin[2],
            leg_in=4.,plate_thickness_in=.25,clip_length_in=4.,slot_length_in=1.5,slot_width_in=.5625)
        b.endpoint_links.append(dict(member_id=post['id'],end='end',connection_id=c['id'],
            basis='The actual post head terminates below its located vertically slotted roof clips; the original analysis workpoint is retained.'))
        b.changes.append(dict(kind='source_cfs_endwall_head_fit',member_id=post['id'],connection_id=c['id'],
            previous_offset=previous,end_offset=copy.deepcopy(post['end_offsets'][end]),roof_member_ids=c['member_ids'][1:],
            basis='S L4x4x1/4 clip legs and two1/2in A325-N bolts per receiving leg; source vertically slotted restraint and outer-rafter-flange attachment. A4in clip length,1in head clearance,1.5in slots and actual sloped/folded plate geometry. No source capacity reassessment.'))
    b.note('ACTUAL-ENDWALL-HEADS','S: source L4x4x1/4 post-head clips, two1/2in bolts per leg and vertical movement, attached to the actual outer rafter flanges. A:4in clip lengths, exact slope folds,1in post-to-roof clearance and1.5in vertical slots. At an apex the foot follows both real roof slopes; no unsupported flat shoe or remote generic rafter is substituted. The separate kicker supplies the scheduled lateral restraint; capacities and movement clearances remain subject to engineering review.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params['actual_cfs_endwall_head'];post=ctx.ms[0];roofs=ctx.ms[1:];origin=ctx.c['point']
    extract(ctx,post,'POST',AXES,30)
    labels={m['id']:'ROOF'+str(i) for i,m in enumerate(roofs)}
    for m in roofs:extract(ctx,m,labels[m['id']],AXES,24)
    # These source wind posts are vertical, with their strong depth normal to
    # the end wall. Their two flanges, not an invented web plane, receive clips.
    u=unit(sub(*post['axis'][::-1]));y=post['local_y'];z=cross(u,y)
    polygons=[[[dot(add(mul(y,q[0]),mul(z,q[1])),v) for v in AXES] for q in poly]
              for poly in strips(p[post['profile_id']],p)]
    t=par['plate_thickness_in'];leg=par['leg_in'];half=par['clip_length_in']/2
    xs=sorted({-half,half,*[q[0]-origin[0] for m in roofs for q in m['axis'] if -half<q[0]-origin[0]<half]})
    def lower(x):return roof_at(roofs,p,origin[0]+x,origin[1])
    def up(m):
        v=unit(sub(*m['axis'][::-1]));n=unit(cross(v,m['local_y']));return n if n[2]>0 else mul(n,-1)
    def fold(x):
        height,_,m=lower(x);return height-origin[2]-t/up(m)[2]
    for side in (-1,1):
        face=max(side*q[1] for poly in polygons for q in poly)*side
        sheets=[poly for poly in polygons if min(abs(q[1]-face) for q in poly)<1e-6]
        sheet=min(max(q[1] for q in poly)-min(q[1] for q in poly) for poly in sheets
                  if max(q[1] for q in poly)-min(q[1] for q in poly)>1e-6)
        tag='CLIP'+str(side)
        verts=[[x,face,fold(x)] for x in xs]+[[x,face,fold(x)-leg] for x in reversed(xs)]
        a.polygon(tag,verts,t,normal=[0,side,0],basis='S thickness/legs; A outline',
                  description='Source1/4in slotted4in post-flange leg; A4in length and slope fit')
        bolts=[[x,face+side*t,par['post_top_relative']-1] for x in (-1,1)]
        a.fastener(tag+'-POST',bolts,[0,-side,0],.5,t+sheet,['POST',tag],
            'S two1/2in A325-N bolts; A2in gauge,1in post end distance and vertical slot set-out')
        a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=1.5,width_in=.5625,travel_in=1.,basis='A')
        for j,(lo,hi) in enumerate(zip(xs,xs[1:])):
            _,_,roof=lower((lo+hi)/2);n=up(roof);name=tag+'-FOOT'+str(j)
            yy0=face+side*t;yy1=face+side*leg
            vertices=[[x,yy,lower_surface(roof,p,[origin[0]+x,origin[1]+yy])-origin[2]]
                      for x,yy in ((lo,yy0),(hi,yy0),(hi,yy1),(lo,yy1))]
            a.polygon(name,vertices,t,normal=mul(n,-1),basis='S thickness/legs; A slope fit',
                description='Source4in roof leg against the actual outer-channel bottom flange')
            a.interfaces.append(dict(id=name+'-FOLD',kind='continuous_folded_clip',connects=[tag,name],basis='A',
                description='Continuous bent sheet at the actual roof pitch; bend radius omitted in design representation'))
            _,intervals=face_intervals(roof,p,mul(n,-1));u=unit(sub(*roof['axis'][::-1]));across=cross(u,mul(n,-1))
            footlo,foothi=sorted((yy0,yy1));choices=[]
            for aa,bb,thickness in intervals:
                # All selected roof worklines are in this actual end-wall plane.
                aa,bb=sorted((aa/across[1],bb/across[1]));left=max(aa+.5,footlo+.5);right=min(bb-.5,foothi-.5)
                if right>=left:choices.append((side*(left+right)/2,(left+right)/2,thickness))
            if not choices:raise ValueError('Wind-post clip misses the actual outer rafter flange')
            _,yy,rt=max(choices)
            for k,x in enumerate(v for v in (-1,1) if lo-1e-7<=v<=hi+1e-7):
                q=[x,yy,lower_surface(roof,p,[origin[0]+x,origin[1]+yy])-origin[2]]
                a.fastener(f'{name}-B{k}',[sub(q,mul(n,t))],n,.5,t+rt,[name,labels[roof['id']]],
                    'S one of the two1/2in roof-leg bolts at this clip; A actual flange stations')
        a.interfaces.append(dict(id=tag+'-MOVEMENT',kind='vertical_slotted_connection',connects=['POST',tag],
            travel_in=1.,basis='A',description='Source vertical-slip restraint; A1in travel; no roof gravity support by post'))
    a.dim([-half,0,par['post_top_relative']],[half,0,par['post_top_relative']],'A4in clip length',basis='A')
    a.section_axis=2;a.section_at=par['post_top_relative']-1
    a.notes.append('Actual post flanges and actual outer rafter bottom flanges receive the clips. Source plate thickness,4in legs and two1/2in bolts per leg are retained. A head cut, slot travel, slope folds and local bolt layout require fit/capacity review; the post does not bear against the roof.')
