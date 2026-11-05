"""Scheduled chord block packs and real interruptions in floor framing.

The checked row, section/count and nominal block length are retained. Packing,
clearances and formed clip geometry are explicit accepted example inputs.
"""
import copy,math,re
from collections import defaultdict
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame,point
from .pilots.model import add,sub,mul,unit,cross,dot
from .pilots.geometry import strips,member_faces

RECORD='framing/chord-squash-floor'


def profile(b,row,above):
    from .review_cfs import physical_pack
    from .review_profile_fit import separate_plies
    name=f'FLOOR-PACK-{row["line"]}-L{row["level"]}'
    if name in b.profiles:return name
    pid=physical_pack(b,row['blocks'],name);p=b.profiles[pid]
    # Preserve the open tie-rod cavity used by the upper chord. The outside
    # plies move only for their actual sheet thickness; all selected plies stay.
    if p['family']=='built_up':
        for i,c in enumerate(p['components']):
            d=b.profiles[c['profile_id']]['dimensions'];sign=-1 if i%2==0 else 1;layer=i//2
            shift=0 if layer==0 else d['t']+.02 if layer==1 else d['t']+.02+2*d['b']-.25
            c.update(offset=[sign*(2+d['t']/2+shift),0],rotation_deg=(0 if sign<0 else 180) if layer!=1 else (180 if sign<0 else 0))
        separate_plies(b.profiles,p)
    p['source_selection']=copy.deepcopy(row)
    p['basis']='S exact scheduled floor block plies; A open rod cavity and separated ply fit'
    return pid


def apply(b):
    if b.key!='cfs6':return
    rows={(r['line'],r['level']):r for r in b.records[RECORD]['data']['rows']}
    tracks=defaultdict(list);floors=defaultdict(list);lookup={m['id']:m for m in b.members}
    for m in b.members:
        if m['kind'] in ('top_track','bottom_track','ordinary_track','tier_track'):
            along=max(range(2),key=lambda i:abs(m['axis'][1][i]-m['axis'][0][i]))
            tracks[m['level'],along,round(m['axis'][0][1-along],6),1 if m['local_y'][2]>0 else -1].append(m)
        if m['kind'] in ('joist','rim_track') and m['level']<5:
            aa,dd=axis(m);ma=max(range(2),key=lambda i:abs(dd[i]-aa[i]));mn=1-ma
            d=b.profiles[m['profile_id']]['dimensions'];ly=m['local_y'][mn]
            ends=sorted((aa[mn]-ly*d['t']/2,aa[mn]+ly*(d['b']-d['t']/2)))
            floors[m['level']].append((m,aa,dd,ma,mn,ends))
    packs=[];cuts=defaultdict(list)
    for above in list(b.members):
        if above['kind']!='chord' or above['level']<=1:continue
        k=above['level']-1;line=above['id'].split('-L')[0];row=rows[line,k]
        along=max(range(2),key=lambda i:abs(above['local_y'][i]));normal=1-along;origin=above['axis'][0]
        selected=[]
        for level,sign in ((k,-1),(k+1,1)):
            options=[t for t in tracks[level,along,round(origin[normal],6),sign]
                     if min(q[along] for q in axis(t))-.01<=origin[along]<=max(q[along] for q in axis(t))+.01]
            if not options:raise ValueError('Source chord pack has no actual bearing track '+above['id'])
            selected.append((max if sign<0 else min)(options,key=lambda t:axis(t)[0][2]))
        lower,upper=selected;bottom=axis(lower)[0][2]+b.profiles[lower['profile_id']]['dimensions']['t']/2
        length=row['block_length_in'];actual=10.1132 if length==10.11 else length
        a0=list(origin);a1=list(origin);a0[2]=bottom;a1[2]=bottom+actual
        block=b.member(above['id']+'-FLOOR-PACK',profile(b,row,above),'chord_squash_pack',a0,a1,k,'S',local_y=above['local_y'],
            records=[RECORD],source_row=copy.deepcopy(row),supported_chord_id=above['id'],
            physical_fit_basis='S scheduled pack section/count and nominal10.00/10.11 in length. A10.1132 in actual rim fit, open rod cavity, finish-depth steel packing and local clips; no new capacity check.')
        c=b.connection(block['id']+'-BEARING','review_chord_floor_pack',a0,[block,lower,upper,above],[RECORD],
            parameters=dict(actual_chord_floor=True,purpose='bearing',direction=along,source_length=length))
        for end in ('start','end'):b.endpoint_links.append(dict(member_id=block['id'],end=end,connection_id=c['id'],basis='Scheduled short pack bears on the real lower top track and supports the upper bottom track through an explicit steel fit pack.'))
        coords=[v for poly in strips(b.profiles[block['profile_id']],b.profiles) for v in poly]
        bb=[[min(v[i] for v in coords),max(v[i] for v in coords)] for i in (0,1)]
        world=[[origin[i]+bb[0 if i==along else 1][0],origin[i]+bb[0 if i==along else 1][1]] for i in (0,1)]
        packs.append(block)
        for m,aa,dd,ma,mn,ends in floors[k]:
            # The source expressly interrupts BOTH parallel joists, although
            # their webs stand one inch outside the pack's six-inch wall face.
            paired=m.get('parallel_wall_line')==line and ma==along
            rim=m['kind']=='rim_track' and ma==along and abs(aa[normal]-origin[normal])<=4
            crosses=ma!=along and min(ends[1],world[mn][1])>max(ends[0],world[mn][0])+.01
            if not (paired or rim or crosses):continue
            low,high=world[ma][0]-.25,world[ma][1]+.25
            if min(high,max(aa[ma],dd[ma]))-max(low,min(aa[ma],dd[ma]))>.01:cuts[m['id']].append((low,high,block['id']))
    split_floors(b,cuts,lookup)
    b.changes.append(dict(kind='source_cfs6_chord_floor_packs',packs=[m['id'] for m in packs],interrupted_members=len(cuts),
        basis='S each line/storey row, whole-footprint bearing requirement, paired-joist/rim interruptions and54mil/fourNo10 cut-end clips. A ply layout,1/4in cut clearances, formed offset clips and finish-datum steel packing. Source loads/capacities retained without redesign.'))
    b.note('CHORD-FLOOR-PACKS','S: every upper chord has its scheduled floor squash pack; both parallel joists and both rims are interrupted where applicable. A:10.1132 in actual tight rim fit for the source10.11 in nominal,1/4 in cut clearance, formed54mil offset clips with fourNo10 each attachment leg, and steel packing beneath the unchanged upper-wall datum. Whole-footprint bearing and the source diaphragm transfer requirements are retained; local fitting and revised clip shape are not capacity approvals.')


