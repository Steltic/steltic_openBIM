"""Source through-fastened roof/wall sheets, actual support groups and doors."""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_cfs_occurrences import axis
from .review_cfs25_cladding import profile,top_flange,T
from .review_receiver_geometry import point
from .drawing_workflow import fingerprint


def apply(b):
    if b.key!='cfs28':return
    surfaces=[];roofplanes={};groups=defaultdict(list)
    for m in b.members:
        tag=m['id'].split('-')
        if m['id'].startswith('AG-P-'):groups['R'+str(int(float(tag[2])>288))].append(m)
        elif m['id'].startswith('AG-G-'):groups['W1'].append(m)
        elif m['id'].startswith('AG-STRUT-south-'):groups['W1'].append(m)
        elif m['id'].startswith('END-G-'):groups['E'+tag[2]].append(m)
    for side in (0,1):
        u=unit([1,0,(1 if side==0 else -1)*1/4]);v=[0,1,0];n=cross(u,v);origin=[0,0,216] if side==0 else [288,0,288];axes=(u,v,n);ms=groups['R'+str(side)]
        h=max(top_flange(b,m,origin,axes)[3] for m in ms)+.5;origin=add(origin,mul(n,h));roofplanes[side]=(origin,u)
        left,right=(-17,287.75) if side==0 else (288.25,593);start=(left-origin[0])/u[0];end=(right-origin[0])/u[0]
        surfaces.append(dict(id='R'+str(side),roof=True,origin=origin,axes=axes,limits=(-12.5,2124.5),total=2112,length=lambda w,s=start,e=end:(s,e),members=ms,record_id='schedules/sched-purlin'))
    def roof_z(x):
        q,u=roofplanes[int(x>288)];return q[2]+(x-q[0])*u[2]/u[0]
    for label in ('W1','E0','E1'):
        side=int(label[1]);ew=label[0]=='E';out=-1 if side==0 else 1;n=[0,out,0] if ew else [out,0,0];u=[0,0,1];v=cross(n,u);axes=(u,v,n)
        total=576 if ew else 2112;along=0 if ew else 1;origin=[0,2112*side,0] if ew else [576*side,0,0]
        if v[along]<0:origin[along]=total
        ms=groups[label];h=max(top_flange(b,m,origin,axes)[3] for m in ms);origin=add(origin,mul(n,h))
        ranges=[(-17,168,.25),(168,408,168),(408,593,.25)] if ew else [(-12.5,2124.5,.25)]
        for j,(lo,hi,bottom) in enumerate(ranges):
            def length(w,oo=origin[:],vv=v[:],low=bottom):return low,roof_z(oo[0]+vv[0]*w)-.25
            surfaces.append(dict(id=label+'-'+str(j),roof=False,origin=origin[:],axes=axes,limits=(lo,hi),total=total,length=length,members=ms,record_id='schedules/sched-endwall' if ew else 'schedules/sched-girt'))
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS28-PANEL26',basis='S',specification='Source26ga0.018in Fy50ksi steel panel,1.25in ribs at12in;0in blanket;No12 C1513 with1/2in bonded washers. Manufacturer zone-pressure tests and restraint stiffness required.')]
    b.panels[:]=[p for p in b.panels if p['kind']!='roof']
    for s in surfaces:build_surface(b,s)
    bind_roof_strap_layers(b)
    b.physical_interfaces=getattr(b,'physical_interfaces',[])+[dict(id='CFS28-PANEL-SUPPLIER',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in b.members if 'cladding_sheet' in m['kind']],panel_ids=[p['id'] for p in b.panels],responsible_party='Roof and wall panel supplier / project engineer',representation='Source gauge/ribs/screws and actual support groups shown; exact ribs, sidelaps, flange packs and perimeter cuts are A. Manufacturer must verify panel pressure capacity, restraint stiffness and edge overhang/closures; no diaphragm action is claimed.',detail_ref=dict(id='gold/cfs28/cladding',revision=fingerprint(b.raw['cc_wind_pressures'])),requirements=dict(wind_basis=b.raw['cc_wind_basis'],zone_pressures=b.raw['cc_wind_pressures'],restraint_conditions=b.raw['purlin_girt_I621_conditions']))]
    b.physical_interfaces.append(dict(id='CFS28-DOORS-AND-FOUNDATIONS',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in b.members if m['kind'] in ('opening_jamb','opening_header','column')],responsible_party='Door supplier / foundation engineer',representation='Source door product, guide attachments and concrete design remain delegated. Source20x14ft doors are nominal workline openings: confirm usable width between actual jamb flanges and guide clearances before procurement. No door hardware or reinforcement capacity is invented.',detail_ref=dict(id='gold/cfs28/endwall-and-foundations',revision=fingerprint(b.raw['anchorage'])),requirements=dict(endwall=b.records['schedules/sched-endwall']['data'],foundation_forces=b.raw['anchorage'])))
    b.note('AG-CLADDING','S:26ga0.018in Fy50ksi through-fastened roof/wall panels,1.25in ribs at12in,No12 C1513 screws at12in with1/2in bonded washers, no insulation or diaphragm action. A:36in nominal cover, rib flats/slopes and valley joggle,No12 sidelap screws at24in, exact cuts/gauges and small solid flange packs. Source manufacturer zone-pressure tests and restraint stiffness remain mandatory. Panel overhang beyond selected P1/edge supports, weather closures, door guide/clear width and foundation concrete remain explicit delegated interfaces; these drawings do not certify their capacity.')


