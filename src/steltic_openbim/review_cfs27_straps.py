"""Continuous source straps with shared, explicitly adopted collector plates."""
import math
from collections import defaultdict
from shapely.geometry import Polygon,box
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_cfs_occurrences import axis
from .review_cfs_frame_straps import closest,face_intervals
from .review_receiver_geometry import extract,point,vector
from .review_assemblies import hull
from .review_cfs27_secondary import STATIONS

RID='schedules/sched-strap'
G=.1875
T=.0713


def apply(b):
    if b.key!='cfs27':return
    old={m['id'] for m in b.members if m['kind']=='strap'}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old]
    lookup={m['id']:m for m in b.members};nodes=defaultdict(list)
    rz=lambda x:192+min(x,432-x)*2/9
    def make(mid,aa,dd,roof,frame0,frame1):
        pid=b.custom('SC-STRAP-'+('3' if roof else '3.5'),'flat',dict(width=3 if roof else 3.5,thickness=T),basis='S')
        m=b.member(mid,pid,'strap',aa,dd,1,'A',records=[RID]);packing=T+.0625 if mid.endswith('-1') else 0
        for end,(q,frame) in enumerate(zip((aa,dd),(frame0,frame1))):
            if roof:
                # A node at the ridge remains on its own roof slope.
                side=int((aa[0]+dd[0])/2>216);host=lookup[f'F{frame}-R{side}'];u=unit(sub(*host['axis'][::-1]));n=cross(u,[0,1,0])
            else:
                host=lookup[f'F{frame}-C{int(q[0]>216)}'];u=[0,0,1];n=[-1 if q[0]==0 else 1,0,0]
            axes=(u,cross(n,u),n);face,_=face_intervals(host,b.profiles,n)
            m['end_offsets'][end]=mul(n,face+G+packing+T/2)
            nodes[host['id'],tuple(q),roof].append(dict(member=m,end=end,packing_in=packing,axes=axes))
        direction=unit(sub(dd,aa))
        for end in (0,1):m['end_offsets'][end]=add(m['end_offsets'][end],mul(direction,12 if end==0 else -12))
        m['local_y']=unit(cross(n,direction));m['physical_fit_basis']='S continuous68mil strap and source end-screw count. A12in setback,3/16in common node plate, two1/2in receiving bolts per end and separate crossing planes; no centre joint or new capacity claim.'
    for j in (0,28):
        for side in (0,1):
            for flip in (0,1):make(f'SC-WALL-X-{j}-{side}-{flip}',[side*432,j*78,192*flip],[side*432,(j+2)*78,192*(1-flip)],False,j,j+2)
        for r,(left,right) in enumerate(zip((0,123,216,309),(123,216,309,432))):
            for flip in (0,1):
                aa,dd=(left,right) if flip else (right,left)
                make(f'SC-ROOF-X-{j}-{r}-{flip}',[aa,j*78,rz(aa)],[dd,(j+2)*78,rz(dd)],True,j,j+2)
    for i,((hid,q,roof),items) in enumerate(sorted(nodes.items())):
        host=lookup[hid];axes=items[0]['axes'];cutouts=[]
        if roof:
            for x in STATIONS:
                if int(x>216)!=int(hid.endswith('R1')):continue
                delta=point([x,q[1],rz(x)],q,axes)
                if abs(delta[0])<32:cutouts.append([delta[0]-3.5,delta[0]+3.5,-3.5,3.5])
        elif q[2]==192:cutouts.append([-18,1,-3.5,3.5])
        ends=[dict(member_id=v['member']['id'],end=v['end'],packing_in=v['packing_in']) for v in items]
        c=b.connection('SC-STRAP-NODE-'+str(i),'review_single_strap_node',q,[host,*[v['member'] for v in items]],[RID],
            parameters=dict(actual_single_strap_node=True,axes=axes,roof=roof,ends=ends,cutouts=cutouts),title='SINGLE CHANNEL / SHARED SOURCE STRAP NODE')
        for v in items:b.endpoint_links.append(dict(member_id=v['member']['id'],end='start' if v['end']==0 else 'end',connection_id=c['id'],basis='Source strap screw group on an actual common collector; explicitly adopted receiving bolts engage the finite frame flange.'))
    b.changes.append(dict(kind='single_channel_source_strap_nodes',removed_generic_members=sorted(old),roof_panel_workpoints_in=[0,123,216,309,432],basis='Source eave/P3/ridge roof bracing and13x16ft side bracing. A actual continuous node plates and receiver fit; no centre splice or invented track.'))
    b.note('SINGLE-STRAP-NODES','S:8 continuous3.5x68mil wall straps,14No12 screws per end;16 continuous3x68mil roof straps,12No12 screws per end, eave/P3/ridge panels across two6.5ft bays at each end. A:12in end setback,3/16in shared collectors relieved around secondary feet, two1/2in receiving bolts per strap, gauges and crossing-plane packing. These local fit choices require checking; saved direct-attachment capacities are not assigned to the collectors. Straps remain uncut at their crossings, which provide no restraint or load transfer.')


