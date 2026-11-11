"""The saved unequal-span portal, with source groups on actual finite steel.

All local outlines and clearances are adopted fictional inputs. Neither the
source strength checks nor the pin-ended prop analysis are reinterpreted.
"""
import math
from shapely.geometry import LineString,box
from .pilots.model import add,sub,mul,unit
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .review_cfs28_primary import CENTRES,AXES


def apply(b):
    if b.key!='cfs17':return
    b.endpoint_links=getattr(b,'endpoint_links',[])
    lookup={m['id']:m for m in b.members}
    nodes={n['id']:n['point'] for n in b.package['analysis']['nodes']}
    for m in b.members:
        if m['kind']=='column' and m['id'].startswith('F'):
            m['end_offsets']=[[0,0,2.25],[0,0,-10]];rid='members/frame-col'
        elif m['kind']=='prop':
            # Preserve the source analysis workline through the valley node;
            # the real HSS still stops at the underside of the source cap.
            m['axis'][1][2]=216;m['end_offsets']=[[0,0,2.25],[0,0,-13.75]];rid='members/frame-col-int'
            matches=[e for e in b.package['analysis']['elements'] if e.get('label')=='col_I1' and all(abs(nodes[n][i]-m['axis'][0][i])<.001 for n in e['node_ids'] for i in (0,1))]
            spans=sorted((min(nodes[n][2] for n in e['node_ids']),max(nodes[n][2] for n in e['node_ids'])) for e in matches)
            if not spans or spans[0][0]!=0 or spans[-1][1]!=216 or any(abs(a[1]-d[0])>.001 for a,d in zip(spans,spans[1:])):raise ValueError('Valley prop does not cover the exact original analysis workline')
            m['analysis_ids']=[e['id'] for e in matches]
            m['mapping_basis']='Exact col_I1 source-node coordinates and complete 0..216in analysis segmentation. Final saved member selection is HSS6x6x1/4; source analysis EA/EI metadata remains unchanged and has not been recalculated.'
        elif m['kind']=='rafter' and m['id'].startswith('F'):
            u=unit(sub(*m['axis'][::-1]));j=int(m['id'][-1])
            m['end_offsets']=[mul(u,10 if j in (0,2) else 2),mul(u,-10 if j in (1,3) else -2)]
            rid='members/frame-raf'
        else:continue
        m['design_record_ids']=[rid]
        m['physical_fit_basis']='S source sections, three independent pairs with3/8in web gaps, pinned valley prop and original worklines. A square10in knee/valley and2in ridge cuts,3/4in base/cap fit and6.375in pair centres; no new capacity verification.'
    for c in b.connections:
        f=c['detail_ref']['id']
        if f not in ('review_portal_base','review_portal_joint'):continue
        purpose='prop_base' if f.endswith('_base') and lookup[c['member_ids'][0]]['kind']=='prop' else 'base' if f.endswith('_base') else c['parameters']['joint']
        c['detail_ref']['id']='review_garage_primary';c['parameters']=dict(actual_garage_primary=True,purpose=purpose)
        if purpose in ('base','prop_base'):
            from .bim_record_clauses import clauses
            rid='anchorage/base-anchor';options=clauses(b.records[rid]['data']['selection'])
            label='interior hss6x6x1/4 columns' if purpose=='prop_base' else 'exterior bases'
            c['source_record_selections']=[dict(record_id=rid,field='selection',clause=label,text=options[label],level=1,basis='Exact labelled source base selection at the actual exterior column or flanked HSS valley prop. Both original source clauses remain fully represented.')]
        for mid in c['member_ids']:
            m=lookup[mid];end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']))
            b.endpoint_links.append(dict(member_id=mid,end='start' if end==0 else 'end',connection_id=c['id'],basis='Source portal/prop member physically connected at this source node through explicitly modeled finite gussets/base/cap.'))
    for m in [m for m in b.members if m['kind'] in ('column','rafter') and m['id'].startswith('F')]:
        if m['kind']=='column':positions=[[m['axis'][0][0],m['axis'][0][1],z] for z in range(24,163,24)]
        else:
            u=unit(sub(*m['axis'][::-1]));j=int(m['id'][-1]);start=(36/abs(u[0]) if j in (0,2) else 24)+3;stop=math.dist(*m['axis'])-(36/abs(u[0]) if j in (1,3) else 24)-3
            positions=[add(m['axis'][0],mul(u,s)) for s in range(math.ceil(start),math.floor(stop)+1,24)]
        for i,q in enumerate(positions):b.connection(m['id']+'-STITCH'+str(i),'review_garage_primary',q,[m],m['design_record_ids'],parameters=dict(actual_garage_primary=True,purpose='stitch'))
    b.note('GARAGE-PRIMARY','S:three independent pairs; knee12 three-quarter-inch A325-N bolts per leg/pair at4in gauge and3in pitch; ridge/valley16 per leg/pair at3.5in gauge/3in pitch,2in plate ends. Bracket-end worklines:column48in below eave; rafter36in horizontally from knee/valley,24in along ridge legs. Continuous valley gussets extend6in below rafters to3/4in cap; six3/4in cap bolts. Pinned HSS6x6x1/4 valley prop, source bases and24in pair stitching retained. A square cuts, continuous plate perimeters, cap22x12in footprint and welded receiver lugs, stitch groups, anchor embedment/gauges and weld fit; original calculations do not verify these proposals.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;purpose=par['purpose']
    if purpose=='base':return exterior_base(ctx)
    if purpose=='prop_base':return prop_base(ctx)
    if purpose=='stitch':
        from .review_cfs28_primary import draw as pair_stitch
        pair_stitch(ctx);a.title='GARAGE / THREE INDEPENDENT PAIR STITCHES';return
    knee=purpose=='knee';valley=purpose=='valley';origin=ctx.c['point'];ms=[m for m in ctx.ms if m['kind']!='prop'];directions=[];lengths=[]
    for j,m in enumerate(ms):
        v=unit(sub(max(m['axis'],key=lambda q:math.dist(q,origin)),origin));directions.append(v)
        lengths.append(48 if m['kind']=='column' else 36/abs(v[0]) if knee or valley else 24)
        extract(ctx,m,'M'+str(j),AXES,62)
    ends=[mul(v,L+2) for v,L in zip(directions,lengths)]
    shape=LineString([(ends[0][0],ends[0][2]),(0,0),(ends[1][0],ends[1][2])]).buffer(7,cap_style=2,join_style=2)
    if valley:shape=shape.union(box(-7,-13,7,0))
    outline=list(shape.exterior.coords)[:-1];across_count=3 if knee else 4;gauge=4 if knee else 3.5
    for i,yy in enumerate(CENTRES):
        tag='G'+str(i);a.polygon(tag,[[x,yy-.1875,z] for x,z in outline],.375,basis='S thickness/depth / A perimeter',description='Source continuous3/8in A572Gr50 plate between this actual pair')
        for j,(m,v,L) in enumerate(zip(ms,directions,lengths)):
            tw=p[p[m['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];across=[-v[2],0,v[0]]
            pts=[add(mul(v,L-r*3),add(mul(across,(g-(across_count-1)/2)*gauge),[0,yy-.1875-tw,0])) for r in range(4) for g in range(across_count)]
            a.fastener(f'B{i}-{j}',pts,[0,1,0],.75,.375+2*tw,['M'+str(j),tag],f'S{4*across_count} A325-N bolts through this pair/gusset,{gauge}in gauge/3in pitch; hardened washers both sides',basis='S')
    if valley:
        prop=next(m for m in ctx.ms if m['kind']=='prop');extract(ctx,prop,'PROP',AXES,40)
        a.box('CAP',[-6,-11,-13.75],[12,22,.75],'S thickness / A footprint','Source3/4in cap on actual pinned HSS; A12x22in footprint')
        for i,yy in enumerate(CENTRES):
            name='CAP-LUG'+str(i);a.box(name,[-4,yy+.1875,-13],[8,.375,4],'A','A welded receiver lug for source two cap bolts per gusset')
            a.fastener('CAP-B'+str(i),[[x,yy-.1875,-11] for x in (-2,2)],[0,1,0],.75,.75,['G'+str(i),name],'S two3/4in A325-N cap/gusset bolts in single shear; A4in gauge',basis='S group / A gauge')
            a.weld('LUG-W'+str(i),[-4,yy+.5625,-13],[4,yy+.5625,-13],['CAP',name],.25,basis='A',description='A1/4in cap-lug fillet; local weld/plate verification required')
        for i,(aa,dd) in enumerate((((-3,-3),(3,-3)),((3,-3),(3,3)),((3,3),(-3,3)),((-3,3),(-3,-3)))):
            a.weld('PROP-W'+str(i),[*aa,-13.75],[*dd,-13.75],['CAP','PROP'],.1875,basis='A',description='A3/16in cap-to-HSS perimeter fillet; retained pin-ended analysis idealization')
    a.dim(mul(directions[0],lengths[0]-9),mul(directions[0],lengths[0]),'S3 @3in')
    a.title='GARAGE / THREE CONTINUOUS '+purpose.upper()+' GUSSETS';a.section_axis=2;a.section_at=-39 if knee else -11 if valley else -3
    a.notes.append('Source bolt groups and original workline design stations retained. A outlines/cuts and local cap/lug fitting are explicit. No source capacity is assigned to an altered fitting; the valley prop remains pin-ended in the saved analysis.')


def exterior_base(ctx):
    a,p=ctx.a,ctx.p;m=ctx.ms[0];tw=p[p[m['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
    extract(ctx,m,'COLUMN',AXES,36);a.box('CONC',[-14,-17,-20],[28,34,20],'A','Delegated foundation envelope',kind='concrete')
    a.box('GROUT',[-8,-11,0],[16,22,1.5],'S','Source1.5in nonshrink grout')
    a.box('BASE',[-8,-11,1.5],[16,22,.75],'S','Source3/4x16x22in A572Gr50 base')
    a.fastener('ANCHORS',[[x,y,-12] for x in (-6.25,6.25) for y in (-9.25,9.25)],[0,0,1],.75,14.25,['CONC','BASE'],'S four3/4in F1554Gr36 anchors; A12in embedment/1.75in plate edges',basis='S group / A fit')
    for i,y in enumerate(CENTRES):
        tag='G'+str(i);a.box(tag,[-6,y-.1875,2.25],[12,.375,10],'S thickness / A outline','Source3/8in welded base gusset; A12x10in outline')
        a.fastener('B'+str(i),[[x,y-.1875-tw,z] for x in (-3,3) for z in (5.25,8.25)],[0,1,0],.75,.375+2*tw,['COLUMN',tag],'S four3/4in A325-N bolts per pair; A6x3in gauge')
        for sg in (-1,1):a.weld(f'W{i}-{sg}',[-6,y+sg*.1875,2.25],[6,y+sg*.1875,2.25],['BASE',tag],.25,basis='A',description='A1/4in base/gusset fillet')
    a.title='GARAGE / SOURCE THREE-PAIR PINNED BASE';a.section_axis=2;a.section_at=1.875
    a.notes.append('Source plate/grout, three gussets and original anchor/web-bolt groups. A embedment, outlines, gauges and local weld size. Foundation breakout/pryout remains delegated and original reactions are retained.')


def prop_base(ctx):
    a=ctx.a;extract(ctx,ctx.ms[0],'PROP',AXES,32)
    a.box('CONC',[-12,-12,-18],[24,24,18],'A','Delegated valley foundation envelope',kind='concrete')
    a.box('GROUT',[-6,-6,0],[12,12,1.5],'A','A1.5in grout under source interior plate')
    a.box('BASE',[-6,-6,1.5],[12,12,.75],'S','Source3/4x12x12in A572Gr50 base')
    a.fastener('ANCHORS',[[x,y,-12] for x in (-4.5,4.5) for y in (-4.5,4.5)],[0,0,1],.75,14.25,['CONC','BASE'],'S four3/4in F1554Gr36 anchors; A9in square gauge/12in embedment',basis='S group / A fit')
    for i,(aa,dd) in enumerate((((-3,-3),(3,-3)),((3,-3),(3,3)),((3,3),(-3,3)),((-3,3),(-3,-3)))):
        a.weld('W'+str(i),[*aa,2.25],[*dd,2.25],['PROP','BASE'],.1875,basis='S',description='S3/16in fillet all around actual HSS')
    a.title='GARAGE / PINNED VALLEY PROP BASE';a.section_axis=2;a.section_at=1.875
    a.notes.append('S HSS6x6x1/4, source plate, four anchors and3/16in weld. A grout, gauges and embedment. Source pin-ended idealization retained; foundation and vehicle bollard protection remain delegated.')
