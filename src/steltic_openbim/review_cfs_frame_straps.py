"""Source strap ends attached to their actual portal members, without a track.

The source schedules select the straps and their end screws. The spanning
collector plate, its per-ply attachments and the separation of crossing straps
are explicit fictional fit proposals, not additional checked connection designs.
"""
import math
from .pilots.model import add,sub,mul,unit,dot,cross
from .pilots.geometry import strips
from .review_receiver_geometry import extract,point,vector
from .assembly_templates import screw_diameter
from .review_assemblies import hull


def closest(member,p):
    aa,bb=[add(q,o) for q,o in zip(member['axis'],member['end_offsets'])]
    u=unit(sub(bb,aa));length=math.dist(aa,bb);s=max(0,min(length,dot(sub(p,aa),u)))
    q=add(aa,mul(u,s))
    return math.dist(p,q),q,u,length,s


def face_intervals(member,profiles,n):
    u=unit(sub(*reversed(member['axis'])));y=member['local_y'];z=cross(u,y);across=cross(u,n)
    polys=[[[dot(add(mul(y,a),mul(z,b)),across),dot(add(mul(y,a),mul(z,b)),n)] for a,b in poly]
           for poly in strips(profiles[member['profile_id']],profiles)]
    face=max(q[1] for poly in polys for q in poly);result=[]
    for poly in polys:
        for a,b in zip(poly,poly[1:]+poly[:1]):
            if abs(a[1]-face)<1e-6 and abs(b[1]-face)<1e-6 and abs(a[0]-b[0])>.2:
                lo,hi=sorted((a[0],b[0]));thickness=face-min(q[1] for q in poly)
                result.append((lo,hi,thickness))
    if not result:raise ValueError('No actual flat receiving flange at the strap attachment')
    return face,result