def split_floors(b,cuts,lookup):
    replacements={};cut_ends=[];removed_blocks=set();deleted_connections=set()
    for mid,intervals in cuts.items():
        old=lookup[mid];aa,dd=axis(old);along=max(range(2),key=lambda i:abs(dd[i]-aa[i]));lo,hi=aa[along],dd[along]
        if hi<=lo:raise ValueError('Floor cut requires the actual ascending source axis')
        merged=[]
        for a,d,pack in sorted(intervals):
            if merged and a<merged[-1][1]:
                if d>merged[-1][1]:merged[-1]=(merged[-1][0],d,merged[-1][2],pack)
            else:merged.append((a,d,pack,pack))
        spans=[];start=lo;left=None
        for a,d,first,last in merged:
            if a>start+.05:spans.append((start,min(a,hi),left,first))
            start=max(start,d);left=last
        if start<hi-.05:spans.append((start,hi,left,None))
        discarded=[(a,d) for a,d,_,_ in spans if d-a<3]
        if discarded:b.changes.append(dict(kind='omit_unbuildable_floor_cut_remnant',member_id=mid,intervals=discarded,
            basis='A remove less-than3in end offcuts beside the source chord-pack interruption; the retained span connects directly to that actual pack. Original unsplit source workline is retained.'))
        spans=[span for span in spans if span[1]-span[0]>=3]
        if not spans:raise ValueError('Chord pack removes a whole floor member '+mid)
        pieces=[]
        for i,(start,end,left,right) in enumerate(spans):
            piece=copy.deepcopy(old);piece['id']=mid if i==0 else mid+f'-CUT{i}'
            piece['axis']=copy.deepcopy([aa,dd]);piece['axis'][0][along]=start;piece['axis'][1][along]=end;piece['end_offsets']=[[0,0,0],[0,0,0]]
            piece.update(source_unsplit_member_id=mid,source_unsplit_axis=copy.deepcopy(old['axis']),source_floor_cut=True)
            pieces.append(piece)
            for end_index,block in ((0,left),(1,right)):
                if block:cut_ends.append((piece,end_index,block))
        replacements[mid]=pieces
    def containing(mid,q,tolerance=.02):
        choices=replacements.get(mid)
        if not choices:return lookup[mid]
        along=max(range(2),key=lambda i:abs(choices[0]['axis'][1][i]-choices[0]['axis'][0][i]))
        return next((m for m in choices if m['axis'][0][along]-tolerance<=q[along]<=m['axis'][1][along]+tolerance),None)
    for block in b.members:
        host=block.get('host_joist_id')
        if host not in replacements:continue
        chosen=containing(host,block['axis'][0])
        if chosen:block['host_joist_id']=chosen['id']
        else:removed_blocks.add(block['id'])
    new_connections=[]
    for c in b.connections:
        if any(mid in removed_blocks for mid in c['member_ids']):deleted_connections.add(c['id']);continue
        mids=[];invalid=False
        for mid in c['member_ids']:
            if mid not in replacements:mids.append(mid);continue
            actual=containing(mid,c['point'],1)
            if actual is None:invalid=True;break
            mids.append(actual['id'])
        if invalid:
            deleted_connections.add(c['id']);continue
        c['member_ids']=list(dict.fromkeys(mids));new_connections.append(c)
    b.connections[:]=new_connections
    b.members[:]=[m for m in b.members if m['id'] not in replacements and m['id'] not in removed_blocks]+[m for pieces in replacements.values() for m in pieces]
    now={m['id']:m for m in b.members}
    for m in b.members:
        if 'source_squash_member_ids' in m:
            m['source_squash_member_ids']=[bid for bid in m['source_squash_member_ids'] if bid in now and now[bid].get('host_joist_id')==m['id']]
    links=[]
    for link in b.endpoint_links:
        if link['member_id'] in removed_blocks or link['connection_id'] in deleted_connections:continue
        if link['member_id'] in replacements:
            choices=replacements[link['member_id']];link=dict(link,member_id=choices[0 if link['end']=='start' else -1]['id'])
        links.append(link)
    b.endpoint_links=links
    for piece,end,block in cut_ends:
        q=piece['axis'][end];cid=piece['id']+f'-PACK-END{end}'
        c=b.connection(cid,'review_chord_floor_clip',q,[piece,now[block]],[RECORD],parameters=dict(actual_chord_floor=True,purpose='clip',end=end))
        b.endpoint_links.append(dict(member_id=piece['id'],end='start' if end==0 else 'end',connection_id=cid,basis='This actual cut floor-member end clips to the scheduled chord block pack.'))
    b.changes.append(dict(kind='physical_floor_members_cut_at_source_chord_packs',
        split_members={mid:[dict(id=m['id'],axis=m['axis']) for m in pieces] for mid,pieces in replacements.items()},
        superseded_block_ids=sorted(removed_blocks),superseded_connection_ids=sorted(deleted_connections),
        basis='Actual separate floor pieces, not disconnected solids hidden behind one member. Existing source selections and unsplit worklines retained. Generic end hardware inside the cut is replaced by the located source clip.'))


