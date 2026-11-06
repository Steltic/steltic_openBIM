"""Source through-fastened roof/wall sheets, actual support groups and doors."""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_cfs_occurrences import axis
from .review_cfs25_cladding import profile,top_flange,T
from .review_receiver_geometry import point
from .drawing_workflow import fingerprint
from .review_cfs17_secondary import ROOF, roof_at, DOORS


def apply(b):
    if b.key!='cfs17':return
    surfaces=[];roofplanes={};groups=defaultdict(list)
    for m in b.members:
        tag=m['id'].split('-')
        if m['id'].startswith('GAR-P-'):groups['R'+str(roof_at(float(tag[2]))[0])].append(m)
        elif m['id'].startswith('GAR-G-'):groups['W'+tag[2]].append(m)
        elif m['id'].startswith(('GAR-STRUT-left-','GAR-STRUT-right-')):groups['W'+str(int(m['axis'][0][0]>500))].append(m)
        elif m['id'].startswith('END-G-'):groups['E'+tag[2]].append(m)
    for seg in range(4):
        u=roof_at((ROOF[seg][0]+ROOF[seg+1][0])/2)[2];v=[0,1,0];n=cross(u,v);origin=[ROOF[seg][0],0,ROOF[seg][1]];axes=(u,v,n);ms=groups['R'+str(seg)]
        h=max(top_flange(b,m,origin,axes)[3] for m in ms);origin=add(origin,mul(n,h));roofplanes[seg]=(origin,u,axes)
    cuts=[-17]
    for j in range(3):
        a,u,_=roofplanes[j];d,v,_=roofplanes[j+1];ma=u[2]/u[0];md=v[2]/v[0];cuts.append((d[2]-md*d[0]-a[2]+ma*a[0])/(ma-md))
    cuts.append(1049)
    for seg in range(4):
        origin,u,axes=roofplanes[seg];left=cuts[seg]+(.25 if seg else 0);right=cuts[seg+1]-(.25 if seg<3 else 0);start=(left-origin[0])/u[0];end=(right-origin[0])/u[0]
        surfaces.append(dict(id='R'+str(seg),roof=True,origin=origin,axes=axes,limits=(-19,2611),total=2592,length=lambda w,s=start,e=end:(s,e),members=groups['R'+str(seg)],record_id='schedules/sched-purlin'))
    def roof_z(x):
        seg=next((j for j in range(4) if x<=cuts[j+1]),3);q,u,_=roofplanes[seg];return q[2]+(x-q[0])*u[2]/u[0]
    for label in ('W0','W1','E0','E1'):
        side=int(label[1]);ew=label[0]=='E';out=-1 if side==0 else 1;n=[0,out,0] if ew else [out,0,0];u=[0,0,1];v=cross(n,u);axes=(u,v,n);total=1032 if ew else 2592;along=0 if ew else 1;origin=[0,2592*side,0] if ew else [1032*side,0,0]
        if v[along]<0:origin[along]=total
        ms=groups[label];h=max(top_flange(b,m,origin,axes)[3] for m in ms);origin=add(origin,mul(n,h));ranges=[]
        if ew:
            door=sorted((v[0]*(x-origin[0]) for x in (54,96)));bounds=sorted({-17,1049,*door,*[v[0]*(x-origin[0]) for x in cuts[1:-1]]})
            ranges=[(lo,hi,84 if door[0]<=.5*(lo+hi)<=door[1] else .25) for lo,hi in zip(bounds,bounds[1:])]
        elif side==0:
            last=-19
            for bay in sorted(DOORS):
                lo=bay*144+9.6;hi=(bay+1)*144-9.6;ranges.extend(((last,lo,.25),(lo,hi,168)));last=hi
            ranges.append((last,2611,.25))
        else:ranges=[(-19,2611,.25)]
        for j,(lo,hi,bottom) in enumerate(ranges):
            def length(w,oo=origin[:],vv=v[:],low=bottom):return low,roof_z(oo[0]+vv[0]*w)-.25
            surfaces.append(dict(id=label+'-'+str(j),roof=False,origin=origin[:],axes=axes,limits=(lo,hi),total=total,length=length,members=ms,record_id='schedules/sched-endwall' if ew else 'schedules/sched-girt'))
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS17-PANEL26',basis='S',specification='Source26ga0.018in Fy50ksi steel panel,1.25in ribs at12in;R11glass-fiber3.5in blanket compressed under panels;No12C1513/1/2in bonded washers. No thermal spacer blocks, standoff screws or diaphragm assumption. Manufacturer pressure/restraint verification required.')]
    b.panels[:]=[p for p in b.panels if p['kind']!='roof']
    for s in surfaces:build_surface(b,s)
    b.physical_interfaces=getattr(b,'physical_interfaces',[])+[dict(id='CFS17-PANEL-SUPPLIER',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in b.members if 'cladding_sheet' in m['kind']],panel_ids=[p['id'] for p in b.panels],responsible_party='Roof/wall supplier and project engineer',representation='Source gauge/ribs/screws and actual support groups shown. Blanket is nonstructural and compressed at supports; no thermal spacer blocks. A exact ribs,sidelaps,minor nesting packs,edge cuts and overhangs need source panel pressure/restraint verification. Ridge/valley flashings,weather closures,gutters and nonstructural insulation/liner are supplier interfaces; panels are not a diaphragm.',detail_ref=dict(id='gold/cfs17/cladding',revision=fingerprint(b.raw['cc_wind_pressures'])),requirements=dict(wind_basis=b.raw['cc_wind_basis'],zone_pressures=b.raw['cc_wind_pressures'],restraint_conditions=b.raw['purlin_girt_I621_conditions']))]
    b.physical_interfaces.append(dict(id='CFS17-DOORS-FOUNDATIONS',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in b.members if m['kind'] in ('opening_jamb','opening_header','column','prop')],responsible_party='Door supplier and foundation engineer',representation='Five accepted10.4x14ft vehicle doors and two A42x84in personnel doors. Source door product/guide attachments,C&C17.5psf certification and foundation concrete/anchor checks remain delegated; no invented product or reinforcement capacity.',detail_ref=dict(id='gold/cfs17/endwall-foundations',revision=fingerprint(b.raw['anchorage'])),requirements=dict(endwall=b.records['schedules/sched-endwall']['data'],foundation_forces=b.raw['anchorage'])))
    b.note('GAR-CLADDING','S:26ga0.018in Fy50ksi through-fastened panels,1.25in ribs/12in pitch,No12C1513 at12in with1/2in bonded washers,R11glass-fiber3.5in blanket compressed under panel,no thermal spacers/standoff screws or diaphragm action. A36in cover,rib flat/joggle,24in sidelaps,physical cuts and minor solid nesting packs. Roof straps lie below purlins; source panel screw grip is not lifted to clear straps. Source pressure/restraint tests,edge closures/overhangs,weather and insulation/liner installation,door guides and foundations remain explicit supplier/engineer verification.')