def build_surface(b,s):
    u,v,n=s['axes'];origin=s['origin'];lo,hi=s['limits'];rid=s['record_id'];total=s['total']
    world=lambda x,w,h=0:add(origin,add(mul(u,x),add(mul(v,w),mul(n,h))))
    edges=[lo]+[36*i for i in range(math.floor(lo/36)+1,math.ceil(hi/36)) if max(0,lo)<36*i<min(total,hi)]+[hi]
    sheets=[];attached=defaultdict(list);rows=defaultdict(list)
    for m in s['members']:
        tag=m['id'].split('-');row=tag[2] if tag[:2] in (['AG','P'],['AG','G']) else '216' if tag[:2]==['AG','STRUT'] else tag[-1]
        rows[row].append(m)
    for i,(aa,dd) in enumerate(zip(edges,edges[1:])):
        start=max(s['length'](w)[0] for w in (aa,dd));end=min(s['length'](w)[1] for w in (aa,dd))
        pid=profile(b,'A-CFS28-SHEET-'+s['id']+'-'+str(i),aa,dd,i==0)
        m=b.member('AG-SKIN-'+s['id']+'-'+str(i),pid,'roof_cladding_sheet' if s['roof'] else 'wall_cladding_sheet',world(start,(aa+dd)/2),world(end,(aa+dd)/2),1,'A',records=[rid],local_y=v,host_panel_id='AG-SKIN-'+s['id'],adopted_width_limits=[aa,dd],sheet_thickness_in=T,source_rib_depth_in=1.25,source_rib_pitch_in=12,physical_fit_basis='Source gauge, ribs and screws. A exact folded shape,36in cover/joggle and conservative rectangular cuts; source pressure tests and restraint stiffness remain delegated.')
        m['material_id']='CFS28-PANEL26';sheets.append(m)
    vertices=[world(s['length'](lo)[0],lo),world(s['length'](hi)[0],hi),world(s['length'](hi)[1],hi)]
    if s['id'].startswith('E') and lo<288<hi:vertices.append(world(s['length'](288)[1],288))
    vertices.append(world(s['length'](lo)[1],lo))
    b.panel('AG-SKIN-'+s['id'],'roof' if s['roof'] else 'cladding_envelope',vertices,1.25,1,'A',records=[rid],material_id='CFS28-PANEL26',physical_constituent_member_ids=[m['id'] for m in sheets],representation='Coordination envelope; individual folded0.018in sheets represent steel. Weather closures and local edge support remain supplier scope.',thickness_direction='normal')
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
                if gap<-1e-6:raise ValueError('CFS28 skin intersects actual support '+mid)
                groups[mid,round(max(0,gap),8)].append(world(gauge,w,T))
            for gi,((mid,gap),qs) in enumerate(groups.items()):
                centre=sub(mul([sum(q[k] for q in qs) for k in range(3)],1/len(qs)),mul(n,T));host=next(m for m in ms if m['id']==mid)
                c=b.connection(f'AG-SKIN-{s["id"]}-{row}-{si}-{gi}','review_ag_cladding',centre,[host,sheet],[rid],parameters=dict(actual_cladding=True,axes=s['axes'],purpose='support',pitch=12,roof=s['roof'],gap=gap,flange_t=top_flange(b,host,origin,s['axes'])[3]-top_flange(b,host,origin,s['axes'])[2],points=[point(q,centre,s['axes']) for q in qs]))
                attached[sheet['id']].append(c)
    for i,(left,right) in enumerate(zip(sheets,sheets[1:]),1):
        w=right['adopted_width_limits'][0];start=max(point(axis(m)[0],origin,s['axes'])[0] for m in (left,right));end=min(point(axis(m)[1],origin,s['axes'])[0] for m in (left,right))
        values=[start+6+24*j for j in range(math.ceil((end-start)/24)) if start+6+24*j<end-.5]
        for batch in range(0,len(values),4):
            xs=values[batch:batch+4];mean=sum(xs)/len(xs);centre=world(mean,w)
            c=b.connection(f'AG-SKIN-{s["id"]}-SEAM-{i}-{batch//4}','review_ag_cladding',centre,[left,right],[rid],parameters=dict(actual_cladding=True,axes=s['axes'],purpose='sidelap',pitch=24,roof=s['roof'],gap=0,flange_t=T,points=[[x-mean,0,2*T] for x in xs]))
            attached[left['id']].append(c);attached[right['id']].append(c)
    for m in sheets:
        if not attached[m['id']]:raise ValueError('CFS28 unattached sheet '+m['id'])
        for i,end in enumerate(('start','end')):
            c=min(attached[m['id']],key=lambda c:math.dist(c['point'],axis(m)[i]));b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Nearest actual screw group on this finite sheet; panel overhang/edge closures are delegated, not an invented end support.'))


