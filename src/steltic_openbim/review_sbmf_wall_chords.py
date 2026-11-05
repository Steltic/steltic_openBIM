"""Actual source chord stitches, base anchors and CFS18 top collector."""
import copy,math
from .pilots.model import add,cross,dot,sub
from .review_receiver_geometry import extract
from .review_sbmf_girts import cross_section
from .review_cfs_source_bindings import attach


def prepare(b):
    if b.key!='cfs18':return
    # Keep the source 24ft wall height and put its source top collector
    # directly under the header. The roof heels keep their original height;
    # the existing seat routine therefore shows the actual 2in bearing shims.
    for m in b.members:
        if not m['id'].startswith('SIDE-') or m['kind'] not in ('bottom_track','top_track'):continue
        pid=m['profile_id']; profile=copy.deepcopy(b.profiles[pid]); t=profile['dimensions']['t']
        profile['id']=pid+'-SBMF-OUTER-FIT';profile['dimensions']['d']=8+2*t+.0625
        profile.update(source_profile_id=pid,basis='A widened bend-to-bend fit; S track thickness and flange length',
            fit_proposal='Source8in stud/chord fits inside track with1/32in clearance per side; source capacity not assigned to widened section.')
        b.profiles[profile['id']]=profile;m['profile_id']=profile['id'];m['basis']='A'
        m['end_offsets'][0][0]=-2;m['end_offsets'][1][0]=2
    for m in b.members:
        if m['id'].startswith('SIDE-') and m['kind']=='chord':
            m['end_offsets'][0][2]=.0713;m['end_offsets'][1][2]=-.0713
    b.note('SBMF-WALL-HEAD-DATUM','A: CFS18 headers sit2in lower than the earlier adopted geometry so their bottom flanges meet the source24ft wall top collector directly. Roof top and bottom chords stay fixed; explicit2in roof bearing shims preserve their datums. Source header sections, frame worklines and24ft chords remain. Track bend widths include1/32in fit clearance each side, with real screw packers; tracks extend2in beyond chord worklines to receive both plies while retaining1/2in clearance to the HSS faces. Source capacity is not assigned to the widened track.')


def axes_for(chord):
    u=chord['local_y'];return (u,cross([0,0,1],u),[0,0,1])


