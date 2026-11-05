"""Source continuous parapet studs, with explicitly adopted local roof fits.

The fictional opening and wall set-out predates this source requirement. Its
short header-supported backspans and larger transition spacings remain visible
exceptions; no source full-storey capacity is assigned to those exceptions.
"""
import copy,math
from collections import defaultdict
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame
from .pilots.model import sub,unit,dot,cross

RID='studs/stud-parapet'
T=.0566


def apply(b):
    if b.key!='cfs5':return
    roof=6;level=dict((k,z) for k,_,z in b.levels);top=level[roof]+36
    old={m['id'] for m in b.members if m['id'].startswith('PAR-')}
    removed={c['id'] for c in b.connections if old.intersection(c['member_ids'])}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if c['id'] not in removed]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in old and v['connection_id'] not in removed]
    groups=defaultdict(list);previous=[]
    for stud in b.members:
        if stud['kind']!='stud' or stud['level']!=roof:continue
        aa,dd=axis(stud);along=max(range(2),key=lambda i:abs(stud['local_y'][i]));normal=1-along
        if aa[normal] not in ((0,720) if normal==1 else (0,2160)) or abs(dd[2]-(level[roof]-12-.1))>.01:continue
        before=copy.deepcopy(stud)
        stud['profile_id']=b.profile('600S162-43');stud['axis'][1][2]=top-.1;stud['end_offsets'][1]=[0,0,0]
        stud['design_record_ids']=list(dict.fromkeys(stud['design_record_ids']+[RID]));b.used_records.add(RID)
        stud['source_parapet_requirement']='S600S162-43 continuous to source cap, 36in above roof; source nominal16in spacing'
        stud['backspan_status']='source_full_storey' if aa[2]<level[5]+1 else 'A header-supported shorter backspan; source full-storey capacity not assigned'
        stud['physical_fit_basis']='Existing physical stud extended continuously; source43mil parapet selection governs the upper exterior stud. Original section and axis retained in change register. No new capacity verification.'
        groups[along,aa[normal]].append(stud)
        previous.append(dict(member_id=stud['id'],previous_profile_id=before['profile_id'],previous_axis=before['axis'],new_axis=copy.deepcopy(stud['axis']),backspan_status=stud['backspan_status']))
    if set(groups)!={(0,0),(0,720),(1,0),(1,2160)}:raise ValueError('Parapet needs all four actual exterior wall runs')
    roof_panel=next(p for p in b.panels if p['kind']=='roof' and p['level']==roof)
    roof_panel['thickness_direction']='negative_global_z'
    for (along,station),studs in groups.items():
        for stud in studs:
            s=stud['axis'][0][along]
            lo=[s-.125,station-3.125] if along==0 else [station-3.125,s-.125]
            hi=[s+1.75,station+3.125] if along==0 else [station+3.125,s+1.75]
            lo=[max(0,v) for v in lo];hi=[min(limit,v) for limit,v in zip((2160,720),hi)]
            oid=stud['id']+':ROOF-CLEARANCE'
            opening=dict(id=oid,kind='wall_bearing_holdback',plane='xy',x_ft=lo[0]/12,y_ft=lo[1]/12,
                z_ft=level[roof]/12,width_ft=(hi[0]-lo[0])/12,height_ft=(hi[1]-lo[1])/12,
                level=roof,basis='A',confirmed=True,host_id=roof_panel['id'],query_id='CFS5-PARAPET-CLEARANCES',
                penetrating_member_ids=[stud['id']],penetration_basis='This local roof-sheet notch clears only its named actual continuous parapet stud. It is material clearance, not an architectural opening.')
            b.openings.append(opening);roof_panel.setdefault('openings',[]).append(oid)
    caps={};cap_pid=b.profile('600T125-43');ct=b.profiles[cap_pid]['dimensions']['t']
    for (along,station),studs in sorted(groups.items()):
        normal=1-along;length=2160 if along==0 else 720
        def q(u,z):return [u,station,z] if along==0 else [station,u,z]
        cap=b.member(f'PAR-CAP-{along}-{station:g}',cap_pid,'parapet_cap',q(0,top+ct/2),q(length,top+ct/2),roof,'S',local_y=[0,0,-1],records=[RID])
        caps[along,station]=cap
        for stud in studs:
            cid=stud['id']+':PAR-CAP'
            b.connection(cid,'cfs_stud',axis(stud)[1],[stud,cap],[RID],title='CONTINUOUS PARAPET STUD / ACTUAL CAP')
            b.endpoint_links[:]=[v for v in b.endpoint_links if not(v['member_id']==stud['id'] and v['end']=='end')]
            b.endpoint_links.append(dict(member_id=stud['id'],end='end',connection_id=cid,basis='Actual continuous parapet stud terminates at its source cap, not at the roof line.'))
        stations=sorted(s['axis'][0][along] for s in studs)
        gaps=[d-a for a,d in zip(stations,stations[1:])]
        b.changes.append(dict(kind='cfs5_parapet_existing_setout',wall_axis=along,station_in=station,
            source_nominal_spacing_in=16,adopted_stations_in=stations,maximum_gap_in=max(gaps),
            basis='A: retain actual ordinary/jamb transition set-out. Any spacing above16in requires verification; the source16in capacity is not assigned to the wider fit.'))
    # The cap opens down; actual orthogonal returns stop clear of the first cap.
    for y in (0,720):
        for x in (0,2160):
            first,second=caps[0,y],caps[1,x];ei=0 if x==0 else 1;ej=0 if y==0 else 1
            point=first['axis'][ei];dx=unit(sub(first['axis'][1-ei],point));dy=unit(sub(second['axis'][1-ej],point))
            cut=b.depth(first['profile_id'])/2+.125;second['end_offsets'][ej][1]=(1 if ej==0 else -1)*cut
            cid=f'PAR-CORNER-{x}-{y}'
            b.connection(cid,'review_track_corner',point,[first,second],parameters=dict(corner_turn=1 if dot(dy,cross([0,0,1],dx))>0 else -1,flange_direction=-1,cutback_in=cut),title='PARAPET CAP CORNER / A FIT')
            for m,e in ((first,ei),(second,ej)):
                b.endpoint_links.append(dict(member_id=m['id'],end='start' if e==0 else 'end',connection_id=cid,basis='Actual formed cap corner joins both finite cap ends.'))
    # Keep roof-line track legs continuous, with explicit local web clearance
    # for the through stud. This is a proposed cut, not an assumed factory hole.
    tracks=[m for m in b.members if m['level']==roof and m['kind'] in ('ordinary_track','top_track','tier_track') and m['local_y'][2]<-.99]
    for (along,station),studs in groups.items():
        for track in tracks:
            aa,dd=axis(track)
            if abs(aa[1-along]-station)>.01 or abs(dd[1-along]-station)>.01:continue
            u=unit(sub(dd,aa));length=math.dist(aa,dd)
            for stud in studs:
                at=dot(sub(stud['axis'][0],aa),u);sign=1 if dot(u,stud['local_y'])>0 else -1
                lo,hi=sorted((at-sign*.125,at+sign*1.75));lo=max(0,lo);hi=min(length,hi)
                if hi<=lo:continue
                track.setdefault('slots',[]).append(dict(start_in=lo,end_in=hi,section_axis=0,centre_in=0,width_in=.13,
                    basis='A local roof-track web clearance for actual continuous parapet stud; flange legs remain. Not a factory punch or capacity approval.',connection_id=stud['id']+':PAR-ROOF'))
    joists=[m for m in b.members if m['level']==roof and m['kind']=='joist' and abs(m['axis'][0][0]-m['axis'][1][0])<.01]
    # The edge joists must clear the newly continuous endwall studs, including
    # their flanges. Keep the source span/section and at most16in field spacing.
    shifted=[]
    for joist in joists:
        x=joist['axis'][0][0]
        shift=5.25 if x==0 else -3.25 if x==2160 else 0
        if not shift:continue
        for point in joist['axis']:point[0]+=shift
        joist.update(parallel_wall_line='CFS5-PARAPET-EDGE',parallel_wall_axis_in=x,parallel_wall_offset_in=shift)
        for c in b.connections:
            if c['member_ids'][0]==joist['id']:c['point'][0]+=shift
        shifted.append(dict(member_id=joist['id'],shift_x_in=shift))
    b.changes.append(dict(kind='cfs5_edge_joist_parapet_clearance',members=shifted,
        basis='A move the edge roof joist webs to5.25/2156.75in, clearing the continuous endwall studs by1/4in including joist flanges. Source section, span and maximum16in spacing retained; wall-end bearing fits remain explicit.'))
    removed=set();placements=[]
    for (along,station),studs in sorted(groups.items()):
        inward=1 if station==0 else -1
        for stud in studs:
            s=stud['axis'][0][along]
            if along==0:
                choices=[m for m in joists if any(abs(q[1]-station)<.01 for q in m['axis']) and -.01<=m['axis'][0][0]-s<=16.01]
                if not choices:raise ValueError('No actual parapet roof joist '+stud['id'])
                joist=min(choices,key=lambda m:abs(m['axis'][0][0]-s));end=min(range(2),key=lambda i:abs(joist['axis'][i][1]-station))
                joist['end_offsets'][end][1]=inward*3.125
                joist['parapet_roof_cut_in']=3.125
                removed.add(joist['id']+':'+str(end))
            else:
                target=5.25 if station==0 else 2156.75
                choices=[m for m in joists if abs(m['axis'][0][0]-target)<.01 and min(q[1] for q in axis(m))-.01<=s and s+2.8<max(q[1] for q in axis(m))]
                if not choices:raise ValueError('No actual endwall roof receiver '+stud['id'])
                joist=choices[0];end=None
            q=list(stud['axis'][0]);q[2]=joist['axis'][0][2];cid=stud['id']+':PAR-ROOF'
            b.connection(cid,'review_parapet_roof',q,[stud,joist],[RID],parameters=dict(actual_parapet=True,wall_axis=along,inward=inward,roof_elevation_in=level[roof],height_in=36),title='CONTINUOUS PARAPET / ACTUAL ROOF ATTACHMENT')
            if end is not None:
                b.endpoint_links[:]=[v for v in b.endpoint_links if not(v['member_id']==joist['id'] and v['end']==('start' if end==0 else 'end'))]
                b.endpoint_links.append(dict(member_id=joist['id'],end='start' if end==0 else 'end',connection_id=cid,basis='Actual cut roof joist end clips to the actual continuous exterior stud. Source fourNo10 each leg retained; offset fit remains unverified.'))
            placements.append(dict(connection_id=cid,stud_id=stud['id'],joist_id=joist['id'],backspan_status=stud['backspan_status']))
    b.connections[:]=[c for c in b.connections if c['id'] not in removed]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['connection_id'] not in removed]
    b.changes.append(dict(kind='cfs5_actual_continuous_parapets',replaced_member_ids=sorted(old),stud_extensions=previous,roof_connections=placements,
        basis='S36in parapet,600S162-43 continuous studs,600T125 cap,54mil roof clips and fourNo10 each side. A actual set-out, slotted roof-track webs, finite joist cuts and formed offsets. Short backspans/wider stations/offset clips are explicit unverified fits, not the source full-storey/in-line capacity.'))
    b.note('PARAPET-CONTINUITY','S:600S162-43 exterior studs continue through the roof to the600T125 cap36in above roof;54mil roof clips retain fourNo10 each side. A: source43mil parapet selection supersedes the lighter endwall top-storey section, retaining both source records. Actual windows create some header-supported shorter backspans; actual transition spacing reaches28in rather than source16in. Source full-storey/16in capacity is not assigned to these exceptions. Formed clip offsets connect actual roof joists; source in-line capacity is not claimed for offsets. Roof-track web clearances, cap corners and screw stations are accepted geometry requiring engineering verification.')


