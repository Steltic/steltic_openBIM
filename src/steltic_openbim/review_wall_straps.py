"""Source CFS wall strap groups fitted to their actual chord and track faces."""
import math,re
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_cfs_frame_straps import closest,face_intervals
from .review_cfs_wall_bindings import local_member
from .review_receiver_geometry import point
from .review_assemblies import hull
from .assembly_templates import findnum,screw_diameter


def gusset(key,width):
    return .1423 if key=='cfs2' else .1242 if width==8 else .1017


def apply(b):
    if b.key not in ('cfs2','cfs5'):return
    chords=[m for m in b.members if m['kind']=='chord']
    tracks=[m for m in b.members if m['kind'] in ('top_track','bottom_track')]
    for m in b.members:
        if m['kind']!='strap' or '-L' not in m['id']:continue
        conns=[c for c in b.connections if c['member_ids']==[m['id']] and c['detail_ref']['id']=='review_cfs_strap']
        if not conns:continue
        if len(conns)!=2:raise ValueError('Wall strap must have both source end groups: '+m['id'])
        direction=sub(*reversed(m['axis']));wall=unit([direction[0],direction[1],0]);nominal=cross(wall,[0,0,1]);hosts=[];normals=[];planes=[]
        prefix=m['id'].split('-X',1)[0]+'-'
        line_prefix=prefix.split('-B',1)[0]+'-B'
        for end,origin in enumerate(m['axis']):
            eligible=[(closest(h,origin)[0],h['id'],h) for h in chords if h['level']==m['level'] and h['id'].startswith(line_prefix)]
            if not eligible:raise ValueError('No source-bay chord for wall strap '+m['id'])
            distance,_,chord=min(eligible)
            if distance>12:raise ValueError('No actual chord at wall strap '+m['id'])
            _,q,*_=closest(chord,origin);normal=mul(nominal,1 if dot(sub(origin,q),nominal)>0 else -1)
            eligible=[(closest(h,origin)[0],h['id'],h) for h in tracks if h['level']==m['level'] and h['id'].startswith(prefix)
                      and abs(dot(unit(sub(*reversed(h['axis']))),wall))>.999]
            distance,_,track=min(eligible)
            if distance>12:raise ValueError('No actual track at wall strap '+m['id'])
            planes.extend(dot(h['axis'][0],normal)+face_intervals(h,b.profiles,normal)[0] for h in (chord,track))
            normals.append(normal);hosts.append((chord,track))
        if dot(*normals)<.99999:raise ValueError('Wall strap ends require an explicitly bent shape')
        normal=normals[0];plane=max(planes);dims=b.profiles[m['profile_id']]['dimensions'];g=gusset(b.key,dims['width']);t=dims['thickness']
        for end,q in enumerate(m['axis']):m['end_offsets'][end]=mul(normal,plane+g+t/2-dot(q,normal))
        travel=unit(sub(*reversed(m['axis'])))
        for end in (0,1):m['end_offsets'][end]=add(m['end_offsets'][end],mul(travel,3 if end==0 else -3))
        m['local_y']=unit(cross(normal,travel));axes=(cross(normal,[0,0,1]),normal,[0,0,1])
        for end,(chord,track) in enumerate(hosts):
            c=min(conns,key=lambda c:math.dist(c['point'],m['axis'][end]));origin=c['point']
            c['member_ids']=[m['id'],chord['id'],track['id']]
            c.setdefault('parameters',{})['physical_wall_strap']=dict(end=end,gusset_in=g,face_in=plane-dot(origin,normal),
                primary=local_member(m,origin,axes,32),chord=local_member(chord,origin,axes,32),track=local_member(track,origin,axes,32))
        m['physical_fit_basis']='S: source strap, gusset thickness and end screw counts. A: actual receiver faces, local gusset outline, face packing, screw stations and three-inch strap end clearance; no new capacity verification or crossing splice.'
        b.changes.append(dict(kind='located_wall_strap_ends',member_id=m['id'],receiver_ids=[[h['id'] for h in hs] for hs in hosts],
                              end_offsets=m['end_offsets'],local_y=m['local_y'],basis=m['physical_fit_basis']))


def pattern(ctx,width,t):
    par=ctx.params;txt=ctx.text;level=par.get('story',ctx.ms[0].get('level',1))
    story=re.search(r'story '+str(level)+r':\s*(.*?)(?=; story|\n|$)',txt,re.I);txt=story[1] if story else txt
    count=int(par.get('screws') or findnum(r'(\d+) No\.?\s*(?:10|12|14)',txt,10))
    size=int(par.get('screw_size') or findnum(r'\d+ No\.?\s*(\d+)',txt,14))
    if ctx.model['pilot']=='cfs2':return count,size,{3:2,4:3,5:3,8:5}[width],{3:(5,6),4:(7,8),5:(8,10),8:(17,19)}[width]
    return count,size,{3:2,4:3,5:3,6:4,8:5}[width],{3:(5,6),4:(7,8),5:(8,10),6:(13,13) if t>.06 else (9,12),8:(15,19)}[width]