def apply(b):
    if b.key not in ('cfs10','cfs18'):return
    lookup={m['id']:m for m in b.members}
    chords=[m for m in b.members if m['kind']=='chord' and m['id'].startswith('NORTH-CH-' if b.key=='cfs10' else 'SIDE-')]
    for chord in chords:
        rid='chords/'+('chord-north-wall' if b.key=='cfs10' else 'chord-side-wall')
        for i,z in enumerate(range(6,288,12)):
            b.connection(chord['id']+'-STITCH'+str(i),'review_sbmf_chord_stitch',
                [*chord['axis'][0][:2],z],[chord],[rid],basis='S')
    if b.key!='cfs18':return
    removed=set()
    for chord in chords:
        label=chord['id'].split('-CH-')[0];bottom=lookup[label+'BT'];top=lookup[label+'TT']
        for end,track,count,rid in ((0,bottom,16,'bases/hd-side-wall'),(1,top,13,'framing/sidewall-top-collector')):
            c=b.connection(chord['id']+'-TRACK'+str(end),'review_sbmf_chord_track',chord['axis'][end],
                [chord,track],[rid],parameters=dict(end=end,screws=count),basis='S')
            b.endpoint_links.append(dict(member_id=chord['id'],end='start' if end==0 else 'end',connection_id=c['id'],
                basis='Actual source chord end screws through the receiving track legs and explicit fit packers.'))
        into=1 if chord['id'].endswith('-0') else -1
        b.connection(chord['id']+'-SHEAR-ANCHORS','review_sbmf_track_anchor',chord['axis'][0],
            [bottom],['bases/hd-side-wall'],parameters=dict(diameter=.75,embedment=8,stations=[into*d for d in (4,8,12)]),basis='S')
        removed.add(bottom['id'])
    for track in [m for m in b.members if m['id'].startswith('SIDE-') and m['kind']=='top_track']:
        label=track['id'].removesuffix('TT');side=int(label.split('-')[1]);index=0 if label.endswith('-0') else 15
        header=lookup[f'HEADER-{side}-{index}'];lo=add(header['axis'][0],header['end_offsets'][0])[0]+1
        hi=add(header['axis'][1],header['end_offsets'][1])[0]-1
        for i in range(13):
            x=lo+(hi-lo)*i/12
            b.connection(label+'-TOP-COLLECTOR'+str(i),'review_sbmf_top_collector',[x,track['axis'][0][1],288],
                [track,header],['framing/sidewall-top-collector'],parameters=dict(side=-1 if i%2 else 1),basis='S')
        # Its ordinary floor-stack recipe picked an unrelated roof truss.
        removed.add(track['id'])
        for end in (0,1):
            cid=label+'-TOP-COLLECTOR'+str(0 if end==0 else 12)
            b.endpoint_links.append(dict(member_id=track['id'],end='start' if end==0 else 'end',connection_id=cid,
                basis='Source top track is fastened along the actual eave-header bottom flanges; its finite end belongs to that continuous collector.'))
    b.connections[:]=[c for c in b.connections if c['id'] not in removed]
    # Source flat-strap bridging at4ft: the12ft tier itself is the fifth
    # restraint line. Width, thickness and screw set-out are adopted.
    for wall in [w for w in b.walls if w['id'].startswith('SIDE-')]:
        run=wall['runs'][0];label=wall['id'];lo,hi,pos=run['start_in'],run['end_in'],run['position_in']
        hosts=[m for m in b.members if m['id'].startswith(label+'-') and m['kind'] in ('stud','chord')]
        for z in (48,96,192,240):
            for side in (-1,1):
                pid=b.custom('A-SBMF-BRIDGE-STRAP','flat',dict(width=1.5,thickness=.0566),basis='A')
                strap=b.member(f'{label}-BRIDGE-{z}-{side}',pid,'bridging',[lo,pos+side*(4+.0566/2),z],
                    [hi,pos+side*(4+.0566/2),z],3,'A',local_y=[0,0,1],records=['framing/sidewall-studs'])
                joints=[]
                for host in hosts:
                    if not host['axis'][0][2]<z<host['axis'][1][2]:continue
                    polys=cross_section(host,b.profiles,([1,0,0],[0,1,0],[0,0,1]));flanges=[]
                    for poly in polys:
                        if max(q[1]*side for q in poly)>3.99 and max(q[1] for q in poly)-min(q[1] for q in poly)<.2:
                            xx=host['axis'][0][0]+(min(q[0] for q in poly)+max(q[0] for q in poly))/2
                            if lo+.3<xx<hi-.3:flanges.append(xx)
                    for j,xx in enumerate(flanges):
                        cid=f'{strap["id"]}-{host["id"]}-{j}'
                        c=b.connection(cid,'review_sbmf_wall_bridging',[xx,pos,z],[strap,host],
                            ['framing/sidewall-studs'],parameters=dict(side=side),basis='A')
                        joints.append((xx,cid))
                assert joints
                for end,cid in (('start',min(joints)[1]),('end',max(joints)[1])):
                    b.endpoint_links.append(dict(member_id=strap['id'],end=end,connection_id=cid,
                        basis='Continuous source-required flat-strap bridging is fixed to its actual end chord flange; end projection is retained.'))
        for m in hosts+[lookup[label+'BT'],lookup[label+'TT']]:
            attach(b,m,'framing/sidewall-studs','Located source braced-bay two-tier studs, bottom/top tracks and4ft bridging. Track width/fastener fit are adopted; source section thickness and tier heights remain.')
    b.note('SBMF-WALL-CHORDS','S: continuous chords have two rows of No.12 web stitches at12in. CFS18 base chords have16 No.12 track-leg screws and three3/4in F1554 shear anchors within12in; head chords have13 No.12 track-leg screws and the top collector has13 No.12 into both header bottom flanges over each panel. A: exact screw/anchor distribution,1/32in track/chord packers,8in shear-anchor embedment,54mil flat bridging and its flange attachments. Source required4ft restraints are located; local fit and capacity remain distinct.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;family=ctx.family
    if family=='review_sbmf_chord_stitch':
        chord=ctx.ms[0];axes=axes_for(chord);extract(ctx,chord,'CHORD',axes,8)
        webs=[]
        for poly in cross_section(chord,p,axes):
            lo,hi=min(q[0] for q in poly),max(q[0] for q in poly)
            if .001<hi-lo<.5 and max(q[1] for q in poly)-min(q[1] for q in poly)>4:webs.append((lo,hi))
        webs.sort();lo,hi=webs[0][1],webs[1][0]
        pid='A-SBMF-STITCH-PACK';p[pid]=dict(id=pid,family='flat',dimensions=dict(width=6,thickness=hi-lo),basis='A')
        a.member('PACK',pid,[(lo+hi)/2,0,-.5],[(lo+hi)/2,0,.5],y=[0,1,0],basis='A',
            representation_role='assembly_component',description='A solid stitch pack between actual chord webs')
        a.fastener('STITCH',[[webs[1][1],y,0] for y in (-2.5,2.5)],[-1,0,0],.216,
            webs[1][1]-webs[0][0],['CHORD','PACK'],'S two rows No.12 web stitches at12in / A packing and gauge',screw=True)
        a.section_axis=2;a.section_at=0
        return
    if family=='review_sbmf_chord_track':
        chord,track=ctx.ms;axes=axes_for(chord);extract(ctx,chord,'CHORD',axes,12);extract(ctx,track,'TRACK',axes,12)
        td=p[track['profile_id']]['dimensions'];cp=p[chord['profile_id']];cd=p[cp['components'][0]['profile_id']]['dimensions']
        sign=1 if par['end']==0 else -1;t=td['t'];gap=td['d']/2-t-cd['d']/2
        assert abs(gap-.03125)<1e-6
        counts=[4,4,4,4] if par['screws']==16 else [4,3,3,3]
        for j,(side,hand) in enumerate(((-1,-1),(-1,1),(1,-1),(1,1))):
            xx=sorted((hand*.4,hand*1.65));face=side*cd['d']/2
            label='PACK'+str(j)
            a.box(label,[xx[0],face if side>0 else face-gap,min(sign*.25,sign*1.7)],[xx[1]-xx[0],gap,1.45],
                'A','A1/32in fit pack between track leg and actual chord flange')
            pts=[[hand*x,side*td['d']/2,sign*z] for z in (.55,1.25) for x in (.55,1.25)][:counts[j]]
            a.fastener('SCREWS'+str(j),pts,[0,-side,0],.216,t+gap+cd['t'],['CHORD','TRACK',label],
                'S No.12 chord-to-track screws / A actual pitch, gauge and clearance pack',screw=True)
        a.section_axis=2;a.section_at=sign*.55
        return
    axes=([1,0,0],[0,1,0],[0,0,1])
    if family=='review_sbmf_track_anchor':
        track=ctx.ms[0];extract(ctx,track,'TRACK',axes,16);t=p[track['profile_id']]['dimensions']['t'];e=par['embedment'];stations=par['stations']
        a.box('CONC',[min(stations)-4,-12,-e-2],[max(stations)-min(stations)+8,24,e+2],'A','A slab/foundation context, capacity delegated',kind='concrete')
        a.fastener('ANCHOR',[[x,0,-e] for x in stations],[0,0,1],par['diameter'],e+t,['TRACK','CONC'],
            'S three3/4in F1554 Gr36 shear anchors within12in of chord / A8in embedment and set-out',basis='S')
        a.section_axis=0;a.section_at=stations[0]
        return
    if family=='review_sbmf_top_collector':
        track,header=ctx.ms;extract(ctx,track,'TRACK',axes,8);extract(ctx,header,'HEADER',axes,8)
        td=p[track['profile_id']]['dimensions'];hp=p[header['profile_id']];ht=p[hp['components'][0]['profile_id']]['dimensions']['t'];side=par['side']
        flanges=[poly for poly in cross_section(header,p,axes) if max(q[2] for q in poly)-min(q[2] for q in poly)<.2 and min(q[2] for q in poly)<-4.9 and min(side*q[1] for q in poly)>0]
        assert len(flanges)==1
        y=(min(q[1] for q in flanges[0])+max(q[1] for q in flanges[0]))/2
        a.fastener('SCREW',[[0,y,-td['t']]],[0,0,1],.216,td['t']+ht,['TRACK','HEADER'],
            'S one of13 No.12 over panel, alternating both actual header bottom flanges; A set-out',screw=True)
        a.section_axis=0;a.section_at=0
        return
    strap,host=ctx.ms;extract(ctx,strap,'BRIDGING',axes,12);extract(ctx,host,'HOST',axes,12);side=par['side']
    h=p[host['profile_id']];ht=p[h['components'][0]['profile_id']]['dimensions']['t'] if h['family']=='built_up' else h['dimensions']['t']
    a.fastener('SCREW',[[0,side*(4+.0566),0]],[0,-side,0],.216,.0566+ht,['BRIDGING','HOST'],
        'A one No.12 to each actual flange at source-required4ft bridging rows',basis='A',screw=True)
    a.section_axis=2;a.section_at=0
