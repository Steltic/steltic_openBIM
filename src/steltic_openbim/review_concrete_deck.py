"""Located CFS4 deck fasteners and blocking, with explicit fictional fit.

The source specifies deck-to-blocking screws at six inches, but no blocking
section, screw diameter or rib set-out. Those are accepted geometry, not a
manufacturer's deck selection or a new connection capacity calculation.
"""
import math
from collections import defaultdict
from shapely.geometry import LineString, Polygon, box
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .pilots.model import add, sub
from .pilots.geometry import extrude

BT=.0566
DT=.036
GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def interval(member,along):
    return sorted(q[along] for q in axis(member))


def apply(b):
    if b.key!='cfs4':return
    records=[r for r in b.records.values() if r['table']=='collectors']
    if any('deck screwed to the blocking track at 6 in.' not in r['data']['selection'] for r in records):
        raise ValueError('Unrecognized source deck attachment schedule')
    pid=b.profile('600T150-54');depth=b.depth(pid)
    joists=[m for m in b.members if m['kind']=='joist' and m['level'] in (1,2,3)]
    panels={p['level']:p for p in b.panels if p['kind']=='deck'}
    openings={o['id']:o for o in b.openings};counts=defaultdict(int)
    xblocks=[];new=[]
    for level,panel in panels.items():
        panel['accepted_rib_fit']=dict(pitch_in=6,valley_centres_x_modulo_in=3,
            valley_flat_width_in=1.5,upper_flat_width_in=3,sheet_thickness_in=DT,
            basis='A geometry only: 1.5 in overall source depth, 20 ga source designation, adopted0.036 in sheet and6 in ribs along Y. Valley fixing lines at X=3+6n. Manufacturer rib shape, seams and structural approval remain requirements.')
        top=panel['vertices'][0][2]-1.5
        panel['representation']='Source deck-depth boundary and accepted rib/attachment set-out; local detail extracts show the actual adopted thin valley ply, not a1.5 in solid steel plate'
        low=[min(q[i] for q in panel['vertices']) for i in (0,1)]
        high=[max(q[i] for q in panel['vertices']) for i in (0,1)]
        available=[m for m in joists if m['level']==level]
        # Longitudinal blocking is beside each real wall-line joist. At the
        # north edge it is back-to-back; elsewhere a folded web link bridges
        # the actual clear distance beyond the joist flange.
        for r in (r for r in records if r['data']['direction']=='X'):
            station=next(q['pos']*12 for q in b.cfg['lines_x'] if q['name']==r['data']['line'])
            selected=[m for m in available if abs(axis(m)[0][1]-station)<.01 and abs(m['local_y'][1]-1)<.01]
            if not selected:raise ValueError('No actual source joist at '+r['id'])
            for host in selected:
                hd=b.profiles[host['profile_id']]['dimensions'];aa,dd=axis(host)
                if abs(aa[2]+hd['d']/2-top)>.005:raise ValueError('Deck blocking bearing datum differs from its actual joist')
                inward=-1 if abs(station-high[1])<.01 else 1
                cross=station-(hd['t']+BT)/2 if inward<0 else station+hd['b']+.2
                lo,hi=interval(host,0);lo+=.5;hi-=.5
                block=b.member(host['id']+'-DECK-BLOCK',pid,'deck_blocking',
                    [lo,cross,top-depth/2],[hi,cross,top-depth/2],level,'A',records=[r['id']],local_y=[0,inward,0],
                    source_schedule='S deck screws at6 in; A600T150-54 blocking and all exact locations',host_joist_id=host['id'])
                xblocks.append(block);new.append((block,panel,r))
                n=max(1,math.ceil((hi-lo-5)/24))
                for j in range(n+1):
                    x=lo+2.5+(hi-lo-5)*j/n
                    c=b.connection(block['id']+'-LINK'+str(j),'review_deck_block_link',[x,cross,top-3],
                        [block,host],[r['id']],parameters=dict(purpose='parallel',back_to_back=inward<0,deck_bottom_in=top),
                        title='A BLOCKING / ACTUAL JOIST WEB LINK')
                    if j in (0,n):b.endpoint_links.append(dict(member_id=block['id'],end='start' if j==0 else 'end',connection_id=c['id'],basis='Actual blocking end attached to the real joist; intermediate links are at no more than24 in. A fit, capacity unverified.'))
                    counts['parallel_links']+=1
        # Transverse blocks occupy the clear interval between actual joists.
        # At a crossing, they terminate clear of the longitudinal blocking and
        # attach to its web, rather than occupying the same steel volume.
        for r in (r for r in records if r['data']['direction']=='Y'):
            station=next(q['pos']*12 for q in b.cfg['lines_y'] if q['name']==r['data']['line'])
            inward=-1 if abs(station-high[0])<.01 else 1
            cross=station+inward*2.25
            by_y={}
            for m in available:
                lo,hi=interval(m,0)
                if lo+.1<cross<hi-.1:by_y.setdefault(round(axis(m)[0][1],7),m)
            ordered=sorted(by_y.items())
            for j,((yl,left),(yr,right)) in enumerate(zip(ordered,ordered[1:])):
                if yr-yl>12.01:raise ValueError('Deck blocking needs an explicit receiver across the interrupted joist run')
                receivers=[left,right];limits=[]
                for end,host in enumerate(receivers):
                    hd=b.profiles[host['profile_id']]['dimensions'];y=axis(host)[0][1]
                    candidates=[v for v in xblocks if v['level']==level and v.get('host_joist_id')==host['id'] and interval(v,0)[0]<cross<interval(v,0)[1]]
                    if candidates:
                        candidate=candidates[0];cy=axis(candidate)[0][1];direction=candidate['local_y'][1]
                        near=cy+(1.5-BT/2 if direction>0 else -BT/2)
                        far=cy+(-BT/2 if direction>0 else -1.5+BT/2)
                        if (end==0 and near>y+hd['b']-hd['t']/2) or (end==1 and far<y-hd['t']/2):
                            host=candidate;receivers[end]=host;hd=b.profiles[host['profile_id']]['dimensions'];y=cy
                    direction=host['local_y'][1]
                    if end==0:limits.append(y+(hd['b']-hd['t']/2 if direction>0 else hd['t']/2)+.125)
                    else:limits.append(y+(-hd['t']/2 if direction>0 else -hd['b']+hd['t']/2)-.125)
                lo,hi=limits
                if hi-lo<4:raise ValueError('No room for the accepted transverse blocking and its end clips')
                block=b.member(f'DECK-BLOCK-L{level}-{r["data"]["line"]}-{j}',pid,'deck_blocking',
                    [cross,lo,top-depth/2],[cross,hi,top-depth/2],level,'A',records=[r['id']],local_y=[inward,0,0],
                    source_schedule='S deck screws at6 in; A600T150-54 blocking between the actual joists',source_wall_line=r['data']['line'])
                new.append((block,panel,r))
                for end,host in enumerate(receivers):
                    c=b.connection(block['id']+'-END'+str(end),'review_deck_block_link',axis(block)[end],
                        [block,host],[r['id']],parameters=dict(purpose='transverse',end=end,deck_bottom_in=top),
                        title='A BLOCKING END / REAL RECEIVER WEB')
                    b.endpoint_links.append(dict(member_id=block['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Finite block cut clear of the actual receiving flange; located folded end clip with twoNo12 screws per leg. A fit, capacity unverified.'))
                    counts['transverse_links']+=1
        for block,host,r in [row for row in new if row[1] is panel]:
            aa,dd=axis(block);along=0 if abs(dd[0]-aa[0])>abs(dd[1]-aa[1]) else 1
            lo,hi=interval(block,along);normal=1-along;sign=block['local_y'][normal]
            fixed=aa[normal]+sign*.75
            if along==0:values=[3+6*n for n in range(math.ceil((lo+.4-3)/6),math.floor((hi-.4-3)/6)+1)]
            else:
                n=max(1,math.ceil((hi-lo-.8)/6));values=[lo+.4+(hi-lo-.8)*j/n for j in range(n+1)]
            if not values:raise ValueError('Deck block has no physical fixing station')
            for start in range(0,len(values),6):
                stations=values[start:start+6];points=[]
                for v in stations:
                    q=[v,fixed,top+DT] if along==0 else [fixed,v,top+DT]
                    if not all(low[i]+.2<q[i]<high[i]-.2 for i in (0,1)):raise ValueError('Deck screw is outside the actual floor edge')
                    for oid in panel.get('openings',[]):
                        o=openings[oid]
                        if o['x_ft']*12-.15<q[0]<(o['x_ft']+o['width_ft'])*12+.15 and o['y_ft']*12-.15<q[1]<(o['y_ft']+o['height_ft'])*12+.15:raise ValueError('Deck screw is in an actual floor opening')
                    if abs((q[0]-3)/6-round((q[0]-3)/6))>.001:raise ValueError('Deck fixing misses the accepted valley centre')
                    points.append(q)
                origin=[sum(p[i] for p in points)/len(points) for i in range(3)]
                b.connection(block['id']+'-SCREWS'+str(start//6),'review_deck_screws',origin,[block],[r['id']],
                    parameters=dict(host_panel_id=panel['id'],points_relative=[sub(p,origin) for p in points],deck_bottom_in=top,source_pitch_in=6),
                    title='S DECK SIX-INCH SCHEDULE / A FIXING FIT')
                counts['deck_screws']+=len(points)
        panel['attachment_schedule']=dict(source_records=[r['id'] for r in records],maximum_pitch_in=6,
            blocking_member_ids=[row[0]['id'] for row in new if row[1] is panel],
            basis='S six-inch deck-to-blocking schedule on each collector line. A600T150-54 blocking, No12 screws, clip positions and accepted valley set-out; manufacturer fastening evaluation and local capacity are unverified.')
    # All components of the source diaphragm selection now have explicit
    # physical occurrences. The source records and numerical checks are intact.
    rid='diaphragms/diaphragm-floors'
    for panel in b.panels:
        if panel['kind']=='floor':
            if not panel.get('reinforcement_design_mat') or not panel.get('perimeter_chord_design'):raise ValueError('Do not bind an incomplete diaphragm selection')
            panel['design_record_ids']=sorted(set(panel['design_record_ids']+[rid]))
    b.used_records.add(rid)
    b.changes.append(dict(kind='source_deck_blocking_and_fixings',counts=dict(counts),blocking_count=len(new),
        basis='Source six-inch schedule retained. Every accepted block and fastener is located on its actual floor/joist receivers; no new deck, connection or concrete capacity approval.'))
    b.note('DECK-BLOCKING','S:1.5 in20 ga composite deck, with deck-to-blocking screws at6 in along every collector line. A:600T150-54 blocking; No12 screws; two screws per folded clip leg; parallel links at24 in maximum; exact end cuts and rib phase. The accepted6 in rib pitch and0.036 in sheet are fictional set-out, not a manufacturer product approval. Detailed valley plies belong to the actual deck panel. Manufacturer seams, evaluation report and connection capacity remain explicit requirements. All source numerical checks remain unchanged.')


def draw(ctx):
    a=ctx.a;par=ctx.params;origin=ctx.c['point'];block=ctx.ms[0]
    local=lambda q:sub(q,origin)
    def brick(label,lo,hi,description):
        left=[min(x,y) for x,y in zip(lo,hi)];right=[max(x,y) for x,y in zip(lo,hi)]
        return a.box(label,local(left),sub(right,left),'A',description)
    if ctx.family=='review_deck_screws':
        points=[add(origin,q) for q in par['points_relative']]
        extent=max(math.dist(p,origin) for p in points)+2
        extract(ctx,block,'BLOCK',GLOBAL,extent)
        x0=min(p[0] for p in points)-.4;x1=max(p[0] for p in points)+.4
        y0=min(p[1] for p in points)-.25;y1=max(p[1] for p in points)+.25
        bottom=par['deck_bottom_in'];profile=[]
        for n in range(math.floor((x0-3)/6)-1,math.ceil((x1-3)/6)+2):
            v=3+6*n
            profile.extend([(v-3,bottom+1.5-DT/2),(v-1.5,bottom+1.5-DT/2),(v-.75,bottom+DT/2),
                            (v+.75,bottom+DT/2),(v+1.5,bottom+1.5-DT/2)])
        shape=LineString(profile).buffer(DT/2,cap_style=2,join_style=2).intersection(box(x0,bottom,x1,bottom+1.5))
        faces=extrude([[x,-z] for x,z in list(shape.exterior.coords)[:-1]],[0,y0,0],[0,y1,0],[1,0,0])
        deck=a.part('DECK','Actual host deck / A rib and thin valley ply; local context extract',[[local(q) for q in f] for f in faces],'A','deck')
        deck.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True)
        a.fastener('SCREWS',[local(p) for p in points],[0,0,-1],.216,DT+BT,['DECK','BLOCK'],
            'S six-inch maximum schedule; A No12 screw diameter and accepted rib stations',basis='A',screw=True)
        a.section_axis=1;a.section_at=round(points[len(points)//2][1]-origin[1],6);a.front_axes=(0,2)
        a.notes.append('S20 ga,1.5 in deck depth and6 in maximum blocking screw schedule. A0.036 in sheet,6 in rib pitch, No12 size and exact valley locations. Deck is clipped host context, not a1.5 in solid steel plate. Manufacturer evaluation, sheet seams and capacity remain unverified.')
        return
    host=ctx.ms[1];hd=ctx.p[host['profile_id']]['dimensions'];top=par['deck_bottom_in']
    extract(ctx,block,'BLOCK',GLOBAL,10);extract(ctx,host,'HOST',GLOBAL,10)
    z0=top-4;z1=top-1.5
    if par['purpose']=='parallel':
        x=origin[0];by=axis(block)[0][1];hy=axis(host)[0][1]
        if par['back_to_back']:
            points=[[x+dx,by-BT/2,top-3] for dx in (-.75,.75)]
            a.fastener('WEB',[local(p) for p in points],[0,1,0],.216,BT+hd['t'],['BLOCK','HOST'],'A twoNo12 screws through touching actual webs',basis='A',screw=True)
        else:
            left=hy+hd['t']/2;right=by-BT/2
            brick('LINK1',[x-1.5,left,z0],[x+1.5,left+BT,z1],'A54 mil folded link / joist leg')
            brick('LINK2',[x-1.5,right-BT,z0],[x+1.5,right,z1],'A54 mil folded link / blocking leg')
            brick('LINK3',[x-1.5,left+BT,z1-BT],[x+1.5,right-BT,z1],'A54 mil folded bridge; same continuous sheet')
            for ident,y,targets in [('FJ',hy-hd['t']/2,['HOST','LINK1']),('FB',right-BT,['LINK2','BLOCK'])]:
                grip=hd['t']+BT if ident=='FJ' else 2*BT
                a.fastener(ident,[local([x+dx,y,top-3]) for dx in (-.75,.75)],[0,1,0],.216,grip,targets,'A twoNo12 screws per folded link leg',basis='A',screw=True)
        a.section_axis=0;a.section_at=0;a.front_axes=(0,2)
    else:
        end=par['end'];sign=1 if end==0 else -1;inward=block['local_y'][0]
        bx=axis(block)[0][0];hy=axis(host)[0][1]
        face=hy+sign*hd['t']/2;xf=bx+inward*BT/2
        cut=axis(block)[end][1];far=cut+sign*2.5
        brick('CLIP1',[xf,face,z0],[xf+inward*BT,far,z1],'A54 mil folded end clip / blocking leg')
        brick('CLIP2',[xf+inward*BT,face,z0],[xf+inward*3,face+sign*BT,z1],'A54 mil folded end clip / receiving-web leg')
        for j,z in enumerate((top-3.5,top-2.5)):
            a.fastener('BF'+str(j),[local([bx-inward*BT/2,cut+sign*1.5,z])],[inward,0,0],.216,2*BT,['BLOCK','CLIP1'],'A No12 screw to actual block web',basis='A',screw=True)
            a.fastener('HF'+str(j),[local([xf+inward*1.5,hy-sign*hd['t']/2,z])],[0,sign,0],.216,hd['t']+BT,['HOST','CLIP2'],'A No12 screw to actual receiving web',basis='A',screw=True)
        a.section_axis=2;a.section_at=top-3.5-origin[2];a.front_axes=(0,2)
    a.notes.append('A600T150-54 blocking and54 mil folded clips are finite physical pieces on these actual receivers. TwoNo12 screws per leg; source steel members remain unchanged. Set-out and clip capacity are unverified. S deck-to-blocking six-inch fixing schedule is detailed separately.')
