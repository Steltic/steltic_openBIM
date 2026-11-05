"""Actual single-channel portal purlins/girts and finite two-ply Z laps."""
import math
from .pilots.model import add,sub,mul,cross,unit,dot
from .review_cfs_occurrences import axis
from .review_z_sections import folded
from .review_cfs25_secondary import sections
from .review_receiver_geometry import extract

STATIONS=(36,79.5,123,166.5,210,222,265.5,309,352.5,396)


def apply(b):
    if b.key!='cfs27':return
    b.endpoint_links=getattr(b,'endpoint_links',[])
    removed={m['id'] for m in b.members if m['id'].startswith(('P-','G-'))}
    b.members[:]=[m for m in b.members if m['id'] not in removed]
    b.connections[:]=[c for c in b.connections if not removed.intersection(c['member_ids'])]
    b.endpoint_links[:]=[x for x in b.endpoint_links if x['member_id'] not in removed]
    lookup={m['id']:m for m in b.members};work=[i*78 for i in range(31)]
    pid=folded(b,b.profile('800Z250-54'));t=.0566
    groups=[('P',x,0) for x in STATIONS]+[('G',side,z) for side in (0,1) for z in (24,84,144)]
    for kind,station,z in groups:
        roof=kind=='P';side=int(station>216) if roof else station
        if roof:
            raf=lookup[f'F0-R{side}'];u=unit(sub(*raf['axis'][::-1]));v=[0,1,0];n=cross(u,v)
            base=[station,0,192+min(station,432-station)*2/9]
        else:
            out=-1 if side==0 else 1;u=[0,0,-out];v=[0,1,0];n=cross(u,v);base=[432*side,0,z]
        axes=(u,v,n);row=[];nested=roof and station in (123,309)
        for j in range(30):
            centre=add(base,add(mul(u,t*(j%2)),mul(n,11.75+t*(j%2))))
            lo=work[j]-(12 if j else 0);hi=work[j+1]+(12 if j<29 else 4)
            # Extend the adjoining lap piece over the source reinforced end
            # bay. This is one longer inner Z, avoiding three coincident plies.
            if nested and j==1:lo=0
            if nested and j==28:hi=work[-1]+4
            m=b.member(f'SC-{kind}-{station:g}-{z}-{j}',pid,'purlin' if roof else 'girt',add(centre,mul(v,lo)),add(centre,mul(v,hi)),1,'A',
                records=['schedules/sched-purlin' if roof else 'schedules/sched-girt'],local_y=mul(u,-1 if j%2 else 1),lap_in=12,source_profile_id='800Z250-54',
                physical_fit_basis='S8in54mil Z, source3.713ft slope /5ft wall spacing and12in laps. A unequal-flange nesting profile,3in-long bearing pack with3/4in minimum stand-off to clear the continuous straps,4in far-end extension and exact set-out. Source capacities do not verify the altered physical profile.')
            if nested and j in (1,28):m['end_bay_nesting_basis']='S two800Z25054 over the door-jamb kicker end bay. A adjacent lap piece extends to the outer frame, continuously supplying the second ply; no third coincident Z or unselected butt splice.'
            row.append(m)
        for i,s in enumerate(work):
            pieces=[m for m in row if axis(m)[0][1]-1e-6<=s<=axis(m)[1][1]+1e-6]
            if len(pieces) not in (1,2):raise ValueError('Nonphysical single-channel Z stack')
            host=lookup[f'F{i}-R{side}' if roof else f'F{i}-C{side}'];origin=add(base,mul(v,s))
            ordered=sorted(pieces,key=lambda m:dot(sub(axis(m)[0],origin),u))
            c=b.connection(f'SC-{kind}-{station:g}-{z}-SUPPORT{i}','review_single_channel_z',origin,[*ordered,host],
                ['schedules/sched-purlin' if roof else 'schedules/sched-girt'],parameters=dict(actual_single_channel_z=True,axes=axes,purpose='support',roof=roof,
                into=-1 if i==30 else 1,extra_web_bolts=roof and station in (123,210,309) and i in (0,30)),title='SINGLE CHANNEL / ACTUAL Z SUPPORT')
            for m in pieces:
                for end in (0,1):
                    if abs(axis(m)[end][1]-s)<=4.01:b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual outer-frame Z attachment including the source end-bay nested ply.'))
            if i in (0,30):continue
            for sign in (-1,1):
                end=s+sign*12;owner=row[i] if sign<0 else row[i-1]
                if abs(axis(owner)[0 if sign<0 else 1][1]-end)>.01:continue
                q=add(origin,mul(v,sign*10.5));cid=c['id']+'-LAP'+str(sign)
                b.connection(cid,'review_single_channel_z',q,ordered,['schedules/sched-purlin' if roof else 'schedules/sched-girt'],
                    parameters=dict(actual_single_channel_z=True,axes=axes,purpose='lap',roof=roof),title='SINGLE CHANNEL / ACTUAL12in Z LAP')
                b.endpoint_links.append(dict(member_id=owner['id'],end='start' if sign<0 else 'end',connection_id=cid,basis='Bolted actual12in lap end; A bolt number/gauge and1.5in end distance.'))
    b.changes.append(dict(kind='single_channel_source_secondary_layout',removed_generic_members=sorted(removed),purlin_stations_in=list(STATIONS),
        basis='Source P1 at36in knee bracket end, P5 at6in from ridge, five purlins per slope at3.713ft. Source full end-bay nested door-jamb purlins retained as continuous extensions of the adjoining lap pieces. A unequal flange fit, secondary bearing offsets and exact hardware.'))
    b.note('SINGLE-CHANNEL-Z','S:8in54mil Z purlins at3.713ft along each roof slope, girts at2/7/12ft,12in laps each side of interior frames; two1/2in purlin-web bolts plus two added at source post-kicker end supports. Door-jamb P3 end bays have two actual nested Z plies. A: continuous adjoining piece supplies the full end-bay nest, unequal flange fit,1/4in bent clips and packs, two1/2in support/lap-end bolts, exact gauges and4in far-end overhang. Changed section/local fitting requires verification; no saved capacity is reassigned.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes'];support=par['purpose']=='support'
    pieces=ctx.ms[:-1] if support else ctx.ms;count=len(pieces);shapes=[]
    for i,m in enumerate(pieces):extract(ctx,m,'Z'+str(i),axes,24);shapes.append(sections(m,p,ctx.c['point'],axes))
    webs=[];flanges=[]
    for polygons in shapes:
        web=max((v for v in polygons if max(q[0] for q in v)-min(q[0] for q in v)<.2),key=lambda v:max(q[2] for q in v)-min(q[2] for q in v))
        webs.append((min(q[0] for q in web),max(q[0] for q in web),min(q[2] for q in web),max(q[2] for q in web)))
        f=min((v for v in polygons if max(q[2] for q in v)-min(q[2] for q in v)<.2 and max(q[0] for q in v)-min(q[0] for q in v)>1),key=lambda v:min(q[2] for q in v))
        flanges.append((min(q[0] for q in f),max(q[0] for q in f),min(q[2] for q in f),max(q[2] for q in f)))
    left=min(x[0] for x in webs);right=max(x[1] for x in webs);bottom=max(x[2] for x in webs);top=min(x[3] for x in webs);mid=(bottom+top)/2
    if not support:
        a.fastener('LAP',[[left,0,z] for z in (mid-2,mid+2)],[1,0,0],.5,right-left,['Z'+str(i) for i in range(count)],'A two1/2in A325 lap-end web bolts,4in gauge and1.5in end distance; source specifies bolted12in laps',basis='A')
        a.title='SINGLE CHANNEL / ACTUAL12in Z LAP';a.front_axes=(1,2);a.section_axis=1;a.section_at=0
        a.notes.append('S12in lap each side of the frame. A two-bolt end group and unequal-flange physical nesting; source point-symmetric capacity does not certify the adopted shape. Each Z is one formed section, not separate loose plates.');return
    host=ctx.ms[-1];part=extract(ctx,host,'HOST',axes,24);ht=p[host['profile_id']]['dimensions']['t'];host_top=max(q[2] for face in part['faces'] for q in face)
    # The final complete frame is handed inward. Both receiving bolts lie
    # within that actual3in flange, including the last frame.
    ct=.25;into=par['into'];yl=0 if into>0 else -3;length=3;zs=[mid-2,mid+2]
    if par['extra_web_bolts']:zs=[mid-2.5,mid-1,mid+1,mid+2.5]
    a.box('CLIP-W',[left-ct,yl,host_top+ct],[ct,length,top-.25-host_top-ct],'A','A1/4in full-height anti-roll bent web leg')
    a.box('CLIP-F',[left-3,yl,host_top],[3,length,ct],'A','A3in bearing length, bent foot on actual single-channel flange')
    a.interfaces.append(dict(id='BEND',kind='formed_bend',connects=['CLIP-W','CLIP-F'],basis='A',description='One bent clip represented by touching legs; bend radius omitted'))
    a.fastener('WEB',[[left-ct,into*1.5,z] for z in zs],[1,0,0],.5,ct+right-left,['CLIP-W']+['Z'+str(i) for i in range(count)],
        'S two1/2in purlin web bolts'+(' plus two source post-kicker bolts' if par['extra_web_bolts'] else '')+'; A gauge and clip' if par['roof'] else 'A two1/2in girt-web bolts and clip',basis='S count / A gauge' if par['roof'] else 'A')
    a.fastener('FOOT',[[left-1.5,y,host_top+ct] for y in (into*.75,into*2.25)],[0,0,-1],.5,ct+ht,['CLIP-F','HOST'],'A two1/2in anti-roll foot bolts into actual3in channel flange',basis='A')
    lo=max(f[0] for f in flanges)+.25;hi=min(f[1] for f in flanges)-.25
    if hi<=lo:raise ValueError('No common finite nested flange')
    x=(lo+hi)/2;previous=host_top;joined=['HOST']
    for i,f in enumerate(sorted(flanges,key=lambda f:f[2])):
        gap=f[2]-previous
        if gap<-1e-6:raise ValueError('Nested Z intersects its support')
        if gap>1e-6:
            name='PACK'+str(i);a.box(name,[lo,yl,previous],[hi-lo,3,gap],'A','A finite3in bearing pack, clear of clip foot');joined.append(name)
        previous=f[3]
    a.fastener('FLANGES',[[x,y,previous] for y in (into*.75,into*2.25)],[0,0,-1],.5,previous-host_top+ht,joined+['Z'+str(i) for i in range(count)],'A two1/2in bolts through actual nested flanges and source frame flange',basis='A')
    a.title='SINGLE CHANNEL / SOURCE Z WEB GROUP ON ACTUAL FRAME';a.front_axes=(1,2);a.section_axis=1;a.section_at=into*1.5
    a.notes.append('Actual single-channel flange carries the source purlin group. The source two added post-kicker bolts are separate from the ordinary two where applicable. A bent clip,3in bearing packs, receiving/lap bolts, unequal-flange Z fit and hardware set-out require verification; original capacities are not assigned to the adopted profile.')
