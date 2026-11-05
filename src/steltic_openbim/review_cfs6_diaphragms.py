"""Source diaphragm attachments on the real floor panels and framing.

Geometry is an accepted example set-out. Stored source strength calculations
are unchanged; the model does not certify local recesses or supplier details.
"""
import math
from collections import defaultdict
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame,point
from .pilots.model import add,sub,mul,unit,dot

T=.0566


def floor_regions(b):
    result={};openings={o['id']:o for o in b.openings}
    for p in b.panels:
        if p['kind']!='floor':continue
        polygon=Polygon([q[:2] for q in p['vertices']]);holes=[]
        for oid in p.get('openings',[]):
            o=openings[oid]
            holes.append(box(o['x_ft']*12,o['y_ft']*12,(o['x_ft']+o['width_ft'])*12,(o['y_ft']+o['height_ft'])*12))
        if holes:polygon=polygon.difference(unary_union(holes))
        result[p['level']]=(p,polygon)
    return result


def apply(b):
    if b.key!='cfs6':return
    regions=floor_regions(b);counts=defaultdict(int)
    for k,(panel,polygon) in regions.items():
        records=[rid for rid in b.records if rid.startswith('diaphragms/')]
        panel['design_record_ids']=sorted(set(panel['design_record_ids']+records));b.used_records.update(records)
        panel['attachment_schedule']=dict(screw='No10',edge_spacing_in=6,field_spacing_in=12,
            source_records=records,source_governing_level=4,source_rating_thickness_in=15/32,
            physical_thickness_in=23/32,sheet_setout='A48x96in nominal sheet grid, long direction across joists; seams on actual joist lines, unblocked unsupported edges',
            basis='S source23/32in subfloor, conservatively rated as15/32in, No10 screws6in edges/12in field. A sheet seams and finite screw stations. No new diaphragm capacity check.')
        # Wall-face blocking has its own source screws through the rebated
        # panel strip. Do not place duplicate plain WSP/joist screws there.
        clear=polygon
        for recess in panel.get('underside_recesses',[]):
            x,y=recess['bounds_xy_in'];clear=clear.difference(box(x[0],y[0],x[1],y[1]))
        safe=clear.buffer(-.4)
        for joist in list(b.members):
            if joist['level']!=k or joist['kind'] not in ('joist','opening_trimmer'):continue
            profile=b.profiles[joist['profile_id']]
            if profile['family']!='channel':continue
            aa,dd=axis(joist);v=unit(sub(dd,aa))
            if abs(v[2])>.01:continue
            along=max(range(2),key=lambda i:abs(v[i]));normal=1-along;dimensions=profile['dimensions']
            # At paired wall joists the panel edge bears on the outside part
            # of the inward-facing flange, just beyond the held-back finish.
            offset=.25 if joist.get('parallel_wall_line') else .75
            line_start=add(add(aa,mul(v,.5)),mul(joist['local_y'],offset));line_end=add(add(dd,mul(v,-.5)),mul(joist['local_y'],offset))
            line=LineString([line_start[:2],line_end[:2]]).intersection(safe)
            segments=[line] if line.geom_type=='LineString' else getattr(line,'geoms',[])
            for run,segment in enumerate(segments):
                if segment.geom_type!='LineString' or segment.length<.5:continue
                first,last=segment.coords[0],segment.coords[-1]
                near_edge=polygon.boundary.distance(Point([(first[i]+last[i])/2 for i in range(2)]))<1
                seam=abs(((aa[normal]-8)/96)-round((aa[normal]-8)/96))<1e-4
                pitch=6 if near_edge or seam else 12
                n=max(1,math.ceil(segment.length/pitch));values=[segment.interpolate(i/n,normalized=True) for i in range(n+1)]
                # Panel short-edge crossings also have real screws at each
                # supporting joist. The unsupported interval remains unblocked.
                low,high=sorted((first[along],last[along]))
                for station in range(math.ceil(low/48)*48,math.floor(high/48)*48+1,48):
                    for delta in (-.4,.4):
                        q=list(first);q[along]=station+delta
                        if low+.01<=q[along]<=high-.01 and safe.covers(Point(q)):values.append(Point(q))
                points=sorted({(round(v.x,7),round(v.y,7)) for v in values},key=lambda q:q[along])
                # Duplicate near-seam stations are combined without exceeding
                # the scheduled maximum pitch or placing a screw in an opening.
                kept=[]
                for q in points:
                    if kept and math.dist(q,kept[-1])<.6:
                        if q is points[-1]:kept[-1]=q
                        continue
                    kept.append(q)
                filled=[]
                for q in kept:
                    if filled:
                        previous=filled[-1];distance=math.dist(previous,q);n=max(1,math.ceil((distance-1e-7)/pitch))
                        filled.extend(tuple(previous[j]+(q[j]-previous[j])*i/n for j in range(2)) for i in range(1,n))
                    filled.append(q)
                kept=filled
                for group in range(0,len(kept),6):
                    selected=kept[group:group+6];origin=list(aa);origin[along]=sum(q[along] for q in selected)/len(selected)
                    actual_points=[[q[0]-origin[0],q[1]-origin[1],panel['vertices'][0][2]-origin[2]] for q in selected]
                    cid=joist['id']+f'-WSP-{run}-{group//6}'
                    region='leg' if sum(q[1] for q in selected)/len(selected)<1080 else 'bar'
                    refs=[rid for rid in records if '-'+region+'-' in rid]
                    b.connection(cid,'review_diaphragm_screws',origin,[joist],refs,
                        parameters=dict(actual_diaphragm=True,purpose='panel_screws',host_panel_id=panel['id'],
                            points_relative=actual_points,source_pitch_in=pitch,subfloor_thickness=23/32,
                            sheet_edge=near_edge or seam))
                    counts['screws']+=len(selected);counts['groups']+=1
    b.changes.append(dict(kind='source_cfs6_floor_diaphragm_screws',counts=dict(counts),
        basis='S No10 screws6in supported boundaries/continuous edges and12in field, actual23/32in WSP. A48x96in sheet set-out, finite screw stations and edge clearances. Every screw is inside its actual clipped floor panel and on the real joist flange.'))
    b.note('FLOOR-DIAPHRAGM','S:23/32in WSP floor diaphragm retains the source15/32in strength rating, No10 screws6in supported boundaries and continuous edges/12in field. A:48x96in sheet set-out and exact screw locations on the actual joists, excluding all wall strips and stair openings. Governing Level4 X/Y leg/bar checks remain attached unchanged; the detail pattern is repeated on the other floors without inventing new capacity results.')