def host_points(data,profiles,count):
    member=dict(data,end_offsets=[[0,0,0],[0,0,0]])
    _,_,u,length,s=closest(member,[0,0,0]);n=[0,1,0];across=cross(u,n)
    face,intervals=face_intervals(member,profiles,n);result=[]
    if count<len(intervals):raise ValueError('Source screw count cannot reach every actual exposed ply')
    into=1 if s<length/2 else -1
    for i in range(count):
        lo,hi,thickness=intervals[i%len(intervals)];station=s+into*(1+i//len(intervals))
        if not .3<station<length-.3:raise ValueError('Source screw group exceeds the actual receiving member')
        q=add(member['axis'][0],add(mul(u,station),add(mul(across,(lo+hi)/2),mul(n,face))))
        result.append((q,thickness))
    return result


def draw(ctx):
    a,p=ctx.a,ctx.p;data=ctx.params['physical_wall_strap'];names={'primary':'STRAP','chord':'CHORD','track':'TRACK'}
    for key,name in names.items():
        m=data[key];a.member(name,m['profile_id'],*m['axis'],y=m['local_y'],basis=m.get('basis','S'),description='Actual '+m['kind']+' '+m['profile_id'])
    primary=data['primary'];dims=p[primary['profile_id']]['dimensions'];width,t=dims['width'],dims['thickness'];g=data['gusset_in'];face=data['face_in']
    count,size,cols,counts=pattern(ctx,width,t);start=primary['axis'][data['end']];far=primary['axis'][1-data['end']]
    along=unit(sub(far,start));across=primary['local_y'];strap_points=[]
    for i in range(count):
        q=add(start,add(mul(along,3+i//cols),mul(across,i%cols-(cols-1)/2)));q[1]=face+g+t;strap_points.append(q)
    if 3+math.ceil(count/cols)>math.dist(start,far)-.5:raise ValueError('Strap source screw group exceeds the actual cut length')
    groups={name:host_points(data[key],p,n) for key,name,n in [('chord','CHORD',counts[0]),('track','TRACK',counts[1])]}
    all_points=strap_points+[q for rows in groups.values() for q,_ in rows]
    outline=hull([(q[0]+dx,q[2]+dz) for q in all_points for dx,dz in ((-.75,-.75),(-.75,.75),(.75,-.75),(.75,.75))])
    a.polygon('GUSSET',[[x,face,z] for x,z in outline],g,basis='S thickness; A outline',description=f'{g:g} in source gusset thickness; A outline joining actual chord and track')
    a.fastener('FS',strap_points,[0,-1,0],screw_diameter(size),g+t,['STRAP','GUSSET'],f'{count} source No.{size} strap-end screws; A stations/grip',screw=True)
    for name,rows in groups.items():
        hostface=rows[0][0][1];gap=face-hostface;joins=[name,'GUSSET']
        if gap>1e-6:
            tag=name+'-PACK';outline=hull([(q[0]+dx,q[2]+dz) for q,_ in rows for dx,dz in ((-.4,-.4),(-.4,.4),(.4,-.4),(.4,.4))])
            a.polygon(tag,[[x,hostface,z] for x,z in outline],gap,basis='A',description='A face packing at actual '+name.lower()+' flange; no empty screw grip');joins.append(tag)
        for i,(q,thickness) in enumerate(rows):
            q=[q[0],face+g,q[2]]
            a.fastener(name+'-S'+str(i),[q],[0,-1,0],.25,g+gap+thickness,joins,
                       f'{len(rows)} source No.14 gusset-to-{name.lower()} screws total; A ply distribution and grip',screw=True)
            a.parts[-1]['annotation_group']=name+'-S'
    a.section_axis=2;a.section_at=groups['TRACK'][0][0][2]
    a.front_depth_sign=-1
    last_row=(count-1)//cols*cols
    if last_row:a.dim(strap_points[0],strap_points[last_row],f'{last_row//cols} x 1 in adopted row pitch',basis='A')
    a.notes.append('Source strap/gusset thicknesses and both receiving screw counts are retained. Receivers are the actual story chord and track, including their roll and finite ends. A gusset outline, face packing and individual screw stations fit those members; capacity of the adopted local fit remains unverified. The two crossing straps remain separate continuous members, without a centre splice.')
