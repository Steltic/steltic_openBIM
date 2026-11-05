"""Actual HR31 crossed rods, supplier clevises and separate turnbuckle ends."""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import extract,point
from .review_assemblies import hull

AXES=([1,0,0],[0,1,0],[0,0,1])


def ends(m):return [add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]


def apply(b):
    if b.key!='hr31':return
    lookup={m['id']:m for m in b.members};removed=set();b.endpoint_links=getattr(b,'endpoint_links',[])
    for rod in list(b.members):
        if rod['kind']!='rod_brace':continue
        joints=[c for c in b.connections if c['member_ids'][0]==rod['id']]
        adjusters=[c for c in joints if c.get('parameters',{}).get('joint')=='turnbuckle']
        if len(joints)!=3 or len(adjusters)!=1:raise ValueError('Rod needs two real ends and one source turnbuckle')
        ends_c=[c for c in joints if c not in adjusters];a,z=rod['axis'];u=unit(sub(z,a))
        if rod['id'].startswith('ROOF-X-'):
            # The roof-plane gusset belongs on the actual rafter web, including
            # at a knee where a coincident column analysis node also exists.
            # The source permits column OR rafter web receivers. Selecting a
            # column by list order gives an oblique, detached roof gusset.
            from .review_hr import nearest
            roof_side=0 if (a[1]+z[1])/2<960 else 1
            excluded=[m['id'] for m in b.members if m['kind']=='rafter' and not m['id'].endswith('-'+str(roof_side))]
            for c in ends_c:
                host=nearest(b,c['point'],('rafter',),excluded)
                if host is None:raise ValueError('Roof rod has no actual rafter receiver')
                c['member_ids'][1]=host['id']
        host=lookup[ends_c[0]['member_ids'][1]];hu=unit(sub(*host['axis'][::-1]));normal=unit(cross(u,hu))
        # Canonical facing keeps the crossed pair in different physical planes.
        dominant=max(range(3),key=lambda i:abs(normal[i]))
        if normal[dominant]<0:normal=mul(normal,-1)
        side=1 if rod['id'].endswith('-0') else -1;shift=mul(normal,side*.75)
        fraction=.4 if side>0 else .6;mid=add(a,mul(sub(z,a),fraction));pieces=[]
        for tag,axis,offsets in [('L',[a,mid],[add(shift,mul(u,24)),add(shift,mul(u,-2))]),
                                 ('R',[mid,z],[add(shift,mul(u,2)),add(shift,mul(u,-24))])]:
            m=copy.deepcopy(rod);m.update(id=rod['id']+':'+tag,axis=copy.deepcopy(axis),end_offsets=offsets,joint_workpoints=copy.deepcopy(axis),
                source_member_ids=[rod['id']],physical_fit_basis='S1 in rod and source clevis/turnbuckle requirement. A separate threaded rod ends,24 in clevis set-back,1.5 in crossed-rod plane separation and staggered adjuster station.')
            original=next((v for v in b.package['physical']['members'] if v['profile_id']=='ROD1' and all(math.dist(p,q)<1e-6 for p,q in zip(v['axis'],rod['axis']))),None)
            if original:
                m['analysis_ids']=[];m['analysis_segments']=[dict(analysis_id=original['id'],start=0 if tag=='L' else fraction,end=fraction if tag=='L' else 1)]
                m['mapping_basis']='Exact original rod workline divided at the physical turnbuckle; physical cutbacks and transverse clearance remain explicit end offsets'
            if rod['id'].startswith('ROOF-X-'):
                m['design_record_ids']=[b.record('members','roof-rod-bracing-ROD1')]
            b.members.append(m);pieces.append(m)
        for c in ends_c:
            end=min(range(2),key=lambda i:math.dist(rod['axis'][i],c['point']));m=pieces[end]
            host=lookup[c['member_ids'][1]];direction=u if end==0 else mul(u,-1);hd=unit(sub(*host['axis'][::-1]));n=unit(cross(direction,hd))
            c['member_ids'][0]=m['id'];c.setdefault('parameters',{}).update(actual_rod_end=True,into=direction,plate_normal=n,rod_plane_shift=shift)
        c=adjusters[0];c['point']=mid;c['member_ids']=[m['id'] for m in pieces]
        c.setdefault('parameters',{}).update(actual_rod_adjuster=True,rod_axis=u,rod_plane_shift=shift)
        for m,end in zip(pieces,('end','start')):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Actual separate threaded rod end is contained in this source turnbuckle assembly'))
        removed.add(rod['id']);b.changes.append(dict(kind='actual_crossed_rod_and_adjuster',original_member=rod,piece_ids=[m['id'] for m in pieces],
            plane_offset_in=side*.75,turnbuckle_fraction=fraction,basis='A: separate rod halves and staggered supplier turnbuckles prevent rods and adjuster bodies colliding at the crossing. Source rod diameter, end pins, gusset thickness and weld sizes are unchanged; supplier and eccentric/local capacities unverified.'))
    b.members[:]=[m for m in b.members if m['id'] not in removed]
    b.note('ROD-RECEIVERS','S:1 in tension rods,1-1/4 in end pins,1/2 in gussets and1/4 in gusset fillets. A: actual web receivers, forged clevis/body envelopes,24 in rod cutbacks,1.5 in separation between crossed-rod planes and staggered turnbuckles at40/60 percent of each workline. Each turnbuckle has two separate threaded rod ends. These are accepted geometry proposals; source design checks do not approve the added eccentricities or supplier parts.')


