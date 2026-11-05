"""Located rim channels and in-line squash blocks from the saved CFS6 design.

Source sections remain separate from accepted local set-out and tight-bearing
fits. This module does not recalculate the saved gravity or diaphragm design.
"""
import copy,math
from collections import defaultdict
from .pilots.model import add,sub,mul,unit,cross
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame,point


def apply(b):
    if b.key!='cfs6':return
    roof=max(k for k,_,z in b.levels);levels={k:z for k,_,z in b.levels}
    members=list(b.members);toptracks=[m for m in members if m['kind'] in ('top_track','ordinary_track','tier_track') and m['local_y'][2]<-.99 and m['level']<roof]
    # The old rounded2.22-in build-up differs from the actual23/32+1.5.
    # Put joist top steel on the exact underside of the subfloor. A tight rim
    # adds one54-mil flange below the joist, which moves its bearing track
    # down0.02535 in; keep the original worklines and log that local fit.
    jt=.0713;rt=.0566;rise=2.22-(23/32+1.5);drop=rt-(.25-(23/32+1.5-2))
    shifted=[];tracks_by_line=defaultdict(list);toptrack_ids={m['id'] for m in toptracks}
    for track in toptracks:
        for off in track['end_offsets']:off[2]-=drop
        shifted.append(track['id'])
        along=max(range(2),key=lambda i:abs(track['axis'][1][i]-track['axis'][0][i]))
        tracks_by_line[track['level'],along,round(track['axis'][0][1-along],6)].append(track)
    for stud in members:
        if stud['kind'] not in ('stud','chord','opening_jamb') or stud['level']>=roof:continue
        end=max(range(2),key=lambda i:stud['axis'][i][2]);q=axis(stud)[end]
        # Only an already fitted touching head follows the track. The normal
        # source0.1-in end allowance needs no further shortening.
        along=max(range(2),key=lambda i:abs(stud['local_y'][i]))
        nearby=tracks_by_line[stud['level'],along,round(q[1-along],6)]
        for track in nearby:
            along=max(range(2),key=lambda i:abs(track['axis'][1][i]-track['axis'][0][i]));normal=1-along
            aa,dd=axis(track)
            if abs(stud['local_y'][along])<.99 or abs(q[normal]-aa[normal])>.01 or not min(aa[along],dd[along])<=q[along]<=max(aa[along],dd[along]):continue
            underside=aa[2]-b.profiles[track['profile_id']]['dimensions']['t']/2
            if q[2]>underside:stud['end_offsets'][end][2]-=q[2]-underside
    for m in members:
        if m['level']>=roof or m['kind'] not in ('joist','opening_trimmer'):continue
        for off in m['end_offsets']:off[2]+=rise
    b.changes.append(dict(kind='cfs6_exact_floor_bearing_fit',track_ids=shifted,track_shift_in=-drop,joist_shift_in=rise,
        basis='A exact steel fit under source23/32 in subfloor plus1.5 in gypsum at unchanged finish levels. A tight rim depth10.1132 in encloses the10 in joist; original worklines retained. Local track head fit and loading require verification.'))
    rimsource=b.profile('1000T150-54');rimid='1000T150-54-TIGHT-FIT';rim=copy.deepcopy(b.profiles[rimsource]);rim['id']=rimid
    rim['dimensions']['d']=10+2*rt;rim.update(source_profile_id=rimsource,basis='A tight formed rim width10.1132 in; S54 mil sheet and1.5 in flanges',fit_proposal='Source nominal10.11 in outside floor depth; actual tight fit to10 in joist, bending radii remain unselected')
    b.profiles[rimid]=rim
    groups=defaultdict(list)
    for m in members:
        if m['level']>=roof or m['kind']!='joist' or m.get('parallel_wall_line') or m['profile_id']!='1000S250-68':continue
        along=max(range(2),key=lambda i:abs(m['axis'][1][i]-m['axis'][0][i]));supports=(0,168,336,408,576,744) if along==0 else (1080,1248,1416,1488,1656,1824)
        for end,q in enumerate(m['axis']):
            if not any(abs(q[along]-v)<.01 for v in supports):continue
            sign=1 if m['axis'][1-end][along]>q[along] else -1
            groups[m['level'],along,round(q[along],6),sign].append((m,end))
    b.endpoint_links=getattr(b,'endpoint_links',[]);counts=defaultdict(int);replaced={}
    for gi,(key,ends) in enumerate(sorted(groups.items())):
        k,along,station,sign=key;wall=1-along;both=(k,along,station,-sign) in groups
        rpos=station+sign*(1.5 if both else -3.125)
        lo=min(q[wall] for m,end in ends for q in m['axis'])-3;hi=max(q[wall] for m,end in ends for q in m['axis'])+3
        centre=levels[k]-(23/32+1.5)-5
        aa=[lo,rpos,centre] if wall==0 else [rpos,lo,centre];dd=[hi,rpos,centre] if wall==0 else [rpos,hi,centre]
        ly=[0.,0.,0.];ly[along]=sign
        rm=b.member(f'SOURCE-RIM-L{k}-{gi}',rimid,'rim_track',aa,dd,k,'A',local_y=ly,records=['framing/rim-ext-stacked'],
            physical_fit_basis='S1000T150-54 source rim; A tight formed depth, exact position and finite run. Source exterior and two-sided wall bearing requirements retained.')
        for j,(joist,end) in enumerate(sorted(ends,key=lambda row:row[0]['id'])):
            old=list(joist['end_offsets'][end]);joist['end_offsets'][end][along]=rpos+sign*(rt/2+.03125)-joist['axis'][end][along]
            jid=f'{rm["id"]}-JOIST{j}';q=axis(joist)[end]
            b.connection(jid,'review_source_floor_rim',q,[joist,rm],[],parameters=dict(actual_source_floor=True,purpose='joist_rim',end=end))
            # The located source rim attachment replaces the generic old joist
            # end recipe. The track's own floor detail remains separately bound.
            oldcid=joist['id']+':'+str(end)
            replaced[oldcid]=jid
            b.endpoint_links.append(dict(member_id=joist['id'],end='start' if end==0 else 'end',connection_id=jid,basis='Actual cut joist end screws to the source rim top flange.'))
            pid=b.profile('600S162-68' if along==0 and station in (168,576) else '600S162-54')
            st=b.profiles[pid]['dimensions']['t'];cp=list(q);cp[along]=station if not both else q[along]+sign*(3+.0625)
            cp=add(cp,mul(joist['local_y'],(jt+st)/2));bottom=centre-5+jt;top=centre+5-jt
            a0=list(cp);a1=list(cp);a0[2]=bottom;a1[2]=top
            rid='framing/squash-mid-leg' if pid.endswith('-68') else 'framing/rim-ext-stacked'
            block=b.member(joist['id']+f'-SQUASH{end}',pid,'squash_block',a0,a1,k,'S',local_y=joist['local_y'],records=[rid],
                host_joist_id=joist['id'],source_nominal_length_in=9.86,physical_fit_basis='S selected squat channel; actual length9.8574 in between the source10 in joist flanges. A exact in-line location and web screw stations; no new capacity check.')
            joist.setdefault('source_squash_member_ids',[]).append(block['id'])
            cid=block['id']+'-WEB'
            b.connection(cid,'review_source_floor_block',cp,[block,joist],[rid],parameters=dict(actual_source_floor=True,purpose='block_web'))
            for label in ('start','end'):b.endpoint_links.append(dict(member_id=block['id'],end=label,connection_id=cid,basis='Squash channel bears tight against the actual joist flange faces; one located web attachment ties this physical block to that joist.'))
            b.changes.append(dict(kind='source_rim_joist_end',member_id=joist['id'],end=end,previous_offset=old,end_offset=list(joist['end_offsets'][end]),rim_id=rm['id'],block_id=block['id']))
            counts['normal_blocks']+=1
        # Bottom-rim screws land on actual track webs, never in a nominal gap.
        eligible=[]
        for track in tracks_by_line[k,wall,station]:
            a,d=axis(track)
            if abs(a[along]-station)>.01 or abs(d[along]-station)>.01:continue
            # A double top track transfers through the outside ply here.
            if track['id']+'-OUTER' in toptrack_ids:continue
            left=max(lo,min(a[wall],d[wall]))+.5;right=min(hi,max(a[wall],d[wall]))-.5
            if right<=left:continue
            values=[left+i*(right-left)/max(1,math.ceil((right-left)/12)) for i in range(max(1,math.ceil((right-left)/12))+1)]
            for x in values:
                pt=[0.,0.,centre];pt[wall]=x;pt[along]=rpos+sign*.75
                cid=rm['id']+'-TRACK'+str(len(eligible));eligible.append(cid)
                b.connection(cid,'review_source_floor_rim',pt,[rm,track],[],parameters=dict(actual_source_floor=True,purpose='rim_track'))
        if not eligible:raise ValueError('Source rim has no real supporting track '+rm['id'])
        for end in (0,1):
            options=[c for c in b.connections if c['id'].startswith(rm['id']+'-JOIST')]
            c=min(options,key=lambda c:math.dist(c['point'],rm['axis'][end]))
            b.endpoint_links.append(dict(member_id=rm['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Physical rim end is attached to its nearest actual end joist; bottom-flange screws to supporting tracks are separately located.'))
        counts['rims']+=1
    b.connections[:]=[c for c in b.connections if c['id'] not in replaced]
    for link in b.endpoint_links:
        if link['connection_id'] in replaced:link['connection_id']=replaced[link['connection_id']]
    # Source paired joists straddle parallel walls. Each ordinary stud flange
    # has its own362 block inside that actual joist pocket.
    upper_studs=defaultdict(list)
    for stud in members:
        if stud['kind']!='stud' or stud['level']<=1:continue
        k=stud['level']-1
        if min(q[2] for q in axis(stud))>levels[k]+1:continue
        along=max(range(2),key=lambda i:abs(stud['local_y'][i]));normal=1-along
        upper_studs[k,along,round(stud['axis'][0][normal],6)].append(stud)
    for joist in members:
        if not joist.get('parallel_wall_line') or joist['level']>=roof:continue
        k=joist['level'];along=max(range(2),key=lambda i:abs(joist['axis'][1][i]-joist['axis'][0][i]));normal=1-along
        aa,dd=axis(joist);lo,hi=sorted((aa[along],dd[along]));d=b.profiles[joist['profile_id']]['dimensions']
        if d['d']!=10 or d['b']!=2.5:raise ValueError('CFS6 paired floor joist source changed')
        for stud in upper_studs[k,along,round(joist['parallel_wall_axis_in'],6)]:
            foot=stud['axis'][0][along]+.8125
            if not lo<=foot<hi:continue
            at=max(lo+3.625/2+.125,min(foot,hi-3.625/2-.125))
            if abs(at-foot)>3.625/2-.1:raise ValueError('Parallel-wall stud has no actual block footprint '+stud['id'])
            pid=b.profile('362S162-54');st=b.profiles[pid]['dimensions']['t'];cp=list(aa);cp[along]=at
            cp=add(cp,mul(joist['local_y'],(d['t']+st)/2));a0=list(cp);a1=list(cp);a0[2]-=5-d['t'];a1[2]+=5-d['t']
            block=b.member(joist['id']+'-UNDER-'+stud['id'],pid,'squash_block',a0,a1,k,'S',local_y=joist['local_y'],
                records=['framing/walls-on-joists'],host_joist_id=joist['id'],supported_stud_id=stud['id'],source_nominal_length_in=9.86,
                physical_fit_basis='S362S162-54 block beneath this actual upper stud flange, inside the source inward-facing paired joist. A local cut/shift within the real span and web retention screws; no revised capacity calculation.')
            joist.setdefault('source_squash_member_ids',[]).append(block['id']);cid=block['id']+'-WEB'
            b.connection(cid,'review_source_floor_block',cp,[block,joist],['framing/walls-on-joists'],parameters=dict(actual_source_floor=True,purpose='block_web',parallel_wall=True))
            for end in ('start','end'):b.endpoint_links.append(dict(member_id=block['id'],end=end,connection_id=cid,basis='Actual source block bears tight within the real paired joist pocket under the upper stud flange.'))
            counts['parallel_blocks']+=1
    b.note('SOURCE-RIMS-AND-SQUASH','S: source1000T150-54 rims and600S162-54 in-line squash blocks, upgraded to600S162-68 at the leg mid-unit lines. Blocks bear between the real joist flanges. S oneNo10 joist/rim-top screw and bottom-rim/track screws at no more than12 in within actual supporting track runs. A: tight formed rim fit, positions, end clearances, three web-retention screws per block and local bearing-datum adjustment. Source floor transfer and chord-pack interruptions remain separate requirements.')
    b.changes.append(dict(kind='source_cfs6_rims_and_normal_blocks',counts=dict(counts)))


def bearing_receivers(b,levels):
    """Real upper/lower tracks for the source block's full steel bearing path."""
    if b.key!='cfs6':return
    lookup={m['id']:m for m in b.members};tracks=defaultdict(list);rims=defaultdict(list)
    for connection in b.connections:
        if connection['detail_ref']['id']=='review_source_floor_rim' and connection['parameters']['purpose']=='joist_rim':rims[connection['member_ids'][0]].append(connection)
    for track in b.members:
        if track['kind'] not in ('top_track','bottom_track','ordinary_track','tier_track'):continue
        along=max(range(2),key=lambda i:abs(track['axis'][1][i]-track['axis'][0][i]));normal=1-along
        tracks[track['level'],along,round(track['axis'][0][normal],6),1 if track['local_y'][2]>0 else -1].append(track)
    for c in b.connections:
        if c['detail_ref']['id']!='review_source_floor_block':continue
        block,joist=[lookup[mid] for mid in c['member_ids'][:2]];k=block['level'];ja=max(range(2),key=lambda i:abs(joist['axis'][1][i]-joist['axis'][0][i]))
        if joist.get('parallel_wall_line'):
            along=ja;station=joist['parallel_wall_axis_in'];foot=block['axis'][0][along]
        else:
            along=1-ja;end=min(range(2),key=lambda i:math.dist(joist['axis'][i],c['point']));station=joist['axis'][end][ja];foot=joist['axis'][end][along]+joist['local_y'][along]*.75
        for key,tier,sign in (('lower_track_index',k,-1),('upper_track_index',k+1,1)):
            choices=[]
            for track in tracks[tier,along,round(station,6),sign]:
                aa,dd=axis(track)
                if min(aa[along],dd[along])+.1<=foot<=max(aa[along],dd[along])-.1:choices.append(track)
            if not choices:continue
            # Lower bearing is on the outer top track of a nested collector;
            # upper bearing is below the actual bottom-track web.
            track=(max if sign<0 else min)(choices,key=lambda t:axis(t)[0][2])
            c['parameters'][key]=len(c['member_ids']);c['member_ids'].append(track['id'])
        if not joist.get('parallel_wall_line'):
            rim=next((other for other in rims[joist['id']] if math.dist(other['point'],c['point'])<10),None)
            if rim:c['parameters']['rim_index']=len(c['member_ids']);c['member_ids'].append(rim['member_ids'][1])


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;purpose=par['purpose']
    if purpose=='block_web':
        block,joist=ctx.ms[:2];axes=horizontal_frame(joist['local_y'])
        bp=extract(ctx,block,'BLOCK',axes,16);jp=extract(ctx,joist,'JOIST',axes,16)
        st=p[block['profile_id']]['dimensions']['t'];jt=p[joist['profile_id']]['dimensions']['t']
        x=bp['member']['axis'][0][0]+st/2;z0,z1=bp['bounds'][2]
        a.fastener('WEB',[[x,0,z] for z in (z0+1.25,(z0+z1)/2,z1-1.25)],[-1,0,0],.19,st+jt,['BLOCK','JOIST'],'A threeNo10 block-web retention screws; compression bears directly between the joist flanges',basis='A',screw=True)
        a.interfaces.append(dict(id='BEARING',kind='compression_bearing',connects=['BLOCK','JOIST'],basis='S',description='Selected squash channel cut tight between the actual joist flange faces; nominal9.86 in'))
        for key,label,edge in (('lower_track_index','LOWER',-1),('upper_track_index','UPPER',1)):
            if key not in par:continue
            track=ctx.ms[par[key]];tp=extract(ctx,track,label,axes,18);tt=p[track['profile_id']]['dimensions']['t']
            jz=jp['bounds'][2][1 if edge>0 else 0];tz=tp['bounds'][2][0 if edge>0 else 1];gap=(tz-jz)*edge
            if gap<-.001:raise ValueError('Source block bearing track intersects the joist flange')
            if edge<0 and 'rim_index' in par:
                extract(ctx,ctx.ms[par['rim_index']],'RIM',axes,18)
                a.interfaces.append(dict(id='LOWER-RIM',kind='compression_bearing',connects=['JOIST','RIM','LOWER'],basis='S',description='Actual rim lower flange bears on the actual top track; source rim screws are on their own located detail'))
                continue
            xy=[[max(bp['bounds'][i][0],jp['bounds'][i][0],tp['bounds'][i][0]),min(bp['bounds'][i][1],jp['bounds'][i][1],tp['bounds'][i][1])] for i in (0,1)]
            if min(hi-lo for lo,hi in xy)<.3:raise ValueError('Block has no actual steel bearing overlap with '+label)
            names=['JOIST',label]
            if gap>.001:
                tag=label+'-PACK';a.box(tag,[xy[0][0],xy[1][0],min(tz,jz)],[xy[0][1]-xy[0][0],xy[1][1]-xy[1][0],gap],
                    'A','A solid steel bearing pack within the actual block/joist/track footprint; held-back floor layers are absent here; local capacity unverified');names.append(tag)
            x=sum(xy[0])/2;ys=[xy[1][0]+(xy[1][1]-xy[1][0])*r for r in (.3,.7)]
            top=tz+tt if edge>0 else jz+jt
            a.fastener(label+'-S',[[x,y,top] for y in ys],[0,0,-1],.19,tt+jt+max(gap,0),names,
                'A twoNo10 steel-pack/track retention screws; source compression path retained',basis='A',screw=True)
            a.interfaces.append(dict(id=label+'-BEARING',kind='compression_bearing',connects=names,basis='A',description='Actual steel bearing with explicit fit packing; source floor forces retained, local packing capacity unverified'))
        a.section_axis=2;a.section_at=(z0+z1)/2;a.front_axes=(1,2)
        return
    primary,support=ctx.ms;axes=horizontal_frame(primary['local_y']) if purpose=='joist_rim' else horizontal_frame(sub(primary['axis'][1],primary['axis'][0]))
    first=extract(ctx,primary,'JOIST' if purpose=='joist_rim' else 'RIM',axes,18);second=extract(ctx,support,'RIM' if purpose=='joist_rim' else 'TRACK',axes,18)
    t=p[primary['profile_id']]['dimensions']['t'];tt=p[support['profile_id']]['dimensions']['t']
    if purpose=='joist_rim':
        aa,dd=axis(primary);end=par['end'];toward=unit(sub((aa,dd)[1-end],(aa,dd)[end]));q=add(add((aa,dd)[end],mul(toward,.75)),mul(primary['local_y'],.75));q[2]+=5+tt
        q=point(q,ctx.c['point'],axes);joins=['JOIST','RIM'];grip=t+tt
    else:
        q=[0,0,first['bounds'][2][0]+t];joins=['RIM','TRACK'];grip=t+tt
    a.fastener('TRANSFER',[q],[0,0,-1],.19,grip,joins,'S oneNo10 screw at the actual source flange/track interface; A station',screw=True)
    a.section_axis=0;a.section_at=q[0]
