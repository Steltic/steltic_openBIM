"""Source canopy strap screws and bolted, shared node gussets.

One plate at a shared node avoids coincident independent collector plates.
Exact outline, gauges and upper-diagonal packing remain adopted fit choices.
"""
from collections import defaultdict
import math
from .pilots.model import add,sub,mul,dot,unit
from .review_cfs26_purlins import AXES,bolted
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point,vector
from .review_cfs_frame_straps import face_intervals,closest
from .review_assemblies import hull

RID='schedules/sched-strap'


def apply(b):
    if b.key!='cfs26':return
    for member in b.members:
        if member['kind']!='strap':continue
        direction=unit(sub(*axis(member)[::-1]))
        member['end_offsets']=[add(v,mul(direction,3 if i==0 else -3)) for i,v in enumerate(member['end_offsets'])]
        member['physical_fit_basis']=member['physical_fit_basis'].replace('3 in end clearance','6 in end clearance')+'; A canopy end setback clears adjacent strut caps without cutting the continuous gusset.'
        b.changes.append(dict(kind='canopy_strap_cap_clearance',member_id=member['id'],adopted_workline_end_clearance_in=6,basis='A finite strap ends clear cap legs; source19-screw group and continuous gusset retained'))
    lookup={m['id']:m for m in b.members};groups=defaultdict(list)
    for c in b.connections:
        if not c.get('parameters',{}).get('physical_strap_end'):continue
        groups[tuple(round(x,5) for x in c['point'])].append(c)
    old={c['id'] for cs in groups.values() for c in cs}
    b.connections[:]=[c for c in b.connections if c['id'] not in old]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['connection_id'] not in old]
    for i,(p,cs) in enumerate(sorted(groups.items())):
        hosts={c['parameters']['receiver_member_id'] for c in cs}
        if len(hosts)!=1:raise ValueError('Canopy node spans different rafters')
        host=lookup[hosts.pop()];straps=[lookup[c['member_ids'][0]] for c in cs]
        ends=[dict(member_id=m['id'],end=c['parameters']['strap_end'],packing_in=c['parameters']['packing_in']) for c,m in zip(cs,straps)]
        c=b.connection('ROOF-NODE-'+str(i),'review_canopy_roof_strap',p,[host,*straps],[RID],
            parameters=dict(actual_canopy_roof_strap=True,axes=AXES,ends=ends),title='CANOPY / SHARED SOURCE ROOF-STRAP NODE')
        for item in ends:b.endpoint_links.append(dict(member_id=item['member_id'],end='start' if item['end']==0 else 'end',connection_id=c['id'],basis='Source19-screw end on this actual common gusset; two source receiving bolts per strap.'))
    b.note('CANOPY-ROOF-NODES','S:3.5x97mil continuous tension straps,19No12 screws per end in nine pairs plus one final centreline screw,3/16in A36 gussets and two1/2in A325 receiving bolts per strap. A:6in strap-end setback clears adjacent caps; shared continuous plate where two strap ends meet, exact plate outline, bolt gauges and upper-diagonal packing. Every receiving bolt passes through an actual rafter top flange. Source capacities are not extended to adopted common-plate geometry. The two diagonals cross continuously in separate planes; no centre splice, weld or restraint is introduced.')


def draw(ctx):
    a=ctx.a;par=ctx.params;origin=ctx.c['point'];host=ctx.ms[0];n=AXES[2];g=.1875;t=.1017
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),AXES,40)
    _,centre,_,_,_=closest(host,origin);face,intervals=face_intervals(host,ctx.p,n)
    face+=point(centre,origin,AXES)[2]
    # In AXES, the actual two rafter top flanges run along U, across V.
    flange_gauges=sorted(-.5*(lo+hi) for lo,hi,_ in intervals)
    if len(flange_gauges)!=2:raise ValueError('Expected two actual canopy rafter flanges')
    sets=[];allpoints=[]
    for j,item in enumerate(par['ends'],1):
        m=next(m for m in ctx.ms if m['id']==item['member_id']);end=item['end'];ends=axis(m)
        start=point(ends[end],origin,AXES);along=vector(unit(sub(ends[1-end],ends[end])),AXES);across=vector(m['local_y'],AXES)
        qs=[add(start,add(mul(along,3+r),mul(across,s*.5))) for r in range(9) for s in (-1,1)]
        qs.append(add(start,mul(along,12)))
        pack=item['packing_in']
        for q in qs:q[2]=face+g+pack+t
        station=(-2 if along[0]<0 else 2)
        bolts=[[station,v,face+g] for v in flange_gauges]
        sets.append((j,qs,pack,bolts));allpoints.extend(qs+bolts)
    outline=hull([(q[0]+du,q[1]+dv) for q in allpoints for du,dv in ((-1,-1),(-1,1),(1,-1),(1,1))])
    a.polygon('GUSSET',[[u,v,face] for u,v in outline],g,normal=[0,0,1],basis='S thickness / A common outline',description='Source3/16in A36 gusset; A single continuous plate shared by adjacent strap ends')
    for j,qs,pack,bolts in sets:
        joined=['M'+str(j),'GUSSET']
        if pack:
            outline=hull([(q[0]+du,q[1]+dv) for q in qs for du,dv in ((-.8,-.8),(-.8,.8),(.8,-.8),(.8,.8))])
            a.polygon('PACK'+str(j),[[u,v,face+g] for u,v in outline],pack,normal=[0,0,1],basis='A',description='A upper-diagonal packing; both crossing straps remain continuous');joined.append('PACK'+str(j))
        a.fastener('STRAP'+str(j),qs,[0,0,-1],.216,t+g+pack,joined,'S19No12 C1513 screws: nine pairs plus one centreline screw; A1in row pitch and grip',screw=True)
        bolted(a,'FRAME'+str(j),bolts,[0,0,-1],g+.1017,['GUSSET','M0'],'S two1/2in A325 receiving bolts per strap, one through each actual rafter top flange; A station and grip','S')
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=sets[0][3][0][0]
    a.dim(sets[0][1][0],sets[0][1][-1],'S19No12; A1in rows',basis='A')
    a.notes.append('One physical gusset serves this actual node, retaining two receiving bolts and19 strap screws per strap end. Exact common outline, packing, gauges and access are accepted fictional fit, not a newly verified connection design. No centre joint is added to either diagonal.')
