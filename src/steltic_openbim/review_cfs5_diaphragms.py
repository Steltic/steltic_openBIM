"""CFS5 blocked WSP edges on the actual joists, with explicit A blocking fit.

The source selects the WSP and No10 edge schedule. Sheet seams, blocking
sections and end clips are accepted geometric proposals, not checked designs.
"""
import math
from collections import defaultdict
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .pilots.model import add,sub,mul,unit
from .pilots.geometry import strips

T=.0566
GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def region(panel,openings):
    polygon=Polygon([q[:2] for q in panel['vertices']])
    holes=[]
    for oid in panel.get('openings',[]):
        o=openings[oid];holes.append(box(o['x_ft']*12,o['y_ft']*12,
            (o['x_ft']+o['width_ft'])*12,(o['y_ft']+o['height_ft'])*12))
    return polygon.difference(unary_union(holes)) if holes else polygon


def xfaces(b,member):
    aa,dd=axis(member);profile=b.profiles[member['profile_id']]
    if profile['family']!='channel' or abs(dd[0]-aa[0])>.001 or abs(member['local_y'][0])<.99:
        raise ValueError('CFS5 diaphragm needs a selected Y-joist section')
    xs=[aa[0]+member['local_y'][0]*q[0] for poly in strips(profile,b.profiles) for q in poly]
    return min(xs),max(xs)


