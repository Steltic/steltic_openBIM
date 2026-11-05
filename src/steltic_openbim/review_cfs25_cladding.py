"""Source Option A cladding and screws on the actual retrofit Z flanges.

Rib flats, joggles, panel edges and local packing are adopted geometry. The
source manufacturer's panel tests and existing-structure handoff are retained.
"""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_cfs_occurrences import axis
from .review_cfs25_secondary import sections
from .review_sbmf_deck import folded_profile
from .review_receiver_geometry import extract,point

RID='schedules/sched-fastener'
T=.018


def profile(b,label,lo,hi,first):
    left=lo if first else lo-.375;right=hi;mid=(lo+hi)/2
    def height(w):
        if not first and w<lo+.75:
            return 1.5*T if w<=lo+.375 else 1.5*T-(w-lo-.375)*T/.375
        r=w%12
        if r<=4 or r>=8:return T/2
        if r<5:return T/2+(r-4)*(1.25-T)
        if r<=7:return 1.25-T/2
        return T/2+(8-r)*(1.25-T)
    xs={left,right}
    for n in range(math.floor(left/12)-1,math.ceil(right/12)+1):
        xs.update(x for x in (n*12+4,n*12+5,n*12+7,n*12+8) if left<x<right)
    if not first:xs.update((lo+.375,lo+.75))
    return folded_profile(b,label,[[x-mid,height(x)] for x in sorted(xs)],T)


def top_flange(b,m,origin,axes):
    polys=sections(m,b.profiles,origin,axes)
    flat=[v for v in polys if max(q[2] for q in v)-min(q[2] for q in v)<.2 and max(q[0] for q in v)-min(q[0] for q in v)>1]
    poly=max(flat,key=lambda v:max(q[2] for q in v))
    return [min(q[0] for q in poly),max(q[0] for q in poly),min(q[2] for q in poly),max(q[2] for q in poly)]


def apply(b):
    if b.key!='cfs25':return
    if 'through-fastened Option A' not in b.records[RID]['data']['note']:raise ValueError('CFS25 cladding selection changed')
    b.connections[:]=[c for c in b.connections if c['detail_ref']['id']!='review_skin_fastener']
    groups=defaultdict(list)
    for m in b.members:
        if not m.get('source_profile_id'):continue
        tag=m['id'].split('-')
        if tag[0]=='P':groups['R'+str(int(float(tag[1])>600))].append(m)
        elif tag[0]=='G':groups['W'+tag[1]].append(m)
        else:groups['E'+str(int(float(tag[2])>0))].append(m)
    surfaces=[];roofplanes={}
    for side in (0,1):
        u=unit([1,0,(1 if side==0 else -1)/12]);v=[0,1,0];n=cross(u,v);origin=[0,0,240] if side==0 else [600,0,290]
        ms=groups['R'+str(side)];axes=(u,v,n)
        h=max(top_flange(b,m,origin,axes)[3] for m in ms)
        origin=add(origin,mul(n,h));roofplanes[side]=(origin,u,n)
        start=(-18-origin[0])/u[0] if side==0 else 0
        end=(1218-origin[0])/u[0] if side else (600-origin[0])/u[0]-2
        surfaces.append(dict(id='R'+str(side),roof=True,axes=axes,origin=origin,limits=(-18,3018),length=lambda w,s=start,e=end:(s,e),members=ms))
    def roof_z(x):
        origin,u,n=roofplanes[int(x>600)]
        return origin[2]+(x-origin[0])/u[0]*u[2]
    for label in ('W0','W1','E0','E1'):
        side=int(label[1]);endwall=label[0]=='E';out=-1 if side==0 else 1
        v=[1,0,0] if endwall else [0,1,0];n=[0,out,0] if endwall else [out,0,0];u=cross(v,n)
        # Always draw upright sheets; flip the width axis when required.
        u=[0,0,1];v=cross(n,u);axes=(u,v,n)
        origin=[0,3000*side,0] if endwall else [1200*side,0,0];ms=groups[label]
        h=max(top_flange(b,m,origin,axes)[3] for m in ms);origin=add(origin,mul(n,h))
        total=1200 if endwall else 3000;along=0 if endwall else 1
        if v[along]<0:origin[along]=total
        def length(w,lo=origin[:],vv=v[:],ew=endwall):
            x=lo[0]+vv[0]*w
            return .25,roof_z(x)-.25 if ew else roof_z(lo[0])-.25
        surfaces.append(dict(id=label,roof=False,axes=axes,origin=origin,limits=(-16,total+16),length=length,members=ms))
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS25-PANEL26',basis='S designation / A exact thickness and rib fit',specification='26ga ASTM A792 SS Grade50,1.25in ribs at12in; A0.018in sheet and folded geometry; source ASTM E1592 tested uplift requirements retained')]
    b.panels[:]=[p for p in b.panels if not p['id'].startswith('ROOF-')]
    for surface in surfaces:build_surface(b,surface)
    reason='Source Option B standing-seam alternative is not selected: the accepted fictional scenario adopts through-fastened Option A. Retain all alternative calculations, but do not add its quarter-point bridging or sliding clips to Option A.'
    b.record_dispositions=getattr(b,'record_dispositions',[])+[dict(record_id='schedules/sched-purlin-standing-seam',status='not_applicable',reason=reason,evidence_member_ids=[m['id'] for m in groups['R0']+groups['R1']])]
    b.note('CLADDING-OPTION-A','S: through-fastened26ga panels,1.25in ribs at12in, No12-14 C1513 screws with1/2in bonded sealing washers;12in supports,6in roof-corner supports. A:0.018in sheet, rib flats/slopes,36in nominal cover with partial/extended edge sheets, joggled valley sidelaps, No12 sidelap screws at24in, flange gauges, minor flange packing and exact envelope. Blanket insulation remains compressed at screws, with no structural stand-off. Rib sheet edges use conservative rectangular cuts; roof/wall perimeter closures, weather seals, insulation and any edge overhang/local panel capacity are a manufacturer coordination interface. Original E1592 test, existing receiving-structure and source-capacity requirements remain unverified; the drawing is not a new design certificate.')