def draw(ctx):
    a=ctx.a;par=ctx.params;origin=ctx.c['point'];axes=par['axes'];host=ctx.ms[0];u,v,n=axes
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),axes,45)
    _,centre,_,_,_=closest(host,origin);face,intervals=face_intervals(host,ctx.p,n);face+=point(centre,origin,axes)[2]
    if len(intervals)!=1:raise ValueError('Source single-channel strap requires one real receiving flange')
    lo,hi,ht=intervals[0];gauge=-(lo+hi)/2;sets=[];allpoints=[]
    for j,item in enumerate(par['ends'],1):
        m=ctx.ms[j];ends=axis(m);start=point(ends[item['end']],origin,axes);along=vector(unit(sub(ends[1-item['end']],ends[item['end']])),axes);across=vector(m['local_y'],axes)
        count=12 if par['roof'] else 14;pack=item['packing_in']
        qs=[add(start,add(mul(along,2+k//2),mul(across,(k%2-.5)))) for k in range(count)]
        for q in qs:q[2]=face+G+pack+T
        sign=1 if along[0]>0 else -1
        stations=(26,29) if not par['roof'] and origin[2]==192 else (15,18)
        bolts=[[sign*s,gauge,face+G] for s in stations]
        sets.append((j,qs,pack,bolts));allpoints.extend(qs+bolts)
    poly=Polygon(hull([(q[0]+dx,q[1]+dy) for q in allpoints for dx,dy in ((-1,-1),(-1,1),(1,-1),(1,1))]))
    for x0,x1,y0,y1 in par['cutouts']:poly=poly.difference(box(x0,y0,x1,y1))
    if poly.geom_type!='Polygon' or poly.interiors:raise ValueError('Strap collector must remain one connected relieved plate')
    a.polygon('COLLECTOR',[[x,y,face] for x,y in list(poly.exterior.coords)[:-1]],G,normal=[0,0,1],basis='A',description='A continuous3/16in common collector, relieved around actual secondary support feet')
    for j,qs,pack,bolts in sets:
        joined=['M'+str(j),'COLLECTOR']
        if pack:
            outline=hull([(q[0]+dx,q[1]+dy) for q in qs for dx,dy in ((-.7,-.7),(-.7,.7),(.7,-.7),(.7,.7))])
            a.polygon('PACK'+str(j),[[x,y,face+G] for x,y in outline],pack,normal=[0,0,1],basis='A',description='A upper-diagonal packing; both crossing straps remain continuous');joined.append('PACK'+str(j))
        a.fastener('STRAP'+str(j),qs,[0,0,-1],.216,T+G+pack,joined,f'S{len(qs)} No12 strap-end screws; A two-column1in-row pattern',basis='S count / A fit',screw=True)
        a.fastener('FRAME'+str(j),bolts,[0,0,-1],.5,G+ht,['COLLECTOR','M0'],'A two1/2in receiver bolts per strap into actual frame flange; local attachment capacity unverified',basis='A')
    a.title='SINGLE CHANNEL / SHARED '+('ROOF' if par['roof'] else 'WALL')+' STRAP NODE';a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=sets[0][3][0][0]
    a.dim(sets[0][1][0],sets[0][1][-1],f'S{12 if par["roof"] else 14} No12 / A1in rows',basis='S/A')
    a.notes.append('Source continuous strap and end screws are retained. Common collector, reliefs, receiving bolts,12in end cut and packing are accepted fictional fit; source direct-attachment capacity is not reassigned. No centre weld, splice or false track is added. Secondary bearing stand-off clears both continuous strap planes.')
