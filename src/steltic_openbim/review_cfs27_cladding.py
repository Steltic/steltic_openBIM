"""Source through-fastened roof/wall sheets, actual support groups and doors."""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_cfs_occurrences import axis
from .review_cfs25_cladding import profile,top_flange,T
from .review_receiver_geometry import point
from .drawing_workflow import fingerprint


def apply(b):
    if b.key!='cfs27':return
    surfaces=[];roofplanes={};groups=defaultdict(list)
    for m in b.members:
        tag=m['id'].split('-')
        if m['id'].startswith('SC-P-'):groups['R'+str(int(float(tag[2])>216))].append(m)
        elif m['id'].startswith('SC-G-'):groups['W'+tag[2]].append(m)
        elif m['id'].startswith('EAVE-'):groups['W'+tag[1]].append(m)
        elif m['id'].startswith('END-G-'):groups['E'+tag[2]].append(m)
    for side in (0,1):
        u=unit([1,0,(1 if side==0 else -1)*2/9]);v=[0,1,0];n=cross(u,v);origin=[0,0,192] if side==0 else [216,0,240];axes=(u,v,n);ms=groups['R'+str(side)]
        h=max(top_flange(b,m,origin,axes)[3] for m in ms);origin=add(origin,mul(n,h));roofplanes[side]=(origin,u)
        left,right=(-16.25,215.75) if side==0 else (216.25,448.25);start=(left-origin[0])/u[0];end=(right-origin[0])/u[0]
        surfaces.append(dict(id='R'+str(side),roof=True,origin=origin,axes=axes,limits=(-12.5,2352.5),total=2340,length=lambda w,s=start,e=end:(s,e),members=ms,record_id='schedules/sched-purlin'))
    def roof_z(x):
        q,u=roofplanes[int(x>216)];return q[2]+(x-q[0])*u[2]/u[0]
    for label in ('W0','W1','E0','E1'):
        side=int(label[1]);ew=label[0]=='E';out=-1 if side==0 else 1;n=[0,out,0] if ew else [out,0,0];u=[0,0,1];v=cross(n,u);axes=(u,v,n)
        total=432 if ew else 2340;along=0 if ew else 1;origin=[0,2340*side,0] if ew else [432*side,0,0]
        if v[along]<0:origin[along]=total
        ms=groups[label];h=max(top_flange(b,m,origin,axes)[3] for m in ms);origin=add(origin,mul(n,h))
        ranges=[(-16.25,120,.25),(120,312,168),(312,448.25,.25)] if ew else [(-12.5,2352.5,.25)]
        for j,(lo,hi,bottom) in enumerate(ranges):
            def length(w,oo=origin[:],vv=v[:],low=bottom):return low,roof_z(oo[0]+vv[0]*w)-.25
            surfaces.append(dict(id=label+'-'+str(j),roof=False,origin=origin[:],axes=axes,limits=(lo,hi),total=total,length=length,members=ms,record_id='schedules/sched-endwall' if ew else 'schedules/sched-girt'))
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS27-PANEL26',basis='S',specification='Source26ga0.018in Fy50ksi steel panel,1.25in ribs at12in;0in blanket;No12 C1513 with1/2in bonded washers. Manufacturer zone-pressure tests and restraint stiffness required.')]
    b.panels[:]=[p for p in b.panels if p['kind']!='roof']
    for s in surfaces:build_surface(b,s)
    b.physical_interfaces=getattr(b,'physical_interfaces',[])+[dict(id='CFS27-PANEL-SUPPLIER',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in b.members if 'cladding_sheet' in m['kind']],panel_ids=[p['id'] for p in b.panels],responsible_party='Roof and wall panel supplier / project engineer',representation='Source gauge/ribs/screws and actual support groups shown; exact ribs, sidelaps, flange packs and perimeter cuts are A. Manufacturer must verify panel pressure capacity, restraint stiffness and edge overhang/closures; no diaphragm action is claimed.',detail_ref=dict(id='gold/cfs27/cladding',revision=fingerprint(b.raw['cladding_wind_pressures'])),requirements=dict(wind_basis=b.raw['cladding_wind_basis'],zone_pressures=b.raw['cladding_wind_pressures'],restraint_conditions=b.raw['purlin_girt_I621_conditions']))]
    b.physical_interfaces.append(dict(id='CFS27-DOORS-AND-FOUNDATIONS',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in b.members if m['kind'] in ('opening_jamb','opening_header','column')],responsible_party='Door supplier / foundation engineer',representation='Source door product, guide attachments and concrete design remain delegated. Source16x14ft doors are nominal workline openings: confirm usable width between actual jamb flanges and guide clearances before procurement. No door hardware or reinforcement capacity is invented.',detail_ref=dict(id='gold/cfs27/endwall-and-foundations',revision=fingerprint(b.raw['foundation_forces_by_base'])),requirements=dict(endwall=b.records['schedules/sched-endwall']['data'],foundation_forces=b.raw['foundation_forces_by_base'])))
    b.note('SINGLE-CLADDING','S:26ga0.018in Fy50ksi through-fastened roof/wall panels,1.25in ribs at12in,No12 C1513 screws at12in with1/2in bonded washers, no insulation or diaphragm action. A:36in nominal cover, rib flats/slopes and valley joggle,No12 sidelap screws at24in, exact cuts/gauges and small solid flange packs. Source manufacturer zone-pressure tests and restraint stiffness remain mandatory. Panel overhang beyond selected P1/edge supports, weather closures, door guide/clear width and foundation concrete remain explicit delegated interfaces; these drawings do not certify their capacity.')


