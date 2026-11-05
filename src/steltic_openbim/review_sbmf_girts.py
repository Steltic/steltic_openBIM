"""Real bypass girt clips on SBMF columns and end-wall posts."""
import math
from .pilots.model import sub,unit,dot,cross,add,mul
from .pilots.geometry import strips
from .review_receiver_geometry import extract


def cross_section(member,profiles,axes):
    u=unit(sub(*member['axis'][::-1]));y=member['local_y'];z=cross(u,y)
    return [[[dot(add(mul(y,q[0]),mul(z,q[1])),a) for a in axes] for q in poly]
            for poly in strips(profiles[member['profile_id']],profiles)]


def apply(b):
    if b.key not in ('cfs10','cfs18','cfs27'):return
    # The source distinguishes the stud-framed braced end bays from the
    # metal-clad girt walls between them. Generic infill studs had no source
    # selection or tracks and duplicated the latter system.
    if b.key=='cfs18':
        removed={m['id'] for m in b.members if m['id'].startswith('SIDE-STUD-')}
        b.members[:]=[m for m in b.members if m['id'] not in removed]
        b.connections[:]=[c for c in b.connections if not removed.intersection(c['member_ids'])]
        b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in removed]
        b.changes.append(dict(kind='remove_duplicate_unselected_wall_infills',member_ids=sorted(removed),
            basis='Source sidewall-studs applies to the braced end bays. Intermediate walls use source800S200-54 girts; generic field studs had no source design or receiving tracks. Source braced-bay studs remain.'))
    lookup={m['id']:m for m in b.members};hosts=[m for m in b.members if m['kind'] in ('column','endwall_post','opening_jamb')]
    girts=[m for m in b.members if m['id'].startswith(('END-G-',) if b.key=='cfs27' else ('SIDE-GIRT-','END-GIRT-','STOREFRONT-GIRT-'))]
    for m in girts:
        along=0 if abs(m['axis'][1][0]-m['axis'][0][0])>1 else 1;normal=1-along
        outward=-1 if m['axis'][0][normal]==0 else 1;old=[list(q) for q in m['axis']]
        candidates=[]
        for end,point in enumerate(old):
            options=[h for h in hosts if all(abs(h['axis'][0][i]-point[i])<.01 for i in (0,1))]
            if not options:raise ValueError('Girt has no located supporting column/post: '+m['id'])
            candidates.append(min(options,key=lambda h:h['id']))
        u=[1,0,0] if along==0 else [0,1,0];v=cross([0,0,1],u);axes=(u,v,[0,0,1]);sg=outward*v[normal]
        profile_depth=b.depth(m['profile_id'])
        half=max(max(outward*q[normal] for poly in cross_section(h,b.profiles,([1,0,0],[0,1,0],[0,0,1])) for q in poly) for h in candidates)
        offset=outward*(half+profile_depth/2+.25)
        m['local_y']=[0,0,1]
        for q in m['axis']:q[normal]+=offset
        for end,h in enumerate(candidates):
            into=1 if end==0 else -1;m['end_offsets'][end][along]=into*.125
            c=next(c for c in b.connections if c['id']==m['id']+':'+str(end))
            polys=cross_section(h,b.profiles,axes);faces=[]
            for poly in polys:
                aa,bb=min(q[1] for q in poly),max(q[1] for q in poly)
                if .001<bb-aa<1 and max(q[0] for q in poly)-min(q[0] for q in poly)>(1.5 if b.key=='cfs27' else 2):
                    face=bb if sg>0 else aa;faces.append((sg*face,face,bb-aa))
            if not faces:raise ValueError('No broad host face for bypass clip '+c['id'])
            _,face,thickness=max(faces);face-=offset*v[normal]
            c['point']=list(m['axis'][end]);c['member_ids']=[m['id'],h['id']];c['detail_ref']['id']='review_sbmf_girt'
            c.setdefault('parameters',{}).update(actual_sbmf_girt=True,along=along,into=into,outward=sg,host_face=face,host_thickness=thickness)
            b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],
                basis='Actual bypass girt clears the supporting column/post; located folded clip connects its full web stack to the actual receiving face.'))
        b.changes.append(dict(kind='sbmf_bypass_girt',member_id=m['id'],normal_offset_in=offset,
            basis='S source girt section. A outside-column set-out,1/4in clearance,1/8in end cuts, folded1/4in clips, two1/2in bolts per leg and built-up-web packing. Attachment/local capacity unverified.'))
    if b.key=='cfs27':
        b.note('ENDWALL-BYPASS-GIRTS','S8in54mil end-wall Z girts and actual single-channel columns / paired posts. A outward set-out,1/4in folded clips, two1/2in bolts per leg and end clearances. Receiver legs attach to actual broad webs or flanges; no invented post beyond the opening is used.')
        return
    b.note('SBMF-BYPASS-GIRTS','S: saved side-wall, end-wall and storefront girt selections. A: actual outward bypass set-out clears the HSS/post faces,1/4in folded clips, two1/2in bolts per leg and solid web-stack packers for boxed storefront members. Receiver bolts need accessible assembly or a verified blind-fastener system. Intermediate CFS18 walls use the source girt system; the previously invented untracked infill studs are omitted. Cladding offsets, girt sag-angle restraint and clip capacities remain explicit coordination/supplier requirements.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,host=ctx.ms;along=par['along'];u=[1,0,0] if along==0 else [0,1,0];axes=(u,cross([0,0,1],u),[0,0,1])
    if ctx.model['pilot']=='cfs27':a.title='SINGLE CHANNEL / ACTUAL END-WALL GIRT CLIP'
    extract(ctx,m,'GIRT',axes,28);extract(ctx,host,'HOST',axes,20)
    polys=cross_section(m,p,axes);webs=[]
    for poly in polys:
        lo,hi=min(q[2] for q in poly),max(q[2] for q in poly)
        if .001<hi-lo<.5 and max(q[1] for q in poly)-min(q[1] for q in poly)>4:webs.append((lo,hi))
    webs=sorted(webs);into=par['into'];sg=par['outward'];face=par['host_face'];t=.25;top=webs[-1][1];cut=into*.125;far=cut+into*5
    a.polygon('GIRT-LEG',[[x,y,top] for x,y in ((0,face),(far,face),(far,sg),(0,sg))],t,normal=[0,0,1],basis='A',description='A1/4in folded bypass clip at actual top web')
    a.polygon('HOST-LEG',[[x,face,z] for x,z in ((0,top-4),(into*2.5,top-4),(into*2.5,top),(0,top))],t,normal=[0,sg,0],basis='A',description='A4in receiving leg on actual HSS/post face')
    packs=[]
    for i,((_,low),(high,_)) in enumerate(zip(webs,webs[1:])):
        if high-low<1e-7:continue
        label='PACK'+str(i);packs.append(label)
        a.box(label,[min(cut,far),-1,low],[5,2,high-low],'A','A solid pack between actual boxed-girt webs')
    a.fastener('GIRT-BOLTS',[[cut+into*x,0,top+t] for x in (1.25,3.75)],[0,0,-1],.5,t+top-webs[0][0],
        ['GIRT','GIRT-LEG']+packs,'A two1/2in through-bolts engage the complete actual girt web stack',basis='A')
    a.fastener('HOST-BOLTS',[[into*1.25,face+sg*t,top-z] for z in (1,3)],[0,-sg,0],.5,t+par['host_thickness'],
        ['HOST','HOST-LEG'],'A two1/2in receiver bolts; accessible assembly or verified blind-fastener system required',basis='A')
    a.interfaces.append(dict(id='FOLD',kind='continuous_folded_clip',connects=['GIRT-LEG','HOST-LEG'],basis='A',description='Continuous bent clip; bend radius omitted'))
    a.dim([0,face,top],[0,sg,top],'A actual bypass projection',basis='A');a.section_axis=0;a.section_at=into*1.25
    a.notes.append('Actual source girt and supporting column/post, with the girt web rolled horizontally for out-of-plane wall bending. Boxed-girt bolts engage both webs through explicit solid packs. The bypass distance, clip, access method and attachment capacity are A accepted fictional fit selections. Source member capacities do not certify these local attachments.')
