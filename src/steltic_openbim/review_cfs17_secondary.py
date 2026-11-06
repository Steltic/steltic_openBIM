"""Finite garage Z rows, source laps and six-flange supports."""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .review_z_sections import folded
from .review_cfs25_secondary import sections
from .review_cfs_frame_straps import face_intervals

ROOF=((0,216),(300,270),(600,216),(816,252),(1032,216))
WORK=tuple(i*144 for i in range(19))
DOORS={2,5,8,11,14}
POST_ROWS=(126,174,300-24/math.sqrt(1+.18**2),300+24/math.sqrt(1+.18**2),426,474,720,768,864,912)
STATIONS=(16,36,84,126,174,222,252,284,316,350,378,426,474,522,564,584,616,636,684,720,768,800,832,864,912,960,996,1016)
STATIONS=tuple(sorted(set(STATIONS)|{300+sg*24/math.sqrt(1+.18**2) for sg in (-1,1)}|{816+sg*24/math.sqrt(1+(1/6)**2) for sg in (-1,1)}))


def roof_at(x):
    j=next(j for j,(a,d) in enumerate(zip(ROOF,ROOF[1:])) if a[0]<=x<=d[0])
    a,d=ROOF[j:j+2];slope=(d[1]-a[1])/(d[0]-a[0])
    return j,a[1]+(x-a[0])*slope,unit([1,0,slope])