def build_surface(b,s):
    u,v,n=s['axes'];origin=s['origin'];lo,hi=s['limits'];total=hi-(18 if s['roof'] else 16)
    def world(x,w,h=0):return add(add(add(origin,mul(u,x)),mul(v,w)),mul(n,h))
    edges=[lo]+[i*36 for i in range(1,math.ceil(total/36))]+[hi];sheets=[];attached=defaultdict(list)
    for i,(a,d) in enumerate(zip(edges,edges[1:])):
        start=max(s['length'](w)[0] for w in (a,d));end=min(s['length'](w)[1] for w in (a,d))
        pid=profile(b,'A-CFS25-SKIN-'+s['id']+'-'+str(i),a,d,i==0)
        m=b.member('SKIN-'+s['id']+'-'+str(i),pid,'roof_cladding_sheet' if s['roof'] else 'wall_cladding_sheet',world(start,(a+d)/2),world(end,(a+d)/2),1,'A',records=[RID],local_y=v,host_panel_id='SKIN-'+s['id'],material_selection='CFS25-PANEL26',
            source_rib_pitch_in=12,source_rib_depth_in=1.25,sheet_thickness_in=T,adopted_width_limits=[a,d],physical_fit_basis='Single folded26ga sheet; A rib/joggle and edge fit, conservative rectangular ends, source tested panel capacity remains delegated')
        m['material_id']='CFS25-PANEL26';sheets.append(m)
    poly=[world(s['length'](lo)[0],lo),world(s['length'](hi)[0],hi),world(s['length'](hi)[1],hi)]
    if s['id'].startswith('E'):poly.append(world(s['length'](600)[1],600))
    poly.append(world(s['length'](lo)[1],lo))
    panel=b.panel('SKIN-'+s['id'],'roof' if s['roof'] else 'cladding_envelope',poly,1.25,1,'A',records=[RID],material_id='CFS25-PANEL26',physical_constituent_member_ids=[m['id'] for m in sheets],
        representation='Coordination envelope only; explicit folded sheet members represent steel, not a solid1.25in slab. Perimeter closures/insulation by panel supplier.',thickness_direction='positive_global_z' if s['roof'] else 'normal',accepted_rib_fit=dict(depth_in=1.25,pitch_in=12,sheet_thickness_in=T,source_option='through-fastened Option A'))
    rows=defaultdict(list)
    for m in s['members']:
        # Nominal row keys survive local nesting translations.
        tag=m['id'].split('-');key=tag[1] if tag[0]=='P' else tag[-1]
        rows[key].append(m)
    for row,ms in rows.items():
        for si,sheet in enumerate(sheets):
            a,d=sheet['adopted_width_limits'];stations=[3+6*j for j in range(math.ceil(total/6)) if max(0,a)<=3+6*j<min(total,d)]
            data=defaultdict(list)
            for w in stations:
                corner=s['roof'] and min(float(row),1200-float(row))<=96 and min(w,3000-w)<300
                if not corner and round((w-3)/6)%2:continue
                candidates=[]
                for m in ms:
                    ends=[point(q,origin,s['axes']) for q in axis(m)]
                    if min(q[1] for q in ends)-1e-7<=w<=max(q[1] for q in ends)+1e-7:
                        f=top_flange(b,m,origin,s['axes']);candidates.append((f[3],m['id'],m,f))
                if not candidates:raise ValueError('No finite cladding support '+s['id']+'/'+row+'/'+str(w))
                _,_,host,f=max(candidates,key=lambda x:x[:2]);gauge=(f[0]+f[1])/2
                gap=-f[3]
                if gap<-.00001:raise ValueError('Sheet intersects support '+host['id'])
                data[host['id'],round(gap,8),6 if corner else 12].append(dict(q=world(gauge,w,T),flange=f))
            for gi,((mid,gap,pitch),items) in enumerate(data.items()):
                host=next(m for m in ms if m['id']==mid);centre=world(sum(vv['flange'][0]+vv['flange'][1] for vv in items)/len(items)/2,sum(dot(sub(vv['q'],origin),v) for vv in items)/len(items))
                f=items[0]['flange'];ct=b.profiles[host['profile_id']]['source_dimensions']['t']
                par=dict(axes=s['axes'],actual_cladding=True,purpose='support',pitch=pitch,roof=s['roof'],gap=gap,flange_t=ct,points=[point(vv['q'],centre,s['axes']) for vv in items])
                c=b.connection(f'SKIN-{s["id"]}-{row}-{si}-{gi}','review_retrofit_cladding',centre,[host,sheet],[RID],parameters=par)
                attached[sheet['id']].append(c)
    for i,(left,right) in enumerate(zip(sheets,sheets[1:]),1):
        w=right['adopted_width_limits'][0];start=max(dot(sub(m['axis'][0],origin),u) for m in (left,right));end=min(dot(sub(m['axis'][1],origin),u) for m in (left,right))
        values=[start+6+24*j for j in range(math.ceil((end-start)/24)) if start+6+24*j<end-.5]
        for batch in range(0,len(values),4):
            xs=values[batch:batch+4];centre=world(sum(xs)/len(xs),w)
            c=b.connection(f'SKIN-{s["id"]}-SEAM-{i}-{batch//4}','review_retrofit_cladding',centre,[left,right],[RID],parameters=dict(axes=s['axes'],actual_cladding=True,purpose='sidelap',pitch=24,roof=s['roof'],gap=0,flange_t=T,points=[[x-sum(xs)/len(xs),0,2*T] for x in xs]),basis='A')
            attached[left['id']].append(c);attached[right['id']].append(c)
    for sheet in sheets:
        cons=attached[sheet['id']]
        if not cons:raise ValueError('Unattached cladding sheet '+sheet['id'])
        for i,end in enumerate(('start','end')):
            c=min(cons,key=lambda c:math.dist(c['point'],sheet['axis'][i]))
            b.endpoint_links.append(dict(member_id=sheet['id'],end=end,connection_id=c['id'],basis='Nearest actual support or sidelap screw group on this same finite sheet; this is not an invented end support. Free edge overhang and perimeter closure remain explicitly subject to source manufacturer verification.'))


