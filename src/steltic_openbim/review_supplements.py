"""Explicit fictional architectural answers, physically coordinated with framing."""
import math
from .review_model import add,sub,mul
from .review_cfs import frange,intersections
from .design_geometry import interval_in_rectangle

def track_bearing_datums(b):
    """Keep the nominal bearing plane on the outside face of the track web."""
    if not b.key.startswith('cfs') or b.key in ('cfs3','cfs7'):return
    for m in b.members:
        if m['kind'] not in ('top_track','bottom_track','ordinary_track','tier_track'):continue
        if abs(m['local_y'][2])<.999:continue
        p=b.profiles[m['profile_id']]
        if p['family']!='channel':raise ValueError('Built-up track needs an explicit bearing datum')
        shift=p['dimensions']['t']/2*m['local_y'][2]
        previous=[list(v) for v in m['end_offsets']]
        for off in m['end_offsets']:off[2]+=shift
        b.changes.append(dict(kind='track_web_bearing_surface_offset',member_id=m['id'],previous_end_offsets=previous,
            end_offsets=[list(v) for v in m['end_offsets']],basis='A: nominal wall bearing/slab workpoint is the outside web face. Offset the physical track web centre by half its actual thickness into the wall; retain analysis axis and selected section.'))

def complete_walls(b,outline,bystory,levels):
    if b.key=='cfs29':return
    for k in range(1,len(levels)):
        poly=bystory.get(str(k),outline);lines={}
        for w in b.walls:
            if w['level']!=k:continue
            axis=0 if w['direction']=='X' else 1
            for r in w['runs']:lines[axis,round(r['position_in'],4)]=w['top_z_in']
        roof_bearing=b.key in ('cfs11','cfs13','cfs14') and k==len(levels)-1
        ordinary_depth=0 if roof_bearing else (14 if b.key=='cfs3' else 14.25 if b.key=='cfs13' else 16.25 if b.key=='cfs14' else 12)
        for a,d in zip(poly,poly[1:]+poly[:1]):
            axis=0 if abs(a[0]-d[0])>.01 else 1;normal=1-axis;lines[axis,round(a[normal]*12,4)]=levels[k]-ordinary_depth
        if b.key=='cfs14':
            for y in (210,630):
                if k>1 or y<420:lines[0,y]=levels[k]-ordinary_depth
        if roof_bearing:
            b.changes.append(dict(kind='ordinary_roof_wall_bearing_datum',level=k,top_z_in=levels[k],
                basis='A: ordinary return/bearing walls terminate at the same roof bearing workpoint as the source braced walls. Do not deduct an occupied-floor joist zone beneath the delegated roof truss. Source braced-wall sections and elevations are retained.'))
        if b.key in ('cfs2','cfs4','cfs6','cfs9','cfs12'):
            from .review_next_cfs_walls import bearing_lines,depth
            lines={key:levels[k]-depth(b,k) for key in lines}
            for axis,pos in bearing_lines(b):lines[axis,pos]=levels[k]-depth(b,k)
        if b.key in ('cfs1','cfs5','cfs15'):
            from .review_final_cfs import bearing_lines,depth
            lines={key:levels[k]-depth(b,k) for key in lines}
            for axis,pos in bearing_lines(b):lines[axis,pos]=levels[k]-depth(b,k)
        if b.key=='cfs7':
            from .review_cfs7 import depth,finish,wall_ranges
            lines={key:levels[k]-depth(k==len(levels)-1) for key in lines}
        for (axis,pos),top in lines.items():
            normal=1-axis;ranges=intersections(poly,axis,pos/12)
            if b.key=='cfs7':ranges=wall_ranges(b,axis,pos,ranges)
            occupied=[(r['start_in']-6,r['end_in']+6) for w in b.walls if w['level']==k and w['direction']==('X' if axis==0 else 'Y') for r in w['runs'] if abs(r['position_in']-pos)<.1]
            opens=[f for f in b.openings if f['level']==k and f['plane']==('xz' if axis==0 else 'yz') and abs(f['xy'[normal]+'_ft']*12-pos)<.1]
            bottom=levels[k-1];tp=b.profile('600T150-54');sp=b.profile('600S162-54');ly=[1,0,0] if axis==0 else [0,1,0]
            if b.key=='cfs7' and k>1:bottom-=finish()
            def pt(u,z):return [u,pos,z] if axis==0 else [pos,u,z]
            def void(u,z):return b.key=='cfs11' and k==1 and 960-1<u<1120+1 and axis==0 and 840-1<=pos<=1152+1
            for run,(lo,hi) in enumerate(ranges):
                lo*=12;hi*=12;label=f'ORD-{axis}-{pos}-{k}-{run}'
                # Continuous floor/top tracks close gaps while preserving source braced tracks.
                gaps=[(lo,hi)]
                for aa,dd in occupied+([(960,1120)] if b.key=='cfs11' and k==1 and axis==0 and 840<=pos<=1152 else []):
                    new=[]
                    for u,v in gaps:
                        if dd<=u or aa>=v:new.append((u,v))
                        else:
                            if aa>u:new.append((u,aa))
                            if dd<v:new.append((dd,v))
                    gaps=new
                for gi,(aa,dd) in enumerate(gaps):
                    if dd-aa<6:continue
                    for tag,z,up in [('B',bottom,1),('T',top,-1)]:
                        # Door threshold track is deliberately removed.
                        parts=[(aa,dd)]
                        if tag=='B':
                            for f in opens:
                                if abs(f['z_ft']*12-bottom)>.1:continue
                                start=f['xy'[axis]+'_ft']*12;end=start+f['width_ft']*12;new=[]
                                for u,v in parts:
                                    if end<=u or start>=v:new.append((u,v))
                                    else:
                                        if start>u:new.append((u,start))
                                        if end<v:new.append((end,v))
                                parts=new
                        for pi,(u,v) in enumerate(parts):
                            m=b.member(f'{label}-{gi}-{tag}-{pi}',tp,'ordinary_track',pt(u,z),pt(v,z),k,'A',local_y=[0,0,up]);b.connection(m['id'],'review_cfs_sill' if tag=='B' else 'review_cfs_floor',pt((u+v)/2,z),[m],parameters={'floor_depth':levels[k]-top,'level':k})
                for j,u in enumerate(frange(lo+8,hi,16)):
                    if void(u,bottom) or any(aa<u<dd for aa,dd in occupied):continue
                    # Opening jambs already occupy these narrow end zones. The
                    # old 7-in mask left duplicate, unsupported short studs
                    # just outside the actual header/sill span.
                    if any(any(abs(u-v)<4 for v in (f['xy'[axis]+'_ft']*12-3,f['xy'[axis]+'_ft']*12+f['width_ft']*12+3)) for f in opens):
                        b.changes.append(dict(kind='ordinary_stud_replaced_by_opening_jamb',station_in=u,wall_axis=axis,wall_position_in=pos,level=k,basis='A: existing opening jamb occupies this station; omit duplicate ordinary stud, retain source stud schedule'))
                        continue
                    intervals=[(bottom+.1,top-.1)]
                    for f in opens:
                        start=f['xy'[axis]+'_ft']*12
                        if start-7<u<start+f['width_ft']*12+7:
                            low=f['z_ft']*12-8;high=(f['z_ft']+f['height_ft'])*12+8;intervals=[(a,d) for a,d in ((bottom+.1,low),(high,top-.1)) if d-a>2]
                    for piece,(a,d) in enumerate(intervals):
                        m=b.member(f'{label}-S{j}-{piece}',sp,'stud',pt(u,a),pt(u,d),k,'A',local_y=ly);b.ends(m,'cfs_stud')
    b.note('ORDINARY-WALLS','A: non-braced infill and exterior return walls are fully framed with 600S162-54 studs at 16 in centres and 600T150-54 tracks. Openings remove the threshold/ordinary studs they cross; short cripple studs stop at the actual headers and sills. Source braced panels and open breezeway are preserved. Additional bearing-wall sizes require design verification.')

