"""Actual header/column bearing interfaces of the two delegated SBMF roofs."""
import math
from .pilots.model import add,sub,unit
from .pilots.geometry import strips
from .review_receiver_geometry import extract
from .review_cfs_occurrences import axis

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key not in ('cfs10','cfs18'):return
    lookup={m['id']:m for m in b.members};caps=[m for m in b.members if m['kind']=='header_cap']
    columns=[m for m in b.members if m['kind']=='column' and m['id'].startswith('FRAME-')];closures={}
    for c in list(b.connections):
        if c['detail_ref']['id']!='review_roof_seat' or c['point'][1] not in (0,600):continue
        chord=next(lookup[mid] for mid in c['member_ids'] if lookup[mid]['kind']=='truss_chord');x,y,z=c['point']
        choices=[m for m in caps if abs(axis(m)[0][1]-y)<.01 and axis(m)[0][0]+2<=x<=axis(m)[1][0]-2]
        if choices:
            cap=min(choices,key=lambda m:m['id']);header=lookup[cap['id'].removesuffix('-CAP')]
            receivers=[chord,cap,header];support='header'
        else:
            column=min((m for m in columns if m['axis'][0][1]==y),key=lambda m:abs(m['axis'][0][0]-x))
            cd=b.depth(column['profile_id']);half=cd/2+3
            if abs(column['axis'][0][0]-x)+1.8>half:raise ValueError('Truss heel has no finite roof bearing support: '+c['id'])
            if column['id'] not in closures:
                # A quarter-inch closure fits below the lowest actual heel.
                # A small end cut is represented as a real column offset.
                top=min(axis(column)[1][2],z-3-.25);column['end_offsets'][1][2]=top-column['axis'][1][2]
                cx,cy=column['axis'][1][:2];pid=b.custom('A-SBMF-COLUMN-CAP-'+str(cd),'flat',dict(width=2*half,thickness=.25),basis='A')
                cap=b.member(column['id']+'-ROOF-CAP',pid,'column_cap',[cx-half,cy,top+.125],[cx+half,cy,top+.125],3,'A',local_y=[0,1,0])
                closures[column['id']]=cap
                b.connection(cap['id']+'-WELD','review_sbmf_column_cap',[cx,cy,top],[cap,column],
                    parameters=dict(actual_sbmf_roof=True,column_depth_in=cd),basis='A')
                b.endpoint_links.append(dict(member_id=column['id'],end='end',connection_id=cap['id']+'-WELD',
                    basis='A actual HSS closure plate; explicit column top cut fits below the delegated truss bearing.'))
                b.changes.append(dict(kind='sbmf_roof_column_cap',column_id=column['id'],cap_id=cap['id'],column_top_in=top,
                    basis='A quarter-inch welded closure with3in projection beyond each HSS face. Actual truss bearing set-out; plate, weld and overhang capacity not verified.'))
            cap=closures[column['id']];receivers=[chord,cap];support='column'
        c['member_ids']=[m['id'] for m in receivers];c['detail_ref']['id']='review_sbmf_roof_seat'
        far=max(chord['axis'],key=lambda q:math.dist(q,c['point']));into=1 if far[1]>y else -1
        c.setdefault('parameters',{}).update(actual_sbmf_roof=True,support=support,into=into)
        rid=b.record('schedules','sched-purlin')
        if rid:c['design_record_ids']=list(dict.fromkeys(c['design_record_ids']+[rid]));b.used_records.add(rid)
    b.note('SBMF-ROOF-SEATS','S: independent delegated roof trusses bear on the source eave headers. A: actual full-width cap tracks, quarter-inch HSS closure plates and their four1/4in edge welds where a heel falls over a frame column, explicit column end cuts, paired solid bearing shims and two3/8in retention bolts. The original truss reactions remain attached as requirements. Seat, closure, bolt, shim and receiving-member local capacities have not been checked. The truss heel is not an invented generic stud/track stack.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params
    if ctx.family=='review_sbmf_column_cap':
        cap,column=ctx.ms;extract(ctx,cap,'CAP',AXES,30);extract(ctx,column,'COLUMN',AXES,20);half=par['column_depth_in']/2
        corners=[[-half,-half,0],[half,-half,0],[half,half,0],[-half,half,0]]
        for i,(start,end) in enumerate(zip(corners,corners[1:]+corners[:1])):
            a.weld('W'+str(i),start,end,['COLUMN','CAP'],.25,basis='A',description='A quarter-inch HSS closure edge weld')
        a.section_axis=2;a.section_at=.125
        a.notes.append('A real quarter-inch closure spans the open HSS end; the truss is not supported over an empty tube cavity. Exact plate width includes the adopted edge-heel overhang. Plate bending, HSS wall and weld capacity remain unverified.')
        return
    chord,cap=ctx.ms[:2];extract(ctx,chord,'CHORD',AXES,24);extract(ctx,cap,'CAP',AXES,16)
    if par['support']=='header':extract(ctx,ctx.ms[2],'HEADER',AXES,16)
    profile=p[chord['profile_id']];origin=ctx.c['point'];capprofile=p[cap['profile_id']]
    ct=capprofile['dimensions'].get('t',capprofile['dimensions'].get('thickness'))
    top=axis(cap)[0][2]+ct/2-origin[2];bottom=-3.;gap=bottom-top
    if gap< -1e-7:raise ValueError('Actual truss chord penetrates its roof bearing cap')
    sg=par['into'];flanges=[]
    for poly in strips(profile,p):
        if min(q[1] for q in poly)>0 and max(q[1] for q in poly)-min(q[1] for q in poly)<.2:
            lo,hi=min(q[0] for q in poly),max(q[0] for q in poly)
            if hi-lo>1:flanges.append((lo,hi,max(q[1] for q in poly)-min(q[1] for q in poly)))
    for i,(lo,hi,tt) in enumerate(flanges):
        joins=['CHORD','CAP'];ht=0
        if gap>1e-7:
            label='PACK'+str(i);a.box(label,[lo,min(0,sg*3.5),top],[hi-lo,3.5,gap],'A','A actual solid bearing shim at truss flange')
            joins.append(label)
        if par['support']=='header':
            header=p[ctx.ms[2]['profile_id']];ht=p[header['components'][0]['profile_id']]['dimensions']['t'];joins.append('HEADER')
        a.fastener('B'+str(i),[[(lo+hi)/2,sg*1.75,bottom+tt]],[0,0,-1],.375,tt+gap+ct+ht,
            joins,'A one3/8in retention through-bolt per actual chord flange; supplier uplift design required',basis='A')
        a.interfaces.append(dict(id='BEAR'+str(i),kind='bearing',connects=joins,basis='A',
            description='Actual truss flange bears through its shown shim onto the finite cap; source reaction retained as a supplier requirement.'))
    a.section_axis=1;a.section_at=sg*1.75
    a.notes.append('The finite source header/cap or HSS closure is shown at its real elevation. Source truss reactions are requirements, not a verified capacity for the A shim and retention-bolt fit. Truss node screws and heel gussets remain on the separate supplier-node detail.')