def build_surface(b,s):
    u,v,n=s['axes'];origin=s['origin'];lo,hi=s['limits'];rid=s['record_id'];total=s['total']
    world=lambda x,w,h=0:add(origin,add(mul(u,x),add(mul(v,w),mul(n,h))))
    edges=[lo]+[36*i for i in range(math.floor(lo/36)+1,math.ceil(hi/36)) if max(0,lo)<36*i<min(total,hi)]+[hi]
    sheets=[];attached=defaultdict(list);rows=defaultdict(list)
    for m in s['members']:
        tag=m['id'].split('-');row=tag[2] if tag[:2]==['GAR','P'] else tag[3] if tag[:2]==['GAR','G'] else '216' if tag[:2]==['GAR','STRUT'] else tag[-1]
        rows[row].append(m)
    for i,(aa,dd) in enumerate(zip(edges,edges[1:])):
        start=max(s['length'](w)[0] for w in (aa,dd));end=min(s['length'](w)[1] for w in (aa,dd))
        pid=profile(b,'A-CFS17-SHEET-'+s['id']+'-'+str(i),aa,dd,i==0)
        m=b.member('GAR-SKIN-'+s['id']+'-'+str(i),pid,'roof_cladding_sheet' if s['roof'] else 'wall_cladding_sheet',world(start,(aa+dd)/2),world(end,(aa+dd)/2),1,'A',records=[rid],local_y=v,host_panel_id='GAR-SKIN-'+s['id'],adopted_width_limits=[aa,dd],sheet_thickness_in=T,source_rib_depth_in=1.25,source_rib_pitch_in=12,physical_fit_basis='Source gauge, ribs and screws. A exact folded shape,36in cover/joggle and conservative rectangular cuts; source pressure tests and restraint stiffness remain delegated.')
        m['material_id']='CFS17-PANEL26';sheets.append(m)
    vertices=[world(s['length'](lo)[0],lo),world(s['length'](hi)[0],hi),world(s['length'](hi)[1],hi)]
    vertices.append(world(s['length'](lo)[1],lo))
    b.panel('GAR-SKIN-'+s['id'],'roof' if s['roof'] else 'cladding_envelope',vertices,1.25,1,'A',records=[rid],material_id='CFS17-PANEL26',physical_constituent_member_ids=[m['id'] for m in sheets],representation='Coordination envelope; individual folded0.018in sheets represent steel. Weather closures and local edge support remain supplier scope.',thickness_direction='normal')
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
                if gap<-1e-6:raise ValueError('CFS17 skin intersects actual support '+mid)
                groups[mid,round(max(0,gap),8)].append(world(gauge,w,T))
            for gi,((mid,gap),qs) in enumerate(groups.items()):
                centre=sub(mul([sum(q[k] for q in qs) for k in range(3)],1/len(qs)),mul(n,T));host=next(m for m in ms if m['id']==mid)
                c=b.connection(f'GAR-SKIN-{s["id"]}-{row}-{si}-{gi}','review_garage_cladding',centre,[host,sheet],[rid],parameters=dict(actual_cladding=True,axes=s['axes'],purpose='support',pitch=12,roof=s['roof'],gap=gap,flange_t=top_flange(b,host,origin,s['axes'])[3]-top_flange(b,host,origin,s['axes'])[2],points=[point(q,centre,s['axes']) for q in qs]))
                attached[sheet['id']].append(c)
    for i,(left,right) in enumerate(zip(sheets,sheets[1:]),1):
        w=right['adopted_width_limits'][0];start=max(point(axis(m)[0],origin,s['axes'])[0] for m in (left,right));end=min(point(axis(m)[1],origin,s['axes'])[0] for m in (left,right))
        values=[start+6+24*j for j in range(math.ceil((end-start)/24)) if start+6+24*j<end-.5]
        for batch in range(0,len(values),4):
            xs=values[batch:batch+4];mean=sum(xs)/len(xs);centre=world(mean,w)
            c=b.connection(f'GAR-SKIN-{s["id"]}-SEAM-{i}-{batch//4}','review_garage_cladding',centre,[left,right],[rid],parameters=dict(actual_cladding=True,axes=s['axes'],purpose='sidelap',pitch=24,roof=s['roof'],gap=0,flange_t=T,points=[[x-mean,0,2*T] for x in xs]))
            attached[left['id']].append(c);attached[right['id']].append(c)
    for m in sheets:
        if not attached[m['id']]:raise ValueError('CFS17 unattached sheet '+m['id'])
        for i,end in enumerate(('start','end')):
            c=min(attached[m['id']],key=lambda c:math.dist(c['point'],axis(m)[i]));b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Nearest actual screw group on this finite sheet; panel overhang/edge closures are delegated, not an invented end support.'))



def draw(ctx):
    from .review_cfs25_cladding import draw as actual_sheet
    actual_sheet(ctx)
    ctx.a.title='GARAGE CLADDING / '+('ADOPTED SIDELAP' if ctx.params['purpose']=='sidelap' else 'SOURCE SUPPORT SCREWS')
    ctx.a.notes=['S26ga0.018in Fy50ksi panel,1.25in ribs/12in pitch;No12C1513 at12in supports with1/2in bonded washers. SourceR11/3.5in blanket compressed under panels,no thermal spacer blocks or standoff screws. A rib shape/joggle,exact cuts,nesting packs and24in sidelaps. Manufacturer source pressure/restraint verification and perimeter/weather/insulation installation remain delegated; no diaphragm action.']
