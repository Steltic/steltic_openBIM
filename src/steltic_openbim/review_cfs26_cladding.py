"""Source24ga canopy R-panel and its actual finite purlin attachments."""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot
from .review_cfs26_purlins import AXES,U,V,N,STATIONS
from .review_cfs25_cladding import profile,top_flange
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point
from .drawing_workflow import fingerprint

RID='schedules/sched-panel-fastener';T=.0236


def apply(b):
    if b.key!='cfs26':return
    b.connections[:]=[c for c in b.connections if c['detail_ref']['id']!='review_skin_fastener']
    rows=defaultdict(list)
    for m in b.members:
        if m['kind']=='purlin':rows[int(m['id'].split('-')[2])].append(m)
    origin=add([0,0,168],mul(N,19.5));start=-48/U[0];end=408/U[0]
    def world(x,w,h=0):return add(add(add(origin,mul(U,x)),mul(V,w)),mul(N,h))
    edges=[-48+36*i for i in range(27)]+[912];sheets=[];attached=defaultdict(list)
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS26-PANEL24',basis='S material and minimum base thickness',specification='24ga ASTM A653 SSGr80,0.0236in minimum base metal,1.25in ribs at12in; source Fy80/Fu82 and ChapterJ Fu65 cap retained')]
    for i,(lo,hi) in enumerate(zip(edges,edges[1:])):
        pid=profile(b,'A-CFS26-SKIN-'+str(i),lo,hi,i==0,thickness=T)
        m=b.member('CANOPY-SHEET-'+str(i),pid,'roof_cladding_sheet',world(start,(lo+hi)/2),world(end,(lo+hi)/2),1,'A',records=[RID],local_y=V,
            material_selection='CFS26-PANEL24',source_rib_pitch_in=12,source_rib_depth_in=1.25,sheet_thickness_in=T,adopted_width_limits=[lo,hi],host_panel_id='CANOPY-ROOF',
            physical_fit_basis='S24ga minimum thickness and R-panel ribs; A rib flats/slopes,36in cover, joggled valleys and exact edges; source manufacturer tests remain required')
        m['material_id']='CFS26-PANEL24';sheets.append(m)
    b.panels[:]=[p for p in b.panels if p['kind']!='roof']
    b.panel('CANOPY-ROOF','roof',[world(start,-48),world(start,912),world(end,912),world(end,-48)],1.25,1,'A',records=[RID],
        material_id='CFS26-PANEL24',physical_constituent_member_ids=[m['id'] for m in sheets],thickness_direction='positive_global_z',
        representation='Coordination envelope only; explicit folded0.0236in sheets represent steel, not a solid1.25in slab. No roof diaphragm action or insulation.',
        accepted_rib_fit=dict(depth_in=1.25,pitch_in=12,sheet_thickness_in=T,source_option='24ga through-fastened R-panel, exposed underside'))
    for row,ms in sorted(rows.items()):
        x=STATIONS[row]
        for si,sheet in enumerate(sheets):
            lo,hi=sheet['adopted_width_limits'];groups=defaultdict(list)
            for j in range(160):
                w=-45+6*j
                if not lo<=w<hi:continue
                corner=min(x+48,408-x)<=45.6 and min(w+48,912-w)<45.6
                if not corner and j%2:continue
                matches=[m for m in ms if min(q[1] for q in axis(m))<=w<=max(q[1] for q in axis(m))]
                if len(matches)!=1:raise ValueError('No unique actual purlin at canopy sheet screw')
                host=matches[0];f=top_flange(b,host,origin,AXES);gauge=(f[0]+f[1])/2
                if abs(f[3])>1e-7:raise ValueError('Canopy sheet does not contact actual top flange')
                groups[host['id'],6 if corner else 12].append(world(gauge,w,T))
            for gi,((mid,pitch),qs) in enumerate(groups.items()):
                centre=mul([sum(q[k] for q in qs) for k in range(3)],1/len(qs));centre=sub(centre,mul(N,T));host=next(m for m in ms if m['id']==mid)
                c=b.connection(f'CANOPY-SKIN-{row}-{si}-{gi}','review_canopy_cladding',centre,[host,sheet],[RID],
                    parameters=dict(actual_canopy_cladding=True,axes=AXES,purpose='support',pitch=pitch,points=[point(q,centre,AXES) for q in qs]))
                attached[sheet['id']].append(c)
    for i,(left,right) in enumerate(zip(sheets,sheets[1:]),1):
        w=right['adopted_width_limits'][0];xs=[start+6+24*j for j in range(math.ceil((end-start)/24)) if start+6+24*j<end-.5]
        for batch in range(0,len(xs),4):
            values=xs[batch:batch+4];mean=sum(values)/len(values);centre=world(mean,w)
            c=b.connection(f'CANOPY-SKIN-SEAM-{i}-{batch//4}','review_canopy_cladding',centre,[left,right],[RID],parameters=dict(actual_canopy_cladding=True,axes=AXES,purpose='sidelap',pitch=24,points=[[x-mean,0,2*T] for x in values]))
            attached[left['id']].append(c);attached[right['id']].append(c)
    for m in sheets:
        for i,endname in enumerate(('start','end')):
            c=min(attached[m['id']],key=lambda c:math.dist(c['point'],m['axis'][i]))
            b.endpoint_links.append(dict(member_id=m['id'],end=endname,connection_id=c['id'],basis='Nearest actual screw group on this finite sheet; source edge overhang/manufacturer checks remain explicit.'))
    b.physical_interfaces=getattr(b,'physical_interfaces',[])+[dict(id='CFS26-ROOF-PANEL-SUPPLIER',kind='delegated_verification',scope='delegated',member_ids=[m['id'] for m in sheets],panel_ids=['CANOPY-ROOF'],
        responsible_party='Roof-panel supplier / project engineer',representation='Source24ga sheets and screws are physically represented; tested uplift/downward resistance and perimeter closures remain supplier verification.',
        detail_ref=dict(id='gold/cfs26/roof-panel-tests',revision=fingerprint(b.records[RID]['data'])),requirements=b.records[RID]['data'])]
    b.note('CANOPY-ROOF-SHEETS','S:24ga A653SSGr80 R-panel,0.0236in minimum base metal,1.25in ribs at12in, exposed underside, no insulation and no diaphragm action. No12 C1513 screws with1/2in bonded washers at6in corners /12in elsewhere; corner widtha=3.8ft. A: rib flats/slopes,36in cover, valley joggle, sidelapNo12@24in, exact support gauges, washer thickness and cut edges. Source manufacturer tests for both open-roof surfaces, panel edge overhangs and perimeter/weather closures remain required; no source capacity is extended to adopted geometry.')


