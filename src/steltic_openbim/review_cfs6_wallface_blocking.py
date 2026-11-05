"""Source54mil flat blocking along wall faces, spanning the actual floor joists.

The checked across-wall route is panel -> flat blocking -> joist -> rim ->
lower top track -> opposite rim. The flat strip does not cross the wall cavity.
"""
import math
from collections import defaultdict
from shapely.geometry import LineString,Point
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame,point
from .pilots.model import add,sub,mul,unit,dot
from .review_cfs6_diaphragms import floor_regions,T

RID='framing/diaphragm-across-walls'


def apply(b):
    if b.key!='cfs6':return
    regions=floor_regions(b);groups=defaultdict(list);sources=list(b.members)
    for m in sources:
        if m['level']>=5 or m['kind']!='joist' or m.get('parallel_wall_line'):continue
        aa,dd=axis(m);along=max(range(2),key=lambda i:abs(dd[i]-aa[i]));wall=1-along
        supports=(0,168,336,408,576,744) if along==0 else (1080,1248,1416,1488,1656,1824)
        d=b.profiles[m['profile_id']]['dimensions']
        for end,q in enumerate((aa,dd)):
            station=min(supports,key=lambda x:abs(x-q[along]));sign=1 if end==0 else -1
            if abs(q[along]-station)>8:continue
            at=station+sign*(3.3125+.75)
            if not aa[along]+.4<at<dd[along]-.4:continue
            location=list(q);location[along]=at;location=add(location,mul(m['local_y'],.75));location[2]=q[2]+d['d']/2
            if not regions[m['level']][1].covers(Point(location[:2])):continue
            groups[m['level'],wall,station,sign].append((m,location))
    total=defaultdict(int)
    for index,((k,wall,station,sign),rows) in enumerate(sorted(groups.items())):
        panel,polygon=regions[k];normal=1-wall;constant=station+sign*(3.3125+.75)
        low=min(q[wall] for m,q in rows)-.75;high=max(q[wall] for m,q in rows)+.75
        def xy(u,z):return [u,constant,z] if wall==0 else [constant,u,z]
        line=LineString([xy(low,0)[:2],xy(high,0)[:2]]).intersection(polygon.buffer(-.74))
        spans=[line] if line.geom_type=='LineString' else getattr(line,'geoms',[])
        for run,span in enumerate(spans):
            if span.geom_type!='LineString' or span.length<1:continue
            lo,hi=sorted(q[wall] for q in (span.coords[0],span.coords[-1]))
            chosen=sorted([(m,q) for m,q in rows if lo+.01<=q[wall]<=hi-.01],key=lambda row:row[1][wall])
            if len(chosen)<2:continue
            bottom=panel['vertices'][0][2]-23/32
            if any(abs(q[2]-bottom)>.005 for m,q in chosen):raise ValueError('Source blocking has inconsistent real joist top datums')
            label=f'WALLFACE-BLOCK-L{k}-{index}-{run}'
            pid=b.custom('SOURCE-FLAT54-W1.5','flat',dict(width=1.5,thickness=T),basis='S54mil sheet; A1.5in width')
            direction=[1,0,0] if wall==0 else [0,1,0];width=[-direction[1],direction[0],0]
            strip=b.member(label,pid,'diaphragm_blocking',xy(lo,bottom+T/2),xy(hi,bottom+T/2),k,'S',local_y=width,records=[RID],
                physical_fit_basis='S54mil wall-face flat blocking, oneNo10 to each actual joist. A1.5in width, continuous coil length, finite stations and54mil shallow underside WSP rebate; no new capacity verification.')
            # A design panel is a planar boundary plus nominal thickness. The
            # local underside rebate is retained explicitly as geometry data,
            # and is shown in each attachment section; its top plane stays put.
            vertices=[xy(lo,0),xy(hi,0)]
            x0=min(q[0] for q in vertices)-(0 if wall==0 else .75);x1=max(q[0] for q in vertices)+(0 if wall==0 else .75)
            y0=min(q[1] for q in vertices)-(0 if wall==1 else .75);y1=max(q[1] for q in vertices)+(0 if wall==1 else .75)
            panel.setdefault('underside_recesses',[]).append(dict(id=label+'-RECESS',bounds_xy_in=[[x0,x1],[y0,y1]],
                depth_in=T,side='underside',support_member_id=label,basis='A accepted example local rebate for the source54mil blocking. Nominal23/32in panel retained; reduced local thickness and capacity require verification.'))
            required=[q[wall] for m,q in chosen]
            stations=set(required)
            # The single screw through WSP + strip at each joist also serves
            # as that panel-edge screw. Add only the intervening edge screws.
            for a,d in zip([lo+.4]+required,required+[hi-.4]):
                if d-a<.6:continue
                n=max(1,math.ceil((d-a)/6));stations.update(a+(d-a)*i/n for i in range(n+1))
            values=[]
            for u in sorted(stations):
                if any(abs(u-v)<.6 and u!=v for v in required):continue
                if values and u-values[-1]<.6:continue
                values.append(u)
            # Fill any gap created when combining near-coincident stations.
            filled=[]
            for u in values:
                if filled:
                    a=filled[-1];n=max(1,math.ceil((u-a-1e-7)/6));filled.extend(a+(u-a)*i/n for i in range(1,n))
                filled.append(u)
            attachment_ids=[];joist_attachment_ids=[]
            for j in range(0,len(filled),6):
                stations=filled[j:j+6];centre=sum(stations)/len(stations);origin=xy(centre,bottom)
                hosts=[];screws=[]
                for u in stations:
                    host=next((m for m,q in chosen if abs(q[wall]-u)<1e-6),None)
                    if host is not None and host not in hosts:hosts.append(host)
                    screws.append(dict(point_relative=sub(xy(u,bottom+23/32),origin),receiver_index=hosts.index(host)+1 if host is not None else None))
                refs=[RID]+[rid for rid in b.records if rid.startswith('diaphragms/') and ('-leg-' if xy(centre,0)[1]<1080 else '-bar-') in rid]
                cid=label+f'-S{j//6}'
                b.connection(cid,'review_wallface_blocking',origin,[strip]+hosts,refs,
                    parameters=dict(actual_diaphragm=True,purpose='wallface_blocking',host_panel_id=panel['id'],
                        floor_top_relative=23/32,subfloor_rebate_in=T,screws=screws))
                attachment_ids.append(cid);total['screws']+=len(stations);total['joist_screws']+=len(hosts);total['groups']+=1
                if hosts:joist_attachment_ids.append(cid)
            for end,cid in (('start',joist_attachment_ids[0]),('end',joist_attachment_ids[-1])):
                b.endpoint_links.append(dict(member_id=label,end=end,connection_id=cid,basis='The actual continuous wall-face strip extends only to the nearby first/last real joist attachment; every intersected joist has its own sourceNo10 attachment.'))
            total['strips']+=1
    # These two source checks belong to the existing real rim interfaces.
    for c in b.connections:
        if c['detail_ref']['id']=='review_source_floor_rim':c['design_record_ids']=sorted(set(c['design_record_ids']+[RID]))
    b.changes.append(dict(kind='source_cfs6_wallface_blocking',counts=dict(total),
        basis='S54mil flat blocking along both relevant wall faces, sourceNo10 to every actual joist,6in maximum WSP boundary screws, existing real joist/rim and rim/track transfer. A1.5in strip width, continuous coil lengths, finite stations and54mil local underside WSP rebate.'))
    b.note('WALLFACE-BLOCKING','S:54mil flat blocking follows the wall faces across the actual joists. The source across-wall path is WSP -> blocking -> joist -> rim -> continuous lower top track -> opposite rim. OneNo10 joins each intersected joist; WSP boundary screws are at no more than6in. A:1.5in-wide continuous strips and a54mil local underside rebate in the23/32in WSP to preserve the accepted floor datum. Rebate, coil handling, local width and connection capacity are unverified example fit decisions; the saved source checks remain unchanged.')