def apply(b):
    if b.key!='cfs5':return
    panels=[p for p in b.panels if p['kind'] in ('floor','roof')]
    openings={o['id']:o for o in b.openings};joists=[m for m in b.members if m['kind']=='joist'];counts=defaultdict(int)
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for panel in panels:
        k=panel['level'];roof=panel['kind']=='roof';poly=region(panel,openings);top=panel['vertices'][0][2]
        bottom=top-panel['thickness_in'];available=[m for m in joists if m['level']==k]
        records=[r['id'] for r in b.records.values() if r['table']=='diaphragms' and r['data']['level']==k]
        if len(records)!=4:raise ValueError('CFS5 floor must retain three X-zone checks and one Y check')
        made=[]
        # A 48in short-edge rows; 96in long edges coincide with the 16in
        # joist grid. Perimeter support rows clear the continuous parapets.
        rows=[4.0 if roof else .25]+list(range(48,720,48))+[714.5 if roof else 717.5]
        for row,y in enumerate(rows):
            selected={}
            for member in available:
                aa,dd=axis(member);lo,hi=sorted((aa[1],dd[1]))
                if lo+.1<y and y+2.1<hi:
                    selected[round(aa[0],6)]=member
            ordered=sorted(selected.items())
            for j,((xl,left),(xr,right)) in enumerate(zip(ordered,ordered[1:])):
                if xr-xl>16.01:raise ValueError('No actual joist across a diaphragm blocking interval')
                ld=b.profiles[left['profile_id']]['dimensions'];rd=b.profiles[right['profile_id']]['dimensions']
                if abs(axis(left)[0][2]+ld['d']/2-bottom)>.001 or abs(axis(right)[0][2]+rd['d']/2-bottom)>.001:
                    raise ValueError('WSP and joist top datums differ')
                lo=xfaces(b,left)[1]+.125;hi=xfaces(b,right)[0]-.125
                if hi-lo<4:raise ValueError('Diaphragm blocking needs a clear receiver interval')
                footprint=box(lo,y-.1,hi,y+2.1)
                if not poly.covers(footprint):continue
                # Use an explicitly adopted section matching the shallower
                # receiver depth. Do not call it a source blocking selection.
                depth=min(ld['d'],rd['d']);pid=b.profile(f'{round(depth*100)}S200-54')
                block=b.member(f'WSP-BLOCK-L{k}-R{row}-{j}',pid,'diaphragm_blocking',
                    [lo,y,bottom-depth/2],[hi,y,bottom-depth/2],k,'A',records=records,local_y=[0,1,0],
                    source_requirement='S blocked WSP edges; A section, finite seam set-out and attachment')
                made.append(block)
                for end,host in enumerate((left,right)):
                    cid=block['id']+'-END'+str(end)
                    c=b.connection(cid,'review_wsp_block',axis(block)[end],[block,host],records,
                        parameters=dict(actual_cfs5_diaphragm=True,purpose='block_end',end=end),title='WSP EDGE BLOCK / ACTUAL JOIST')
                    b.endpoint_links.append(dict(member_id=block['id'],end='start' if end==0 else 'end',connection_id=cid,
                        basis='A finite block with a54mil folded end clip and twoNo10 screws per leg to the actual joist web; no new capacity verification.'))
        safe=poly.buffer(-.35)
        for host in available+made:
            aa,dd=axis(host);u=unit(sub(dd,aa));d=b.profiles[host['profile_id']]['dimensions']
            if abs(aa[2]+d['d']/2-bottom)>.001:raise ValueError('WSP support does not reach its underside')
            p0=add(add(aa,mul(u,.4)),mul(host['local_y'],.75));p1=add(add(dd,mul(u,-.4)),mul(host['local_y'],.75))
            line=LineString([p0[:2],p1[:2]]).intersection(safe)
            segments=[line] if line.geom_type=='LineString' else getattr(line,'geoms',[])
            for run,segment in enumerate(segments):
                if segment.geom_type!='LineString' or segment.length<.1:continue
                n=max(1,math.ceil(segment.length/6));points=[[q.x,q.y,top] for q in [segment.interpolate(i/n,normalized=True) for i in range(n+1)]]
                for group in range(0,len(points),6):
                    selected=points[group:group+6];origin=[sum(q[i] for q in selected)/len(selected) for i in range(3)]
                    b.connection(host['id']+f'-WSP-{run}-{group//6}','review_wsp_screws',origin,[host],records,
                        parameters=dict(actual_cfs5_diaphragm=True,host_panel_id=panel['id'],subfloor_thickness=panel['thickness_in'],
                            points_relative=[sub(q,origin) for q in selected],source_pitch_in=6),title='SOURCE WSP / SIX-INCH FIXINGS')
                    counts['screws']+=len(selected)
        panel['design_record_ids']=sorted(set(panel['design_record_ids']+records));b.used_records.update(records)
        panel['attachment_schedule']=dict(source_records=records,screw='No10',maximum_pitch_in=6,
            blocking_member_ids=[m['id'] for m in made],sheet_grid_in=[96,48],edge_support_rows_y_in=rows,
            basis='S blocked Structural I WSP and6in edge/other-edge No10 screws. A96x48in nominal seams, matching-depth54mil blocks, twoNo10 per54mil clip leg, and6in field screws. Perimeter support follows actual joists and parapet clearances. Sheet edge offsets and all added connections require verification.')
        counts['blocks']+=len(made)
    b.changes.append(dict(kind='source_cfs5_blocked_diaphragms',counts=dict(counts),
        basis='S WSP thickness/grade, blocked edges andNo10 screws6in maximum; A sheet grid, blocking sections, clips and finite fixing stations. All source checks remain unchanged.'))
    b.note('BLOCKED-DIAPHRAGM','S:23/32in floor and19/32in roof Structural I WSP, blocked, No10 screws6in at edges/other edges. A:96x48in nominal sheet grid; matching-depth54mil blocking;54mil folded clips with twoNo10 per leg;6in field fixing. Boundary blocking is offset to clear actual parapets. These local fits, edge offsets and added attachments are unverified. Collectors have their own source-specific components and end connections.')


