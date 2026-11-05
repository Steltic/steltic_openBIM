"""Source CFS18 WSP fixing schedules with explicit adopted sheet-edge blocking.

The source leaves the blocking section and sheet set-out open. Three-inch
97mil flat blocking and shallow underside rebates are adopted example inputs;
their stiffness, reduced local WSP thickness and capacities remain unverified.
"""
import math
from collections import defaultdict
from shapely.geometry import LineString,Point,box
from .review_cfs5_diaphragms import region
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .pilots.model import add,sub,mul,unit

T=.1017
GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members};openings={o['id']:o for o in b.openings}
    counts=defaultdict(int)
    for k in (1,2):
        panel=next(p for p in b.panels if p['id']=='WING-FLOOR-'+str(k));roof=k==2
        rid='diaphragms/mezz-diaphragm-L'+str(k+1);source=b.records[rid]['data']['selection']
        if ('19/32' if roof else '23/32') not in source:raise ValueError('Mezzanine WSP selection changed')
        top=panel['vertices'][0][2];thickness=panel['thickness_in'];bottom=top-thickness
        if roof:
            b.material_selections.append(dict(id='CFS18-ROOF-WSP',basis='S',specification='19/32in wood structural panel, source blocked diaphragm selection'))
            panel.update(material_id='CFS18-ROOF-WSP')
        else:
            # Remove an unbuildable0.1375in sliver between the bearing-plate
            # cut-out and the actual outer sheet edge. The steel plate remains.
            for oid in panel['openings']:
                o=openings[oid];x,y=o['x_ft']*12,o['y_ft']*12;xx=x+o['width_ft']*12;yy=y+o['height_ft']*12
                if x-1814.8<.25:x=1814.8
                if 2385.2-xx<.25:xx=2385.2
                if y-20.8<.25:y=20.8
                if 579.2-yy<.25:yy=579.2
                o.update(x_ft=x/12,y_ft=y/12,width_ft=(xx-x)/12,height_ft=(yy-y)/12)
        polygon=region(panel,openings);safe=polygon.buffer(-.4)
        joists=[m for m in b.members if m['kind']=='joist' and m['id'].startswith(f'WING-J-{k}-')]
        if roof:
            # First roof joist's original flange faced outside its own panel.
            for m in joists:
                if m['axis'][0][0]==1818:m['local_y']=[1,0,0];m['basis']='A';m['physical_fit_basis']='S800S162-54; A west edge flange faces inward beneath the actual roof WSP.'
        def support_point(m):
            aa,dd=axis(m);d=b.profiles[m['profile_id']]['dimensions'];gauge=d['b']/2
            return aa[0]+m['local_y'][0]*gauge
        bands=[]
        for span,(ya,yb) in enumerate(((24,208),(208,392),(392,576))):
            row=sorted([m for m in joists if m['axis'][0][1]==ya],key=lambda m:m['axis'][0][0])
            step=4 if roof else 6
            seams=[support_point(m) for i,m in enumerate(row) if i%step==0 or i==len(row)-1]
            bands.append(dict(y_range_in=[ya,yb],long_seams_x_in=seams,basis='A nominal96in panels, trimmed to actual flange centres; staggered/joggled intersections at source wall laps require sheet cutting'))
        # Continuous97mil strips block transverse seams at the actual joist
        # top plane. They are rebated into WSP, never layered invisibly beneath
        # an unchanged plane. At each joist a fixing passes through every ply.
        rows=sorted(set([*range(72,576,48),208,392]+([24.5,575.5] if roof else [])))
        strips=[];strip_cons=defaultdict(list)
        for ri,y in enumerate(rows):
            lo,hi=(1818.25,2381.75) if roof else (1815.05,2384.95)
            pid=b.custom('A-MEZZ-DIA-FLAT97','flat',dict(width=3,thickness=T),basis='A selected transverse WSP edge blocking,3in97mil strip')
            strip=b.member(f'MEZZ-DIA-L{k}-STRIP{ri}',pid,'diaphragm_blocking',[lo,y,bottom+T/2],[hi,y,bottom+T/2],k,'A',records=[rid],local_y=[0,1,0])
            strips.append(strip)
            panel.setdefault('underside_recesses',[]).append(dict(id=strip['id']+'-RECESS',bounds_xy_in=[[lo,hi],[max(polygon.bounds[1],y-1.5),min(polygon.bounds[3],y+1.5)]],depth_in=T,side='underside',support_member_id=strip['id'],basis='A underside rebate for adopted97mil blocking; source nominal thickness retained and local reduced thickness/strength requires verification'))
            supports=[]
            for joist in joists:
                aa,dd=axis(joist)
                if aa[1]-.001<=y<=dd[1]+.001:supports.append(joist)
            if not roof:supports += [m for m in b.members if m['id'] in ('MEZZ-RIM-W','MEZZ-RIM-E')]
            for j,host in enumerate(supports):
                aa,dd=axis(host);d=b.profiles[host['profile_id']]['dimensions'];x=support_point(host)
                if not lo+.1<x<hi-.1 or not safe.covers(Point(x,y)):continue
                members=[strip,host];pack=lookup.get(host.get('wsp_packer_id'))
                if pack:members.append(pack)
                edge=roof and y in (24.5,575.5)
                for row,yy in enumerate([y] if edge else [y-.375,y+.375]):
                    if not aa[1]+.285<=yy<=dd[1]-.285:continue
                    if not safe.covers(Point(x,yy)):continue
                    c=b.connection(strip['id']+'-SUPPORT'+str(j)+'-'+str(row),'review_sbmf_wsp',[x,yy,top],members,[rid],parameters=dict(purpose='strip_support',host_panel_id=panel['id'],points_relative=[[0,0,0]],subfloor_thickness=thickness,rebate=T,source_pitch_in=6 if roof else 4),basis='A')
                    strip_cons[strip['id']].append(c);counts['support_fixings']+=1
            if len(strip_cons[strip['id']])<2:raise ValueError('WSP blocking lacks actual end supports '+strip['id'])
            for end,fn in (('start',min),('end',max)):
                c=fn(strip_cons[strip['id']],key=lambda c:c['point'][0]);b.endpoint_links.append(dict(member_id=strip['id'],end=end,connection_id=c['id'],basis='Adopted transverse blocking is screwed through the actual WSP into its real end joist/rim; finite projection outside the fixing is retained.'))
        # Plain fixing rows on joists, and the actual floor rim. Sheet-edge
        # rows are doubled across a joist flange; field rows retain12in pitch.
        hosts=joists+([] if roof else [m for m in b.members if m['id'] in ('MEZZ-RIM-S','MEZZ-RIM-N','MEZZ-RIM-W','MEZZ-RIM-E')])
        for host in hosts:
            aa,dd=axis(host);u=unit(sub(dd,aa));d=b.profiles[host['profile_id']]['dimensions'];along=0 if abs(u[0])>.9 else 1
            edge=host['kind']=='rim_track' or roof and host['axis'][0][0] in (1818,2382)
            span=next((r for r in bands if r['y_range_in'][0]==host['axis'][0][1]),None)
            seam=bool(span and any(abs(support_point(host)-x)<.001 for x in span['long_seams_x_in']))
            offsets=[d['b']/2] if edge or not seam else [d['b']/2-.375,d['b']/2+.375]
            pitch=(6 if roof else 4) if edge or seam else 12
            for line_index,gauge in enumerate(offsets):
                first=add(add(aa,mul(u,.5)),mul(host['local_y'],gauge));last=add(add(dd,mul(u,-.5)),mul(host['local_y'],gauge))
                line=LineString([first[:2],last[:2]]).intersection(safe)
                for strip in strips:
                    if along==1:line=line.difference(box(polygon.bounds[0]-1,strip['axis'][0][1]-1.75,polygon.bounds[2]+1,strip['axis'][0][1]+1.75))
                for cut in host.get('slots',[]):
                    # In the rim-flange interruptions there is no steel under
                    # the sheet. Exclude that interval from the fixing line.
                    if host['kind']=='rim_track':
                        q0=add(aa,mul(u,cut['start_in']-.4));q1=add(aa,mul(u,cut['end_in']+.4))
                        line=line.difference(box(min(q0[0],q1[0])- (0 if along==0 else 4),min(q0[1],q1[1])-(0 if along==1 else 4),max(q0[0],q1[0])+(0 if along==0 else 4),max(q0[1],q1[1])+(0 if along==1 else 4)))
                segments=[line] if line.geom_type=='LineString' else list(getattr(line,'geoms',[]))
                for run,segment in enumerate(segments):
                    if segment.geom_type!='LineString' or segment.length<.1:continue
                    n=max(1,math.ceil(segment.length/pitch));pts=[[q.x,q.y,top] for q in [segment.interpolate(i/n,normalized=True) for i in range(n+1)]]
                    members=[host];pack=lookup.get(host.get('wsp_packer_id'))
                    if pack:members.append(pack)
                    for start in range(0,len(pts),6):
                        chosen=pts[start:start+6];origin=[sum(q[i] for q in chosen)/len(chosen) for i in range(3)]
                        b.connection(host['id']+f'-DIA-{line_index}-{run}-{start//6}','review_sbmf_wsp',origin,members,[rid],parameters=dict(purpose='plain',host_panel_id=panel['id'],points_relative=[sub(q,origin) for q in chosen],subfloor_thickness=thickness,source_pitch_in=pitch))
                        counts['plain_fixings']+=len(chosen)
        for strip in strips:
            y=strip['axis'][0][1];edge=roof and y in (24.5,575.5)
            pitch=6 if roof else 4;xs=sorted(set(c['point'][0] for c in strip_cons[strip['id']]));first,last=strip['axis'][0][0]+.5,strip['axis'][1][0]-.5
            # Add No10 between the coincident panel/block/joist screws without
            # duplicating a fixing. Two rows support both cut sheet edges;
            # the boundary has only its inside row.
            for ri,yy in enumerate([y] if edge else [y-.375,y+.375]):
                points=[]
                for aa,dd in zip([first]+xs,xs+[last]):
                    n=max(1,math.ceil((dd-aa)/pitch))
                    for j in range(n+1):
                        x=aa+(dd-aa)*j/n
                        if min(abs(x-v) for v in xs)<.6:continue
                        if safe.covers(Point(x,yy)):points.append([x,yy,top])
                points=[list(p) for p in sorted(set(map(tuple,points)))]
                for start in range(0,len(points),6):
                    chosen=points[start:start+6];origin=[sum(q[i] for q in chosen)/len(chosen) for i in range(3)]
                    b.connection(strip['id']+f'-EDGE{ri}-{start//6}','review_sbmf_wsp',origin,[strip],[rid],parameters=dict(purpose='strip_edge',host_panel_id=panel['id'],points_relative=[sub(q,origin) for q in chosen],subfloor_thickness=thickness,rebate=T,source_pitch_in=pitch))
                    counts['strip_fixings']+=len(chosen)
        panel['design_record_ids']=sorted(set(panel['design_record_ids']+[rid]));b.used_records.add(rid)
        panel['attachment_schedule']=dict(source_record=rid,screw='No10',boundary_pitch_in=6 if roof else 4,continuous_edge_pitch_in=6 if roof else 4,other_edge_pitch_in=6,field_pitch_in=12,sheet_bands=bands,transverse_seams_y_in=rows,blocking_member_ids=[m['id'] for m in strips],basis='S nominal WSP and fixing maxima; A trimmed sheet set-out, two edge rows,3in97mil flat blocking with actual end fixings and0.1017in underside rebates. Local plate-clearance cuts and altered diaphragm/blocking strength require verification; no new capacity check.')
    b.changes.append(dict(kind='cfs18_source_wsp_diaphragm_fixings',counts=dict(counts)))
    b.note('MEZZ-DIAPHRAGM','S:23/32in blocked WSP floor,No10 at4in boundary/continuous edges,6in otheredges,12in field,1.5in gypsum;19/32in blocked WSP roof,No10 at6in edges/12in field. A: actual flange-based sheet bands and seams,3in97mil transverse flat blocking, shallow0.1017in underside rebates, two screw rows across interior seams and finite end fixings. Continuous blocking procurement and capacities, rebates, local plate-cutouts and roof edge flange roll require verification. Saved source strength is retained without certifying the changed fit.')


