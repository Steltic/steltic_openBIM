"""CFS18 folded roof-deck runs and located support/sidelap screws.

The source deck designation and fastening schedule are retained. Rib bends,
joggle fit and continuous run procurement are explicit adopted geometry.
"""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,unit
from .review_receiver_geometry import extract

RID='diaphragms/diaphragm-roof-deck'
T=.0295
GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def folded_profile(b,label,points,thickness):
    components=[]
    for i,(a,d) in enumerate(zip(points,points[1:])):
        delta=sub(d,a);length=math.hypot(*delta)
        if length<1e-8:continue
        pid=b.custom(label+'-STRIP'+str(i),'flat',dict(width=length,thickness=thickness),basis='A geometric strip of one continuous folded sheet')
        components.append(dict(profile_id=pid,rotation_deg=math.degrees(math.atan2(delta[1],delta[0])),offset=[(a[j]+d[j])/2 for j in range(2)]))
    return b.custom(label,'built_up',{},components=components,basis='A one folded sheet represented by joined geometric strips, not separate plates',fabrication_form='single folded sheet; bend radii and procurement verification delegated')


def section(b,label,lo,hi,total):
    left=max(0,lo-.375);right=min(total,hi+.375);mid=(lo+hi)/2
    def height(w):
        if lo>0 and w<lo+.75:
            return 1.5*T if w<=lo+.375 else 1.5*T-(w-lo-.375)*T/.375
        q=w%6
        if q<=.75 or q>=5.25:return T/2
        if q<1.5:return T/2+(q-.75)/.75*(1.5-T)
        if q<=4.5:return 1.5-T/2
        return T/2+(5.25-q)/.75*(1.5-T)
    xs={left,right}
    for n in range(math.floor(left/6)-1,math.ceil(right/6)+1):
        xs.update(v for v in (n*6+.75,n*6+1.5,n*6+4.5,n*6+5.25) if left<v<right)
    if lo>0:xs.update(v for v in (lo+.375,lo+.75) if left<v<right)
    return folded_profile(b,label,[[v-mid,height(v)] for v in sorted(xs)],T)