def draw(ctx):
    a=ctx.a;joist=ctx.ms[0];par=ctx.params;axes=horizontal_frame(sub(*axis(joist)[::-1]))
    points=[point(add(ctx.c['point'],q),ctx.c['point'],axes) for q in par['points_relative']]
    extent=max(abs(q[0]) for q in points)+1
    steel=extract(ctx,joist,'JOIST',axes,extent)
    top=points[0][2];bottom=top-par['subfloor_thickness'];jt=ctx.p[joist['profile_id']]['dimensions']['t']
    if abs(bottom-steel['bounds'][2][1])>.005:raise ValueError('Subfloor screw has no actual joist-top bearing datum')
    x0=min(q[0] for q in points)-.3;x1=max(q[0] for q in points)+.3;y=points[0][1]
    panel=a.box('WSP',[x0,y-.25,bottom],[x1-x0,.5,par['subfloor_thickness']],'S thickness; A local context extent','Actual23/32in source floor panel; openings/holdbacks are respected',kind='wood_panel')
    panel.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True)
    a.fastener('SCREWS',points,[0,0,-1],.19,par['subfloor_thickness']+jt,['WSP','JOIST'],
        f'S No10 diaphragm screws; maximum{par["source_pitch_in"]}in pitch here; A finite stations',screw=True)
    a.section_axis=0;a.section_at=points[len(points)//2][0];a.front_axes=(0,2)
    a.notes.append('The WSP is a local view of its actual host floor panel, not an added duplicate panel. Exact source thickness, screw size and spacing retained; A sheet joints and stations. Cross-wall strap blocking is detailed separately.')