def draw(ctx):
    a,par=ctx.a,ctx.params;points=par['points_relative'];extent=max(math.sqrt(sum(v*v for v in q)) for q in points)+2
    parts=[extract(ctx,m,'M'+str(i),GLOBAL,extent) for i,m in enumerate(ctx.ms)]
    top=points[0][2];t=par['subfloor_thickness'];rebate=par.get('rebate',0);bottom=top-t+rebate
    low=[min(q[i] for q in points)-.15 for i in (0,1)];high=[max(q[i] for q in points)+.15 for i in (0,1)]
    panel=a.box('WSP',[*low,bottom],[high[0]-low[0],high[1]-low[1],t-rebate],'S nominal thickness; A rebate where shown','Actual host WSP; blocking rebate explicitly retained',kind='wood_panel')
    panel.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True,drawing_style='outline')
    if par['purpose']=='strip_edge':grip=t
    else:
        host=ctx.ms[1] if par['purpose']=='strip_support' else ctx.ms[0]
        ht=ctx.p[host['profile_id']]['dimensions']['t'];pack=next((m for m in ctx.ms if m['kind']=='bearing_packer'),None)
        grip=t+ht+(ctx.p[pack['profile_id']]['dimensions']['thickness'] if pack else 0)
    a.fastener('WSP-S',points,[0,0,-1],.19,grip,['WSP']+['M'+str(i) for i in range(len(parts))],f'S No10 source fixing; maximum{par["source_pitch_in"]}in here. A actual seam/blocking/pack fit',screw=True)
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=points[0][0]
    if len(points)>1:a.dim(points[0],points[1],'A finite fixing pitch; source maximum'+str(par['source_pitch_in']),basis='A')
    a.notes.append('Source nominal plywood thickness and screw schedule retained. A97mil strip blocking and underside rebate are explicit actual geometry; local panel thickness, blocking stiffness, seam/plate-cutout details and capacity remain unverified. The WSP view is context from its declared host panel, not a duplicate layer.')