def end(ctx):
    a,p=ctx.a,ctx.p;rod,host=ctx.ms;origin=ctx.c['point'];u=ctx.params['into'];n=ctx.params['plate_normal'];shift=ctx.params['rod_plane_shift'];v=cross(n,u)
    extract(ctx,rod,'ROD',AXES,60);extract(ctx,host,'HOST',AXES,70)
    hd=unit(sub(*host['axis'][::-1]));width=host['local_y'];pd=p[host['profile_id']]['dimensions']
    if p[host['profile_id']]['family']!='i' or abs(dot(u,width))<.1:raise ValueError('Rod requires an actual accessible I-section web: '+ctx.c['id']+' / '+host['id']+' / '+str((u,width)))
    face=(1 if dot(u,width)>0 else -1)*pd['tw']/2
    ha,hz=ends(host);station=dot(sub(add(origin,shift),ha),hd);length=math.dist(ha,hz)
    centre=max(8,min(length-8,station));anchor=add(ha,add(mul(hd,centre),mul(width,face)))
    # Put the plate in the physical rod plane; its edge intersects the real
    # receiving web at the correct transverse position along the web depth.
    anchor=add(anchor,mul(n,dot(sub(add(origin,shift),anchor),n)))
    anchor=point(anchor,origin,AXES);pin=add(shift,mul(u,16));coords=[]
    for q in (add(anchor,mul(hd,-6)),add(anchor,mul(hd,6)),add(pin,mul(v,-3)),add(pin,mul(v,3)),add(pin,mul(u,3))):coords.append((dot(q,u),dot(q,v)))
    offset=dot(shift,n)
    polygon=[add(add(mul(u,x),mul(v,y)),mul(n,offset-.25)) for x,y in hull(coords)]
    a.polygon('GUSSET',polygon,.5,normal=n,basis='S thickness; A outline',description='Source1/2 in gusset at actual host web; A pin station/outline')
    for sg in (-1,1):
        aa=add(anchor,add(mul(hd,-6),mul(n,sg*.25)));bb=add(anchor,add(mul(hd,6),mul(n,sg*.25)))
        a.weld('GW'+str(sg),aa,bb,['HOST','GUSSET'],.25,description='S1/4 in gusset-to-actual-web fillet; A12 in local length')
    for i,off in enumerate((-.875,.375)):
        points=[add(pin,add(add(mul(u,x),mul(v,y)),mul(n,off))) for x,y in ((-3,-2),(10,-2),(10,2),(-3,2))]
        a.polygon('CLEVIS'+str(i),points,.5,normal=n,basis='A',description='A forged supplier jaw envelope;1/8 in clearance each side of source gusset')
    a.cylinder('BODY',add(pin,mul(u,8)),u,3,5,'A','A threaded forged clevis body envelope')
    a.fastener('PIN',[add(pin,mul(n,-.875))],n,1.25,1.75,['CLEVIS0','GUSSET','CLEVIS1'],'S1-1/4 in source clevis pin; A grip')
    a.interfaces.append(dict(id='THREAD',kind='threaded_clevis',connects=['ROD','BODY','CLEVIS0','CLEVIS1'],basis='A',description='A forged jaws/body and threaded rod engagement; no welded rod or supplier capacity approval'))
    a.front_axes=(0,2) if abs(n[1])>.5 else (0,1);a.section_axis=max(range(3),key=lambda i:abs(u[i]));a.section_at=pin[a.section_axis]
    a.dim(shift,pin,'A16 in pin station',basis='A');a.notes.append('Actual rod axis, cutback and host web are shown. S pin diameter, gusset thickness and fillet size. A forged parts, plate outline, weld length and transverse offset require supplier/local capacity verification.')


def adjuster(ctx):
    a,p=ctx.a,ctx.p;u=ctx.params['rod_axis'];shift=ctx.params['rod_plane_shift']
    for label,m in zip(('ROD-L','ROD-R'),ctx.ms):extract(ctx,m,label,AXES,28)
    # A hollow adjustment barrel leaves the physical2 in end gap visible.
    from .review_assemblies import tube
    profile=tube(p,3,3,.25);y=unit(cross([0,0,1],u))
    a.member('BODY',profile,add(shift,mul(u,-8)),add(shift,mul(u,8)),y=y,basis='A',representation_role='assembly_component',description='A hollow forged turnbuckle barrel; two separate threaded rod ends')
    for sg in (-1,1):a.cylinder('END'+str(sg),add(shift,mul(u,sg*6)),u,2.5,1.5,'A','A threaded end boss envelope')
    a.interfaces.append(dict(id='THREADS',kind='threaded_adjuster',connects=['ROD-L','ROD-R','BODY','END-1','END1'],basis='A',description='A opposite-hand threaded rod engagement; separate rod ends remain2 in each side of the adjustment workpoint'))
    a.dim(add(shift,mul(u,-8)),add(shift,mul(u,8)),'A16 in supplier envelope',basis='A');a.front_axes=(0,2) if abs(u[2])>.4 else (0,1);a.section_axis=max(range(3),key=lambda i:abs(u[i]));a.section_at=shift[a.section_axis]