def draw(ctx):
    a,par=ctx.a,ctx.params;axes=par['axes'];seam=par['purpose']=='sidelap';points=par['points']
    a.title='RETROFIT CLADDING / ACTUAL SIDELAP' if seam else 'RETROFIT CLADDING / ACTUAL SUPPORT SCREWS'
    extent=max(math.sqrt(dot(q,q)) for q in points)+3
    for i,m in enumerate(ctx.ms):
        p=extract(ctx,m,'M'+str(i),axes,extent);p['drawing_style']='outline_iso' if 'cladding_sheet' in m['kind'] else 'normal'
    joined=['M0','M1'];gap=par['gap'];grip=(2*T if seam else T+par['flange_t']+gap)
    if gap>1e-7:
        x=min(q[0] for q in points)-.4;y=min(q[1] for q in points)-.4
        a.box('PACK',[x,y,-gap],[max(q[0] for q in points)-x+.4,max(q[1] for q in points)-y+.4,gap],'A','Actual sheet-to-flange packing; local capacity and insulation compression require verification');joined.append('PACK')
    # Source half-inch bonded sealing washers have their own visible geometry.
    wt=.0625
    for i,q in enumerate(points):
        a.cylinder('WASHER'+str(i),q,[0,0,1],.5,wt,'S diameter / A thickness','1/2in bonded sealing washer',kind='washer')
        a.fastener('SCREW'+str(i),[add(q,[0,0,wt])],[0,0,-1],.216,grip+wt,joined+['WASHER'+str(i)],
            'A No12-14 sidelap screw at24in; supplier approval required' if seam else f'S No12-14 C1513 panel screw at{par["pitch"]}in;1/2in bonded sealing washer; A finite gauge and packing',basis='A' if seam else 'S',screw=True)
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=1;a.section_at=points[0][1]
    if len(points)>1:a.dim(points[0],points[1],('A sidelap pitch' if seam else 'S support pitch'),basis='A' if seam else 'S',offset=-45)
    a.notes.append('S through-fastened Option A,26ga Grade50 panels,1.25in ribs at12in; No12-14 C1513 screws and1/2in bonded sealing washers. A0.018in sheet, rib flats/slopes, joggle, local gauge, minor packing and washer thickness. One folded panel is represented by geometric strips. Source E1592 panel test and existing-structure requirements still apply; edge closures, insulation/compression, overhang and all adopted changes need supplier verification.')