def draw(ctx):
    if ctx.params['purpose']=='clip':return draw_clip(ctx)
    a=ctx.a;block,lower,upper,above=ctx.ms;axes=horizontal_frame(block['local_y'])
    bp=extract(ctx,block,'PACK',axes,20);lp=extract(ctx,lower,'LOWER',axes,16);up=extract(ctx,upper,'UPPER',axes,16);extract(ctx,above,'CHORD',axes,16)
    gap=up['bounds'][2][0]-bp['bounds'][2][1]
    if gap<-.001:raise ValueError('Source floor pack collides with upper track')
    # Separate cap strips retain the continuous central tie-rod opening.
    profile=ctx.p[block['profile_id']];groups=defaultdict(list)
    for poly in strips(profile,ctx.p):
        side=-1 if sum(v[0] for v in poly)/len(poly)<0 else 1;groups[side].extend(poly)
    caps=[]
    for side,points in groups.items():
        x0,x1=min(v[0] for v in points),max(v[0] for v in points);y0,y1=min(v[1] for v in points),max(v[1] for v in points)
        tag='UPPER-PACK'+str(side)
        if gap>.001:a.box(tag,[x0,y0,bp['bounds'][2][1]],[x1-x0,y1-y0,gap],'A','A separate steel bearing cap over the actual source ply footprint; central rod cavity stays open');caps.append(tag)
    a.interfaces.append(dict(id='LOWER-BEAR',kind='compression_bearing',connects=['PACK','LOWER'],basis='S',description='Scheduled pack bears directly on the real lower top track; joist/rim are interrupted, not used as web-bearing blocks'))
    a.interfaces.append(dict(id='UPPER-BEAR',kind='compression_bearing',connects=['PACK','UPPER']+caps,basis='A',description='Upper track bears through explicit steel finish-datum packing on both source pack halves; rod cavity remains clear'))
    a.dim([bp['bounds'][0][0],0,bp['bounds'][2][0]],[bp['bounds'][0][0],0,bp['bounds'][2][1]],f'{ctx.params["source_length"]:.2f} in source nominal; actual fit shown',basis='S')
    a.section_axis=2;a.section_at=sum(bp['bounds'][2])/2;a.front_axes=(0,2)