def floor_openings(b):
    if b.key in ('cfs17','cfs19','cfs26','cfs30','hr33'):return
    ishr=b.key.startswith('hr');panels=[p for p in b.panels if p['kind']=='floor'];group={}
    for p in panels:group.setdefault(p['level'],[]).append(p)
    for k,ps in group.items():
        if b.key=='hr14' and k==0:continue
        if b.key=='hr13' and k==4:continue  # Workshop roof is not an occupied office/mezzanine floor.
        top_level=max((row[0] for row in getattr(b,'levels',[])),default=max(group))
        if not ishr and k==top_level and b.key not in ('cfs29','cfs10','cfs18'):continue
        # Choose the two most separated source floor cells / polygon corners with an interior margin.
        candidates=[]
        # Include the actual ordinary/bearing framing ABOVE this floor. Testing
        # only the source braced segments left stairs under a through wall.
        from bisect import bisect_left,bisect_right
        z=ps[0]['vertices'][0][2]
        wall_points=sorted({tuple(m['axis'][0][:2]) for m in b.members
            if m['kind'] in ('stud','chord','opening_jamb','column')
            and math.dist(m['axis'][0][:2],m['axis'][1][:2])<.01
            and max(q[2] for q in m['axis'])>z+.1 and min(q[2] for q in m['axis'])<z+24})
        wall_x=[p[0] for p in wall_points]
        def clear_of_walls(xx,yy):
            return not any(yy-8<wy<yy+224 for _,wy in wall_points[bisect_left(wall_x,xx-8):bisect_right(wall_x,xx+104)])
        for panel in ps:
            poly=[[q[0],q[1]] for q in panel['vertices']];z=panel['vertices'][0][2]
            xs=[q[0] for q in poly];ys=[q[1] for q in poly]
            if ishr:
                if len(poly)!=4 or max(xs)-min(xs)<240 or max(ys)-min(ys)<300:continue
                candidates.append((min(xs)+(132 if b.key=='hr30' else 60),min(ys)+60,96,216,z))
            else:
                xstations=list(dict.fromkeys([min(xs)+72,max(xs)-168]+list(frange(min(xs)+24,max(xs)-119,24))))
                ystations=list(dict.fromkeys([min(ys)+72,max(ys)-288]+list(frange(min(ys)+24,max(ys)-239,24))))
                for xx in xstations:
                    for yy in ystations:
                        if all(any(lo<xxx<hi for lo,hi in intersections(poly,0,yyy)) for xxx in (xx,xx+96) for yyy in (yy,yy+216)):
                            # Keep floor holes clear of all source bearing/braced wall planes.
                            hit=any(w['level']==k and any((xx-12<r['position_in']<xx+108 if w['direction']=='Y' else yy-12<r['position_in']<yy+228) for r in w['runs']) for w in b.walls)
                            if not hit and clear_of_walls(xx,yy):candidates.append((xx,yy,96,216,z))
        if not candidates:continue
        chosen=[candidates[0]]
        if len(candidates)>1:
            far=max(candidates,key=lambda q:math.dist(q[:2],chosen[0][:2]))
            if math.dist(far[:2],chosen[0][:2])>400:chosen.append(far)
        for oi,(x,y,w,h,z) in enumerate(chosen):
            # Proprietary open-web floor joists are excluded from the void as full units;
            # headers/trimmers support their replacement supplier bay, explicitly A.
            feature=dict(id=f'STAIR-{k}-{oi+1}',kind='stair',plane='xy',x_ft=x/12,y_ft=y/12,z_ft=z/12,width_ft=w/12,height_ft=h/12,level=k,basis='A',query_id=b.key.upper()+'-OPENINGS',confirmed=True)
            # Secondary worklines end on the perimeter framing worklines. The
            # clear architectural void is still x/y/w/h, four inches inside.
            b.openings.append(feature);lo=[x-4,y-4,z-32];hi=[x+w+4,y+h+4,z+2];replaced={};cut_members=[]
            for m in list(b.members):
                if m['level']!=k or m['kind'] not in ('infill','joist','truss_chord','truss_web'):continue
                if max(q[2] for q in m['axis'])<z-32 or min(q[2] for q in m['axis'])>z+2:continue
                cut=interval_in_rectangle(*m['axis'],lo,hi,(0,1))
                if cut is None:continue
                cut_members.append(m)
                aa,dd=m['axis'];v=sub(dd,aa);chunks=[(0,cut[0]),(cut[1],1)];b.members.remove(m);new=[]
                for j,(u,t) in enumerate(chunks):
                    if (t-u)*math.dist(aa,dd)<1:continue
                    mm=b.member(m['id']+f'-O{oi}-{j}',m['profile_id'],m['kind'],add(aa,mul(v,u)),add(aa,mul(v,t)),k,'A',local_y=m['local_y'],records=m['design_record_ids'],source=m.get('source_member_id'))
                    # A cut does not erase the selected physical datum offset.
                    # Interpolate both offsets at the retained interval ends.
                    offsets=m.get('end_offsets',[[0,0,0],[0,0,0]])
                    mm['end_offsets']=[[a+s*(d-a) for a,d in zip(*offsets)] for s in (u,t)]
                    mm['original_physical_member_id']=m.get('original_physical_member_id',m['id'])
                    new.append(mm)
                    # Only a newly cut end receives an opening connection.
                    # Preserve the selected original end detail at uncut ends.
                    for end,station in ((0,u),(1,t)):
                        if (end==0 and station>1e-7) or (end==1 and station<1-1e-7):
                            b.connection(mm['id']+':opening-'+str(end),'test_floor_opening',mm['axis'][end],[mm])
                replaced[m['id']]=[q['id'] for q in new]
                b.changes.append(dict(kind='framed_opening_cut',old_member=m['id'],new_members=replaced[m['id']],opening=feature['id'],basis='A'))
            if replaced:
                kept=[];byid={m['id']:m for m in b.members}
                for c in b.connections:
                    original=list(c['member_ids'])
                    mapped=[]
                    for mid in original:
                        if mid not in replaced:mapped.append(mid);continue
                        for rid in replaced[mid]:
                            axis=byid[rid]['axis'];vector=sub(axis[1],axis[0]);length=math.dist(*axis)
                            station=sum(v*(q-a) for v,q,a in zip(vector,c['point'],axis[0]))/(length*length)
                            nearest=add(axis[0],mul(vector,max(0,min(1,station))))
                            if math.dist(nearest,c['point'])<.01:mapped.append(rid)
                    c['member_ids']=list(dict.fromkeys(mapped))
                    if c['member_ids']:
                        if len(c['member_ids'])==1 and c['detail_ref']['id'] in ('review_truss_node','review_truss_heel'):
                            # A cut exactly at a panel point can remove the web
                            # and the next chord without creating a new cut-end
                            # connection. Its surviving chord meets the opening
                            # frame; it has not acquired a wall/roof seat.
                            old_family=c['detail_ref']['id'];c['detail_ref']['id']='test_floor_opening'
                            b.changes.append(dict(kind='opening_panel_point_attachment',connection_id=c['id'],previous_family=old_family,
                                opening=feature['id'],basis='A: surviving truss panel-point end attaches to the actual opening header/trimmer; supplier opening redesign remains delegated'))
                        kept.append(c)
                    else:b.changes.append(dict(kind='opening_removed_connection',source=c,source_member_ids=original,opening=feature['id'],basis='Accepted fictional opening removes this station; source design remains in the record register'))
                b.connections=kept
            fp=b.profile('W18X40' if ishr else '2X1200S250-97');depth=b.depth(fp);zz=z-depth/2 if ishr else z-.75-depth/2
            plain_joists=[m for m in cut_members if m['kind']=='joist']
            chord_sources=[m for m in cut_members if m['kind']=='truss_chord' and abs(m['axis'][0][2]-m['axis'][1][2])<.01]
            framing_sources=plain_joists
            frame_axis=None
            if not ishr and plain_joists and len(plain_joists)==len(cut_members):
                # A rectangular perimeter floating between cut joists has no
                # independent bearing route. Run the parallel trimmers to the
                # same supports as the original joists, with headers between.
                directions={0 if abs(m['axis'][1][0]-m['axis'][0][0])>.01 else 1 for m in plain_joists}
                if len(directions)==1:
                    frame_axis=directions.pop()
                    zz=max(q[2]+o[2]+b.depth(m['profile_id'])/2 for m in plain_joists for q,o in zip(m['axis'],m['end_offsets']))-depth/2
            elif not ishr and chord_sources:
                directions={0 if abs(m['axis'][1][0]-m['axis'][0][0])>.01 else 1 for m in chord_sources}
                if len(directions)==1:
                    # Open-web units have several chord pieces. Their whole
                    # original span, not one cut panel length, defines the
                    # trimmer's bearing route. Keep the actual top-chord datum.
                    frame_axis=directions.pop()
                    prefixes={m.get('original_physical_member_id',m['id']).rsplit('-',1)[0] for m in chord_sources}
                    framing_sources=[m for m in b.members+cut_members if m['kind']=='truss_chord'
                        and m.get('original_physical_member_id',m['id']).rsplit('-',1)[0] in prefixes]
                    zz=max(q[2]+o[2]+b.depth(m['profile_id'])/2 for m in chord_sources for q,o in zip(m['axis'],m['end_offsets']))-depth/2
            for j,(aa,dd) in enumerate((([x-4,y-4,zz],[x+w+4,y-4,zz]),([x-4,y+h+4,zz],[x+w+4,y+h+4,zz]),([x-4,y-4,zz],[x-4,y+h+4,zz]),([x+w+4,y-4,zz],[x+w+4,y+h+4,zz]))):
                parallel=frame_axis is not None and (0 if j<2 else 1)==frame_axis
                if parallel:
                    example=min(framing_sources,key=lambda m:abs(m['axis'][0][1-frame_axis]-aa[1-frame_axis]))
                    span=[example]
                    if example['kind']=='truss_chord':
                        prefix=example.get('original_physical_member_id',example['id']).rsplit('-',1)[0]
                        span=[m for m in framing_sources if m.get('original_physical_member_id',m['id']).rsplit('-',1)[0]==prefix]
                    aa[frame_axis]=min(q[frame_axis] for m in span for q in m['axis']);dd[frame_axis]=max(q[frame_axis] for m in span for q in m['axis'])
                kind=('opening_trimmer' if parallel else 'opening_header') if frame_axis is not None else ('opening_header' if j<2 else 'opening_trimmer')
                m=b.member(feature['id']+'-FRAME'+str(j),fp,kind,aa,dd,k,'A');b.ends(m,'review_cfs_joist' if parallel else 'test_floor_opening')
            if frame_axis is not None:
                b.changes.append(dict(kind='opening_trimmers_to_source_supports',opening=feature['id'],source_joist_ids=[m['id'] for m in framing_sources],
                    basis='A: full-span paired trimmers parallel the original joists and share their bearing lines. Header top flanges align with the actual joist top flanges; source joist datums and selected sections are unchanged. New framing/connection capacity remains unverified.'))
            for panel in ps:
                panel.setdefault('openings',[]).append(feature['id'])
    b.note('FLOOR-OPENINGS','A: dimensioned 8 x 18 ft stair coordination openings occupy the scheduled floor cells, with W18x40 HR or paired 1200S250-97 CFS perimeter framing. Affected secondary members terminate at the new perimeter and receive end details. Any cut proprietary joist is a fictional replacement assembly, not an approved alteration to a supplier product; reactions and capacity approval remain delegated.')