def draw(ctx):
    a=ctx.a;par=ctx.params;strip=ctx.ms[0];axes=horizontal_frame(sub(*axis(strip)[::-1]))
    points=[point(add(ctx.c['point'],row['point_relative']),ctx.c['point'],axes) for row in par['screws']]
    extent=max(abs(q[0]) for q in points)+1;sp=extract(ctx,strip,'STRIP',axes,extent)
    top=par['floor_top_relative'];base=par['subfloor_rebate_in']
    x0=min(q[0] for q in points)-.3;x1=max(q[0] for q in points)+.3
    context=a.box('WSP',[x0,-.25,base],[x1-x0,.5,top-base],'S nominal23/32in; A54mil underside rebate',
        'Actual host panel at the wall-face blocking; explicit local underside rebate',kind='wood_panel')
    context.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True)
    for i,joist in enumerate(ctx.ms[1:],1):
        jp=extract(ctx,joist,'JOIST'+str(i),axes,12)
        if abs(jp['bounds'][2][1])>.005:raise ValueError('Wall-face source screw has no actual joist-top contact')
    for i,(row,q) in enumerate(zip(par['screws'],points)):
        joins=['WSP','STRIP'];grip=top;receiver=row['receiver_index']
        if receiver is not None:
            joins.append('JOIST'+str(receiver));grip+=ctx.p[ctx.ms[receiver]['profile_id']]['dimensions']['t']
        a.fastener('S'+str(i),[q],[0,0,-1],.19,grip,joins,
            'S oneNo10 through the WSP and54mil blocking at this actual joist' if receiver is not None else 'S No10 WSP boundary screw to54mil blocking between joists;6in maximum',screw=True)
    a.section_axis=0;a.section_at=points[len(points)//2][0];a.front_axes=(0,2)
    a.notes.append('Source across-wall shear transfers through the real rims and lower top track; this strip runs along the wall face. A54mil underside WSP rebate and1.5in strip width are explicit local fit proposals, without a revised panel/connection capacity approval.')