def draw(ctx):
    a=ctx.a;par=ctx.params;origin=ctx.c['point'];host=ctx.ms[0]
    if ctx.family=='review_wsp_screws':
        points=par['points_relative'];extent=max(math.sqrt(sum(v*v for v in q)) for q in points)+1
        steel=extract(ctx,host,'SUPPORT',GLOBAL,extent);top=points[0][2];t=par['subfloor_thickness'];bottom=top-t
        if abs(bottom-steel['bounds'][2][1])>.001:raise ValueError('Actual WSP fixing misses the steel top')
        lo=[min(q[i] for q in points)-.2 for i in (0,1)];hi=[max(q[i] for q in points)+.2 for i in (0,1)]
        wsp=a.box('WSP',[*lo,bottom],[hi[0]-lo[0],hi[1]-lo[1],t],'S thickness; A local context extent',
            'Actual Structural I host panel; no duplicate physical sheathing',kind='wood_panel')
        wsp.update(representation_role='context_only',source_panel_parameter='host_panel_id',show_in_section=True)
        ht=ctx.p[host['profile_id']]['dimensions']['t']
        a.fastener('SCREWS',points,[0,0,-1],.19,t+ht,['WSP','SUPPORT'],'S No10 screws6in maximum; A exact stations',screw=True)
        along=max(range(2),key=lambda i:abs(host['axis'][1][i]-host['axis'][0][i]))
        a.front_axes=(along,2);a.section_axis=1-along;a.section_at=points[0][1-along]
        a.notes.append('The sheathing is context from its declared actual panel. Source layer, screw size and maximum edge pitch retained. The6in field pattern, finite sheet seams and block fit are accepted proposals, without new diaphragm capacity verification.')
        return
    block,joist=ctx.ms;bp=extract(ctx,block,'BLOCK',GLOBAL,10);jp=extract(ctx,joist,'JOIST',GLOBAL,10)
    bt=ctx.p[block['profile_id']]['dimensions']['t'];jt=ctx.p[joist['profile_id']]['dimensions']['t']
    bx,by,bz=bp['member']['axis'][par['end']];jx=jp['member']['axis'][0][0];sign=1 if par['end']==0 else -1
    face=jx+sign*jt/2;far=bx+sign*2.5
    side=1 if by-min(q[1] for q in jp['member']['axis'])<4 else -1
    yface=by+side*bt/2
    def plate(label,lo,hi,description):
        low=[min(x,y) for x,y in zip(lo,hi)];size=[abs(x-y) for x,y in zip(lo,hi)]
        return a.box(label,low,size,'A',description)
    plate('BLOCK-LEG',[face,yface,bz-1.25],[far,yface+side*T,bz+1.25],'A54mil folded clip on actual block web')
    plate('JOIST-LEG',[face,yface+side*(T+3),bz-1.25],[face+sign*T,yface+side*T,bz+1.25],'A54mil return on actual joist web')
    source_block=bool(par.get('roof_restraint_block'))
    a.fastener('FB',[[bx+sign*1.25,yface+side*T,bz+z] for z in (-.75,.75)],[0,-side,0],.19,T+bt,['BLOCK-LEG','BLOCK'],
        ('S' if source_block else 'A')+' twoNo10 to actual block web; A stations',basis='S' if source_block else 'A',screw=True)
    a.fastener('FJ',[[face+sign*T,yface+side*(T+1.25),bz+z] for z in (-.75,.75)],[-sign,0,0],.19,T+jt,['JOIST-LEG','JOIST'],'A twoNo10 to actual joist web',basis='A',screw=True)
    a.weld('BEND',[face,yface+side*T,bz-1.25],[face,yface+side*T,bz+1.25],['BLOCK-LEG','JOIST-LEG'],kind='BEND',basis='A',description='A continuous folded sheet, not a weld')
    a.section_axis=2;a.section_at=bz+.75;a.front_axes=(0,2)
    a.notes.append('S diaphragm requires blocked sheet edges. A block section,54mil folded clip, twoNo10 screws per leg and all local offsets. Source joists and their checks remain unchanged; added blocking and connections have no new capacity verification.')
