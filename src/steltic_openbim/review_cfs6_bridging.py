"""Located CFS6 cold-rolled channels, stud clips and diagonal row anchors."""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_receiver_geometry import extract,point,horizontal_frame
from .review_cfs_occurrences import axis as actual_axis
from .review_crossings import slot
from .pilots.geometry import strips

T=.0566;Z=[0,0,1]


def flange(member,profiles,along,near):
    u=[1,0,0] if along==0 else [0,1,0];n=cross(Z,u);y=member['local_y'];z=cross(Z,y);candidates=[]
    for poly in strips(profiles[member['profile_id']],profiles):
        xy=[[dot(add(mul(y,q[0]),mul(z,q[1])),v) for v in (u,n)] for q in poly]
        x0,x1=min(q[0] for q in xy),max(q[0] for q in xy);y0,y1=min(q[1] for q in xy),max(q[1] for q in xy)
        if x1-x0>.8 and y1-y0<.2 and y1>2.9:
            x=member['axis'][0][along]+(x0+x1)/2;candidates.append((abs(x-near),x,y1,y1-y0))
    if not candidates:raise ValueError('No actual exposed flange for CRC anchor '+member['id'])
    _,x,face,sheet=min(candidates);return x,face,sheet


def apply(b):
    if b.key!='cfs6':return
    rows={r['id']:r for r in b.raw['studs']};groups=defaultdict(list)
    for m in b.members:
        if m['kind']!='stud' or b.profiles[m['profile_id']]['family']!='channel':continue
        refs=[r for r in m['design_record_ids'] if r.startswith('studs/stud-')]
        if not refs:continue
        source=rows[refs[0].split('/',1)[1]];pitch=float(source['bridging_in']);u=m['local_y'];along=max(range(2),key=lambda i:abs(u[i]));normal=1-along
        if u[along]<.99:raise ValueError('CFS6 source stud roll needs an explicit bridging orientation')
        lo,hi=sorted(q[2] for q in actual_axis(m))
        groups[along,round(m['axis'][0][normal],6),m['level'],round(lo,6),round(hi,6),pitch].append(m)
    old={m['id'] for m in b.members if m['kind']=='stud_bridging'}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    crc=b.custom('CRC1.5X.5-54','channel',dict(d=1.5,b=.5,t=T,lip=0),basis='S:1.5 x .5 in54 mil source bridging')
    strap=b.custom('CRC-ANCHOR-1.5X54','flat',dict(width=1.5,thickness=T),basis='S:1.5 in x54 mil diagonal bridging anchor')
    tracks=[m for m in b.members if m['kind'] in ('bottom_track','ordinary_track','tier_track') and m['local_y'][2]>.99]
    chords=[m for m in b.members if m['kind'] in ('chord','opening_jamb')]
    b.endpoint_links=getattr(b,'endpoint_links',[]);placements=[];isolated=[]
    for index,(key,ms) in enumerate(sorted(groups.items())):
        along,station,k,bottom,top,maximum=key;u=[1,0,0] if along==0 else [0,1,0];n=cross(Z,u)
        ms.sort(key=lambda m:m['axis'][0][along]);runs=[]
        for m in ms:
            if not runs:runs.append([m]);continue
            a,d=runs[-1][-1]['axis'][0],m['axis'][0]
            barrier=any(v['level']==k and abs(v['axis'][0][1-along]-station)<.01 and a[along]<v['axis'][0][along]<d[along] for v in chords)
            if d[along]-a[along]>24.01 or barrier:runs.append([])
            runs[-1].append(m)
        for runid,run in enumerate(runs):
            if top-bottom<=maximum+.01:continue
            if len(run)<2:
                isolated.append(run[0]['id']);continue
            xs=[m['axis'][0][along] for m in run];grid=min(b-a for a,b in zip(xs,xs[1:]) if b-a>.01)
            if any(abs((x-xs[0])/grid-round((x-xs[0])/grid))>.001 for x in xs):raise ValueError('Irregular source CRC stud run')
            pitch=min(math.floor(maximum/grid)*grid,xs[-1]-xs[0])
            if pitch<grid-.01:raise ValueError('CRC source brace spacing smaller than stud grid')
            zs=[];z=bottom+pitch
            while z<top-1:zs.append(z);z+=pitch
            made=[];label=f'CRC-ACTUAL-{index}-{runid}'
            def q(x,z,offset=0):
                v=[x,station,z] if along==0 else [station,x,z];return add(v,mul(n,offset))
            for j,z in enumerate(zs):
                bridge=b.member(label+f'-ROW{j}',crc,'stud_bridging',q(xs[0]-.5,z,-.25),q(xs[-1]+.5,z,-.25),k,'S',local_y=n)
                made.append(bridge)
                for si,stud in enumerate(run):
                    origin=q(xs[si],z);sg=-1 if si==len(run)-1 else 1
                    slot(stud,origin,n,-.875,.875,.75,bridge['id'],'A fitted1.75 x.75 in web punch for source CRC; original selected section/design retained')
                    cid=bridge['id']+'-CLIP-'+str(si)
                    b.connection(cid,'review_angle_clip',origin,[bridge,stud],stud['design_record_ids'],parameters=dict(actual_crc=True,purpose='clip',direction=along,side=sg))
                    if si in (0,len(run)-1):b.endpoint_links.append(dict(member_id=bridge['id'],end='start' if si==0 else 'end',connection_id=cid,basis='Source CRC row end extends1/2 in beyond its actual end stud, with the located web clip; no unsupported remote end.'))
            # Source anchor spacing is at most8 ft, with both run ends present.
            anchor_indices=[0];last=xs[0]
            for i,x in enumerate(xs[1:-1],1):
                if x-last>=96-grid+.01:anchor_indices.append(i);last=x
            if anchor_indices[-1]!=len(run)-1:anchor_indices.append(len(run)-1)
            for j,(z,bridge) in enumerate(zip(zs,made)):
                for ai in anchor_indices:
                    upper=run[ai];x=xs[ai]+.75;sign=1 if x+pitch<=xs[-1]+.751 else -1
                    if j:
                        want=xs[ai]+sign*pitch;li=min(range(len(xs)),key=lambda i:abs(xs[i]-want))
                        if abs(xs[li]-want)>.01:raise ValueError('No real stud at source diagonal anchor foot')
                        lower=run[li];lowz=zs[j-1];lowx=xs[li]+.75;hostkind='stud'
                    else:
                        lowz=bottom+.65;lowx=x+sign*(z-lowz);candidates=[]
                        for track in tracks:
                            if track['level']!=k:continue
                            aa,dd=actual_axis(track)
                            if abs(aa[1-along]-station)>.01 or abs(dd[1-along]-station)>.01:continue
                            if min(aa[along],dd[along])+.25<=lowx<=max(aa[along],dd[along])-.25 and abs(aa[2]-bottom)<.5:candidates.append(track)
                        if not candidates:
                            isolated.append(upper['id']+':first-row-anchor');continue
                        lower=min(candidates,key=lambda m:m['id']);hostkind='track'
                    upperpoint=q(x,z,3.25+T/2);lowerpoint=q(lowx,lowz,3.25+T/2);v=unit(sub(upperpoint,lowerpoint));width=cross(n,v)
                    anchor=b.member(label+f'-ANCHOR-{j}-{ai}',strap,'bridging_anchor',lowerpoint,upperpoint,k,'S',records=upper['design_record_ids'],local_y=width)
                    anchor['end_offsets']=[mul(v,-1),mul(v,1)]
                    cid=anchor['id']+'-FIX';origin=q(x,z)
                    b.connection(cid,'review_angle_clip',origin,[anchor,upper,lower],upper['design_record_ids'],parameters=dict(actual_crc=True,purpose='anchor',direction=along,lower_kind=hostkind,pitch=pitch))
                    for end in ('start','end'):b.endpoint_links.append(dict(member_id=anchor['id'],end=end,connection_id=cid,basis='Both ends of this actual45-degree anchor strap are attached by the same two-end screw assembly.'))
            placements.append(dict(row_ids=[m['id'] for m in made],stud_ids=[m['id'] for m in run],source_maximum_spacing_in=maximum,adopted_spacing_in=pitch,anchor_stations_in=[xs[i] for i in anchor_indices]))
    # A short ordinary fragment beside a real chord/jamb still needs its own
    # brace. Terminate its CRC at that actual outer web; keep the chord's rod
    # pocket intact. Additional lower rows receive the45-degree straps.
    lookup={m['id']:m for m in b.members};completed=[]
    for si,mid in enumerate(isolated):
        if mid not in lookup:raise ValueError('Unlocated first-row anchor '+mid)
        stud=lookup[mid];along=max(range(2),key=lambda i:abs(stud['local_y'][i]));station=stud['axis'][0][1-along];k=stud['level'];u=[1,0,0] if along==0 else [0,1,0];n=cross(Z,u)
        bottom,top=sorted(q[2] for q in actual_axis(stud));maximum=float(rows[next(r for r in stud['design_record_ids'] if r.startswith('studs/stud-')).split('/',1)[1]]['bridging_in'])
        choices=[]
        for host in chords:
            aa,dd=actual_axis(host)
            if host['level']==k and abs(aa[1-along]-station)<.01 and min(aa[2],dd[2])<=bottom+.2 and max(aa[2],dd[2])>=top-.2:
                distance=abs(aa[along]-stud['axis'][0][along])
                if 4<distance<48:choices.append((distance,host['id'],host))
        if not choices:raise ValueError('Isolated source stud has no real end receiver '+mid)
        host=min(choices)[2];sx=stud['axis'][0][along]+.75;hx,_,_=flange(host,b.profiles,along,sx);drop=abs(hx-sx)
        if drop>maximum:raise ValueError('Isolated anchor exceeds source maximum brace spacing')
        def q(x,z,offset=0):return add([x,station,z] if along==0 else [station,x,z],mul(n,offset))
        heights=[];upper=[];zz=bottom+max(maximum,drop+3)
        while zz<top-1:upper.append(zz);heights.extend((zz,zz-drop));zz+=maximum
        if not upper:raise ValueError('Isolated stud needs an explicit short-row brace selection')
        for j,z in enumerate(sorted(set(round(v,6) for v in heights))):
            lo,hi=sorted((stud['axis'][0][along],host['axis'][0][along]));bridge=b.member(f'CRC-ISOLATED-{si}-{j}',crc,'stud_bridging',q(lo,z,-.25),q(hi,z,-.25),k,'S',local_y=n)
            for end,x in enumerate((lo,hi)):
                support=stud if abs(x-stud['axis'][0][along])<.01 else host;cid=bridge['id']+':'+str(end)
                b.connection(cid,'cfs_stud_bridging',q(x,z),[bridge,support],stud['design_record_ids'],parameters=dict(screw_count=2))
                b.endpoint_links.append(dict(member_id=bridge['id'],end='start' if end==0 else 'end',connection_id=cid,basis='Actual CRC end clip on the isolated stud or adjacent source chord/jamb outer web; no passage through the rod pocket.'))
        for j,z in enumerate(upper):
            a0,a1=q(hx,z-drop,3.25+T/2),q(sx,z,3.25+T/2);v=unit(sub(a1,a0))
            anchor=b.member(f'CRC-ISOLATED-{si}-ANCHOR{j}',strap,'bridging_anchor',a0,a1,k,'S',records=stud['design_record_ids'],local_y=cross(n,v));anchor['end_offsets']=[mul(v,-1),mul(v,1)];cid=anchor['id']+':FIX'
            b.connection(cid,'review_angle_clip',q(sx,z),[anchor,stud,host],stud['design_record_ids'],parameters=dict(actual_crc=True,purpose='anchor',direction=along,lower_kind='stud',pitch=maximum))
            for end in ('start','end'):b.endpoint_links.append(dict(member_id=anchor['id'],end=end,connection_id=cid,basis='Located45-degree short-run strap between two actual CRC row/flange stations; no invented chord centre web.'))
        completed.append(mid)
    b.changes.append(dict(kind='cfs6_actual_crc_bridging',removed_member_ids=sorted(old),runs=placements,isolated_members_completed=completed,unresolved_isolated_members=[],
        basis='S CRC,54 mil clips,twoNo10 screws and1.5 in54 mil45-degree anchors retained. A tighter rows where short runs require them, web punches, exact flange anchor stations and1/4 in face packing. Source anchorage stiffness/capacity must also cover the adopted stud-flange transfer path.'))
    b.note('CRC-BRIDGING','S:1.5 x.5 in54 mil CRC through stud web punches;54 mil clips with twoNo10 stud screws;1.5 in54 mil45-degree straps, twoNo10 each end, rows anchored at ends and at most8 ft. A: exact1.75 x.75 in punches, added CRC-side screws, closer rows at short segments, strap anchors on actual stud flanges/floor-track flanges with1/4 in face packing. The source brace-force and stiffness requirements remain; this adopted flange/clip transfer path has no new capacity verification.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=horizontal_frame([1,0,0] if par['direction']==0 else [0,1,0])
    if par['purpose']=='anchor':return anchor_detail(ctx,axes)
    bridge,stud=ctx.ms;extract(ctx,bridge,'CRC',axes,8);extract(ctx,stud,'STUD',axes,6)
    st=p[stud['profile_id']]['dimensions']['t'];sg=par['side'];x=sg*st/2;y=-.25+T/2;xx=min(x,x+sg*T)
    a.box('CLIP-STUD',[xx,y+T,-.75],[T,1.5-T,1.5],'S','Source54 mil clip leg at actual stud web; A1.5 in legs')
    a.box('CLIP-CRC',[min(x,x+sg*1.5),y,-.75],[1.5,T,1.5],'S','Source54 mil return on actual CRC web; A1.5 in legs')
    a.fastener('STUD-S',[[x+sg*T,v,0] for v in (.65,1.15)],[-sg,0,0],.19,T+st,['STUD','CLIP-STUD'],'S twoNo10 screws to each actual stud; A exact stations',screw=True)
    a.fastener('CRC-S',[[x+sg*v,y+T,0] for v in (.5,1.15)],[0,-1,0],.19,2*T,['CRC','CLIP-CRC'],'A twoNo10 CRC-side screws',basis='A',screw=True)
    a.weld('FOLD',[x,y+T,-.75],[x,y+T,.75],['CLIP-STUD','CLIP-CRC'],kind='BEND',basis='A',description='Continuous folded54 mil clip, not a weld')
    a.section_axis=2;a.section_at=0;a.front_axes=(0,1)
    a.notes.append('Source CRC passes through the actual stud web punch. No imaginary centre web is used. A punch dimensions and clip stations; source bracing checks/requirements retained.')


def anchor_detail(ctx,axes):
    a,p,par=ctx.a,ctx.p,ctx.params;strap,upper,lower=ctx.ms
    extract(ctx,strap,'STRAP',axes,150);extract(ctx,upper,'UPPER',axes,6);extract(ctx,lower,'LOWER',axes,150)
    ends=[point(q,ctx.c['point'],axes) for q in strap['axis']]
    for i,(q,host,label) in enumerate(((ends[0],lower,'LOWER'),(ends[1],upper,'UPPER'))):
        d=p[host['profile_id']]['dimensions']
        if host['kind'] in ('bottom_track','ordinary_track','tier_track'):sheet=d['t'];face=d['d']/2
        else:_,face,sheet=flange(host,p,par['direction'],ctx.c['point'][par['direction']]+q[0])
        gap=3.25-face
        if gap<0:raise ValueError('Anchor plane penetrates actual wall face')
        a.box('PACK'+str(i),[q[0]-.75,face,q[2]-.65],[1.5,gap,1.3],'A','A fitted face packing at actual source flange')
        a.fastener('END'+str(i),[[q[0]+v,3.25+T,q[2]] for v in (-.375,.375)],[0,-1,0],.19,T+gap+sheet,['STRAP',label,'PACK'+str(i)],'S twoNo10 anchor screws each end; A flange transfer/packing/stations',screw=True)
    a.section_axis=2;a.section_at=ends[1][2];a.dim(ends[0],ends[1],'Source45-degree anchor; A exact endpoint fit')
    a.notes.append('S strap width/thickness,45-degree inclination and twoNo10 screws each end. A attachment through actual stud/floor-track flange and fitted face packing; CRC force transfers through the nearby stud clip. The adopted local path needs the source strength/stiffness verification; none is inferred here.')
