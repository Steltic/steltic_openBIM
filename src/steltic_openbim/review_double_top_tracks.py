"""CFS6 source collector tracks with explicitly adopted nested fit and splices.

The governing headline is not the lower-storey thickness schedule. Both source
track plies, every real segment and both ends of each splice remain explicit.
"""
import copy,math,re
from collections import defaultdict
from .pilots.model import add,sub,mul,unit
from .review_receiver_geometry import extract,horizontal_frame
from .review_cfs_source_bindings import attach


LINES={'X90':'collector-X-X90','XCS':'collector-X-XCS','XCN':'collector-X-XCS',
       'XN':'collector-X-XN','YLC1':'collector-Y-YLC1','YLC2':'collector-Y-YLC1',
       'YLE':'collector-Y-YLE','Y0':'collector-Y-Y0',
       **{'P'+str(x):'collector-Y-P30' for x in (30,60,90,120,150)}}


def apply(b):
    if b.key!='cfs6':return
    locations={}
    for wall in b.walls:
        if wall['line'] not in LINES:continue
        along=0 if wall['direction']=='X' else 1
        for run in wall['runs']:locations[along,run['position_in'],wall['level']]=wall['line']
    groups=defaultdict(list)
    for m in b.members:
        if m['kind'] not in ('top_track','ordinary_track','tier_track') or m['local_y'][2]>-.99:continue
        along=max(range(2),key=lambda i:abs(m['axis'][1][i]-m['axis'][0][i]))
        key=(along,m['axis'][0][1-along],m['level'])
        if key in locations:groups[key].append(m)
    vertical=[m for m in b.members if m['kind'] in ('stud','chord','opening_jamb')]
    vertical_connections=defaultdict(list)
    for c in b.connections:
        if c['member_ids']:vertical_connections[c['member_ids'][0]].append(c)
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for key,tracks in sorted(groups.items()):
        along,station,k=key;line=locations[key];rid='collectors/'+LINES[line];source=b.records[rid]['data']
        match=re.search(r'level '+str(k)+r' 2 x (600T200-\d+)',source['design_note'])
        if not match:raise ValueError('Collector has no explicit storey track '+line+str(k))
        pid=b.profile(match[1]);d=b.profiles[pid]['dimensions'];t=d['t']
        count=int(re.search(r'splices with (\d+) No\. 10',source['selection'])[1])
        outerpid=pid+'-OUTER-FIT';outer=copy.deepcopy(b.profiles[pid]);outer['id']=outerpid
        outer['dimensions']['d']+=2*t+.0625
        outer.update(basis='A: formed outer track widened by two sheet thicknesses plus 1/16 in nesting clearance; source thickness and 2 in flange retained',
                     source_profile_id=pid,fit_proposal='Actual nested double top track; altered bend-to-bend width requires source strength verification')
        b.profiles[outerpid]=outer
        tracks.sort(key=lambda m:min(q[along] for q in m['axis']))
        joints=[]
        for left,right in zip(tracks,tracks[1:]):
            le=max(range(2),key=lambda i:left['axis'][i][along]);re_=min(range(2),key=lambda i:right['axis'][i][along])
            a,c=left['axis'][le][along],right['axis'][re_][along]
            if -.001<=c-a<=12.001:
                split=(a+c)/2
                left['end_offsets'][le][along]=split-.0625-a
                right['end_offsets'][re_][along]=split+.0625-c
                joints.append((left,right,split))
        outers={}
        for inner in tracks:
            previous=inner['profile_id'];top=inner['axis'][0][2];inner['profile_id']=pid
            for offset in inner['end_offsets']:offset[2]=-1.5*t
            attach(b,inner,rid,'Exact line/storey source double top-track collector; source schedule supersedes governing headline. A nested fit, local splice set-out and original fictional wall layout; no capacity re-verification.')
            a,c=copy.deepcopy(inner['axis']);a[2]=c[2]=top
            upper=b.member(inner['id']+'-OUTER',outerpid,'top_track',a,c,k,'A',records=[rid],local_y=[0,0,-1])
            upper['end_offsets']=copy.deepcopy(inner['end_offsets'])
            for offset in upper['end_offsets']:offset[2]=-t/2
            outers[inner['id']]=upper
            lo,hi=sorted(add(q,o)[along] for q,o in zip(inner['axis'],inner['end_offsets']))
            # Keep the original floor bearing surface; the inner web moves down
            # one sheet, and only vertical workpieces that actually meet it follow.
            for stud in vertical:
                if stud['level']!=k or abs(stud['local_y'][along])<.99 or abs(stud['axis'][0][1-along]-station)>.01 or not lo-.01<=stud['axis'][0][along]<=hi+.01:continue
                end=max(range(2),key=lambda i:stud['axis'][i][2]);old=add(stud['axis'][end],stud['end_offsets'][end])
                if abs(old[2]-top)>.3:continue
                stud['end_offsets'][end][2]=top-2*t-stud['axis'][end][2]
                for connection in vertical_connections[stud['id']]:
                    if connection['detail_ref']['id']=='cfs_stud' and abs(connection['point'][2]-top)<.3:
                        connection['point'][2]=top-2*t
                        b.endpoint_links.append(dict(member_id=stud['id'],end='start' if end==0 else 'end',connection_id=connection['id'],
                            basis='The actual stud head is cut below the nested inner-track web and is attached by this same located stud/track screw detail; the retained workline is not an additional free joint.'))
            # Web stitches make the two separate physical plies an assembly.
            xs=[];x=lo+min(2,(hi-lo)/3)
            while x<hi-.25:xs.append(x);x+=24
            if not xs:raise ValueError('Collector segment too short for its nested-track stitching')
            for j,x in enumerate(xs):
                q=[x,station,top] if along==0 else [station,x,top]
                b.connection(upper['id']+'-STITCH'+str(j),'review_double_top_track',q,[inner,upper],[rid],
                             parameters=dict(actual_double_top_track=True,purpose='stitch',direction=along))
            b.changes.append(dict(kind='source_double_top_track',member_id=inner['id'],outer_member_id=upper['id'],
                previous_profile=previous,source_profile=pid,source_record_id=rid,
                basis='S two source tracks and storey thickness. A outer nesting width, 1/8 in butt gaps, extended segment ends across former 6 in drawing gaps and exact splice/stitch locations; floor bearing top retained. Existing source forces and verification requirements remain.'))
        for j,(left,right,x) in enumerate(joints):
            top=left['axis'][0][2];q=[x,station,top] if along==0 else [station,x,top]
            cid=f'COLLECTOR-{line}-L{k}-SPLICE{j}'
            b.connection(cid,'review_double_top_track',q,[left,outers[left['id']],right,outers[right['id']]],[rid],
                parameters=dict(actual_double_top_track=True,purpose='splice',direction=along,screws_per_end=count))
            for inner,side in ((left,1),(right,-1)):
                end=max(range(2),key=lambda i:side*inner['axis'][i][along])
                for m in (inner,outers[inner['id']]):b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=cid,basis='Located source collector splice joins both nested tracks on each side of the actual butt joint.'))
        # Unspliced line termini have a nearby real web stitch, not a remote
        # endpoint exemption; the source wall/floor transfer remains separate.
        for inner in tracks:
            outer=outers[inner['id']]
            for end in (0,1):
                if any(v['member_id']==outer['id'] and v['end']==('start' if end==0 else 'end') for v in b.endpoint_links):continue
                available=[c for c in b.connections if c['id'].startswith(outer['id']+'-STITCH')]
                c=min(available,key=lambda c:math.dist(c['point'],add(outer['axis'][end],outer['end_offsets'][end])))
                b.endpoint_links.append(dict(member_id=outer['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual outer-track end is stitched to its continuous inner source track; wall/floor transfer is separately detailed.'))
    b.note('DOUBLE-TOP-COLLECTORS','S: both top-track plies and source per-storey thicknesses; exact source splice screw counts on every modelled butt joint. A: nested outer-track width, local 68 mil splice straps, screw stations, web stitches, and continuity across former drawing gaps. Original fictional wall set-out retained; source force/capacity records do not certify the adopted local fit or the revised receiver geometry.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=horizontal_frame([1,0,0] if par['direction']==0 else [0,1,0])
    for label,m in zip(('INNER-L','OUTER-L','INNER-R','OUTER-R'),ctx.ms):extract(ctx,m,label,axes,24)
    d=p[ctx.ms[0]['profile_id']]['dimensions'];outer=p[ctx.ms[1]['profile_id']]['dimensions'];t=d['t']
    if par['purpose']=='stitch':
        a.fastener('STITCH',[[0,0,0]],[0,0,-1],.19,2*t,['INNER-L','OUTER-L'],
            'A one No.10 web stitch at no more than 24 in; source collector force check retained',basis='A',screw=True)
        a.section_axis=0;a.section_at=0
        return
    count=par['screws_per_end'];plate=.0713;perface=count//2
    if count%2:raise ValueError('Collector screw count requires explicit face allocation')
    cols=math.ceil(perface/2);reach=1+(cols-1)*1.5+.75
    for side in (-1,1):
        face=side*outer['d']/2;tag='SPLICE'+str(side)
        a.box(tag,[-reach,face if side>0 else face-plate,-1.7],[2*reach,plate,1.3],
              'A','A 68 mil external splice strap; source total screw count each side retained')
        for end,sign in (('L',-1),('R',1)):
            points=[[sign*(1+(i//2)*1.5),face+side*plate,-.65-(i%2)*.75] for i in range(perface)]
            grip=plate+(outer['d']-d['d'])/2+t
            a.fastener(tag+'-'+end,points,[0,-side,0],.19,grip,[tag,'INNER-'+end,'OUTER-'+end],
                f'S {perface} of {count} No.10 screws at this splice end; A two-face allocation and stations',screw=True)
    a.section_axis=0;a.section_at=1;a.front_axes=(0,2)
    a.dim([-reach,0,-1.7],[reach,0,-1.7],'A fitted splice length',basis='A')
    a.notes.append('Both actual nested track plies on both sides are present. S source total screw count per end and sheet thickness; A outer-track nesting width, splice-strap selection and local hole layout. Source capacity is retained as evidence, not re-verified for these adopted fit details.')