def apply(b):
    if b.key!='cfs18':return
    source=b.records[RID]['data']['selection']
    if not all(v in source for v in ('22 ga','36/4','No. 10 sidelaps @ 12')):raise ValueError('CFS18 roof deck selection changed')
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS18-DECK22',basis='S designation; A sheet thickness and rib fit',specification='Source1.5in22ga wide-rib steel deck; A0.0295in sheet and geometric rib/joggle fit; manufacturer evaluation phiSn>=250plf remains required')]
    source_chords=[m for m in b.members if m['kind']=='truss_chord' and m['id'].startswith('ROOF-') and '-T' in m['id']]
    roof=[];support_by_member=defaultdict(list)
    for side,panel in enumerate([p for p in b.panels if p['id'].startswith('MAIN-ROOF-')]):
        slope=(1 if side==0 else -1)/24;u=unit([0,1,slope]);normal=[0,-u[2],u[1]];ya=side*300;length=300/u[1]
        intercept=324 if side==0 else 336.5;origin=[0,ya,intercept+3*math.sqrt(1+slope*slope)]
        def world(x,w,h=0):return add(add(origin,[x,u[1]*w,u[2]*w]),mul(normal,h))
        panel.update(vertices=[world(x,w) for x,w in ((0,0),(2400,0),(2400,length),(0,length))],thickness_in=1.5*math.sqrt(1+slope*slope),
            thickness_direction='positive_global_z',material_id='CFS18-DECK22',design_record_ids=[RID],
            reference_line='Actual valley underside / source truss-top bearing plane',source_depth_normal_in=1.5,
            representation='Coordination boundary for explicit folded deck-run members; not a solid steel slab',
            accepted_rib_fit=dict(pitch_in=6,depth_in=1.5,sheet_thickness_in=T,cover_width_in=36,overlap_width_in=.75,
                basis='A rib flats/slopes,0.75in joggled valley sidelap and continuous200ft site-formed run procurement; source22ga/1.5in retained, manufacturer shape/capacity approval unverified'))
        sheets=[]
        for i in range(math.ceil(length/36)):
            lo=i*36;hi=min(length,lo+36);pid=section(b,f'A-DECK22-S{side}-W{i}',lo,hi,length)
            sheet=b.member(f'MAIN-DECK-{side}-{i}',pid,'roof_deck_sheet',world(0,(lo+hi)/2),world(2400,(lo+hi)/2),3,'A',records=[RID],local_y=u,
                host_panel_id=panel['id'],source_cover_width_in=36,source_deck_depth_in=1.5,
                physical_fit_basis='One adopted continuous site-formed deck run; geometric profile strips are folds, not assembled independent plates. End-lap-free200ft procurement, rib and joggle shape require manufacturer verification.')
            sheet['material_id']='CFS18-DECK22';sheets.append(sheet)
        panel['physical_constituent_member_ids']=[m['id'] for m in sheets]
        roof.append(dict(panel=panel,sheets=sheets,u=u,normal=normal,origin=origin,length=length))
        frames=defaultdict(list)
        for chord in source_chords:
            a,d=chord['axis']
            if ya-.01<=a[1] and d[1]<=ya+300+.01:frames[round(a[0],6)].append(chord)
        for x,chords in sorted(frames.items()):
            groups=defaultdict(list)
            values=[12*j for j in range(math.floor(length/12)+1)]
            # Keep screws inside the finite edge sheet and clear of the
            # truss-face offset at the ridge. Both stations remain in a valley.
            values[0]=.5;values[-1]=length-.5
            for j,w in enumerate(values):
                q=world(x,w);candidates=[]
                for chord in chords:
                    a,d=[add(q,o) for q,o in zip(chord['axis'],chord['end_offsets'])];v=unit(sub(d,a));station=dot(sub(q,a),v)
                    if -.00001<=station<=math.dist(a,d)+.00001:candidates.append(chord)
                if len(candidates)!=1:raise ValueError('Deck support screw has no unique finite truss chord')
                chord=candidates[0];seam=w>0 and abs(w/36-round(w/36))<1e-7
                index=min(len(sheets)-1,int(w//36));joined=[sheets[index-1],sheets[index]] if seam else [sheets[index]]
                hand=1 if x<1 else -1 if x>2399 else (1 if j%2==0 else -1)
                points=world(x+hand*.85,w,T*len(joined))
                groups[chord['id']].append((points,joined))
            for chord_id,rows in groups.items():
                chord=next(c for c in chords if c['id']==chord_id);attached=[chord]+list({s['id']:s for _,ss in rows for s in ss}.values())
                centre=[sum(q[i] for q,_ in rows)/len(rows) for i in range(3)];parts={m['id']:i for i,m in enumerate(attached)}
                cp=b.profiles[chord['profile_id']];ct=b.profiles[cp['components'][0]['profile_id']]['dimensions']['t']
                groups_data=[dict(point_relative=sub(q,centre),axis=mul(normal,-1),diameter=.216,grip=T*len(ss)+ct,
                    receivers=[0]+[parts[s['id']] for s in ss],basis='S',description='S No12 support fixing in36/4 sheet pattern; A actual flange gauge and rib fit') for q,ss in rows]
                c=b.connection(chord_id+'-DECK','review_sbmf_deck',centre,attached,[RID],parameters=dict(purpose='support',fasteners=groups_data))
                for _,ss in rows:
                    for sheet in ss:support_by_member[sheet['id']].append(c)
        for seam,(left,right) in enumerate(zip(sheets,sheets[1:]),1):
            for start in range(0,200,6):
                xs=[6+12*j for j in range(start,min(start+6,200))];centre=world(sum(xs)/len(xs),seam*36)
                fasteners=[dict(point_relative=sub(world(x,seam*36,2*T),centre),axis=mul(normal,-1),diameter=.19,grip=2*T,
                    receivers=[0,1],basis='S',description='S No10 sidelap screw at12in; A physical joggled valley overlap') for x in xs]
                b.connection(f'DECK-SIDELAP-{side}-{seam}-{start//6}','review_sbmf_deck',centre,[left,right],[RID],parameters=dict(purpose='sidelap',fasteners=fasteners))
    # A folded ridge strip closes the small normal-offset gap between slopes.
    cap_t=.0566;u=roof[0]['u'];apex=roof[0]['origin'][2]+u[2]*roof[0]['length']+(T+cap_t/2)/u[1]
    cap_pid=folded_profile(b,'A-DECK-RIDGE54',[[-.75*u[1],-.75*u[2]],[0,0],[.75*u[1],-.75*u[2]]],cap_t)
    cap=b.member('MAIN-DECK-RIDGE',cap_pid,'roof_deck_closure',[0,300,apex],[2400,300,apex],3,'A',records=[RID],local_y=[0,1,0])
    ridge_connections=[]
    for start in range(0,200,6):
        xs=[6+12*j for j in range(start,min(start+6,200))];centre=[sum(xs)/len(xs),300,apex];fasteners=[]
        for i,row in enumerate(roof):
            w=row['length']-.375 if i==0 else .375
            for x in xs:
                q=add(add(row['origin'],[x,row['u'][1]*w,row['u'][2]*w]),mul(row['normal'],T+cap_t))
                fasteners.append(dict(point_relative=sub(q,centre),axis=mul(row['normal'],-1),diameter=.19,grip=T+cap_t,
                    receivers=[0,i+1],basis='A',description='A No10 ridge-closure screw at12in each side; manufacturer/load-transfer verification required'))
        c=b.connection('DECK-RIDGE-'+str(start//6),'review_sbmf_deck',centre,[cap,roof[0]['sheets'][-1],roof[1]['sheets'][0]],[RID],parameters=dict(purpose='ridge',fasteners=fasteners),basis='A')
        ridge_connections.append(c)
    for sheet in [m for row in roof for m in row['sheets']]+[cap]:
        cons=ridge_connections if sheet is cap else support_by_member[sheet['id']]
        for end,fn in (('start',min),('end',max)):
            c=fn(cons,key=lambda c:c['point'][0])
            b.endpoint_links.append(dict(member_id=sheet['id'],end=end,connection_id=c['id'],basis='Actual deck-run end participates in the located truss support screw group; ridge closure ends use their first/last real screw group. No independent fictitious support.'))
    b.note('MAIN-ROOF-DECK','S:1.5in22ga wide-rib roof deck, No12 support screws36/4 on every actual truss and No10 sidelaps at12in; saved required manufacturer phiSn>=250plf retained. A:0.0295in sheet,6in rib pitch with stated flats/slopes and0.75in joggled valley laps, continuous200ft site-formed procurement, actual flange screw gauge, partial edge sheets,1/2in eave/ridge edge distances, and54mil folded ridge closure with No10 at12in each side. Boundary now lies on the actual sloped truss-top plane; explicit folded deck members carry the sheet geometry. Manufacturing, end-lap-free procurement and altered fit/capacity remain delegated verification, not certified by the saved calculations.')


def draw(ctx):
    a,par=ctx.a,ctx.params;fasteners=par['fasteners'];extent=max(math.sqrt(sum(v*v for v in f['point_relative'])) for f in fasteners)+2
    for i,m in enumerate(ctx.ms):
        part=extract(ctx,m,'M'+str(i),GLOBAL,extent)
        if m['kind'].startswith('roof_deck'):part['drawing_style']='outline_iso'
    for i,f in enumerate(fasteners):
        a.fastener('F'+str(i),[f['point_relative']],f['axis'],f['diameter'],f['grip'],['M'+str(j) for j in f['receivers']],f['description'],basis=f['basis'],screw=True)
    a.front_axes=(1,0);a.front_depth_sign=-1;a.section_axis=0;a.section_at=fasteners[0]['point_relative'][0]
    first=fasteners[0]['point_relative']
    if par['purpose']=='support':
        normal=mul(fasteners[0]['axis'],-1);along=[0,normal[2],-normal[1]]
        a.dim(first,add(first,mul(along,12)),'A fixing pitch within36/4 pattern',basis='A',offset=-65)
    elif len(fasteners)>1:
        a.dim(first,fasteners[1]['point_relative'],'S sidelap pitch' if par['purpose']=='sidelap' else 'A ridge pitch',basis='S' if par['purpose']=='sidelap' else 'A',offset=-65)
    a.notes.append('S source22ga/1.5in deck designation and No12 support / No10 sidelap schedule. A rib, joggle, gauge and continuous-run procurement. Each deck profile is one folded sheet; its geometric strips are not separate loose plates. Isometric deck outlines expose the fasteners; the section cuts the actual thin sheets.')
