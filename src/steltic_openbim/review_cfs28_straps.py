"""Source single-bay X systems and continuous roof straps above real purlins."""
import math
from collections import defaultdict
from shapely.geometry import Polygon,box
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_cfs_occurrences import axis
from .review_receiver_geometry import point,vector,extract
from .review_cfs_frame_straps import face_intervals
from .review_cfs25_secondary import sections
from .review_cfs25_cladding import top_flange
from .review_assemblies import hull

RID='schedules/sched-strap'
G=.1875
ROOF_T=.0713
ROOF_ROWS=(16,114,168,222,280,296,354,408,462,560)


def apply(b):
    if b.key!='cfs28':return
    old={m['id'] for m in b.members if m['kind']=='strap'}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old]
    lookup={m['id']:m for m in b.members};nodes=defaultdict(list);roofstraps=[]
    rz=lambda x:216+min(x,576-x)/4
    roof_height={}
    for side in (0,1):
        u=unit([1,0,.25 if side==0 else -.25]);axes=(u,[0,1,0],cross(u,[0,1,0]));origin=[0,0,216] if side==0 else [288,0,288]
        roof_height[side]=max(top_flange(b,m,origin,axes)[3] for m in b.members if m['id'].startswith('AG-P-') and int(float(m['id'].split('-')[2])>288)==side)
    def make(mid,aa,dd,kind,width,thickness,count,hosts):
        roof=kind=='roof';pid=b.custom('AG-STRAP-'+str(width)+'-'+str(thickness),'flat',dict(width=width,thickness=thickness),basis='S')
        m=b.member(mid,pid,'strap',aa,dd,1,'A',records=[RID]);packing=thickness+.0625 if mid.endswith('-1') else 0;direction=unit(sub(dd,aa))
        for end,(q,hid) in enumerate(zip((aa,dd),hosts)):
            if roof:
                side=int((aa[0]+dd[0])/2>288);u=unit([1,0,.25 if side==0 else -.25]);n=cross(u,[0,1,0]);axes=(u,[0,1,0],n);height=roof_height[side]
            else:
                host=lookup[hid];u=[0,0,1];n=([0,-1 if q[1]==0 else 1,0] if kind=='end' else [-1 if q[0]==0 else 1,0,0]);axes=(u,cross(n,u),n)
                height=9.5625 if kind=='end' else 7
            setback=16 if kind=='south' and q[2]==216 else 12
            m['end_offsets'][end]=add(mul(n,height+G+packing+thickness/2),mul(direction,setback if end==0 else -setback))
            nodes[hid,tuple(q),kind].append(dict(member=m,end=end,packing_in=packing,axes=axes,height=height,count=count))
        m['local_y']=unit(cross(n,direction));m['physical_fit_basis']='S continuous source strap and end-screw count. A12in setback (16in at south eave), common3/16in collector, receiving hardware and separate crossing planes; no centre weld or splice. Source attachment/stiffness capacities not assigned to these fit changes.'
        if roof:roofstraps.append(m)
    for j in (0,1,8,9):
        for flip in (0,1):make(f'AG-SOUTH-X-{j}-{flip}',[576,j*211.2,216*flip],[576,(j+1)*211.2,216*(1-flip)],'south',5,.1242,33,(f'F{j}-C1',f'F{j+1}-C1'))
    for j in (0,9):
        for flip in (0,1):make(f'AG-OPEN-X-{j}-{flip}',[0,j*211.2,171 if flip else 216],[0,(j+1)*211.2,216 if flip else 171],'open',3,.1017,17,(f'F{j}-C0',f'F{j+1}-C0'))
    for end,y in enumerate((0,2112)):
        for side,(aa,dd) in enumerate(((0,168),(408,576))):
            hosts=(f'F{10*end}-C0',f'DOOR-JAMB-{end}-0') if side==0 else (f'DOOR-JAMB-{end}-1',f'F{10*end}-C1')
            for flip in (0,1):make(f'AG-END-X-{end}-{side}-{flip}',[aa,y,rz(aa)*flip],[dd,y,rz(dd)*(1-flip)],'end',3.5,.0713,14,hosts)
    for j in (0,1,2,7,8,9):
        for side in (0,1):
            stations=ROOF_ROWS[:5] if side==0 else ROOF_ROWS[5:]
            for k,(left,right) in enumerate(zip(stations,stations[1:])):
                for flip in (0,1):
                    aa,dd=(left,right) if flip else (right,left)
                    make(f'AG-ROOF-X-{j}-{side}-{k}-{flip}',[aa,j*211.2,rz(aa)],[dd,(j+1)*211.2,rz(dd)],'roof',3,ROOF_T,12,(f'ROOF-{aa}-{j}',f'ROOF-{dd}-{j+1}'))
    for i,((hid,q,kind),items) in enumerate(sorted(nodes.items())):
        roof=kind=='roof';axes=items[0]['axes'];par=dict(actual_ag_strap=True,purpose='roof_node' if roof else 'wall_node',axes=axes,kind=kind,ends=[dict(member_id=v['member']['id'],end=v['end'],packing_in=v['packing_in']) for v in items],height=items[0]['height'],count=items[0]['count'])
        if roof:
            station=float(hid.split('-')[1]);probe=q[1]+(-10 if q[1]>2111 else 10)
            hosts=[m for m in b.members if m['id'].startswith(f'AG-P-{station:g}-') and min(e[1] for e in axis(m))<=probe<=max(e[1] for e in axis(m))]
            if not hosts:raise ValueError('No real roof strap node receivers '+hid)
            par.update(host_count=len(hosts),web_y=-10 if q[1]>2111 else 10)
        else:hosts=[lookup[hid]];par.update(host_count=1)
        c=b.connection('AG-STRAP-NODE-'+str(i),'review_ag_strap',q,[*hosts,*[v['member'] for v in items]],[RID],parameters=par)
        for v in items:b.endpoint_links.append(dict(member_id=v['member']['id'],end='start' if v['end']==0 else 'end',connection_id=c['id'],basis='Source strap-end screws on one real shared collector, with actual receiving attachments.'))
    # Source straps are screwed at every intervening purlin crossing. Select
    # the real finite span and its flange, not the purlin workline at the web.
    for strap in roofstraps:
        aa,dd=axis(strap);side=int((aa[0]+dd[0])/2>288);u=unit([1,0,.25 if side==0 else -.25]);axes=(u,[0,1,0],cross(u,[0,1,0]));origin=[0,0,216] if side==0 else [288,0,288];a,d=[point(q,origin,axes) for q in (aa,dd)];direction=unit(sub(dd,aa))
        for m in [m for m in b.members if m['id'].startswith('AG-P-') and int(float(m['id'].split('-')[2])>288)==side]:
            flange=top_flange(b,m,origin,axes);at=(flange[0]+flange[1])/2;ratio=(at-a[0])/(d[0]-a[0])
            if not .02<ratio<.98:continue
            q=add(aa,mul(sub(dd,aa),ratio));ends=axis(m)
            if not min(v[1] for v in ends)+1<q[1]<max(v[1] for v in ends)-1:continue
            above=point(q,origin,axes)[2]-ROOF_T/2;gap=above-flange[3]
            if gap< -1e-6:raise ValueError('Roof strap below actual purlin top')
            qs=[point(add(q,mul(direction,s)),q,axes) for s in (-.5,.5)]
            for v in qs:v[2]=ROOF_T/2
            b.connection(strap['id']+'-CROSS-'+m['id'],'review_ag_strap',q,[m,strap],[RID],parameters=dict(actual_ag_strap=True,purpose='crossing',axes=axes,gap=gap,flange_t=flange[3]-flange[2],points=qs))
    b.note('AG-CONTINUOUS-X-SYSTEMS','S:south-wall X in each of bays1/2/9/10,5x118mil33No12 per end; roof X in each of bays1/2/3/8/9/10,3x68mil12No12 per end with eave/P2/P3/P4/ridge load path and fixings at every purlin crossing; end-wall3.5x68mil14No12, north header3x97mil17No12. The previous two-/three-bay-wide diagonals did not match the source single-bay diagonal checks. A:roof end receivers inset to actual16in eave/8in ridge rows, P2/P4 at114/222in and jamb P3 at168in; shared3/16in collectors, elevated crossing planes/packs,12in end cut (16in at south eave)s (16in at south eave), exact screw gauges, receiver bolts and local restraints. Roof straps remain continuous over purlin tops. Source capacities/stiffness remain conditional on checking these adopted fits; crossings have no centre joint.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes'];origin=ctx.c['point'];purpose=par['purpose']
    if purpose=='crossing':
        extract(ctx,ctx.ms[0],'PURLIN',axes,24);extract(ctx,ctx.ms[1],'STRAP',axes,20);gap=par['gap'];joined=['PURLIN','STRAP']
        if gap>1e-7:
            outline=hull([(q[0]+dx,q[1]+dy) for q in par['points'] for dx,dy in ((-.3,-.3),(-.3,.3),(.3,-.3),(.3,.3))]);a.polygon('PACK',[[x,y,-ROOF_T/2-gap] for x,y in outline],gap,normal=[0,0,1],basis='A',description='A solid crossing pack to the actual purlin flange');joined.append('PACK')
        a.fastener('CROSSING',par['points'],[0,0,-1],.216,ROOF_T+gap+par['flange_t'],joined,'S fix at every crossing / A twoNo12 and pack',basis='S condition / A group',screw=True)
        a.title='AG ROOF / CONTINUOUS STRAP AT ACTUAL PURLIN';a.front_axes=(0,1);a.section_axis=1;a.section_at=par['points'][0][1];return
    hc=par['host_count'];hosts=ctx.ms[:hc];straps=ctx.ms[hc:];height=par['height'];sets=[];corners=[]
    for i,m in enumerate(hosts):extract(ctx,m,'HOST'+str(i),axes,48)
    for i,m in enumerate(straps):extract(ctx,m,'STRAP'+str(i),axes,48)
    count=par['count'];cols=3 if count==33 else 2
    for i,(m,item) in enumerate(zip(straps,par['ends'])):
        ends=axis(m);start=point(ends[item['end']],origin,axes);along=vector(unit(sub(ends[1-item['end']],ends[item['end']])),axes);across=vector(m['local_y'],axes);t=p[m['profile_id']]['dimensions']['thickness'];packing=item['packing_in']
        qs=[add(start,add(mul(along,2+k//cols),mul(across,k%cols-(cols-1)/2))) for k in range(count)]
        for q in qs:q[2]=height+G+packing+t
        sets.append((i,qs,packing,t,along));corners.extend((q[0]+dx,q[1]+dy) for q in qs for dx,dy in ((-.75,-.75),(-.75,.75),(.75,-.75),(.75,.75)))
    if purpose=='roof_node':
        webs=[]
        for m in hosts:
            poly=max((r for r in sections(m,p,origin,axes) if max(q[0] for q in r)-min(q[0] for q in r)<.3),key=lambda r:max(q[2] for q in r)-min(q[2] for q in r))
            webs.append((min(q[0] for q in poly),max(q[0] for q in poly),min(q[2] for q in poly),max(q[2] for q in poly)))
        right=max(w[1] for w in webs);left=min(w[0] for w in webs);mid=(max(w[2] for w in webs)+min(w[3] for w in webs))/2;yy=par['web_y']
        corners.extend((x,y) for x in (right,right+2) for y in (yy-2.5,yy+2.5))
        a.box('WEB-LEG',[right,yy-2.5,mid-3],[.1875,5,height-(mid-3)],'A','A shared collector web leg reaches the actual purlin webs clear of the opposite anti-roll clip')
        a.fastener('RECEIVER',[[right+G,yy,z] for z in (mid-2,mid+2)],[-1,0,0],.5,G+right-left,['WEB-LEG']+['HOST'+str(i) for i in range(hc)],'A two1/2in through-web collector bolts; source roof-strap end group retained separately',basis='A')
    else:
        host=hosts[0];face,bands=face_intervals(host,p,axes[2]);across=cross(unit(sub(*host['axis'][::-1])),axes[2]);choices=[]
        if par['kind']=='end':
            from .review_sbmf_girts import cross_section
            faces=[]
            for poly in cross_section(host,p,axes):
                lo,hi=min(q[2] for q in poly),max(q[2] for q in poly);aa,dd=min(q[1] for q in poly),max(q[1] for q in poly)
                if .001<hi-lo<.3 and dd-aa>1.5:faces.append((hi,aa,dd,hi-lo))
            face=max(v[0] for v in faces)
            bands=[(aa*dot(across,axes[1]),dd*dot(across,axes[1]),t) for h,aa,dd,t in faces if abs(h-face)<1e-6]
        for lo,hi,tt in bands:
            gauge=(lo+hi)/2/dot(across,axes[1]);choices.append((abs(gauge),gauge,tt))
        _,gauge,ht=min(choices);bolts=[]
        for _,_,_,_,along in sets:
            sign=1 if along[0]>0 else -1;stations=(30,33) if par['kind'] in ('south','open') and origin[2]==216 else (-6,-9) if par['kind']=='open' and origin[2]==171 else (15,18)
            bolts.extend([[sign*s if s>0 else s,gauge,height+G] for s in stations])
        bolts=[list(q) for q in sorted({tuple(q) for q in bolts})]
        corners.extend((q[0]+dx,q[1]+dy) for q in bolts for dx,dy in ((-1,-.75),(-1,.75),(1,-.75),(1,.75)))
        joined=['COLLECTOR','HOST0']
        if height-face>1e-6:
            for i,q in enumerate(bolts):a.box('RECEIVER-PACK'+str(i),[q[0]-.75,q[1]-.6,face],[1.5,1.2,height-face],'A','A solid pack bridges to the actual broad receiving web/flange');joined.append('RECEIVER-PACK'+str(i))
        # Each rod names only the pack it actually traverses.
        for i,q in enumerate(bolts):a.fastener('RECEIVER'+str(i),[q],[0,0,-1],.5,height+G-face+ht,['COLLECTOR','HOST0']+(['RECEIVER-PACK'+str(i)] if height-face>1e-6 else []),'A actual collector/receiver bolt; local capacity not checked',basis='A')
    polygon=Polygon(hull(corners))
    if purpose=='wall_node' and par['kind'] in ('south','open'):
        if origin[2]==216:polygon=polygon.difference(box(-16, -9.5,1,9.5))
        elif par['kind']=='open' and origin[2]==171:polygon=polygon.difference(box(-3,-9.5,3,9.5))
    if polygon.geom_type!='Polygon' or polygon.interiors:raise ValueError('Source strap collector must remain one connected plate')
    a.polygon('COLLECTOR',[[x,y,height] for x,y in list(polygon.exterior.coords)[:-1]],G,normal=[0,0,1],basis='A',description='A continuous common3/16in collector, relieved around the actual strut receiver')
    if purpose=='roof_node':a.interfaces.append(dict(id='FOLD',kind='formed_bend',connects=['COLLECTOR','WEB-LEG'],basis='A',description='One continuous folded collector cap/web leg; local force transfer needs verification'))
    for i,qs,packing,t,_ in sets:
        joined=['STRAP'+str(i),'COLLECTOR']
        if packing:
            outline=hull([(q[0]+dx,q[1]+dy) for q in qs for dx,dy in ((-.6,-.6),(-.6,.6),(.6,-.6),(.6,.6))]);a.polygon('PACK'+str(i),[[x,y,height+G] for x,y in outline],packing,normal=[0,0,1],basis='A',description='A separate continuous crossing plane pack');joined.append('PACK'+str(i))
        a.fastener('STRAP-END'+str(i),qs,[0,0,-1],.216,t+G+packing,joined,f'S{count} No12 per strap end; A{cols}-column1in-row set-out',basis='S count / A fit',screw=True)
    a.title='AG '+par['kind'].upper()+' / SOURCE SHARED STRAP NODE';a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=0;a.section_at=sets[0][1][0][0]
    a.notes.append('Continuous source straps and source end-screw counts. A common collector, receiving bolts/packs,12in end cut (16in at south eave) and crossing planes. Roof straps pass over and are fixed at actual purlin crossings; wall panels occupy their separate source bays. Exact collector capacity, local receiver behavior and source restraint/stiffness conditions require checking; no centre weld or splice is added.')
