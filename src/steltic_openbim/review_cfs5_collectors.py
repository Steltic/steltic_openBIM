"""CFS5 source drag straps on actual joists and source full-depth blocks.

Source sections and fastener counts are retained. The prior fictional bay
set-out exceeds some source gap lengths; finite fits and WSP rebates are
explicit adopted inputs and do not inherit the saved capacity verification.
"""
import math
from collections import defaultdict
from shapely.geometry import box,Point
from shapely.ops import unary_union
from shapely.prepared import prep
from .review_cfs5_diaphragms import region,xfaces,GLOBAL
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .pilots.model import add,sub

T=.0566
PT=.1017


def gaps(wall,limit):
    """Only external boundaries of contiguous braced runs need a gap drag."""
    groups=[]
    for i,run in enumerate(wall['runs']):
        if groups and abs(groups[-1][1]-run['start_in'])<.01:
            groups[-1][1]=run['end_in'];groups[-1][3]=i+1
        else:groups.append([run['start_in'],run['end_in'],i+1,i+1])
    result=[];previous=None
    for lo,hi,first,last in groups:
        # Chords are located three inches inside the bay ends in the
        # accepted set-out. Bind by exact IDs, never to a nearby stud.
        left=wall['id']+f'-B{first}-CH0'
        right=wall['id']+f'-B{last}-CH1'
        result.append((0 if previous is None else previous[0],lo+3,
                       [] if previous is None else [previous[1]],left))
        previous=(hi-3,right)
    result.append((previous[0],limit,[previous[1]],None))
    return result


def rebate(panel,member,along,width,depth):
    normal=1-along;aa,dd=axis(member);bounds=[None,None]
    bounds[along]=sorted((aa[along],dd[along]));bounds[normal]=[aa[normal]-width/2,aa[normal]+width/2]
    panel.setdefault('underside_recesses',[]).append(dict(id=member['id']+'-RECESS',bounds_xy_in=bounds,
        depth_in=depth,side='underside',support_member_id=member['id'],
        basis='A explicit underside rebate for steel drag; source nominal WSP thickness retained. Reduced local panel thickness and strength require verification.'))


