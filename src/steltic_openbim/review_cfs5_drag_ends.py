"""CFS5 source8-No14 drag terminals, with explicitly adopted formed returns.

The source gives an8in97mil plate, sixNo14 to track and a chord tie. Folded
returns, clearance cut-outs, chord-tie geometry and welds are adopted fits.
Their capacities and fabrication requirements have not been designed here.
"""
from collections import defaultdict
from .review_cfs_occurrences import axis
from .review_sbmf_girts import cross_section
from .review_receiver_geometry import extract
from .review_cfs5_diaphragms import GLOBAL,region
from .pilots.model import sub
from shapely.geometry import box,Polygon

PT=.1017


def bounds(m,profiles):
    section=cross_section(m,profiles,GLOBAL);aa,dd=axis(m)
    return [[min(aa[i],dd[i])+min(q[i] for poly in section for q in poly),
             max(aa[i],dd[i])+max(q[i] for poly in section for q in poly)] for i in range(3)]


def subtract(intervals,lo,hi):
    result=[]
    for a,b in intervals:
        if hi<=a or lo>=b:result.append((a,b));continue
        if lo>a:result.append((a,lo))
        if hi<b:result.append((hi,b))
    return result


def apply(b,straps):
    lookup={m['id']:m for m in b.members};by_level=defaultdict(list)
    for m in b.members:
        if m['kind'] in ('joist','diaphragm_blocking','collector_blocking','stud','opening_jamb','chord'):by_level[m['level']].append((m,bounds(m,b.profiles)))
    panels={p['level']:p for p in b.panels if p['kind'] in ('floor','roof')};openings={o['id']:o for o in b.openings}
    for strap in straps:
        sa,sd=axis(strap);along=0 if abs(sd[0]-sa[0])>1 else 1;normal=1-along;k=strap['level']
        strip_centre=sa[normal];st=b.profiles[strap['profile_id']]['dimensions']['thickness'];rid=strap['design_record_ids'][0]
        panel=panels[k];wsp_top=panel['vertices'][0][2];wsp_bottom=wsp_top-panel['thickness_in'];top_base=sa[2]+st/2
        for ci,chord_id in enumerate(strap['drag_end_chords']):
            chord=lookup[chord_id];track=lookup[chord_id.rsplit('-CH',1)[0]+'-TT'];ch=axis(chord)[0][along]
            into=1 if chord_id.endswith('CH0') else -1;ta,td=axis(track);t=b.profiles[track['profile_id']]['dimensions']['t']
            tz=max(q[2] for q in (ta,td))+t/2;boundary=ta[along] if into==1 else td[along]
            polys=cross_section(chord,b.profiles,GLOBAL);ca=axis(chord)[0];webs=[]
            for poly in polys:
                amin,amax=min(q[along] for q in poly),max(q[along] for q in poly)
                nmin,nmax=min(q[normal] for q in poly),max(q[normal] for q in poly)
                if amax-amin<.3 and nmax-nmin>.75:webs.append((amin if into==1 else amax,nmin,nmax,amax-amin))
            if not webs:raise ValueError('No actual chord web for drag tie '+chord_id)
            face,chord_nlo,chord_nhi,ct=(min(webs) if into==1 else max(webs));face+=ca[along];chord_nlo+=ca[normal];chord_nhi+=ca[normal]
            # The parapet-offset roof joist leaves a narrow common band.
            # Offset the8in plate slightly from the strap centre to retain
            # a full3/4in chord cap within the actual web, with1/32in reserve.
            centre=min(chord_nhi+3.25-.03125,max(chord_nlo-3.25+.03125,strip_centre))
            chord_bounds=bounds(chord,b.profiles)[along]
            plane=min(boundary-.25,chord_bounds[0]-.125-PT) if into==1 else max(boundary+.25,chord_bounds[1]+.125+PT)
            def clears_vertical_members(v):
                lo,hi=sorted((v,v+into*PT))
                for member,bb in by_level[k]:
                    if member['kind'] not in ('stud','opening_jamb','chord'):continue
                    if bb[2][1]<tz-6.5 or bb[2][0]>top_base:continue
                    if bb[normal][1]<centre-4 or bb[normal][0]>centre+4:continue
                    if bb[along][0]-.125<hi and bb[along][1]+.125>lo:return False
                return True
            if along==0:
                candidates=[]
                for member,bb in by_level[k]:
                    if not member.get('source_collector_block') or abs(axis(member)[0][1]-(centre-.75))>1.01:continue
                    aa,dd=axis(member);mid=(aa[0]+dd[0])/2
                    outside_chord=mid+PT<chord_bounds[0]-.125 if into==1 else mid-PT>chord_bounds[1]+.125
                    if into*(boundary-mid)>.125 and outside_chord and abs(mid-boundary)<32 and clears_vertical_members(mid):candidates.append(mid)
                if not candidates:raise ValueError('No clear collector-block interval outside actual track '+track['id'])
                plane=min(candidates,key=lambda v:abs(v-boundary))
            elif not clears_vertical_members(plane):
                candidates=[plane-into*i*.25 for i in range(1,65) if clears_vertical_members(plane-into*i*.25)]
                if not candidates:raise ValueError('No actual vertical-member clearance for Y drag '+chord_id)
                plane=candidates[0]
            prefix=strap['id']+'-END'+str(ci)
            def point(u,n,z):return [u,n,z] if along==0 else [n,u,z]
            def flat(name,width,thick,aa,dd,ly,kind='drag_plate'):
                pid=b.custom(f'CFS5-DRAG-PL{width:g}X{thick:g}','flat',dict(width=width,thickness=thick),basis='S97mil drag material where stated; A individual formed/welded piece geometry')
                return b.member(prefix+'-'+name,pid,kind,aa,dd,k,'A',records=[rid],local_y=ly)
            normal_vec=[0,1,0] if normal==1 else [1,0,0]
            top=flat('TOP',8,PT,point(plane,centre,top_base+PT/2),point(ch+into*3,centre,top_base+PT/2),normal_vec)
            footprint=bounds(top,b.profiles)
            clipped=box(footprint[0][0],footprint[1][0],footprint[0][1],footprint[1][1]).intersection(Polygon([q[:2] for q in panel['vertices']]))
            if not region(panel,openings).covers(clipped):
                for oid in panel.get('openings',[]):
                    o=openings[oid];xl,yl=o['x_ft']*12,o['y_ft']*12;xh=xl+o['width_ft']*12;yh=yl+o['height_ft']*12
                    if not clipped.intersects(box(xl,yl,xh,yh)):continue
                    if not o.get('penetrating_member_ids'):raise ValueError('Drag terminal crosses an architectural opening '+prefix)
                    limits=[(xl,xh),(yl,yh)];slots=sorted((v-plane)*into for v in limits[along])
                    lo=max(0,slots[0]);hi=min(abs(ch+into*3-plane),slots[1])
                    if hi>lo:
                        nl,nh=limits[normal]
                        top.setdefault('slots',[]).append(dict(start_in=lo,end_in=hi,section_axis=0,centre_in=(nl+nh)/2-centre,width_in=nh-nl,
                            connection_id=prefix,basis='A relief around named continuous parapet stud '+','.join(o['penetrating_member_ids'])+'; original8in plate stock retained, reduced plate section unverified'))
            bx,by,bxx,byy=clipped.bounds
            panel.setdefault('underside_recesses',[]).append(dict(id=top['id']+'-RECESS',bounds_xy_in=[[bx,bxx],[by,byy]],depth_in=top_base+PT-wsp_bottom,side='underside',support_member_id=top['id'],basis='A local underside WSP rebate for actual97mil drag plate; source nominal panel retained, reduced local section unverified. Plate may project past the panel edge.'))
            web=flat('WEB',8,PT,point(plane+into*PT/2,centre,tz-6.5),point(plane+into*PT/2,centre,top_base),normal_vec)
            track_bounds=bounds(track,b.profiles)[normal]
            sides=[(out,face) for out,face in ((-1,track_bounds[0]),(1,track_bounds[1])) if centre-4+PT<face<centre+4-PT]
            if not sides:raise ValueError('No actual track leg within drag return '+prefix)
            outward,track_face=min(sides,key=lambda r:abs(r[1]-centre))
            foot_n=track_face+outward*PT/2
            foot=flat('FOOT',1,PT,point(plane+into*PT,foot_n,tz-.75),point(ch+into*6,foot_n,tz-.75),[0,0,1])
            # Clearance slots belong to the adopted plate, not the source
            # joists/blocks. Keep continuous side ligaments around real steel.
            web_bands=[(centre-4,centre+4)]
            for member,bb in by_level[k]:
                if bb[normal][1]<centre-4 or bb[normal][0]>centre+4:continue
                nl,nh=bb[normal][0]-.125,bb[normal][1]+.125
                if bb[along][0]-.125<=plane+into*PT/2<=bb[along][1]+.125:
                    zlo=max(tz-6.5,bb[2][0]-.125);zhi=min(top_base,bb[2][1]+.125)
                    if zhi>zlo:
                        web.setdefault('slots',[]).append(dict(start_in=zlo-(tz-6.5),end_in=zhi-(tz-6.5),section_axis=0,centre_in=(nl+nh)/2-centre,width_in=nh-nl,connection_id=prefix,basis='A actual steel clearance in97mil drag return; side ligaments and capacity unverified'))
                        if zhi>=top_base-.001:web_bands=subtract(web_bands,nl,nh)
            if not web_bands:raise ValueError('Drag return loses its continuous plate ligament '+prefix)
            # Use an actual outer chord web, with a thin formed return across
            # the offset. A hollow sheet tie replaces an unrealistic solid pack.
            safe=[(max(centre-4+.375,chord_nlo+.375),min(centre+4-.375,chord_nhi-.375))]
            safe=[r for r in safe if r[1]>=r[0]-1e-7]
            if not safe:raise ValueError('No actual chord fixing band '+prefix+str((centre,chord_nlo,chord_nhi)))
            band=max(safe,key=lambda r:r[1]-r[0]);n=(band[0]+band[1])/2
            cap=flat('CHORD-CAP',.75,PT,point(face-into*PT/2,n,tz-6.5),point(face-into*PT/2,n,tz-1.5),normal_vec)
            ties=[]
            for sign in (-1,1):
                ties.append(flat('TIE'+str(sign),5,PT,point(plane+into*PT,n+sign*(.375-PT/2),tz-4),point(face-into*PT,n+sign*(.375-PT/2),tz-4),[0,0,1]))
            members=[strap,top,web,foot,cap,*ties,track,chord];origin=point(ch,centre,tz)
            points8=[point(ch+u,strip_centre+v,wsp_top) for u in (-1.5,-.5,.5,1.5) for v in (-.75,.75)]
            points6=[point(boundary+into*(1.5+i*.75),track_face+outward*PT,tz-.75) for i in range(6)]
            chord6=[point(face-into*PT,n,tz-2-i*.75) for i in range(6)]
            welds=[]
            for a,d in web_bands:
                if d-a>.05:welds.append(dict(parts=[1,2],points=[point(plane+into*PT/2,a,top_base),point(plane+into*PT/2,d,top_base)]))
            welds.append(dict(parts=[2,3],points=[point(plane+into*PT,foot_n,tz-1.25),point(plane+into*PT,foot_n,tz-.25)]))
            for j,tie in enumerate(ties):
                aa,dd=axis(tie)
                for host,q in ((2,aa),(4,dd)):
                    welds.append(dict(parts=[host,5+j],points=[[q[0],q[1],tz-6.5],[q[0],q[1],tz-1.5]]))
            track_direction=[0,0,0];track_direction[normal]=-outward
            par=dict(purpose='source_drag_end',along=along,into=into,track_direction=track_direction,host_panel_id=panel['id'],subfloor_thickness=panel['thickness_in'],
                rebate=top_base+PT-wsp_bottom,strap_grip=wsp_top-(sa[2]-st/2),track_grip=PT+t,chord_grip=PT+ct,
                points_relative=[sub(q,origin) for q in points8],track_points=[sub(q,origin) for q in points6],chord_points=[sub(q,origin) for q in chord6],
                welds=[dict(parts=w['parts'],points=[sub(q,origin) for q in w['points']]) for w in welds])
            c=b.connection(prefix,'review_cfs5_drag_end',origin,members,[rid],parameters=par,title='SOURCE DRAG / EIGHT No14 / ACTUAL TRACK AND CHORD')
            for m in members[1:7]:
                for end in ('start','end'):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Actual welded/screwed97mil drag terminal; adopted fit and capacity unverified.'))
            end='end' if into==1 else 'start'
            b.endpoint_links[:]=[v for v in b.endpoint_links if not(v['member_id']==strap['id'] and v['end']==end)]
            b.endpoint_links.append(dict(member_id=strap['id'],end=end,connection_id=c['id'],basis='Source eightNo14 strap/drag-plate joint, sixNo14 track screws and explicit adopted chord tie at actual source receivers.'))
    b.note('DRAG-TERMINALS','S:8in97mil drag plate, eightNo14 strap screws and sixNo14 to the actual braced-bay top track. A: formed return geometry, plate clearances around source joists/blocks, hollow97mil chord tie with sixNo14,1/16in welds, finite gauges and WSP rebates. Source capacities do not verify these local fit proposals or extended gap lengths.')