def draw(ctx):
    a=ctx.a;stud,joist=ctx.ms;par=ctx.params
    axes=horizontal_frame([1,0,0]);sp=extract(ctx,stud,'STUD',axes,44);jp=extract(ctx,joist,'JOIST',axes,24)
    st=ctx.p[stud['profile_id']]['dimensions']['t'];jt=ctx.p[joist['profile_id']]['dimensions']['t'];h=4
    sx,sy=sp['member']['axis'][0][:2];jx=jp['member']['axis'][0][0]
    if par['wall_axis']==0:
        sign=par['inward'];sface=sx-st/2;jface=jx+jt/2;bend=sy+sign*3.0625
        ylo,yhi=sorted((sy-sign*2.5,bend));a.box('STUD-LEG',[sface-T,ylo,-h/2],[T,yhi-ylo,h],'S54mil; A outline','Source54mil clip fitted outside actual stud web')
        ylo,yhi=sorted((bend,sy+sign*6.5));a.box('JOIST-LEG',[jface,ylo,-h/2],[T,yhi-ylo,h],'S54mil; A outline','Source54mil clip fitted outside actual joist web')
        xlo,xhi=sorted((sface-T,jface+T));by=min(bend,bend+sign*T)
        a.box('OFFSET',[xlo,by,-h/2],[xhi-xlo,T,h],'A','A continuous formed offset clears the stud flange; no in-line capacity assigned')
        a.fastener('STUD-S',[[sface-T,sy+sign*y,z] for y in (.75,1.75) for z in (-1,1)],[1,0,0],.19,T+st,['STUD','STUD-LEG'],'S fourNo10 to stud; A pitch/gauge',screw=True)
        a.fastener('JOIST-S',[[jface+T,sy+sign*y,z] for y in (4,5.5) for z in (-1,1)],[-1,0,0],.19,T+jt,['JOIST','JOIST-LEG'],'S fourNo10 to roof joist; A pitch/gauge',screw=True)
        for name,x in (('STUD-LEG',sface),('JOIST-LEG',jface)):
            a.weld('BEND-'+name,[x,bend,-2],[x,bend,2],[name,'OFFSET'],kind='BEND',basis='A',description='A continuous formed clip; no site weld')
    else:
        sface=sy-st/2;jface=jx+jt/2;lx=min(sx-2.5,jface);hx=max(sx+2.5,jface+T)
        a.box('STUD-LEG',[lx,sface-T,-h/2],[hx-lx,T,h],'S54mil; A outline','A extended formed leg to actual endwall stud web; offset capacity unverified')
        a.box('JOIST-LEG',[jface,sface-T,-h/2],[T,3+T,h],'S54mil; A outline','Source54mil clip return on actual roof joist web')
        a.fastener('STUD-S',[[sx+x,sface-T,z] for x in (-1.5,1.5) for z in (-1,1)],[0,1,0],.19,T+st,['STUD','STUD-LEG'],'S fourNo10 to stud; A pitch/gauge',screw=True)
        a.fastener('JOIST-S',[[jface+T,sy+y,z] for y in (.75,1.75) for z in (-1,1)],[-1,0,0],.19,T+jt,['JOIST','JOIST-LEG'],'S fourNo10 to actual roof joist; A offset fit',screw=True)
        a.weld('BEND',[jface,sface,-2],[jface,sface,2],['STUD-LEG','JOIST-LEG'],kind='BEND',basis='A',description='A continuous formed clip; no site weld')
    a.section_axis=2;a.section_at=1;a.front_axes=(0,2)
    roof=par['roof_elevation_in']-ctx.c['point'][2]
    a.dim([-8,0,roof],[-8,0,roof+par['height_in']],'Roof to cap datum',basis='S')
    a.notes.append('Actual continuous stud and roof joist. S54mil sheet and fourNo10 each attachment retained. A formed outline and any lateral offset are unverified; source in-line connection capacity is not assigned to the offset. Some studs have header-supported shorter backspans and wider transition spacing; see the accepted-decision register.')
