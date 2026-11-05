"""Located retrofit Z laps and source attachment groups on existing receivers."""
import copy, math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point
from .review_sbmf_girts import cross_section
from .review_z_sections import folded


def apply(b):
    if b.key!='cfs25':return
    if not hasattr(b,'endpoint_links'):b.endpoint_links=[]
    lookup={m['id']:m for m in b.members};groups=defaultdict(list)
    for m in b.members:
        if m['id'].startswith('P-'):groups['P',m['id'].split('-')[1]].append(m)
        elif m['id'].startswith('G-'):
            _,side,bay,z=m['id'].split('-');groups['G',side,z].append(m)
        elif m['id'].startswith('END-G-'):
            _,_,end,x,z=m['id'].split('-');groups['END',end,z].append(m)
    changed={m['id'] for ms in groups.values() for m in ms}
    b.connections[:]=[c for c in b.connections if not (c['detail_ref']['id']=='review_next_secondary' and changed.intersection(c['member_ids']))]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in changed]
    for tag,ms in sorted(groups.items()):
        roof=tag[0]=='P';endwall=tag[0]=='END';along=0 if endwall else 1
        ms.sort(key=lambda m:m['axis'][0][along])
        work=[i*300 for i in range(len(ms)+1)]
        if roof:
            old_x=float(tag[1]);x=4 if old_x==0 else 1196 if old_x==1200 else 596 if old_x==600 else old_x
            side=int(x>600);raf=lookup[f'F0-R{side}'];u=unit(sub(*axis(raf)[::-1]));v=[0,1,0];n=cross(u,v)
            r=axis(raf)[0];z=r[2]+u[2]/u[0]*(x-r[0]);base=add([x,0,z],mul(n,b.depth(raf['profile_id'])/2))
            hosts=[lookup[f'F{i}-R{side}'] for i in range(len(work))]
        elif endwall:
            y=float(tag[1]);out=-1 if y==0 else 1;u=[0,0,out];v=[1,0,0];n=cross(u,v);base=[0,y+out*8,float(tag[2])]
            frame=0 if y==0 else 10
            hosts=[lookup[f'F{frame}-C0']]+[lookup[f'EXIST-POST-{tag[1]}-{x}'] for x in (300,600,900)]+[lookup[f'F{frame}-C1']]
        else:
            side=int(tag[1]);out=-1 if side==0 else 1;u=[0,0,-out];v=[0,1,0];n=cross(u,v);base=[1200*side+out*8,0,float(tag[2])]
            hosts=[lookup[f'F{i}-C{side}'] for i in range(len(work))]
        axes=(u,v,n);offset=0.;height=0.;previous=None;rid='schedules/sched-purlin' if roof else 'schedules/sched-girt'
        for j,m in enumerate(ms):
            original=copy.deepcopy(m);source=b.profiles[m['profile_id']];d=source['dimensions'];t=d['t']
            if previous is not None:
                sign=1 if j%2 else -1;offset+=sign*(previous+t)/2;height+=sign*max(previous,t)
            m['profile_id']=folded(b,source['id']);m['local_y']=mul(u,-1 if j%2 else 1)
            lo=work[j]-(30 if j else 0);hi=work[j+1]+(30 if j<len(ms)-1 else 0)
            centre=add(add(base,mul(u,offset)),mul(n,d['d']/2+height))
            m['axis']=[add(centre,mul(v,s)) for s in (lo,hi)];m['end_offsets']=[[0,0,0],[0,0,0]];m['lap_in']=30
            m.update(basis='A',source_profile_id=source['id'],physical_fit_basis='S depth, thickness and30in lap; A unequal flange shape, alternating hand, contact nesting and finite set-out. Source point-symmetric capacity is not assigned to this fit.')
            b.changes.append(dict(kind='cfs25_actual_nested_z',member_id=m['id'],previous_axis=original['axis'],previous_local_y=original['local_y'],previous_profile=source['id'],axis=copy.deepcopy(m['axis']),source_record=rid))
            previous=t
        low=min(dot(sub(axis(m)[0],base),n)-b.profiles[m['profile_id']]['dimensions']['d']/2 for m in ms)
        if low<0:
            for m in ms:
                m['axis']=[add(q,mul(n,-low)) for q in m['axis']]
            b.changes.append(dict(kind='cfs25_nested_row_bearing_offset',member_ids=[m['id'] for m in ms],offset=mul(n,-low),basis='A uniform row translation preserves every touching lap and clears the actual support face; local support packs shown.'))
        for i,s in enumerate(work):
            pieces=ms[max(0,i-1):min(len(ms),i+1)];host=hosts[i];origin=add(base,mul(v,s))
            ordered=sorted(pieces,key=lambda m:dot(sub(axis(m)[0],origin),u))
            c=b.connection('RETROFIT-'+ '-'.join(tag)+'-SUPPORT'+str(i),'review_retrofit_z_support',origin,[*ordered,host],[rid],
                parameters=dict(actual_retrofit_z=True,axes=axes,purpose='purlin' if roof else 'girt',edge_into=1 if i==0 else -1 if i==len(work)-1 else 0,flange_bolts=4 if roof and float(tag[1]) in (0,60,1140,1200) and 0<i<len(work)-1 else 2),
                title='RETROFIT Z / ACTUAL SUPPORT AND ANTI-ROLL CLIP')
            if i==0:b.endpoint_links.append(dict(member_id=ms[0]['id'],end='start',connection_id=c['id'],basis='Actual source end-support attachment to the existing contextual frame.'))
            if i==len(work)-1:b.endpoint_links.append(dict(member_id=ms[-1]['id'],end='end',connection_id=c['id'],basis='Actual source end-support attachment to the existing contextual frame.'))
            if len(pieces)==2:
                for sign in (-1,1):
                    q=add(origin,mul(v,sign*28.5));cid=c['id']+'-LAP'+str(sign)
                    b.connection(cid,'review_retrofit_z_lap',q,ordered,[rid],parameters=dict(actual_retrofit_z=True,axes=axes,purpose='purlin' if roof else 'girt'),title='RETROFIT Z / SOURCE LAP-END WEB BOLTS')
                    member=ms[i] if sign<0 else ms[i-1]
                    b.endpoint_links.append(dict(member_id=member['id'],end='start' if sign<0 else 'end',connection_id=cid,basis='Source two half-inch web bolts at this actual30in lap end; A1.5in end distance.'))
    b.note('RETROFIT-Z-FIT','S: nominal10x3in roof Z and8x2.5in girt schedules, source thickness zones,30in laps each side of interior frames, two1/2in web bolts at each lap end and roof anti-roll/support groups. A: unequal flange widths nominal +/-1/4in for a physically nested folded shape; source gold used a point-symmetric section, so its capacities do not certify this change. Webs contact, finite plies alternate hand and any flange or existing-post offset has an explicit pack. Roof end/ridge rows shift4in into the finite existing-rafter receiver; supplier/local capacity and actual existing structure require verification.')