def build_surface(b,s):
    u,v,n=s['axes'];origin=s['origin'];lo,hi=s['limits'];rid=s['record_id'];total=s['total']
    world=lambda x,w,h=0:add(origin,add(mul(u,x),add(mul(v,w),mul(n,h))))
    edges=[lo]+[36*i for i in range(math.floor(lo/36)+1,math.ceil(hi/36)) if max(0,lo)<36*i<min(total,hi)]+[hi]
    sheets=[];attached=defaultdict(list);rows=defaultdict(list)
    for m in s['members']:
        tag=m['id'].split('-');row=tag[2] if tag[:2]==['SC','P'] else tag[3] if tag[:2]==['SC','G'] else '192' if tag[0]=='EAVE' else tag[-1]
        rows[row].append(m)
    for i,(aa,dd) in enumerate(zip(edges,edges[1:])):
        start=max(s['length'](w)[0] for w in (aa,dd));end=min(s['length'](w)[1] for w in (aa,dd))
        pid=profile(b,'A-CFS27-SHEET-'+s['id']+'-'+str(i),aa,dd,i==0)
        m=b.member('SC-SKIN-'+s['id']+'-'+str(i),pid,'roof_cladding_sheet' if s['roof'] else 'wall_cladding_sheet',world(start,(aa+dd)/2),world(end,(aa+dd)/2),1,'A',records=[rid],local_y=v,host_panel_id='SC-SKIN-'+s['id'],adopted_width_limits=[aa,dd],sheet_thickness_in=T,source_rib_depth_in=1.25,source_rib_pitch_in=12,physical_fit_basis='Source gauge, ribs and screws. A exact folded shape,36in cover/joggle and conservative rectangular cuts; source pressure tests and restraint stiffness remain delegated.')
        m['material_id']='CFS27-PANEL26';sheets.append(m)
    vertices=[world(s['length'](lo)[0],lo),world(s['length'](hi)[0],hi),world(s['length'](hi)[1],hi)]
    if s['id'].startswith('E') and lo<216<hi:vertices.append(world(s['length'](216)[1],216))
    vertices.append(world(s['length'](lo)[1],lo))
    b.panel('SC-SKIN-'+s['id'],'roof' if s['roof'] else 'cladding_envelope',vertices,1.25,1,'A',records=[rid],material_id='CFS27-PANEL26',physical_constituent_member_ids=[m['id'] for m in sheets],representation='Coordination envelope; individual folded0.018in sheets represent steel. Weather closures and local edge support remain supplier scope.',thickness_direction='normal')
    for row,ms in rows.items():
        for si,sheet in enumerate(sheets):
            aa,dd=sheet['adopted_width_limits'];groups=defaultdict(list);ends=[point(q,origin,s['axes'])[0] for q in axis(sheet)]
            for w in (3+12*j for j in range(math.ceil(total/12))):
                if not max(0,aa)<=w<min(total,dd):continue
                options=[]
                for m in ms:
                    e=[point(q,origin,s['axes'])[1] for q in axis(m)]
                    if not min(e)-1e-7<=w<=max(e)+1e-7:continue
                    f=top_flange(b,m,origin,s['axes']);gauge=(f[0]+f[1])/2
                    if min(ends)+.25<=gauge<=max(ends)-.25:options.append((f[3],m['id'],m,gauge))
                if not options:continue # Other finite girt segments / below-door rows.
                top,mid,host,gauge=max(options,key=lambda q:q[:2]);gap=-top
                if gap<-1e-6:raise ValueError('CFS27 skin intersects actual support '+mid)
                groups[mid,round(max(0,gap),8)].append(world(gauge,w,T))
            for gi,((mid,gap),qs) in enumerate(groups.items()):
                centre=sub(mul([sum(q[k] for q in qs) for k in range(3)],1/len(qs)),mul(n,T));host=next(m for m in ms if m['id']==mid)
                c=b.connection(f'SC-SKIN-{s["id"]}-{row}-{si}-{gi}','review_single_cladding',centre,[host,sheet],[rid],parameters=dict(actual_cladding=True,axes=s['axes'],purpose='support',pitch=12,roof=s['roof'],gap=gap,flange_t=.0566,points=[point(q,centre,s['axes']) for q in qs]))
                attached[sheet['id']].append(c)
    for i,(left,right) in enumerate(zip(sheets,sheets[1:]),1):
        w=right['adopted_width_limits'][0];start=max(point(axis(m)[0],origin,s['axes'])[0] for m in (left,right));end=min(point(axis(m)[1],origin,s['axes'])[0] for m in (left,right))
        values=[start+6+24*j for j in range(math.ceil((end-start)/24)) if start+6+24*j<end-.5]
        for batch in range(0,len(values),4):
            xs=values[batch:batch+4];mean=sum(xs)/len(xs);centre=world(mean,w)
            c=b.connection(f'SC-SKIN-{s["id"]}-SEAM-{i}-{batch//4}','review_single_cladding',centre,[left,right],[rid],parameters=dict(actual_cladding=True,axes=s['axes'],purpose='sidelap',pitch=24,roof=s['roof'],gap=0,flange_t=T,points=[[x-mean,0,2*T] for x in xs]))
            attached[left['id']].append(c);attached[right['id']].append(c)
    for m in sheets:
        if not attached[m['id']]:raise ValueError('CFS27 unattached sheet '+m['id'])
        for i,end in enumerate(('start','end')):
            c=min(attached[m['id']],key=lambda c:math.dist(c['point'],axis(m)[i]));b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Nearest actual screw group on this finite sheet; panel overhang/edge closures are delegated, not an invented end support.'))


def draw(ctx):
    from .review_cfs25_cladding import draw as actual_sheet
    actual_sheet(ctx);seam=ctx.params['purpose']=='sidelap'
    ctx.a.title='SINGLE CHANNEL CLADDING / '+('ADOPTED SIDELAP' if seam else 'SOURCE SUPPORT SCREWS')
    ctx.a.notes=['S26ga0.018in Fy50ksi panel,1.25in ribs at12in;No12 C1513 at12in supports with1/2in bonded washers. A rib flats/joggle, exact cuts, flange packing and24in sidelaps. Source tested pressure capacity/restraint stiffness and all perimeter overhang/closure details remain supplier verification; no insulation or roof diaphragm action.']