def draw_clip(ctx):
    """A formed54mil clip closes real web offsets; fourNo10 on each leg."""
    from .review_located_wall_details import section_bounds
    a=ctx.a;joist,block=ctx.ms;aa,dd=axis(joist);end=ctx.params['end'];toward=unit(sub((aa,dd)[1-end],(aa,dd)[end]))
    axes=horizontal_frame(toward);jp=extract(ctx,joist,'FLOOR',axes,16);bp=extract(ctx,block,'PACK',axes,20)
    jt=ctx.p[joist['profile_id']]['dimensions']['t'];t=.0566
    # In this frame the real joist web is y=0. A channel ply of the block
    # provides either a parallel flange or a perpendicular web.
    polygons=section_bounds(ctx.p,bp['member']);choices=[]
    for box in polygons:
        dx=box[0][1]-box[0][0];dy=box[1][1]-box[1][0]
        if dx<.3 and dy>.6:choices.append((abs(sum(box[0])/2),0,box))
        if dy<.3 and dx>.6:choices.append((abs(sum(box[1])/2),1,box))
    if not choices:raise ValueError('Chord block has no real sheet for cut-end clip')
    # Favour the near face but keep every selected screw inside actual sheet.
    _,thin,box=min(choices,key=lambda row:(row[0],row[1]))
    zlo=max(jp['bounds'][2][0],bp['bounds'][2][0])+1.25;zhi=min(jp['bounds'][2][1],bp['bounds'][2][1])-1.25
    if zhi-zlo<3:raise ValueError('Chord floor clip has insufficient real web height')
    zs=[zlo+(zhi-zlo)*i/3 for i in range(4)];bottom=zlo-.5;height=zhi-zlo+1
    jsign=1 if joist['local_y'][0]*axes[1][0]+joist['local_y'][1]*axes[1][1]>0 else -1
    # Use the outside of the floor web so the vertical clip stays out of its
    # flanges. Fold at the actual pack sheet, adding an explicit offset return
    # when its flange plane differs from that web.
    yj=-jsign*jt/2;leg_y=min(yj,yj-jsign*t)
    a.box('FLOOR-LEG',[.25,leg_y,bottom],[2,t,height],'S','S54mil clip sheet; A2in leg and exact cut-end fit')
    a.fastener('FLOOR-S',[[1.25,yj-jsign*t,z] for z in zs],[0,jsign,0],.19,t+jt,['FLOOR-LEG','FLOOR'],'S fourNo10 at this attachment; A stations and offset clip fit',screw=True)
    if thin==0:
        xp=box[0][1];bt=box[0][1]-box[0][0];ys=max(box[1][0]+.3,min(yj,box[1][1]-.3))
        low=min(ys-.4,leg_y);high=max(ys+.4,leg_y+t)
        a.box('PACK-LEG',[xp,low,bottom],[t,high-low,height],'S','S54mil clip return against the actual pack web; A developed width')
        a.fastener('PACK-S',[[xp+t,ys,z] for z in zs],[-1,0,0],.19,t+bt,['PACK-LEG','PACK'],'S fourNo10 at pack attachment; A stations',screw=True)
        x0=min(xp+t,.25);x1=max(xp+t,.25)
        if x1-x0>.001:a.box('FOLD',[x0,leg_y,bottom],[x1-x0,t,height],'A','A continuous formed return between the two actual clip legs')
    else:
        yp=box[1][1] if yj>sum(box[1])/2 else box[1][0];sign=1 if yj>yp else -1;bt=box[1][1]-box[1][0]
        xs=sum(box[0])/2;x0=box[0][0]+.15;x1=box[0][1]-.15
        if x1-x0<.3:raise ValueError('Pack flange too narrow for the clip screw')
        a.box('PACK-LEG',[x0,min(yp,yp+sign*t),bottom],[x1-x0,t,height],'S','S54mil clip sheet against actual pack flange; A fit')
        a.fastener('PACK-S',[[xs,yp+sign*t,z] for z in zs],[0,-sign,0],.19,t+bt,['PACK-LEG','PACK'],'S fourNo10 at pack attachment; A stations',screw=True)
        bend=x1 if x1<.25 else x0
        ya,yb=sorted((yp+sign*t/2,yj-jsign*t/2))
        if yb-ya>.001:a.box('OFFSET',[bend-t/2,ya,bottom],[t,yb-ya,height],'A','A formed offset closes the actual pack-flange/floor-web eccentricity; capacity not recalculated')
        xa,xb=sorted((bend,.25))
        if xb-xa>.001:a.box('FOLD',[xa,leg_y,bottom],[xb-xa,t,height],'A','A continuous formed horizontal return')
    a.section_axis=2;a.section_at=sum(zs)/len(zs);a.front_axes=(0,2)
    a.notes.append('S54mil clip and fourNo10 screws per attachment. A bent return dimensions fit the actual source pack and interrupted member; the changed clip eccentricity needs a real-project capacity check. No fastener is placed in the hollow rod cavity.')