def apply(b):
    if b.key!='cfs5':return
    lookup={m['id']:m for m in b.members};openings={o['id']:o for o in b.openings}
    joists=[m for m in b.members if m['kind']=='joist'];existing={}
    for m in b.members:
        if m['kind']=='diaphragm_blocking':
            aa,dd=axis(m);existing[(m['level'],round(aa[1],5),round(aa[0],5),round(dd[0],5))]=m
    end_cons={c['id']:c for c in b.connections};counts=defaultdict(int);footprints=defaultdict(list)
    collector_straps=[]
    for panel in [p for p in b.panels if p['kind'] in ('floor','roof')]:
        k=panel['level'];roof=panel['kind']=='roof';poly=region(panel,openings)
        top=panel['vertices'][0][2];bottom=top-panel['thickness_in']
        available=[m for m in joists if m['level']==k]

        def block_row(y,rid,start,finish,adjacent_to=None):
            selected={}
            for m in available:
                aa,dd=axis(m)
                if aa[1]+.1<y and y+2.1<dd[1]:selected[round(aa[0],6)]=m
            ordered=sorted(selected.items());made=[]
            for j,((xl,left),(xr,right)) in enumerate(zip(ordered,ordered[1:])):
                if xr<start or xl>finish:continue
                if adjacent_to is not None and min(abs(xl-adjacent_to),abs(xr-adjacent_to))>.001:continue
                lo=xfaces(b,left)[1]+.125;hi=xfaces(b,right)[0]-.125
                if hi-lo<4 or xr-xl>16.01:raise ValueError('No finite source collector blocking interval')
                if not poly.covers(box(lo,y-.1,hi,y+2.1)):raise ValueError('Collector blocking crosses a panel opening')
                key=(k,round(y,5),round(lo,5),round(hi,5));block=existing.get(key)
                if block is None:
                    block=b.member(f'DRAG-BLOCK-L{k}-Y{y:g}-X{xl:g}','1000S200-68','collector_blocking' if adjacent_to is not None else 'diaphragm_blocking',
                        [lo,y,bottom-5],[hi,y,bottom-5],k,'A',records=[rid],local_y=[0,1,0])
                    existing[key]=block
                    for e,host in enumerate((left,right)):
                        cid=block['id']+'-END'+str(e)
                        end_cons[cid]=b.connection(cid,'review_wsp_block',axis(block)[e],[block,host],[rid],
                            parameters=dict(actual_cfs5_diaphragm=True,purpose='block_end',end=e,source_collector_block=True),title='SOURCE DRAG BLOCK / SIX SCREWS PER CLIP LEG')
                        b.endpoint_links.append(dict(member_id=block['id'],end='start' if e==0 else 'end',connection_id=cid,basis='S full-depth68mil block and54mil end clip, sixNo10 per leg; A finite piece length, clip dimensions and stations.'))
                else:
                    block['profile_id']=b.profile('1000S200-68')
                    block['design_record_ids']=sorted(set(block['design_record_ids']+[rid]))
                    for e in (0,1):
                        c=end_cons[block['id']+'-END'+str(e)];c['parameters']['source_collector_block']=True
                        c['design_record_ids']=sorted(set(c['design_record_ids']+[rid]))
                block['source_collector_block']=True
                block['physical_fit_basis']='S1000S200-68 full-depth block; A finite clearance length and screw gauge fitted to the actual joists. Source14.5in nominal length is not assigned to shorter intervals.'
                made.append(block)
            return made

        def fix(cid,strap,host,points,rid,purpose):
            origin=[sum(q[i] for q in points)/len(points) for i in range(3)]
            return b.connection(cid,'review_cfs5_drag_screws',origin,[strap,host],[rid],parameters=dict(
                purpose=purpose,host_panel_id=panel['id'],subfloor_thickness=panel['thickness_in'],
                rebate=b.profiles[strap['profile_id']]['dimensions']['thickness'],points_relative=[sub(q,origin) for q in points]),
                title='SOURCE DRAG STRAP / ACTUAL SHEATHING AND SUPPORT')

        for wall in [w for w in b.walls if w['level']==k and w['direction']=='X']:
            rid='collectors/collector-'+wall['line']+'-drag'
            if rid not in b.records:raise ValueError('Missing source drag '+rid)
            y={'XS':4 if roof else .25,'XCS':324.25,'XCN':393.75,'XN':714.5 if roof else 717.5}[wall['line']]
            for gi,(aa,dd,left,right) in enumerate(gaps(wall,2160)):
                ends=left+([right] if right else []);blocks=block_row(y,rid,aa-3,dd+3)
                if not blocks:raise ValueError('Source gap has no blocking')
                lo=max(poly.bounds[0]+(3.25 if roof else .25),min(aa-3,min(axis(m)[0][0] for m in blocks)-.25))
                hi=min(poly.bounds[2]-(3.25 if roof else .25),max(dd+3,max(axis(m)[1][0] for m in blocks)+.25))
                centre=min(poly.bounds[3]-1.5,max(poly.bounds[1]+1.5,y+.75))
                if not poly.covers(box(lo,centre-1.5,hi,centre+1.5)):raise ValueError('Source drag crosses an unresolved floor opening '+str((panel['id'],wall['id'],gi,lo,hi,centre,poly.bounds)))
                pid=b.custom('CFS5-S-DRAG3X54','flat',dict(width=3,thickness=T),basis='S3in54mil Gr50 collector strap')
                strap=b.member(f'DRAG-{wall["id"]}-G{gi}',pid,'collector',[lo,centre,bottom+T/2],[hi,centre,bottom+T/2],k,'A',records=[rid],local_y=[0,1,0],
                    source_selection='S3in54mil strap; A fitted span and overlap. Actual gaps may exceed source9ft; saved capacity does not certify this changed fit.',drag_end_chords=ends)
                collector_straps.append(strap);rebate(panel,strap,0,3,T)
                footprints[panel['id']].append(box(lo,centre-1.5,hi,centre+1.5))
                connections=[]
                for block in blocks:
                    ba,bd=axis(block);span=bd[0]-ba[0];pitch=min(3,(span-1.5)/3);mid=(ba[0]+bd[0])/2
                    pts=[[mid+(i-1.5)*pitch,y+.75,top] for i in range(4)]
                    c=fix(strap['id']+'-'+block['id'],strap,block,pts,rid,'four_per_block');connections.append(c)
                    counts['block_screws']+=4
                for host in available:
                    ja,jd=axis(host);hd=b.profiles[host['profile_id']]['dimensions']
                    x=ja[0]+host['local_y'][0]*hd['b']/2
                    if lo+.285<x<hi-.285 and ja[1]+.285<y+.75<jd[1]-.285:
                        c=fix(strap['id']+'-'+host['id'],strap,host,[[x,y+.75,top]],rid,'joist_intersection');connections.append(c)
                for end,fn in (('start',min),('end',max)):
                    c=fn(connections,key=lambda c:c['point'][0]);b.endpoint_links.append(dict(member_id=strap['id'],end=end,connection_id=c['id'],basis='Actual terminal source block/joist fixing; braced-bay drag terminal separately connects to the source chord and top track.'))
                counts['x_straps']+=1
        xstrips=[m for m in collector_straps if m['level']==k]
        for wall in [w for w in b.walls if w['level']==k and w['direction']=='Y']:
            endwall=wall['line'] in ('YW','YE');width=6 if endwall else 3;thickness=.0713 if endwall else T
            rid='collectors/collector-'+('end' if endwall else 'party')+'-drag'
            wallx=wall['runs'][0]['position_in']
            joistx=(5.25 if wallx==0 else 2156.75 if wallx==2160 else wallx) if roof else wallx
            hosts=[m for m in available if abs(axis(m)[0][0]-joistx)<.001]
            if not hosts:raise ValueError('Y drag lacks actual wall-line joist '+wall['id'])
            for host in hosts:
                # The source specifically requires68mil wall-line drag joists
                # even at the54mil field roof. Retain the source selection.
                if host['profile_id'] not in ('1000S200-54','1000S200-68'):raise ValueError('Unexpected source wall-line joist '+host['id']+' '+host['profile_id'])
                if host['profile_id']!='1000S200-68':
                    host['prior_profile_id']=host['profile_id'];host['profile_id']=b.profile('1000S200-68')
                    host['design_record_ids']=sorted(set(host['design_record_ids']+[rid]))
                    host['physical_fit_basis']='S collector selection explicitly requires68mil wall-line joist;54mil field-roof selection applies away from these collectors.'
            j=hosts[0];centre=joistx+j['local_y'][0]*b.profiles[j['profile_id']]['dimensions']['b']/2
            centre=min(poly.bounds[2]-width/2,max(poly.bounds[0]+width/2,centre))
            if roof and endwall:centre=min(poly.bounds[2]-3.25-width/2,max(poly.bounds[0]+3.25+width/2,centre))
            pid=b.custom('CFS5-S-DRAG'+('6X68' if endwall else '3X54'),'flat',dict(width=width,thickness=thickness),basis='S selected Gr50 collector strap')
            packpid=b.custom('A-CFS5-DRAG-PACK'+str(width),'flat',dict(width=width,thickness=T),basis='A54mil pack beneath crossing Y drag, interrupted at actual X straps')
            for gi,(aa,dd,left,right) in enumerate(gaps(wall,720)):
                lo=max(3.25 if roof else .25,aa-3);hi=min(716.75 if roof else 719.75,dd+3)
                if not poly.covers(box(centre-width/2,lo,centre+width/2,hi)):raise ValueError('Y source drag crosses an unresolved panel opening '+wall['id'])
                strap=b.member(f'DRAG-{wall["id"]}-G{gi}',pid,'collector',[centre,lo,bottom+T+PT+thickness/2],[centre,hi,bottom+T+PT+thickness/2],k,'A',records=[rid],local_y=[1,0,0],
                    source_selection='S selected strap and wall-line joist; A extended gap/overlap,54+97mil raised crossing plane and actual finite packing. No original capacity assigned to changed fit.',drag_end_chords=left+([right] if right else []))
                collector_straps.append(strap);rebate(panel,strap,1,width,T+PT+thickness)
                footprints[panel['id']].append(box(centre-width/2,lo,centre+width/2,hi))
                # Keep crossing steel as separate touching plies, never two
                # solids occupying the same volume. Constant-height Y straps
                # have explicit finite packing everywhere except X crossings.
                intervals=[(lo,hi)]
                for xs in xstrips:
                    xa,xd=axis(xs)
                    if xa[0]<centre+width/2 and xd[0]>centre-width/2:
                        yl,yh=xa[1]-1.5,xa[1]+1.5;next_intervals=[]
                        for al,ah in intervals:
                            if yh<=al or yl>=ah:next_intervals.append((al,ah));continue
                            if yl>al:next_intervals.append((al,yl))
                            if yh<ah:next_intervals.append((yh,ah))
                        intervals=next_intervals
                for pi,(al,ah) in enumerate(intervals):
                    if ah-al<.01:continue
                    b.member(strap['id']+'-PACK'+str(pi),packpid,'collector_packing',[centre,al,bottom+T/2],[centre,ah,bottom+T/2],k,'A',records=[rid],local_y=[1,0,0])
                connections=[]
                for host in hosts:
                    ja,jd=axis(host);yl=max(lo+.5,ja[1]+.5);yh=min(hi-.5,jd[1]-.5)
                    if yh<yl:continue
                    count=max(1,math.ceil((yh-yl)/3));x=ja[0]+host['local_y'][0]*b.profiles[host['profile_id']]['dimensions']['b']/2
                    points=[[x,yl+(yh-yl)*i/count,top] for i in range(count+1)]
                    for start in range(0,len(points),6):
                        c=fix(strap['id']+'-'+host['id']+'-'+str(start),strap,host,points[start:start+6],rid,'wall_line_3in');connections.append(c)
                    counts['wall_line_screws']+=len(points)
                for y in range(12,720,24):
                    if lo<y and y+2<hi:block_row(y,rid,joistx-16,joistx+16,adjacent_to=joistx)
                for end,fn in (('start',min),('end',max)):
                    c=fn(connections,key=lambda c:c['point'][1]);b.endpoint_links.append(dict(member_id=strap['id'],end=end,connection_id=c['id'],basis='Actual terminal wall-line joist fixing; source braced-bay terminal is separately detailed.'))
                counts['y_straps']+=1
        b.used_records.update(c for c in b.records if c.startswith('collectors/collector-X'))
    from .review_cfs5_drag_ends import apply as drag_ends
    drag_ends(b,collector_straps)
    # A second97mil packing layer places the Y straps above X drag end
    # plates. Interrupt that layer wherever a real X terminal plate already
    # fills it; do not allow two crossing collector solids to occupy one ply.
    xplates=[m for m in b.members if m['kind']=='drag_plate' and m['id'].endswith('-TOP') and abs(axis(m)[1][0]-axis(m)[0][0])>1]
    panels_by_level={p['level']:p for p in b.panels if p['kind'] in ('floor','roof')}
    for strap in collector_straps:
        aa,dd=axis(strap)
        if abs(dd[1]-aa[1])<1:continue
        width=b.profiles[strap['profile_id']]['dimensions']['width'];k=strap['level'];intervals=[(aa[1],dd[1])]
        for plate in xplates:
            if plate['level']!=k:continue
            pa,pd=axis(plate);xl,xh=sorted((pa[0],pd[0]));yl,yh=pa[1]-4,pa[1]+4
            if xh<=aa[0]-width/2 or xl>=aa[0]+width/2 or yh<=aa[1] or yl>=dd[1]:continue
            if xl>aa[0]-width/2+.001 or xh<aa[0]+width/2-.001:raise ValueError('X drag plate only partly covers a Y crossing '+plate['id'])
            from .review_cfs5_drag_ends import subtract
            intervals=subtract(intervals,yl,yh)
        panel=panels_by_level[k];bottom=panel['vertices'][0][2]-panel['thickness_in']
        pid=b.custom('A-CFS5-DRAG-UPPER-PACK'+str(width),'flat',dict(width=width,thickness=PT),basis='A97mil crossing pack; interrupted at actual X terminal plates')
        for pi,(lo,hi) in enumerate(intervals):
            if hi-lo>.01:b.member(strap['id']+'-UPPER-PACK'+str(pi),pid,'collector_packing',[aa[0],lo,bottom+T+PT/2],[aa[0],hi,bottom+T+PT/2],k,'A',records=strap['design_record_ids'],local_y=[1,0,0])
    # Each screw explicitly traverses every overlapping steel ply. Separate
    # local WSP contexts represent the different rebate depths at crossings.
    flats=[m for m in b.members if m['kind'] in ('collector','collector_packing','drag_plate') and m['id'].startswith('DRAG-') and abs(axis(m)[1][2]-axis(m)[0][2])<.001]
    flat_levels={m['id']:m['level'] for m in flats};cells=defaultdict(list)
    bottoms={p['level']:p['vertices'][0][2]-p['thickness_in'] for p in b.panels if p['kind'] in ('floor','roof')}
    for m in flats:
        aa,dd=axis(m);d=b.profiles[m['profile_id']]['dimensions'];steel_top=aa[2]+d['thickness']/2
        if steel_top<bottoms[m['level']]-.001:continue
        along=0 if abs(dd[0]-aa[0])>1 else 1;normal=1-along
        bb=[None,None];bb[along]=sorted((aa[along],dd[along]));bb[normal]=[aa[normal]-d['width']/2+.095,aa[normal]+d['width']/2-.095]
        for ix in range(math.floor(bb[0][0]/32),math.floor(bb[0][1]/32)+1):
            for iy in range(math.floor(bb[1][0]/32),math.floor(bb[1][1]/32)+1):cells[m['level'],ix,iy].append((m,bb,steel_top))
    attached=defaultdict(list)
    for c in b.connections:
        if c['detail_ref']['id']!='review_cfs5_drag_screws':continue
        par=c['parameters'];k=flat_levels[c['member_ids'][0]];points=[add(c['point'],p) for p in par['points_relative']]
        par['fixing_layers']=[]
        for point in points:
            indices=[0,1];top_steel=point[2]-par['subfloor_thickness']
            for m,bb,steel_top in cells[k,math.floor(point[0]/32),math.floor(point[1]/32)]:
                if all(bb[i][0]-.0001<=point[i]<=bb[i][1]+.0001 for i in (0,1)):
                    if m['id'] not in c['member_ids']:c['member_ids'].append(m['id'])
                    indices.append(c['member_ids'].index(m['id']));top_steel=max(top_steel,steel_top)
                    attached[m['id']].append(c)
            par['fixing_layers'].append(dict(member_indices=sorted(set(indices)),rebate=top_steel-(point[2]-par['subfloor_thickness'])))
    for m in flats:
        if m['kind']!='collector_packing':continue
        candidates=attached[m['id']]
        if not candidates:raise ValueError('Crossing pack lacks an actual fixing '+m['id'])
        for end,fn in (('start',min),('end',max)):
            c=fn(candidates,key=lambda c:c['point'][1]);b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='A finite crossing pack retained by the actual through-ply source drag screws.'))
    # Replace only sheet screws inside the added steel footprint. Their new
    # source four-per-block/joist fixings go through every physical ply.
    keep=[];covered={panel:prep(unary_union(polygons)) for panel,polygons in footprints.items()}
    for c in b.connections:
        par=c.get('parameters',{});panel=par.get('host_panel_id')
        if c['detail_ref']['id']=='review_wsp_screws' and panel in footprints:
            par['points_relative']=[p for p in par['points_relative'] if not covered[panel].covers(Point(add(c['point'],p)[:2]))]
            if not par['points_relative']:continue
        keep.append(c)
    b.connections[:]=keep
    b.changes.append(dict(kind='cfs5_source_collector_straps',counts=dict(counts)))
    b.note('SOURCE-COLLECTORS','S X-line3in54mil straps,1000S200-68 blocks in every joist space, fourNo10 maximum3in pitch per block and54mil clips with sixNo10 each leg; party3in54mil/end6in68mil straps on68mil wall-line joists withNo10 at3in and solid blocking at24in. A finite spans, clipped blocks, additional joist fixings,54+97mil Y crossing packs and underside WSP rebates. Actual X/party gaps can exceed source9ft/8ft lengths; original capacities do not certify the altered set-out, packing or reduced WSP thickness.')


