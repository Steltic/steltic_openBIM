"""Source garage X systems, continuous below-purlin roof plane and real nodes."""
from collections import defaultdict
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_cfs_occurrences import axis
from .review_receiver_geometry import point,vector,extract
from .review_cfs_frame_straps import face_intervals
from .review_assemblies import hull
from .review_cfs17_secondary import roof_at
G=.1875
RID='schedules/sched-strap'
ROWS=((16,126,222,284),(316,426,522,584),(616,684,768,800),(832,912,960,1016))


def apply(b):
    if b.key!='cfs17':return
    old={m['id'] for m in b.members if m['kind']=='strap'}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old]
    lookup={m['id']:m for m in b.members};nodes=defaultdict(list)
    def make(mid,aa,dd,kind,width,t,count,hosts):
        roof=kind=='roof';pid=b.custom('GAR-STRAP-'+str(width)+'-'+str(t),'flat',dict(width=width,thickness=t),basis='S')
        m=b.member(mid,pid,'strap',aa,dd,1,'A',records=[RID]);pack=t+.0625 if mid.endswith('-1') else 0;along=unit(sub(dd,aa))
        for end,(q,hid) in enumerate(zip((aa,dd),hosts)):
            if roof:
                _,_,u=roof_at((aa[0]+dd[0])/2);n=cross(u,[0,1,0]);axes=(u,[0,1,0],n);height=7.6
            else:
                n=[-1 if q[0]==0 else 1,0,0];u=[0,0,1];axes=(u,cross(n,u),n);height=3 if kind=='valley' else 7
            setback=18 if not roof and q[2]>190 else 12
            m['end_offsets'][end]=add(mul(n,height+G+pack+t/2),mul(along,setback if end==0 else -setback))
            nodes[hid,tuple(q),kind].append(dict(member=m,end=end,packing_in=pack,axes=axes,height=height,count=count))
        m['local_y']=unit(cross(n,along));m['physical_fit_basis']='Source continuous strap section/end-screw count. A physical end cuts, shared collectors, receiver bolts/packs and separate crossing planes. Roof straps lie below the actual purlins, retaining direct panel fastening; no centre splice or weld.'
    for side in (0,1):
        for j in (0,17):
            for flip in (0,1):make(f'GAR-SIDE-X-{side}-{j}-{flip}',[side*1032,j*144,216*flip],[side*1032,(j+1)*144,216*(1-flip)],'side',5,.1017,27,(f'F{j+1}-C{side}',f'F{j+2}-C{side}'))
    for j in range(0,18,2):
        for flip in (0,1):make(f'GAR-VALLEY-X-{j}-{flip}',[600,j*144,203*flip],[600,(j+1)*144,203*(1-flip)],'valley',3,.0713,12,(f'F{j+1}-PROP',f'F{j+2}-PROP'))
    for j in (0,17):
        for seg,stations in enumerate(ROWS):
            for k,(left,right) in enumerate(zip(stations,stations[1:])):
                for flip in (0,1):
                    aa,dd=(left,right) if flip else (right,left)
                    make(f'GAR-ROOF-X-{j}-{seg}-{k}-{flip}',[aa,j*144,roof_at(aa)[1]],[dd,(j+1)*144,roof_at(dd)[1]],'roof',4,.1017,22,(f'F{j+1}-R{seg}',f'F{j+2}-R{seg}'))
    for i,((hid,q,kind),items) in enumerate(sorted(nodes.items())):
        par=dict(actual_garage_strap=True,axes=items[0]['axes'],kind=kind,ends=[dict(member_id=v['member']['id'],end=v['end'],packing_in=v['packing_in']) for v in items],height=items[0]['height'],count=items[0]['count'])
        c=b.connection('GAR-STRAP-NODE-'+str(i),'review_garage_strap',q,[lookup[hid],*[v['member'] for v in items]],[RID],parameters=par)
        for v in items:b.endpoint_links.append(dict(member_id=v['member']['id'],end='start' if v['end']==0 else 'end',connection_id=c['id'],basis='Actual shared collector and source end screws attached to real source frame/prop.'))
    b.note('GAR-CONTINUOUS-X-SYSTEMS','S:side-wall X in both end bays,5x97mil/27No12 each end; valley-line X in nine alternate bays,3x68mil/12No12; each gable end-bay roof truss,4x97mil/22No12. A:exact roof panel subdivisions/set-out, finite12in end cuts (18in at wall tops), shared3/16in collectors and actual frame/prop receiving bolts. Roof planes below purlins leave through-fastened panels in direct bearing; no roof-strap/panel stand-off and no centre weld/splice. Roof collector and valley-strut offsets require local verification; original capacities/stiffness remain conditional and unchanged.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes'];origin=ctx.c['point'];host=ctx.ms[0];straps=ctx.ms[1:];height=par['height'];kind=par['kind'];count=par['count'];cols=3 if count==27 else 2;sets=[];corners=[]
    extract(ctx,host,'HOST',axes,50)
    for i,(m,item) in enumerate(zip(straps,par['ends'])):
        extract(ctx,m,'STRAP'+str(i),axes,50);ends=axis(m);start=point(ends[item['end']],origin,axes);along=vector(unit(sub(ends[1-item['end']],ends[item['end']])),axes);across=vector(m['local_y'],axes);t=p[m['profile_id']]['dimensions']['thickness'];pack=item['packing_in']
        qs=[add(start,add(mul(along,2+k//cols),mul(across,k%cols-(cols-1)/2))) for k in range(count)]
        for q in qs:q[2]=height+G+pack+t
        sets.append((i,qs,pack,t,along));corners.extend((q[0]+dx,q[1]+dy) for q in qs for dx,dy in ((-.75,-.75),(-.75,.75),(.75,-.75),(.75,.75)))
    face,bands=face_intervals(host,p,axes[2]);across=cross(unit(sub(*host['axis'][::-1])),axes[2]);choices=[((lo+hi)/2/dot(across,axes[1]),tt) for lo,hi,tt in bands];bolts=[]
    for _,_,_,_,along in sets:
        if kind=='roof':
            # Outside channel flange, beyond the10in Z saddle width and
            # beyond its anti-roll foot's5in length. Both ends face the bay.
            gauge,ht=min(choices,key=lambda v:abs(v[0]-(8 if along[1]>0 else -8)))
            sign=1 if along[0]>0 else -1;stations=(6,9)
        else:
            gauge,ht=min(choices,key=lambda v:abs(v[0]));sign=1 if along[0]>0 else -1;stations=(28,31) if origin[2]>190 else (15,18)
        bolts.extend([[sign*s,gauge,height+G] for s in stations])
    bolts=[list(q) for q in sorted({tuple(q) for q in bolts})]
    corners.extend((q[0]+dx,q[1]+dy) for q in bolts for dx,dy in ((-1,-.6),(-1,.6),(1,-.6),(1,.6)))
    a.polygon('COLLECTOR',[[x,y,height] for x,y in hull(corners)],G,normal=[0,0,1],basis='A',description='A one-piece3/16in collector joining actual strap ends and frame receiver groups')
    for i,q in enumerate(bolts):
        joined=['COLLECTOR','HOST']
        if height>face+1e-7:
            tag='RECEIVER-PACK'+str(i);a.box(tag,[q[0]-.75,q[1]-.5,face],[1.5,1,height-face],'A','A solid collector-to-actual-frame flange bearing pack');joined.append(tag)
        a.fastener('RECEIVER'+str(i),[q],[0,0,-1],.5,height+G-face+ht,joined,'A1/2in actual receiving-steel bolt; local capacity remains unverified',basis='A')
    for i,qs,pack,t,_ in sets:
        joined=['STRAP'+str(i),'COLLECTOR']
        if pack:
            shape=hull([(q[0]+dx,q[1]+dy) for q in qs for dx,dy in ((-.6,-.6),(-.6,.6),(.6,-.6),(.6,.6))]);a.polygon('PACK'+str(i),[[x,y,height+G] for x,y in shape],pack,normal=[0,0,1],basis='A',description='A separate continuous crossing-plane pack');joined.append('PACK'+str(i))
        a.fastener('STRAP-END'+str(i),qs,[0,0,-1],.216,t+G+pack,joined,f'S{count}No12 per end; A{cols}-column1in-row gauge',basis='S group / A fit',screw=True)
    a.title='GARAGE '+kind.upper()+' / SOURCE CONTINUOUS X STRAP';a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=sets[0][1][0][0]
    a.notes.append('Source strap size and screw count retained. A exact collector, receiving bolts/packs, end cuts and crossing-plane fit require verification. Roof straps pass beneath the actual purlins without lifting source through-fastened roof panels. Each X remains continuous; the crossing is not a welded joint.')
