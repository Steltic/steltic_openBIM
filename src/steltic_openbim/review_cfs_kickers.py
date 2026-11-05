"""Source angle kickers with explicit actual flange/web receiving hardware.

The angle section, source end counts and 30in rafter-brace length are retained.
Local folded clips, shims and source end-wall 45deg set-out are accepted A fits.
"""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import extract,point
from .review_cfs_frame_straps import face_intervals
from .review_endwall_posts import lower_surface
from .review_assemblies import hull

AXES=([1,0,0],[0,1,0],[0,0,1])


def roof_normal(m):
    n=unit(cross(unit(sub(*m['axis'][::-1])),m['local_y']))
    return n if n[2]>0 else mul(n,-1)


def apply(b):
    if b.key not in ('cfs17','cfs19','cfs30'):return
    lookup={m['id']:m for m in b.members};roofs=[m for m in b.members if m['kind']=='rafter'
        and abs(m['axis'][0][1]-m['axis'][1][1])<.01 and abs(m['axis'][0][0]-m['axis'][1][0])>.01]
    frame_ys=sorted({m['axis'][0][1] for m in roofs});b.endpoint_links=getattr(b,'endpoint_links',[])
    duplicates=[c for c in b.connections if c['detail_ref']['id']=='review_kicker'
                and not c.get('parameters',{}).get('post_top') and lookup[c['member_ids'][2]].get('full_length_nested')]
    duplicate_ids={c['member_ids'][0] for c in duplicates};duplicate_connections={c['id'] for c in duplicates}
    if duplicate_ids:
        b.members[:]=[m for m in b.members if m['id'] not in duplicate_ids]
        b.connections[:]=[c for c in b.connections if c['id'] not in duplicate_connections]
        b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in duplicate_ids]
        b.changes.append(dict(kind='nested_purlin_kicker_duplicates_removed',member_ids=sorted(duplicate_ids),
            basis='The base purlin kicker now connects both actual nested webs. The earlier second pair created solely by the0.2in nested-ply offset duplicated that same source restraint.'))
    purlins=[m for m in b.members if m['kind']=='purlin' and not m.get('full_length_nested')]
    for c in b.connections:
        if c['detail_ref']['id']!='review_kicker':continue
        angle,previous_low,high=[lookup[mid] for mid in c['member_ids'][:3]]
        if high['kind']!='purlin':continue
        old=copy.deepcopy(angle);par=c['parameters'];post=bool(par.get('post_top'))
        y0=min(frame_ys,key=lambda y:abs(y-angle['axis'][0][1]));xp=high['axis'][0][0]
        direction=1 if angle['axis'][1][1]>angle['axis'][0][1] else -1
        if post:direction=1 if y0==frame_ys[0] else -1
        probe=y0+direction*36
        spans=[m for m in purlins if abs(m['axis'][0][0]-xp)<.01
               and min(q[1] for q in m['axis'])<=probe<=max(q[1] for q in m['axis'])]
        if not spans:raise ValueError('No real purlin span lies on this side of the kicker support: '+angle['id']+str((y0,xp,direction,probe)))
        high=min(spans,key=lambda m:abs(sum(q[1] for q in m['axis'])/2-probe))
        # Full end-bay nested sections are real additional receivers, not an
        # unlocated cartoon of a second Z section in the detail.
        parent=high['id'].removesuffix('-NEST');hs=[lookup[mid] for mid in (parent,parent+'-NEST') if mid in lookup]
        if not hs:hs=[high]
        candidates=[]
        for sx in (1,-1):
            face=max(sx*h['axis'][0][0]+b.profiles[h['profile_id']]['dimensions']['t']/2 for h in hs)*sx
            for roof in roofs:
                lo,hi=sorted(q[0] for q in roof['axis'])
                if abs(roof['axis'][0][1]-y0)>.01:continue
                if lo+.01<=min(face,face+sx*5) and max(face,face+sx*5)<=hi-.01:
                    candidates.append((0 if sx==1 else 1,roof['id'],roof,sx,face))
        if not candidates:raise ValueError('Kicker has no real rafter flange for its folded foot: '+angle['id'])
        _,_,roof,sx,face=min(candidates,key=lambda v:v[:2]);n=roof_normal(roof)
        side=1 if angle['axis'][0][1]>=y0 else -1
        if post:side=1 if y0==frame_ys[0] else -1
        _,intervals=face_intervals(roof,b.profiles,mul(n,-1))
        across=cross(unit(sub(*roof['axis'][::-1])),mul(n,-1));choices=[]
        for aa,bb,rt in intervals:
            aa,bb=sorted((aa/across[1],bb/across[1]))
            if bb-aa>=2.5:choices.append((side*(aa+bb)/2,(aa+bb)/2,rt))
        if not choices:raise ValueError('No source outer flange can receive the kicker foot')
        _,offset,rt=max(choices);lowy=y0+offset
        footz=lower_surface(roof,b.profiles,[face,lowy])+rt/n[2]
        lowz=footz+1.5 if post else footz+.125/n[2]+1.5
        headz=high['axis'][0][2]
        count=int(par.get('upper_count',4));mean=1+(count-1)*.75
        for _ in range(30):
            rise=headz-lowz
            if post:run=rise
            else:
                if not 0<rise<29.5:raise ValueError('Saved30in kicker cannot reach these actual receivers')
                run=math.sqrt(900-rise*rise)
            u=unit([0,direction*run,rise]);v=cross([sx,0,0],u)
            headz=high['axis'][0][2]+mean*u[2]-v[2]
        rise=headz-lowz;run=rise if post else math.sqrt(900-rise*rise)
        heel=[face+sx*.125,lowy,lowz];head=[heel[0],lowy+direction*run,headz]
        u=unit(sub(head,heel));v=cross([sx,0,0],u)
        # The head must lie on the selected physical span, including its real
        # end-bay nested companion. Do not grow a receiver to make it fit.
        for h in hs:
            a,d=[add(q,o) for q,o in zip(h['axis'],h['end_offsets'])]
            low,highy=sorted((a[1],d[1]))
            stations=[head[1]-u[1]*(1+i*1.5)+v[1] for i in range(count)]
            if min(stations)<low+.25 or max(stations)>highy-.25:
                raise ValueError('Kicker source screw group lies beyond its actual purlin span: '+angle['id'])
        angle.update(axis=[heel,head],local_y=v,end_offsets=[[0,0,0],[0,0,0]],
                     source_kicker_length_in=None if post else 30.,source_kicker_angle_deg=45. if post else None)
        c['point']=heel;c['member_ids']=[angle['id'],roof['id']]+[h['id'] for h in hs]
        par['actual_cfs_kicker']=dict(face_side=sx,roof_flange_thickness=rt,foot_face_x=face,
            foot_centre_y=lowy,source_length_in=None if post else 30.,source_angle_deg=45. if post else None)
        b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id']!=angle['id']]
        for end in ('start','end'):b.endpoint_links.append(dict(member_id=angle['id'],end=end,connection_id=c['id'],
            basis='The complete located kicker assembly includes its actual rafter-flange foot and actual purlin-web end.'))
        b.changes.append(dict(kind='source_cfs_kicker_actual_receivers',member_id=angle['id'],previous_member=old,
            previous_lower_receiver=previous_low['id'],actual_lower_receiver=roof['id'],upper_receiver_ids=c['member_ids'][2:],
            basis='S angle section and source end screw counts;30in rafter-brace length or45deg end-wall top kicker with PL1/4x3in bent foot. A physical set-out,1/8in upper clips (and rafter-kicker lower clips), fitted web packers and exact foot outlines; no new stiffness/capacity verification.'))
    b.note('ACTUAL-KICKER-FIT','S: source angle sections, end screw counts,30in rafter braces and45deg end-wall top kickers with PL1/4x3in bent feet. A: exact cut/set-out,1/8in upper clips and ordinary rafter-kicker lower clips, with explicit packers at nested webs. End-wall top kickers restrain the actual rafter flange, as required by the source note. New local clip/packer capacities are not verified by the saved checks.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;data=par['actual_cfs_kicker'];angle,roof=ctx.ms[:2];hs=[m for m in ctx.ms[2:] if m['kind']=='purlin']
    plate=next((m for m in ctx.ms[2:] if m['kind']=='flange_cross_plate'),None)
    origin=ctx.c['point'];sx=data['face_side'];normal=[sx,0,0];u=unit(sub(*angle['axis'][::-1]));v=angle['local_y'];end=point(angle['axis'][1],origin,AXES)
    extract(ctx,angle,'ANGLE',AXES,50);extract(ctx,roof,'RAFTER',AXES,40)
    if plate:extract(ctx,plate,'CROSS-PLATE',AXES,30)
    for i,h in enumerate(hs):extract(ctx,h,'PURLIN'+str(i),AXES,45)
    at=p[angle['profile_id']]['dimensions']['t'];t=.125;n=roof_normal(roof)
    lower=int(par.get('lower_count',4));upper=int(par.get('upper_count',4));dia=.25 if par.get('stainless') else .216
    screw='1/4-14 stainless bi-metal' if par.get('stainless') else 'No.12'
    lowpts=[add(mul(u,1+i*1.5),v) for i in range(lower)]
    # The vertical web leg reaches the real source bottom-flange upper face.
    fx=data['foot_face_x'];fy=data['foot_centre_y'];rt=data['roof_flange_thickness']
    def top(x,y):return lower_surface(roof,p,[x,y])+rt/n[2]
    footverts=[[x-origin[0],y-origin[1],top(x,y)-origin[2]]
               for x,y in ((fx,fy-1),(fx+sx*5,fy-1),(fx+sx*5,fy+1),(fx,fy+1))]
    a.polygon('LOW-FOOT',footverts,t,normal=n,basis='A',description='A1/8in folded5x2in foot reaching the actual finite outer rafter bottom flange')
    lowz=top(fx,fy)+t/n[2]-origin[2]
    coords=[(-1,lowz),(1,lowz)]+[(q[1]+dy,q[2]+dz) for q in lowpts for dy,dz in ((-.5,-.5),(-.5,.5),(.5,-.5),(.5,.5))]
    a.polygon('LOW-LEG',[[-sx*t,y,z] for y,z in hull(coords)],t,normal=normal,basis='A',description='A continuous lower folded clip at actual angle-leg plane')
    a.fastener('LOW-ANGLE',[[q[0]-sx*t,q[1],q[2]] for q in lowpts],normal,dia,t+at,['LOW-LEG','ANGLE'],
        f'S {lower} {screw} source lower end screws; A local folded receiving clip',screw=True)
    footstations=[(2.5,-.5),(4.,-.5),(2.5,.5),(4.,.5)][:lower]
    if lower==2:footstations=[(2.5,0),(4.,0)]
    if lower==6:footstations=[(x,y) for x in (2.,3.,4.) for y in (-.5,.5)]
    cross_t=p[plate['profile_id']]['dimensions']['thickness'] if plate else 0
    footpts=[]
    for x,y in footstations:
        xx,yy=fx+sx*x,fy+y;q=[xx,yy,lower_surface(roof,p,[xx,yy])];footpts.append(sub(add(q,mul(n,-cross_t)),origin))
    a.fastener('LOW-RAFTER',footpts,n,dia,rt+t+cross_t,['RAFTER','LOW-FOOT']+(['CROSS-PLATE'] if plate else []),
        f'A {lower} {screw} folded-foot screws into the actual outer flange',basis='A',screw=True)
    a.interfaces.append(dict(id='LOW-FOLD',kind='continuous_folded_clip',connects=['LOW-LEG','LOW-FOOT'],basis='A',description='A continuous formed sheet; bend radius omitted'))
    if par.get('post_top'):
        # The two-screw detail belongs to the separate post flange brace at a
        # girt. The top kicker uses its own source 4/5/6 screws and a 1/4 x 3
        # plate bent to the 45-degree angle, against the angle's other leg.
        a.parts[:]=[r for r in a.parts if r['id'] not in ('LOW-FOOT','LOW-LEG','LOW-ANGLE','LOW-RAFTER')]
        a.fasteners[:]=[r for r in a.fasteners if r['id'] not in ('LOW-ANGLE','LOW-RAFTER')]
        a.interfaces[:]=[r for r in a.interfaces if r['id']!='LOW-FOLD']
        post_lower(ctx,angle,roof,u,v,normal,n,rt,lower,dia,screw)
    highpts=[add(sub(end,mul(u,1+i*1.5)),v) for i in range(upper)]
    coords=[(q[1]+dy,q[2]+dz) for q in highpts for dy,dz in ((-.5,-.5),(-.5,.5),(.5,-.5),(.5,.5))]
    poly=hull(coords)
    a.polygon('HIGH-CLIP',[[-sx*t,y,z] for y,z in poly],t,normal=normal,basis='A',description='A1/8in angle-to-actual-purlin web plate')
    # Close the explicitly declared gap between nested thin webs with real
    # packer solids. No bolt is claimed to engage a remote generic second Z.
    web_intervals=sorted((sx*(h['axis'][0][0]-origin[0])-p[h['profile_id']]['dimensions']['t']/2,
                          sx*(h['axis'][0][0]-origin[0])+p[h['profile_id']]['dimensions']['t']/2) for h in hs)
    shims=[]
    for i,((_,hi),(lo,_)) in enumerate(zip(web_intervals,web_intervals[1:])):
        gap=lo-hi
        if gap<=1e-6:continue
        tag='WEB-PACKER'+str(i);start=hi if sx>0 else -lo
        y0,y1=min(q[0] for q in poly),max(q[0] for q in poly);z0,z1=min(q[1] for q in poly),max(q[1] for q in poly)
        a.box(tag,[start,y0,z0],[gap,y1-y0,z1-z0],'A','A fitted steel packer between actual nested purlin webs');shims.append(tag)
    grip=at-web_intervals[0][0]
    a.fastener('HIGH',[[q[0]+sx*at,q[1],q[2]] for q in highpts],mul(normal,-1),dia,grip,
        ['ANGLE','HIGH-CLIP']+['PURLIN'+str(i) for i in range(len(hs))]+shims,
        f'S {upper} {screw} source upper end screws through the actual web/clip stack; A packer fit',screw=True)
    length=math.dist(*angle['axis']);a.dim([0,0,0],end,('S30in source angle length' if data['source_length_in'] else f'A{length:.2f}in length / S45deg'),basis='S' if data['source_length_in'] else 'A')
    a.front_axes=(1,2);a.section_axis=1;a.section_at=highpts[0][1]
    a.notes.append('Actual angle, outer rafter flange and purlin webs are shown. S angle section, end counts and length/angle requirements; '+('S quarter-inch bent foot; A upper web clip, web packing and local set-out.' if par.get('post_top') else 'A1/8in folded clips, web packing and receiving-foot screw group.')+' Saved member/connection checks do not certify these local fit additions.')


def post_lower(ctx,angle,roof,u,v,normal,n,rt,count,dia,screw):
    """Source quarter-inch, three-inch-wide foot bent to the actual kicker."""
    a,p=ctx.a,ctx.p;origin=ctx.c['point'];t=.25;at=p[angle['profile_id']]['dimensions']['t']
    def surface(x,y):return lower_surface(roof,p,[x,y])+rt/n[2]
    def fold(x):
        q=add(origin,add(mul(normal,x),mul(v,-t)))
        station=(surface(q[0],q[1])-q[2])/u[2]
        return add(sub(q,origin),mul(u,station))
    edge=[fold(x) for x in (0.,3.)];last=1+(count-1)*1.5+.75
    high=[add(mul(normal,x),add(mul(u,last),mul(v,-t))) for x in (3.,0.)]
    a.polygon('LOW-LEG',edge+high,t,normal=v,basis='S thickness and width; A length and fit',
              description='S PL1/4 x 3 in. inclined foot leg against the actual angle second leg')
    # Folded foot terminates inside the finite source flange. The outer edge
    # follows its actual roof pitch; no generic horizontal support is added.
    fy=ctx.params['actual_cfs_kicker']['foot_centre_y'];direction=1 if u[1]>0 else -1
    yy=fy+direction*1.35
    far=[[q[0],yy-origin[1],surface(origin[0]+q[0],yy)-origin[2]] for q in edge]
    a.polygon('LOW-FOOT',edge+[far[1],far[0]],t,normal=n,basis='S thickness and width; A length and fit',
              description='S PL1/4 x 3 in. source bent foot; A compound fold following actual rafter slope')
    points=[add(mul(u,1+i*1.5),add(mul(normal,1.),mul(v,-t))) for i in range(count)]
    a.fastener('LOW-ANGLE',points,v,dia,t+at,['LOW-LEG','ANGLE'],
               f'S {count} {screw} through the angle second leg and quarter-inch bent foot; A stations',screw=True)
    stations=[(x,y) for y in (.0,.8) for x in (.5,1.5,2.5)]
    if count==4:stations=[(x,y) for y in (.0,.8) for x in (.75,2.25)]
    points=[]
    for x,y in stations[:count]:
        xx=origin[0]+normal[0]*x;yy=fy+direction*y
        points.append(sub([xx,yy,lower_surface(roof,p,[xx,yy])],origin))
    a.fastener('LOW-RAFTER',points,n,dia,rt+t,['RAFTER','LOW-FOOT'],
               f'S {count} {screw} source bent-foot-to-rafter flange screws; A stations',screw=True)
    a.interfaces.append(dict(id='LOW-FOLD',kind='continuous_folded_clip',connects=['LOW-LEG','LOW-FOOT'],basis='S/A',
        description='S PL1/4 x 3 in. bent to the 45-degree top kicker; A compound roof-slope fit and sharp bend representation'))
    a.notes.append('Top kicker source schedule: PL1/4 x 3 in. bent foot and '+str(count)+' screws at each interface. The separate two-screw post flange brace at a girt is a different connection.')
