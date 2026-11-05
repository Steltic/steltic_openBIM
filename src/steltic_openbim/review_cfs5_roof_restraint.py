"""Source roof-joist bottom-flange restraint and saved drift-check bindings."""
import math
from collections import defaultdict
from .review_cfs_occurrences import axis
from .review_cfs5_diaphragms import xfaces
from .review_cfs_source_bindings import attach
from .review_receiver_geometry import extract
from .pilots.model import add,sub

T=.0566
GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs5':return
    source_ids=['framing/joist-roof','framing/joist-roof-parapet']
    for rid in source_ids:
        data=b.records[rid]['data'];text=str(data)
        if not all(s in text for s in ('1.5','54 mil','6.8','12 ft')):
            raise ValueError('CFS5 source bottom-flange restraint changed')
    roof=[m for m in b.members if m['kind']=='joist' and m['level']==6 and source_ids[0] in m['design_record_ids']]
    groups=defaultdict(list)
    for joist in roof:
        lo,hi=sorted(q[1] for q in joist['axis'])
        if hi-lo>100:groups[round(lo,6),round(hi,6)].append(joist)
    pid=b.custom('ROOF-BOTTOM-STRAP-1.5X54','flat',dict(width=1.5,thickness=T),basis='S1.5in54mil roof-joist bottom-flange strap')
    counts=defaultdict(int)
    for row,((lo,hi),joists) in enumerate(sorted(groups.items())):
        joists.sort(key=lambda m:axis(m)[0][0]);y=lo+6.8*12
        if not lo<y<hi:raise ValueError('Source roof restraint row is outside the actual span')
        points=[]
        for joist in joists:
            aa,dd=axis(joist);d=b.profiles[joist['profile_id']]['dimensions']
            if joist['profile_id']!='1000S200-54':raise ValueError('Roof restraint cannot borrow another joist selection')
            points.append([aa[0]+joist['local_y'][0]*.75,y,aa[2]-d['d']/2-T])
        bottom=points[0][2]
        if any(abs(q[2]-bottom)>.001 for q in points):raise ValueError('Nonplanar roof strap needs a separate fit')
        strap=b.member(f'ROOF-BOTTOM-STRAP-{row}',pid,'roof_joist_bridging',[points[0][0]-.5,y,bottom+T/2],
            [points[-1][0]+.5,y,bottom+T/2],6,'S',records=source_ids,local_y=[0,1,0],
            physical_fit_basis='S source strap row6.8ft along nominal13.5ft span. A continuous coil extent and actual flange screw stations.')
        for i,(joist,q) in enumerate(zip(joists,points)):
            c=b.connection(strap['id']+'-J'+str(i),'review_roof_bottom_strap',q,[strap,joist],source_ids,
                parameters=dict(actual_roof_bottom_strap=True,source_joist_screw=True),title='SOURCE ROOF BOTTOM-FLANGE STRAP')
            if i in (0,len(joists)-1):b.endpoint_links.append(dict(member_id=strap['id'],end='start' if i==0 else 'end',
                connection_id=c['id'],basis='Actual strap ends1/2in beyond their first/last joist-flange screw; source oneNo10 at each joist.'))
            counts['joist_screws']+=1
        # Source same-section solid blocking at no more than12ft across.
        intervals=list(range(0,len(joists)-1,9))
        if intervals[-1]!=len(joists)-2:intervals.append(len(joists)-2)
        centres=[]
        for j in intervals:
            left,right=joists[j:j+2];start=xfaces(b,left)[1]+.125;end=xfaces(b,right)[0]-.125
            centre=axis(left)[0][2]
            block=b.member(f'ROOF-RESTRAINT-BLOCK-{row}-{j}',left['profile_id'],'roof_joist_blocking',
                [start,y,centre],[end,y,centre],6,'S',records=source_ids,local_y=[0,1,0],
                physical_fit_basis='S same joist section, blocks at12ft maximum across; A finite cut ends and54mil clips to actual joist webs')
            centres.append((start+end)/2)
            for e,host in enumerate((left,right)):
                c=b.connection(block['id']+'-END'+str(e),'review_wsp_block',axis(block)[e],[block,host],source_ids,
                    parameters=dict(actual_cfs5_diaphragm=True,purpose='block_end',end=e,roof_restraint_block=True),
                    title='SOURCE ROOF RESTRAINT BLOCK / A END CLIP')
                b.endpoint_links.append(dict(member_id=block['id'],end='start' if e==0 else 'end',connection_id=c['id'],
                    basis='Source twoNo10 at each blocking end; A54mil clip and two receiving-joist screws retain the actual web connection.'))
            q=[(start+end)/2,y+.5,bottom]
            b.connection(block['id']+'-STRAP','review_roof_bottom_strap',q,[strap,block],source_ids,
                parameters=dict(actual_roof_bottom_strap=True,source_joist_screw=False),title='A STRAP RETENTION / SOURCE SOLID BLOCK')
            counts['blocks']+=1
        if any(d-a>144.00001 for a,d in zip(centres,centres[1:])):raise ValueError('Roof solid-blocking pitch exceeds source12ft')
    if len(groups)!=4:raise ValueError('CFS5 roof needs four13.5ft joist rows, separate from the short corridor span')
    for joist in roof:
        if joist['profile_id']!='1000S200-54':raise ValueError('Unrecognized CFS5 roof joist')
        x=joist['axis'][0][0];lo,hi=sorted(q[1] for q in joist['axis'])
        if x<24.8*12 or x>2160-24.8*12 or lo<16.9*12 or hi>720-16.9*12:
            attach(b,joist,source_ids[1],'Actual source1000S200-54 roof joist overlaps a source24.8ft end-wall or16.9ft long-wall parapet drift zone. Stored uniform full-span peak-drift check retained; no new demand calculation.')
        for rid in list(joist['design_record_ids']):
            if rid not in source_ids:continue
            alias=rid.replace('framing/','gravity_framing/',1)
            if b.records[alias]['data']!=b.records[rid]['data']:raise ValueError('CFS5 roof gravity alias differs from the original check')
            attach(b,joist,alias,'Exact duplicate saved gravity/framing member check on the same physical roof joist, including its source bottom-flange restraint.')
    b.changes.append(dict(kind='source_cfs5_roof_bottom_restraint',counts=dict(counts),
        basis='S1.5in54mil strap,6.8ft row, oneNo10 per joist, same-section blocks at12ft maximum and twoNo10 at each block end. A continuous coil set-out,54mil end clips, receiving screws and one strap-to-block retention screw.'))
    b.note('ROOF-BOTTOM-RESTRAINT','S:one1.5in54mil strap row at6.8ft along each13.5ft roof-joist span; oneNo10 per joist; same-section full-depth blocking at12ft maximum across with twoNo10 per end. The6ft corridor spans are shorter than the source unbraced interval. A:continuous coil extents,54mil end clips and their additional receiving screws, plus one strap/block retention screw. Source drift zones and unchanged roof checks remain bound to their actual members.')


def draw(ctx):
    a=ctx.a;strap,host=ctx.ms;par=ctx.params
    sp=extract(ctx,strap,'STRAP',GLOBAL,20);hp=extract(ctx,host,'HOST',GLOBAL,16)
    ht=ctx.p[host['profile_id']]['dimensions']['t']
    if abs(sp['bounds'][2][1]-hp['bounds'][2][0])>.001:raise ValueError('Bottom strap does not touch the actual lower flange')
    basis='S' if par['source_joist_screw'] else 'A'
    a.fastener('SCREW',[[0,0,0]],[0,0,1],.19,T+ht,['STRAP','HOST'],
        ('S oneNo10 per actual joist' if basis=='S' else 'A oneNo10 strap-to-block retention screw')+'; A flange station',basis=basis,screw=True)
    a.section_axis=0;a.section_at=0;a.front_axes=(0,2)
    a.notes.append('Actual1.5in54mil continuous strap beneath the selected roof joist or solid block. The source restraint row and screw count are retained; exact flange stations, coil extents and added block clips are A fits without new capacity checks.')