def draw(ctx):
    a,par=ctx.a,ctx.params
    a.title='SOURCE DRAG TERMINAL / EIGHT No14 STRAP + SIX No14 TRACK'
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,32)
    points=par['points_relative'];height=par['subfloor_thickness']-par['rebate']
    lo=[min(p[i] for p in points)-.15 for i in (0,1)];hi=[max(p[i] for p in points)+.15 for i in (0,1)]
    wsp=a.box('WSP',[*lo,points[0][2]-height],[hi[0]-lo[0],hi[1]-lo[1],height],'S nominal panel; A local rebate','Actual host WSP context',kind='wood_panel')
    wsp.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True,drawing_style='outline')
    a.fastener('STRAP',points,[0,0,-1],.25,par['strap_grip'],['WSP','M1','M0'],'S eightNo14 total; A through-WSP head bearing and exact stations',basis='S',screw=True)
    a.fastener('TRACK',par['track_points'],par['track_direction'],.25,par['track_grip'],['M3','M7'],'S sixNo14 to actual top-track leg; A stations',basis='S',screw=True)
    direction=[0,0,0];direction[par['along']]=par['into']
    a.fastener('CHORD',par['chord_points'],direction,.25,par['chord_grip'],['M4','M8'],'A sixNo14 source chord tie; count/gauge and local capacity unverified',basis='A',screw=True)
    for i,w in enumerate(par['welds']):a.weld('W'+str(i),*w['points'],['M'+str(j) for j in w['parts']],size=.0625,basis='A',description='A1/16in joining weld; source97mil sheet retained, weld capacity and fabrication unverified')
    a.front_axes=(par['along'],2);a.section_axis=2;a.section_at=par['chord_points'][0][2]
    a.notes.append('Source eightNo14 strap/8in97mil plate and sixNo14 track screws are at the actual source chord and track. A returns, cut-outs around unchanged source framing, hollow chord tie, six chord screws,1/16in welds and WSP rebates require verification. No new capacity or fabrication approval.')