def apply(builder):
    if builder.key not in ('cfs10','cfs18','cfs17','cfs19','cfs26','cfs27','cfs28','cfs30'):return
    members={m['id']:m for m in builder.members}
    for m in builder.members:
        if m['kind']!='strap':continue
        wall_panel=builder.key in ('cfs10','cfs18') and '-X-' in m['id']
        if wall_panel:kinds=('chord',)
        elif m['id'].startswith('ROOF-X-'):kinds=('rafter',)
        elif m['id'].startswith(('SIDE-X-','WALL-X-')):kinds=('column',)
        elif m['id'].startswith('END-X-'):kinds=('column','endwall_post','opening_jamb')
        elif m['id'].startswith('VALLEY-X-'):kinds=('prop',)
        elif m['id'].startswith('VEST-X-'):kinds=('stud',)
        else:continue
        conns=[c for c in builder.connections if c['member_ids']==[m['id']] and c['detail_ref']['id']=='review_cfs_strap']
        if len(conns)!=2:raise ValueError('Expected both actual strap end connections: '+m['id'])
        thickness=builder.profiles[m['profile_id']]['dimensions']['thickness']
        packing=thickness+.0625 if m['id'].endswith('True') or builder.key in ('cfs10','cfs18','cfs27','cfs28') and m['id'].endswith('-1') else 0.
        normals=[];receivers=[]
        for end,p in enumerate(m['axis']):
            roof_normal=None
            if kinds==('rafter',):
                dv=sub(*reversed(m['axis']));roof_normal=unit([-dv[2],0,dv[0]])
            choices=[(closest(r,p)[0],r['id'],r) for r in builder.members if r['kind'] in kinds
                     and (not wall_panel or r['id'].startswith(m['id'].split('-X-',1)[0]+'-CH-'))
                     and (roof_normal is None or abs(dot(cross(unit(sub(*reversed(r['axis']))),r['local_y']),roof_normal))>.99999)]
            distance,_,host=min(choices)
            if distance>(16 if m['id'].startswith('VALLEY-X-') else 10):raise ValueError('No physical portal receiver at '+m['id'])
            _,q,u,_,_=closest(host,p)
            if wall_panel:
                direction=sub(*reversed(m['axis']));wall=unit([direction[0],direction[1],0]);normal=cross(wall,[0,0,1])
                n=mul(normal,1 if dot(sub(p,q),normal)>0 else -1)
            elif kinds==('rafter',):
                n=cross(u,host['local_y'])
                if n[2]<0:n=mul(n,-1)
            elif m['id'].startswith(('END-X-','VEST-X-')):n=[0,-1 if p[1]<=0 else 1,0]
            else:n=[-1 if p[0]<=builder.cfg.get('span_ft',1)*6 else 1,0,0]
            face,_=face_intervals(host,builder.profiles,n)
            target=add(p,mul(n,dot(sub(q,p),n)+face+.1875+packing+thickness/2))
            m['end_offsets'][end]=sub(target,p);normals.append(n);receivers.append(host['id'])
            c=min(conns,key=lambda c:math.dist(c['point'],p));c['member_ids']=[m['id'],host['id']]
            c['parameters'].update(physical_strap_end=True,receiver_member_id=host['id'],strap_end=end,
                                   normal=n,gusset_in=.1875,packing_in=packing)
            c['parameters'].pop('host_profile',None)
        if dot(*normals)<.99999:raise ValueError('Nonplanar strap needs an explicit bend selection: '+m['id'])
        ends=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
        travel=unit(sub(*reversed(ends)))
        for end in (0,1):m['end_offsets'][end]=add(m['end_offsets'][end],mul(travel,3 if end==0 else -3))
        ends=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
        m['local_y']=unit(cross(normals[0],unit(sub(*reversed(ends)))))
        m['physical_fit_basis']='A: flat strap on actual receiving flange; 3 in end clearance from workpoint; 3/16 in collector plate; paired crossing straps remain continuous in separate planes with 1/16 in clear gap; packing and per-ply plate attachments require engineering verification'
        builder.changes.append(dict(kind='actual_frame_strap_receivers',member_id=m['id'],receiver_ids=receivers,
            end_offsets=m['end_offsets'],local_y=m['local_y'],packing_in=packing,basis=m['physical_fit_basis']))


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;strap=ctx.ms[0]
    host=next(m for m in ctx.ms if m['id']==par['receiver_member_id']);n=par['normal']
    _,centre,u,length,station=closest(host,ctx.c['point']);axes=(u,n,cross(u,n))
    extract(ctx,host,'RECEIVER',axes,extent=42);extract(ctx,strap,'STRAP',axes,extent=42)
    face,intervals=face_intervals(host,p,n);host_c=point(centre,ctx.c['point'],axes)
    face+=host_c[1];g=par['gusset_in'];pack=par['packing_in'];t=p[strap['profile_id']]['dimensions']['thickness']
    ends=[add(q,o) for q,o in zip(strap['axis'],strap['end_offsets'])]
    end=par['strap_end'];start=point(ends[end],ctx.c['point'],axes)
    along=vector(unit(sub(ends[1-end],ends[end])),axes);across=vector(strap['local_y'],axes)
    count=par['screws'];size=par['screw_size'];columns=2
    # Both source CFS19 strap rupture checks specify two holes across the width.
    # The one-inch row pitch and starting offset are adopted fit dimensions.
    screw_points=[add(start,add(mul(along,3+i//columns),mul(across,(i%columns-.5)))) for i in range(count)]
    for q in screw_points:q[1]=face+g+pack+t
    host_points=[]
    # Each actual channel ply receives two screws on its exposed flange.
    row_stations=(2,5) if station<6 else (-5,-2) if station>length-6 else (-3,3)
    for lo,hi,ht in intervals:
        for x in row_stations:host_points.append(([host_c[0]+x,face+g,host_c[2]+(lo+hi)/2],ht))
    outline=hull([(q[0]+dx,q[2]+dz) for q in screw_points+[q for q,_ in host_points] for dx,dz in ((-1,-1),(-1,1),(1,-1),(1,1))])
    a.polygon('COLLECTOR',[[x,face,z] for x,z in outline],g,basis='A',description='A 3/16 in collector plate to the actual receiver; no horizontal track is selected')
    connects=['STRAP','COLLECTOR']
    if pack:
        pack_outline=hull([(q[0]+dx,q[2]+dz) for q in screw_points for dx,dz in ((-1,-1),(-1,1),(1,-1),(1,1))])
        a.polygon('PACKING',[[x,face+g,z] for x,z in pack_outline],pack,basis='A',description='A end packing separates the continuous crossing straps; no centre splice or weld')
        connects.append('PACKING')
    a.fastener('FS',screw_points,[0,-1,0],screw_diameter(size),t+pack+g,connects,
        f'{count} No.{size} source strap-end screws; A two-column pattern and grip'+('; stainless bi-metal' if par.get('stainless') else ''),screw=True)
    for j,(q,ht) in enumerate(host_points):
        a.fastener('FP'+str(j),[q],[0,-1,0],screw_diameter(size),g+ht,['COLLECTOR','RECEIVER'],
            'A collector-to-receiver screws, two into each actual exposed channel flange; additional attachment design unverified',basis='A',screw=True)
        a.parts[-1]['annotation_group']='FP'
    a.section_axis=0;a.section_at=host_points[0][0][0]
    a.dim(screw_points[0],screw_points[-1],f'{count} No.{size}; A 1 in row pitch',basis='A')
    a.notes.append('Source strap section and end screw count retained. Collector plate, per-ply receiving attachments, packing and screw lengths are accepted fictional fit proposals, not source capacity checks. The original direct strap/chord capacity is not assigned to an added collector plate. Both diagonals remain continuous; their crossing is not a restraint or load-transfer connection.')
    if abs(u[2])>.99999:
        from .assembly_scene import upright_receiver
        upright_receiver(a)