def sections(m,p,origin,axes):
    delta=point(axis(m)[0],origin,axes)
    return [[[q[i]+delta[i] for i in range(3)] for q in poly] for poly in cross_section(m,p,axes)]


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes'];origin=ctx.c['point']
    count=len(ctx.ms)-(ctx.family=='review_retrofit_z_support');pieces=ctx.ms[:count]
    a.title='RETROFIT Z / SOURCE LAP-END BOLTS' if ctx.family.endswith('_lap') else 'RETROFIT Z / ACTUAL SUPPORT AND ANTI-ROLL CLIP'
    shapes=[]
    for i,m in enumerate(pieces):
        extract(ctx,m,'Z'+str(i),axes,36);shapes.append(sections(m,p,origin,axes))
    webs=[];flanges=[]
    for polygons in shapes:
        web=max((v for v in polygons if max(q[0] for q in v)-min(q[0] for q in v)<.2),key=lambda v:max(q[2] for q in v)-min(q[2] for q in v))
        webs.append((min(q[0] for q in web),max(q[0] for q in web),min(q[2] for q in web),max(q[2] for q in web)))
        bands=[v for v in polygons if max(q[2] for q in v)-min(q[2] for q in v)<.2 and max(q[0] for q in v)-min(q[0] for q in v)>1]
        flange=min(bands,key=lambda v:min(q[2] for q in v))
        flanges.append((min(q[0] for q in flange),max(q[0] for q in flange),min(q[2] for q in flange),max(q[2] for q in flange)))
    left=min(v[0] for v in webs);right=max(v[1] for v in webs);bottom=max(v[2] for v in webs);top=min(v[3] for v in webs);mid=(bottom+top)/2
    if ctx.family.endswith('_lap'):
        a.fastener('LAP',[[left,0,z] for z in (mid-2,mid+2)],[1,0,0],.5,right-left,['Z'+str(i) for i in range(count)],'S two1/2in A325 web bolts per actual lap end; A4in vertical gauge and1.5in end distance',basis='S')
        a.front_axes=(1,2);a.section_axis=1;a.section_at=0
        a.notes.append('The actual two finite Z pieces overlap30in each side of the frame. Source two web bolts are at each end of that lap. A unequal-flange shape and hand make the webs touch without intersecting steel; original point-symmetric capacities do not certify this changed section.')
        return
    host=ctx.ms[-1];extract(ctx,host,'HOST',axes,18)
    host_part=next(v for v in a.parts if v['id']=='HOST')
    hp=p[host['profile_id']];ht=hp['dimensions']['t'];host_top=max(q[2] for face in host_part['faces'] for q in face)
    edge=par['edge_into'];yl=0 if edge==1 else -6 if edge==-1 else -3;web_y=2.25*edge
    # The source anti-roll stock is3/8in; exact bend and attachment dimensions
    # are adopted. It bears on the actual existing HSS wall, not an empty box.
    ct=.375;clip_bottom=host_top;clip_top=top-.25
    clip_basis='S thickness / A fit' if par['purpose']=='purlin' else 'A'
    a.box('CLIP-W',[left-ct,yl,clip_bottom+ct],[ct,6,clip_top-clip_bottom-ct],clip_basis,'3/8in bent anti-roll clip web')
    a.box('CLIP-F',[left-3,yl,clip_bottom],[3,6,ct],clip_basis,'Same3/8in bent anti-roll clip foot')
    a.interfaces.append(dict(id='BEND',kind='formed_bend',connects=['CLIP-W','CLIP-F'],basis='A',description='One bent plate represented by two touching legs; bend radius and local capacity unverified'))
    a.fastener('WEB',[[left-ct,web_y,z] for z in (mid-2,mid+2)],[1,0,0],.5,ct+right-left,['CLIP-W']+['Z'+str(i) for i in range(count)],'S two1/2in A325 to roof Z web; A same fitted girt clip and gauge',basis='S' if par['purpose']=='purlin' else 'A')
    foot_y=[edge*1.5,edge*3] if edge else [-1.5,1.5]
    a.fastener('CLIP-FOOT',[[left-1.5,y,clip_bottom+ct] for y in foot_y],[0,0,-1],.5,ct+ht,['CLIP-F','HOST'],'A two1/2in clip-foot bolts to actual existing HSS wall; access/installation and capacity unverified',basis='A')
    flanges.sort(key=lambda v:v[2]);lo=max(v[0] for v in flanges)+.25;hi=min(v[1] for v in flanges)-.25
    if hi-lo<.5:raise ValueError('No finite common nested flange bolt band '+ctx.c['id'])
    x=(lo+hi)/2;joined=['HOST']+['Z'+str(i) for i in range(count)]
    previous=host_top
    for i,f in enumerate(flanges):
        gap=f[2]-previous
        if gap<-.00001:raise ValueError('Z support intersects an actual receiver '+ctx.c['id'])
        if gap>1e-6:
            label='PACK'+str(i);a.box(label,[lo,yl,previous],[hi-lo,6,gap],'A','Actual finite flange/bearing gap packing; capacity unverified');joined.append(label)
        previous=f[3]
    ys=(-2.25,-.75,.75,2.25) if par['flange_bolts']==4 else foot_y
    a.fastener('FLANGES',[[x,y,previous] for y in ys],[0,0,-1],.5,previous-host_top+ht,joined,
        'S roof support bolts through actual nested flanges; A girt support bolts, finite gauge and HSS installation' if par['purpose']=='purlin' else 'A two1/2in girt-flange bolts to actual existing HSS, finite gauge and packing',basis='S' if par['purpose']=='purlin' else 'A')
    a.front_axes=(1,2);a.section_axis=1;a.section_at=web_y
    a.notes.append('Source roof3/8in anti-roll clip and two web bolts; source roof support count2, or4 on interior eave lines. Girt clip/support adoption is A. Each Z is one folded sheet; geometric strips are its web, flanges and lips. Actual finite HSS receiver is existing survey context. A exact bends, packs, gauges, access for nuts and unequal-flange Z fit need verification. No source capacity is assigned to the changed profile or existing stand-in.')