def draw(ctx):
    a=ctx.a;par=ctx.params;seam=par['purpose']=='sidelap';qs=par['points'];extent=max(math.sqrt(dot(q,q)) for q in qs)+3
    for i,m in enumerate(ctx.ms):
        p=extract(ctx,m,'M'+str(i),AXES,extent)
        if m['kind']=='roof_cladding_sheet':p['drawing_style']='outline_iso'
    a.title='CANOPY ROOF / '+('ADOPTED SIDELAP' if seam else 'SOURCE PANEL SCREWS')
    grip=2*T if seam else T+.1242
    for i,q in enumerate(qs):
        label='WASHER'+str(i);a.cylinder(label,q,[0,0,1],.5,.0625,'S diameter / A thickness','1/2in bonded sealing washer',kind='washer')
        a.fastener('SCREW'+str(i),[add(q,[0,0,.0625])],[0,0,-1],.216,grip+.0625,['M0','M1',label],
            'A No12 sidelap screw at24in; supplier verification required' if seam else f'S No12 C1513 screw at{par["pitch"]}in through actual24ga panel and118mil purlin',basis='A' if seam else 'S',screw=True)
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=1;a.section_at=qs[0][1]
    if len(qs)>1:a.dim(qs[0],qs[1],'A24in sidelap pitch' if seam else 'S support screw pitch',basis='A' if seam else 'S',offset=-45)
    a.notes.append('S24ga A653SSGr80,0.0236in minimum,1.25in ribs at12in; exposed underside, no insulation and no diaphragm action. S No12 C1513 screws with1/2in bonded washers,6in corner /12in general support pitch. A exact rib/joggle, sidelap, edge and washer geometry. Manufacturer uplift/downward tests, cut-edge support and weather closures remain required.')