def draw(ctx):
    a,par=ctx.a,ctx.params;points=par['points_relative'];extent=max(math.sqrt(sum(v*v for v in p)) for p in points)+2
    a.title='SOURCE DRAG STRAP / ACTUAL SHEATHING, STEEL PLIES AND SUPPORT'
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,extent)
    top=points[0][2];t=par['subfloor_thickness']
    ht=ctx.p[ctx.ms[1]['profile_id']]['dimensions']['t']
    groups=[]
    for point,layers in zip(points,par['fixing_layers']):
        if groups and groups[-1][0]==layers:groups[-1][1].append(point)
        else:groups.append((layers,[point]))
    for i,(layers,chosen) in enumerate(groups):
        rebate_depth=layers['rebate'];label='WSP'+str(i);bottom=top-t+rebate_depth
        lo=[min(q[j] for q in chosen)-.15 for j in (0,1)];hi=[max(q[j] for q in chosen)+.15 for j in (0,1)]
        wsp=a.box(label,[*lo,bottom],[hi[0]-lo[0],hi[1]-lo[1],t-rebate_depth],
            'S nominal WSP thickness; A explicit underside rebate','Actual host sheathing, no duplicate physical layer',kind='wood_panel')
        wsp.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True,drawing_style='outline')
        source=par['purpose']!='joist_intersection'
        a.fastener('S'+str(i),chosen,[0,0,-1],.19,t+ht,[label]+['M'+str(j) for j in layers['member_indices']],
            'S No10 maximum3in pitch; A finite gauge, crossing plies and through-WSP head bearing' if source else 'A No10 through WSP/drag plies into actual joist top flange',basis='S' if source else 'A',screw=True)
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=points[0][0]
    a.notes.append('Source strap and block sections, screw count and maximum pitch retained. A finite lengths, WSP rebate and head bearing need verification; no capacity is assigned to an extended source gap or modified sheathing.')
