"""Finite agricultural-building Z rows, source laps and six-flange supports."""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .review_z_sections import folded
from .review_cfs25_secondary import sections
from .review_cfs_frame_straps import face_intervals

LEFT=(16,36,60,114,168,222,264,280)
STATIONS=LEFT+tuple(576-x for x in reversed(LEFT))
WORK=tuple(i*211.2 for i in range(11))


def apply(b):
    if b.key!='cfs28':return
    removed={m['id'] for m in b.members if m['id'].startswith(('P-','G-'))}
    b.members[:]=[m for m in b.members if m['id'] not in removed]
    b.connections[:]=[c for c in b.connections if not removed.intersection(c['member_ids'])]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in removed]
    lookup={m['id']:m for m in b.members}
    for kind,station in [('P',x) for x in STATIONS]+[('G',z) for z in (24,96,168)]:
        roof=kind=='P';side=int(station>288) if roof else 1
        if roof:
            u=unit([1,0,.25 if side==0 else -.25]);base=[station,0,216+min(station,576-station)/4]
        else:u=[0,0,-1];base=[576,0,station]
        v=[0,1,0];n=cross(u,v);axes=(u,v,n);row=[];offset=height=0.;previous=None
        for j in range(10):
            # The end-bay roof strut condition also requires97mil. The
            # centre-post schedule's68mil check is retained separately.
            mil=97 if not roof or j in (0,1,2,7,8,9) else 68
            label=('1000' if roof else '800')+'Z250-'+str(mil);pid=folded(b,b.profile(label));d=b.profiles[pid]['dimensions'];t=d['t']
            if previous is not None:
                sign=1 if j%2 else -1;offset+=sign*(previous+t)/2;height+=sign*max(previous,t)
            centre=add(base,add(mul(u,offset),mul(n,7+1.125+d['d']/2+height)))
            lo=WORK[j]-(18 if j else 0);hi=WORK[j+1]+(18 if j<9 else 0)
            if roof and station in (168,408):
                if j==1:lo=0
                if j==8:hi=WORK[-1]
            m=b.member(f'AG-{kind}-{station}-{j}',pid,'purlin' if roof else 'girt',add(centre,mul(v,lo)),add(centre,mul(v,hi)),1,'A',local_y=mul(u,-1 if j%2 else 1),
                records=['schedules/sched-purlin' if roof else 'schedules/sched-girt'],lap_in=18,source_profile_id=label,
                physical_fit_basis='S nominal Z depth/thickness,17.6ft spans and18in laps. A unequal flange nesting, adopted closer support rows,3/8in saddle over all six frame flanges and minimum3/4in bearing pack; local capacity unverified.')
            row.append(m);previous=t
        low=min(dot(sub(axis(m)[0],base),n)-b.profiles[m['profile_id']]['dimensions']['d']/2 for m in row)
        for m in row:
            m['axis']=[add(q,mul(n,8.125-low)) for q in m['axis']]
        rid='schedules/sched-purlin' if roof else 'schedules/sched-girt'
        for i,s in enumerate(WORK):
            pieces=[m for m in row if axis(m)[0][1]-1e-6<=s<=axis(m)[1][1]+1e-6]
            assert len(pieces) in (1,2)
            origin=add(base,[0,s,0]);pieces.sort(key=lambda m:dot(sub(axis(m)[0],origin),u))
            host=lookup[f'F{i}-R{side}' if roof else f'F{i}-C1']
            c=b.connection(f'AG-{kind}-{station}-SUPPORT{i}','review_ag_z',origin,[*pieces,host],[rid],
                parameters=dict(actual_ag_z=True,axes=axes,purpose='support',roof=roof,edge=1 if i==0 else -1 if i==10 else 0),title='AG PORTAL / ACTUAL NESTED Z SUPPORT')
            for m in pieces:
                for end in (0,1):
                    if abs(axis(m)[end][1]-s)<.01:b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual finite source end-bay nested Z attached at its outer frame.'))
            if i in (0,10):continue
            for sign in (-1,1):
                owner=row[i] if sign<0 else row[i-1];end=0 if sign<0 else 1
                if abs(axis(owner)[end][1]-(s+sign*18))>.01:continue
                cc=b.connection(c['id']+'-LAP'+str(sign),'review_ag_z',add(origin,[0,sign*16.5,0]),pieces,[rid],parameters=dict(actual_ag_z=True,axes=axes,purpose='lap',roof=roof))
                b.endpoint_links.append(dict(member_id=owner['id'],end='start' if end==0 else 'end',connection_id=cc['id'],basis='Two actual nested web bolts at this finite18in lap end; A gauge and1.5in end distance.'))
    b.note('AG-Z-ROWS','S:10in roof Z,68mil field/97mil corner and braced-end-bay struts,8in97mil south-wall girts at2/8/14ft,18in laps and5in end bearing. A: roof rows include exact jamb panel points168/408in, bracket-end36/540in and ridge-bracket264/312in stations; maximum54in horizontal gap, additional16in eave/8in ridge offsets. Adjoining Z extends over each door-jamb end bay to provide the source two nested plies without a third coincident ply. Source centre-post schedule references68mil but the same ridge/end-bay region requires97mil in the purlin schedule: adopt97mil there and retain the68mil check as source evidence only. A unequal-flange nesting, full-width saddle, packs, bolt groups and extra support rows require verification; capacities are not reassigned.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes'];support=par['purpose']=='support';pieces=ctx.ms[:-1] if support else ctx.ms
    webs=[];flanges=[]
    for i,m in enumerate(pieces):
        extract(ctx,m,'Z'+str(i),axes,26);polys=sections(m,p,ctx.c['point'],axes)
        w=max((q for q in polys if max(v[0] for v in q)-min(v[0] for v in q)<.2),key=lambda q:max(v[2] for v in q)-min(v[2] for v in q))
        f=min((q for q in polys if max(v[2] for v in q)-min(v[2] for v in q)<.2 and max(v[0] for v in q)-min(v[0] for v in q)>1),key=lambda q:min(v[2] for v in q))
        webs.append((min(v[0] for v in w),max(v[0] for v in w),min(v[2] for v in w),max(v[2] for v in w)))
        flanges.append((min(v[0] for v in f),max(v[0] for v in f),min(v[2] for v in f),max(v[2] for v in f)))
    left=min(w[0] for w in webs);right=max(w[1] for w in webs);bottom=max(w[2] for w in webs);top=min(w[3] for w in webs);mid=(bottom+top)/2;labels=['Z'+str(i) for i in range(len(pieces))]
    if not support:
        a.fastener('LAP',[[left,0,z] for z in (mid-2,mid+2)],[1,0,0],.5,right-left,labels,'A two1/2in A325 lap-end web bolts,4in gauge/1.5in end distance; S18in bolted lap',basis='A')
        a.title='AG PORTAL / ACTUAL18in Z LAP';a.section_axis=1;a.section_at=0
        return
    host=ctx.ms[-1];part=extract(ctx,host,'FRAME',axes,26);ht=p[p[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];face=max(q[2] for f in part['faces'] for q in f)
    ct=.375;a.box('SADDLE',[-5,-9.5,face],[10,19,ct],'A','A3/8in saddle across all six source frame flanges, local plate/bolt capacity unverified')
    _,bands=face_intervals(host,p,axes[2]);across=cross(unit(sub(*host['axis'][::-1])),axes[2]);ys=[]
    for lo,hi,t in bands:
        yy=(lo+hi)/2/(dot(across,axes[1]));ys.append(yy)
        a.fastener('SADDLE'+str(len(ys)),[[x,yy,face+ct] for x in (-4,4)],[0,0,-1],.5,ct+ht,['SADDLE','FRAME'],'A two1/2in saddle bolts into this actual flange; all six flanges connected',basis='A')
    assert len(ys)==6
    edge=par['edge'];yl=0 if edge>0 else -5 if edge<0 else -2.5;web_y=edge*2.5;foot_y=[yl+1,yl+4]
    a.box('CLIP-F',[left-3,yl,face+ct],[3,5,.25],'A','A1/4in anti-roll foot on real saddle')
    a.box('CLIP-W',[left-.25,yl,face+ct+.25],[.25,5,top-.25-face-ct-.25],'A','A1/4in anti-roll web leg, both Z plies restrained')
    a.interfaces.append(dict(id='FOLD',kind='formed_bend',connects=['CLIP-W','CLIP-F'],basis='A',description='One bent anti-roll clip, bend radius omitted'))
    a.fastener('WEB',[[left-.25,web_y,z] for z in (mid-2,mid+2)],[1,0,0],.5,.25+right-left,['CLIP-W',*labels],'A two1/2in Z-web bolts; source anti-roll restraint requirement retained',basis='A')
    a.fastener('FOOT',[[left-1.5,y,face+ct+.25] for y in foot_y],[0,0,-1],.5,.25+ct,['CLIP-F','SADDLE'],'A two1/2in clip/saddle bolts',basis='A')
    lo=max(f[0] for f in flanges)+.25;hi=min(f[1] for f in flanges)-.25
    if hi<=lo:raise ValueError('No common physical flange band at agricultural Z support')
    previous=face+ct;joined=['SADDLE',*labels]
    for i,f in enumerate(sorted(flanges,key=lambda f:f[2])):
        gap=f[2]-previous
        if gap< -1e-6:raise ValueError('Nested Z penetrates its real saddle')
        if gap>1e-6:
            tag='PACK'+str(i);a.box(tag,[lo,yl,previous],[hi-lo,5,gap],'A','A solid5in-long bearing pack under actual Z flange');joined.append(tag)
        previous=f[3]
    a.fastener('BEARING',[[.5*(lo+hi),y,previous] for y in foot_y],[0,0,-1],.5,previous-face,joined,'A two1/2in bolts through actual nested flanges, packs and saddle; S5in end bearing retained',basis='A')
    a.title='AG PORTAL / SIX-FLANGE Z SUPPORT';a.front_axes=(1,2);a.section_axis=1;a.section_at=web_y
    a.notes.append('The real six-channel frame supports the saddle through six distinct flange groups. The source5in bearing length is filled by solid packs. A saddle/clip dimensions, screw/bolt groups and unequal Z flange fit are proposals; the saved point-symmetric Z capacities do not verify these changes.')