def apply(b):
    if b.key!='cfs17':return
    removed={m['id'] for m in b.members if m['id'].startswith(('P-','G-')) or m['kind'] in ('flange_kicker','flange_cross_plate')}
    b.members[:]=[m for m in b.members if m['id'] not in removed]
    b.connections[:]=[c for c in b.connections if not removed.intersection(c['member_ids'])]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in removed]
    lookup={m['id']:m for m in b.members}
    rows=[('P',x,None) for x in STATIONS]+[('G',z,side) for side in (0,1) for z in (24,96,168)]
    for kind,station,side in rows:
        roof=kind=='P'
        if roof:
            segment,z,u=roof_at(station);base=[station,0,z]
        else:u=[0,0,1 if side==0 else -1];base=[1032*side,0,station]
        v=[0,1,0];n=cross(u,v);axes=(u,v,n);row={};offset=height=0.;previous=None
        indices=[j for j in range(18) if roof or side!=0 or j not in DOORS]
        for j in indices:
            if j-1 not in row:offset=height=0.;previous=None
            # Keep the source54mil post-top calculation separate where the
            # same end-bay member also falls in a source68mil snow zone.
            mil=68 if roof and (min(abs(station-r) for r in (300,816))<=204 or abs(station-600)<=96) else 54
            label='800Z250-'+str(mil);pid=folded(b,b.profile(label));d=b.profiles[pid]['dimensions'];t=d['t']
            if previous is not None:
                sign=1 if j%2 else -1;offset+=sign*(previous+t)/2;height+=sign*max(previous,t)
            centre=add(base,add(mul(u,offset),mul(n,8.125+d['d']/2+height)))
            lo=WORK[j]-(15 if j-1 in indices else 0);hi=WORK[j+1]+(15 if j+1 in indices else 0)
            if roof and station in POST_ROWS:
                if j==1:lo=0
                if j==16:hi=WORK[-1]
            tag=f'GAR-P-{station:g}-{j}' if roof else f'GAR-G-{side}-{station}-{j}'
            m=b.member(tag,pid,'purlin' if roof else 'girt',add(centre,mul(v,lo)),add(centre,mul(v,hi)),1,'A',local_y=mul(u,-1 if j%2 else 1),records=['schedules/sched-purlin' if roof else 'schedules/sched-girt'],lap_in=15,source_profile_id=label,
                physical_fit_basis='S nominal800Z section,12ft bays,15in laps each side and5in bearing. A unequal flange nesting, closer support stations, full-width saddle and solid bearing packs; local capacity unverified.')
            row[j]=m;previous=t
        low=min(dot(sub(axis(m)[0],base),n)-b.profiles[m['profile_id']]['dimensions']['d']/2 for m in row.values())
        for m in row.values():m['axis']=[add(q,mul(n,8.125-low)) for q in m['axis']]
        rid='schedules/sched-purlin' if roof else 'schedules/sched-girt'
        for i,s in enumerate(WORK):
            pieces=[m for m in row.values() if axis(m)[0][1]-1e-6<=s<=axis(m)[1][1]+1e-6]
            if not pieces:continue
            assert len(pieces) in (1,2)
            origin=add(base,[0,s,0]);pieces.sort(key=lambda m:dot(sub(axis(m)[0],origin),u))
            host=lookup[f'F{i+1}-R{segment}' if roof else f'F{i+1}-C{side}']
            left=i-1 in row;right=i in row;edge=0 if left and right else 1 if right else -1
            c=b.connection(f'GAR-{kind}-{side}-{station:g}-SUPPORT{i}','review_garage_z',origin,[*pieces,host],[rid],parameters=dict(actual_garage_z=True,axes=axes,purpose='support',roof=roof,edge=edge,post_kicker=roof and station in POST_ROWS and i in (0,18),source_clip=roof and abs(station-600)<=96))
            for m in pieces:
                for end in (0,1):
                    if abs(axis(m)[end][1]-s)<.01:b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual finite source end span or full nested end bay attached at its frame saddle.'))
            if len(pieces)!=2:continue
            for sign in (-1,1):
                owner=row.get(i if sign<0 else i-1);end=0 if sign<0 else 1
                if owner is None or abs(axis(owner)[end][1]-(s+sign*15))>.01:continue
                cc=b.connection(c['id']+'-LAP'+str(sign),'review_garage_z',add(origin,[0,sign*13.5,0]),pieces,[rid],parameters=dict(actual_garage_z=True,axes=axes,purpose='lap',roof=roof))
                b.endpoint_links.append(dict(member_id=owner['id'],end='start' if end==0 else 'end',connection_id=cc['id'],basis='Two actual nested-web bolts at the finite15in lap end; A gauge/1.5in end distance.'))
    b.note('GARAGE-Z-ROWS','S:800Z25054 field/girts;800Z25068 within17ft of ridges and8ft of valley;15in laps each side,5in bearing. Girts at2/8/14ft stop at door-bay frame columns. Nested end-bay purlins receive post-top kickers; source54mil post row and coincident68mil roof zone retained separately,68mil adopted in the overlap without reassigning capacity. A closer rows include both sides of each wind post and bracket stations; unequal flange fit, saddle, packs and local bolt groups. Source valley two1/2in clip bolts and two added end-post clip bolts are retained.')


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
        a.fastener('LAP',[[left,0,z] for z in (mid-2,mid+2)],[1,0,0],.5,right-left,labels,'A two1/2in A325 lap-end web bolts,4in gauge/1.5in end distance; S15in bolted lap',basis='A')
        a.title='GARAGE / ACTUAL15in Z LAP';a.section_axis=1;a.section_at=0
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
    web_rows=[web_y]
    if par.get('post_kicker'):web_rows=[yl+1.25,yl+3.75]
    source=par.get('post_kicker') or par.get('source_clip')
    a.fastener('WEB',[[left-.25,y,z] for y in web_rows for z in (mid-2,mid+2)],[1,0,0],.5,.25+right-left,['CLIP-W',*labels],('S two added end-post bolts plus two adopted normal clip bolts' if par.get('post_kicker') else 'S two1/2in valley clip bolts' if source else 'A two1/2in Z-web bolts')+'; A gauge and actual web grip',basis='S group / A fit' if source else 'A')
    a.fastener('FOOT',[[left-1.5,y,face+ct+.25] for y in foot_y],[0,0,-1],.5,.25+ct,['CLIP-F','SADDLE'],'A two1/2in clip/saddle bolts',basis='A')
    lo=max(f[0] for f in flanges)+.25;hi=min(f[1] for f in flanges)-.25
    if hi<=lo:raise ValueError('No common physical flange band at garage Z support')
    previous=face+ct;joined=['SADDLE',*labels]
    for i,f in enumerate(sorted(flanges,key=lambda f:f[2])):
        gap=f[2]-previous
        if gap< -1e-6:raise ValueError('Nested Z penetrates its real saddle')
        if gap>1e-6:
            tag='PACK'+str(i);a.box(tag,[lo,yl,previous],[hi-lo,5,gap],'A','A solid5in-long bearing pack under actual Z flange');joined.append(tag)
        previous=f[3]
    a.fastener('BEARING',[[.5*(lo+hi),y,previous] for y in foot_y],[0,0,-1],.5,previous-face,joined,'A two1/2in bolts through actual nested flanges, packs and saddle; S5in end bearing retained',basis='A')
    a.title='GARAGE / SIX-FLANGE Z SUPPORT';a.front_axes=(1,2);a.section_axis=1;a.section_at=web_y
    a.notes.append('The real six-channel frame supports the saddle through six distinct flange groups. The source5in bearing length is filled by solid packs. A saddle/clip dimensions, screw/bolt groups and unequal Z flange fit are proposals; the saved point-symmetric Z capacities do not verify these changes.')