def bind_roof_strap_layers(b):
    straps=[m for m in b.members if m['id'].startswith('AG-ROOF-X-')]
    for c in b.connections:
        par=c.get('parameters',{})
        if c['detail_ref']['id']!='review_ag_cladding' or not par['roof'] or par['purpose']!='support':continue
        axes=par['axes'];layers=[];members=[]
        for q in par['points']:
            world=add(c['point'],[sum(q[j]*axes[j][k] for j in range(3)) for k in range(3)]);hits=[]
            for m in straps:
                aa,dd=axis(m);u=unit(sub(dd,aa));length=math.dist(aa,dd);along=dot(sub(world,aa),u);width=b.profiles[m['profile_id']]['dimensions']['width'];across=dot(sub(world,aa),m['local_y'])
                # Include a neighbouring strap if it overlaps the finite
                # small bearing pad, even when this screw misses the strap.
                if -.4<=along<=length+.4 and abs(across)<=width/2+.4:
                    z=point(aa,c['point'],axes)[2];t=b.profiles[m['profile_id']]['dimensions']['thickness'];through=0<=along<=length and abs(across)<width/2
                    hits.append(dict(member_id=m['id'],bottom=z-t/2,top=z+t/2,through=through))
                    if m['id'] not in c['member_ids']:c['member_ids'].append(m['id'])
            layers.append(sorted(hits,key=lambda v:v['bottom']))
        par['strap_layers']=layers


def draw(ctx):
    from .review_cfs25_cladding import draw as actual_sheet
    from .review_receiver_geometry import extract
    a,par=ctx.a,ctx.params
    if not par.get('roof') or par['purpose']=='sidelap':
        actual_sheet(ctx)
    else:
        axes=par['axes'];points=par['points'];extent=max(math.sqrt(dot(q,q)) for q in points)+3
        for i,m in enumerate(ctx.ms):
            part=extract(ctx,m,'M'+str(i),axes,extent);part['drawing_style']='outline_iso' if 'cladding_sheet' in m['kind'] else 'normal'
        names={m['id']:'M'+str(i) for i,m in enumerate(ctx.ms)};wt=.0625
        for i,(q,layers) in enumerate(zip(points,par['strap_layers'])):
            joined=['M0','M1'];bottom=-par['gap'];top=q[2]-T
            # Individual bearing pads avoid a long solid spacer intersecting
            # the source diagonal straps between remote screws. Slots through
            # these pads admit the real strap layer; no duplicate steel.
            cuts=[]
            for row in layers:
                lo=max(bottom,row['bottom']);hi=min(top,row['top'])
                if hi>lo:
                    cuts.append((lo,hi))
                    if row['through']:joined.append(names[row['member_id']])
            current=bottom;segments=[]
            for lo,hi in sorted(cuts):
                if lo>current+1e-7:segments.append((current,lo))
                current=max(current,hi)
            if top>current+1e-7:segments.append((current,top))
            for j,(lo,hi) in enumerate(segments):
                label=f'PACK{i}-{j}';a.box(label,[q[0]-.35,q[1]-.35,lo],[.7,.7,hi-lo],'A','A individual slotted bearing pad; real roof strap passes through its own open layer');joined.append(label)
            a.cylinder('WASHER'+str(i),q,[0,0,1],.5,wt,'S diameter / A thickness','Source1/2in bonded sealing washer',kind='washer')
            a.fastener('SCREW'+str(i),[add(q,[0,0,wt])],[0,0,-1],.216,T+par['gap']+par['flange_t']+wt,joined+['WASHER'+str(i)],'S No12 C1513 panel screw at12in,1/2in bonded washer; A strap-layer grip and slotted pad',basis='S group / A fit',screw=True)
        a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=1;a.section_at=points[0][1]
    a.title='AG CLADDING / '+('ADOPTED SIDELAP' if par['purpose']=='sidelap' else 'SOURCE SUPPORT SCREWS')
    a.notes=['S26ga0.018in Fy50ksi panel,1.25in ribs at12in;No12 C1513 at12in supports with1/2in bonded washers, no insulation or diaphragm action. A rib flats/joggle, exact cuts,1/2in roof stand-off with individual slotted steel pads, grip through actual roof straps and24in sidelaps. Source panel pressure capacity/restraint stiffness and all edge overhang/closure details remain supplier verification.']
