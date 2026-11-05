"""CFS18 saved floor-zone selections on actual members and bearing planes.

All missing fit, setting-out and retention details are adopted example inputs.
The saved capacity checks are retained, not reassigned to the altered geometry.
"""
import copy,math
from .pilots.model import add,sub,mul,dot,unit
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame,point,vector
from .review_cfs_source_bindings import attach
from .review_crossings import slot

RID='framing/mezz-floor-zone-L2'
SHEAR='framing/mezz-floor-zone-L2-shear'
JT=.1017
RT=.0713
WSP_TOP=118.5
WSP_BOTTOM=117.78125
BEARING=107.5
RIM_BOTTOM=WSP_BOTTOM-10.2051
JOIST_BOTTOM=WSP_BOTTOM-RT-10


def prepare(b):
    if b.key!='cfs18':return
    # Keep finish levels120/240. The source10.25in squash block plus3/4in
    # plate sets the lower collector bearing plane exactly107.5in.
    old=107.78125
    for m in b.members:
        if m['level']!=1 or not m['id'].startswith(('MEZZ-','BEARING-1-')):continue
        delta=(BEARING if m['id'].startswith('MEZZ-') else JOIST_BOTTOM)-old
        for q in m['axis']:
            if abs(q[2]-old)<.2:q[2]+=delta
        if m['kind']=='hold_down_rod':
            m['axis'][1][2]+=delta
    for c in b.connections:
        if c['member_ids'][0].startswith(('MEZZ-','BEARING-1-')) and abs(c['point'][2]-old)<.2:
            c['point'][2]+=(BEARING if c['member_ids'][0].startswith('MEZZ-') else JOIST_BOTTOM)-old
    for w in b.walls:
        if w['level']==1 and w['id'].startswith(('MEZZ-','BEARING-1-')):
            w['top_z_in']=BEARING if w['id'].startswith('MEZZ-') else JOIST_BOTTOM
    # An on-grid chord squash block occupies the original joist station.
    # Replace that joist with two <=16in spaced joists, retaining the section.
    # Edge joists move inside the six-inch wall-depth squash block footprint.
    original=[m for m in b.members if m['id'].startswith('WING-J-1-')]
    changes={1818:[1825.5],2378:[2374.5],2382:[],1930:[1926,1934],2154:[2150,2158]}
    removed=set();new=[]
    for m in original:
        x=m['axis'][0][0];stations=changes.get(x,[x]);removed.add(m['id'])
        for j,station in enumerate(stations):
            mm=copy.deepcopy(m);mm['id']=m['id'] if stations==[x] else m['id']+'-FIT'+str(j)
            mm['source_unsplit_axis']=copy.deepcopy(m['axis']);mm['source_workline_station_in']=x
            for q in mm['axis']:q[0]=station;q[2]-=RT
            span=int(m['id'].split('-')[-1]);sg=1 if span!=1 else -1
            mm['local_y']=[sg,0,0]
            for off in mm['end_offsets']:off[0]=sg*JT/2
            mm['end_offsets'][0][1]=(20.8+RT/2+.03125-24) if span==0 else -3.125
            mm['end_offsets'][1][1]=(579.2-RT/2-.03125-576) if span==2 else 3.125
            mm['basis']='A';mm['physical_fit_basis']='S1000S250-97, maximum16in spacing; A local paired stations clearing chord squash blocks, alternating touching-web laps6.25in long, rim end clearance and0.0713in vertical fit.'
            new.append(mm)
    b.members[:]=[m for m in b.members if m['id'] not in removed]+new
    b.connections[:]=[c for c in b.connections if not set(c['member_ids'])&removed]
    # Additional closely spaced bearing studs follow the shifted floor joists.
    # Existing perimeter corner studs remain on the rim; no stud is added in
    # the accepted access door. Interior rows are fully in line.
    for label in ('BEARING-1-0','BEARING-1-1','BEARING-2-0','BEARING-2-1','MEZZ-S1','MEZZ-N1','MEZZ-S2','MEZZ-N2'):
        studs=[m for m in b.members if m['id'].startswith(label+'-ST-')]
        if not studs:raise ValueError('Missing source mezzanine studs '+label)
        template=min(studs,key=lambda m:m['axis'][0][2])
        drop={m['id'] for m in studs if m['axis'][0][0] in changes and (label.startswith('BEARING') or m['axis'][0][0] not in (1818,2382))}
        b.members[:]=[m for m in b.members if m['id'] not in drop]
        b.connections[:]=[c for c in b.connections if not set(c['member_ids'])&drop]
        present={m['axis'][0][0] for m in b.members if m['id'].startswith(label+'-ST-')}
        for x in sorted({q for values in changes.values() for q in values}-present):
            m=copy.deepcopy(template);m['id']=label+'-ST-FIT'+str(x)
            for q in m['axis']:q[0]=x
            m['basis']='A';m['physical_fit_basis']='S stud section; A additional/shifted in-line station at the local floor joist clearance.'
            b.members.append(m);b.ends(m,'cfs_stud')
    b.note('MEZZ-FLOOR-FIT','S:10.25in chord squash blocks,3/4in bearing plates,1000T200-68 rim,1000S250-97 joists and9.62in600S162-43 stiffeners. A: lower collector bearing107.5in, catalog rim10.2051in with0.07615in steel packing, joists lowered0.0713in with matching top packing and0.0625in rim bearing pads. Joists use6.25in touching-web laps over interior walls. Local paired joists/studs clear the chord blocks and maximum16in spacing is retained; source calculations are not reverified for these fits.')


def make_connection(b,cid,purpose,origin,members,records=(RID,),**par):
    return b.connection(cid,'review_sbmf_floor',origin,members,records,parameters=dict(purpose=purpose,**par))


def link(b,m,c,end=None):
    for e in (('start','end') if end is None else (end,)):
        b.endpoint_links.append(dict(member_id=m['id'],end=e,connection_id=c['id'],basis='Actual source floor-zone member participates in this located bearing/retention assembly; no remote or fictitious receiver.'))


def crosses_box(ends,lower,upper):
    lo,hi=0.,1.
    for a,d,left,right in zip(*ends,lower,upper):
        delta=d-a
        if abs(delta)<1e-12:
            if a<left or a>right:return False
        else:
            u,v=sorted(((left-a)/delta,(right-a)/delta));lo=max(lo,u);hi=min(hi,v)
    return hi-lo>1e-8


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members};joists=[m for m in b.members if m['id'].startswith('WING-J-1-')]
    b.material_selections=getattr(b,'material_selections',[])+[
        dict(id='CFS18-FLOOR-WSP',basis='S',specification='23/32in wood structural panel; saved source diaphragm selection retained'),
        dict(id='CFS18-FLOOR-GYPSUM',basis='S',specification='1.5in gypsum underlayment; held back from steel wall bearing')]
    panel=next(p for p in b.panels if p['id']=='WING-FLOOR-1')
    panel.update(vertices=[[x,y,WSP_TOP] for x,y in ((1814.8,20.8),(2385.2,20.8),(2385.2,579.2),(1814.8,579.2))],
        thickness_in=23/32,material_id='CFS18-FLOOR-WSP',thickness_direction='negative_global_z',openings=[],
        datum_basis='S23/32in WSP below structural wall base118.5in; A3.2in extension to actual perimeter rim web')
    finish=b.panel('WING-FLOOR-GYPSUM','floor_finish',[[q[0],q[1],120] for q in panel['vertices']],1.5,1,'S',
        material_id='CFS18-FLOOR-GYPSUM',thickness_direction='negative_global_z',openings=[])
    def opening(host,label,x0,y0,x1,y1,penetrating=()):
        x0=max(x0,1814.8);x1=min(x1,2385.2);y0=max(y0,20.8);y1=min(y1,579.2)
        oid=host['id']+'-CLEAR-'+label
        o=dict(id=oid,kind='wall_bearing_holdback',plane='XY',host_id=host['id'],x_ft=x0/12,y_ft=y0/12,z_ft=host['vertices'][0][2]/12,width_ft=(x1-x0)/12,height_ft=(y1-y0)/12,
            basis='A located clearance for the actual steel bearing path',penetrating_member_ids=list(penetrating),penetration_basis='Actual source floor bearing pieces occupy this material cut-out; not an architectural opening.')
        b.openings.append(o);host['openings'].append(oid)
    for label,along,pos in (('S',0,24),('N',0,576),('W',1,1818),('E',1,2382),('I0',0,208),('I1',0,392)):
        opening(finish,label,1814.8 if along==0 else pos-3.35,pos-3.35 if along==0 else 20.8,2385.2 if along==0 else pos+3.35,pos+3.35 if along==0 else 579.2)
    rims={};pads={}
    for label,along,pos,sg in (('S',0,20.8,1),('N',0,579.2,-1),('W',1,1814.8,1),('E',1,2385.2,-1)):
        lo,hi=(1814.8,2385.2) if along==0 else (22.925,577.075)
        def pt(u,z,offset=0):return [u,pos+sg*offset,z] if along==0 else [pos+sg*offset,u,z]
        ly=[0,sg,0] if along==0 else [sg,0,0]
        rim=b.member('MEZZ-RIM-'+label,'1000T200-68','rim_track',pt(lo,(RIM_BOTTOM+WSP_BOTTOM)/2),pt(hi,(RIM_BOTTOM+WSP_BOTTOM)/2),1,'S',records=[RID],local_y=ly)
        rims[label]=rim
        pid=b.custom('A-RIM-BEARING-PACK','flat',dict(width=2,thickness=RIM_BOTTOM-BEARING),basis='A catalog rim fit packing')
        cuts=sorted(m['axis'][0][along] for m in b.members if m['kind']=='chord' and m['id'].startswith('MEZZ-'+label+'2-'))
        intervals=[];start=lo
        for cut in cuts:intervals.append((start,cut-1.8125));start=cut+1.8125
        intervals.append((start,hi));pads[label]=[]
        for i,(start,end) in enumerate(intervals):
            pad=b.member('MEZZ-RIM-PACK-'+label+'-'+str(i),pid,'bearing_packer',pt(start,(RIM_BOTTOM+BEARING)/2,1-RT/2),pt(end,(RIM_BOTTOM+BEARING)/2,1-RT/2),1,'A',records=[RID],local_y=ly)
            pads[label].append(pad)
        rim.update(physical_fit_basis='S1000T200-68; A rim web3.2in outside wall workline, actualcatalogdepth10.2051in; lower pack retained. Flanges interrupted at source chord blocks, web continuous.')
    # Actual9.62in stiffeners at every floor joist end. Stiffeners are inside
    # alternating joist cavities; the two lapped webs touch without overlap.
    for joist in joists:
        aa,dd=axis(joist);sg=joist['local_y'][0]
        for end,workpoint in enumerate(joist['axis']):
            y=workpoint[1];x=aa[0]+sg*(JT+.0451)/2
            bottom=JOIST_BOTTOM+JT
            block=b.member(joist['id']+'-STIFF'+str(end),'600S162-43','bearing_stiffener',[x,y,bottom],[x,y,bottom+9.62],1,'S',records=[RID],local_y=[sg,0,0])
            receiver=rims['S' if y==24 else 'N'] if y in (24,576) else lookup['BEARING-1-'+str(0 if y==208 else 1)+'TT']
            c=make_connection(b,block['id']+'-WEB','stiffener',[x,y,bottom+4.81],[block,joist,receiver],end=end,perimeter=y in (24,576))
            link(b,block,c);link(b,joist,c,'start' if end==0 else 'end')
        # A continuous shim puts the retained source joist top on WSP underside.
        pid=b.custom('A-JOIST-WSP-PACK','flat',dict(width=2.5-JT,thickness=RT),basis='A exact rim-flange fit packing')
        midx=aa[0]+sg*1.25
        pack=b.member(joist['id']+'-TOP-PACK',pid,'bearing_packer',[midx,aa[1],WSP_BOTTOM-RT/2],[midx,dd[1],WSP_BOTTOM-RT/2],1,'A',records=[RID],local_y=[sg,0,0])
        joist['wsp_packer_id']=pack['id']
        for end,q in enumerate(pack['axis']):
            q=list(q);q[1]+=2 if end==0 else -2
            c=make_connection(b,pack['id']+'-FIX'+str(end),'top_pack',q,[joist,pack])
            link(b,pack,c,'start' if end==0 else 'end')
    groups={}
    for m in joists:groups.setdefault(m['axis'][0][0],[]).append(m)
    for x,ms in groups.items():
        ms.sort(key=lambda m:m['axis'][0][1])
        for i,(left,right) in enumerate(zip(ms,ms[1:])):
            c=make_connection(b,f'MEZZ-JOIST-LAP-{x}-{i}','lap',[x,left['axis'][1][1],JOIST_BOTTOM+5],[left,right],lap_in=6.25)
            upper=lookup[f'BEARING-2-{i}BT'];lower=lookup[f'BEARING-1-{i}TT']
            now={m['id']:m for m in b.members}
            make_connection(b,f'MEZZ-INTERIOR-TRANSFER-{x}-{i}','interior_transfer',[x,left['axis'][1][1],WSP_TOP],
                [upper,left,right,now[left['wsp_packer_id']],now[right['wsp_packer_id']],lower],panel=panel['id'])
    # Source16 chord blocks and3/4x3.5x6 plates. The plate has an adopted
    # edge notch where the real continuous rod passes; no solid covers it.
    for chord in [m for m in b.members if m['kind']=='chord' and m['id'].startswith('MEZZ-') and m['level']==2]:
        label=chord['id'].split('-CH-')[0];side=label[5];along=0 if side in 'SN' else 1;normal=1-along
        q=chord['axis'][0];rim=rims[side];ly=chord['local_y'];x,y=q[:2]
        block=b.member(chord['id']+'-FLOOR-BLOCK','2X600S162-54','chord_squash_pack',[x,y,BEARING],[x,y,BEARING+10.25],1,'S',records=[RID],local_y=ly)
        pid=b.custom('MEZZ-BEARING-PL3/4X6','flat',dict(width=6,thickness=.75),basis='S A36 bearing plate dimensions')
        a0=add([x,y,118.125],mul(ly,-1.75));a1=add([x,y,118.125],mul(ly,1.75))
        plate=b.member(chord['id']+'-BEARING-PL',pid,'bearing_plate',a0,a1,1,'S',records=[RID],local_y=[0,1,0] if along==0 else [1,0,0])
        rod=lookup[chord['id']+'R'];rp=axis(rod)[0]
        slot(plate,rp,[0,1,0] if along==0 else [1,0,0],-.4375,.4375,.875,plate['id'],'A7/8in rod-clearance envelope, open at plate edge; retained plate source size, capacity not reverified')
        aa,bb=axis(rim);station=q[along]-aa[along]
        rim.setdefault('slots',[]).append(dict(start_in=station-1.8125,end_in=station+1.8125,width_in=2-RT/2,centre_in=1+RT/4,section_axis=0,connection_id=block['id'],basis='S rim flanges cut over3.5in block; A1/16in end clearance, full web retained',end_shape='rectangular design envelope'))
        lower=next(m for m in b.members if m['id'].startswith(label[:-1]+'1TT-COLLECTOR') and min(v[along] for v in axis(m))<=q[along]<=max(v[along] for v in axis(m)))
        upper=lookup[label+'BT']
        c=make_connection(b,block['id']+'-BEAR','squash',[x,y,113],[block,plate,lower,upper,chord,rod,rim])
        link(b,block,c);link(b,plate,c)
        opening(panel,block['id'],x-(1.8125 if along==0 else 3.0625),y-(3.0625 if along==0 else 1.8125),x+(1.8125 if along==0 else 3.0625),y+(3.0625 if along==0 else 1.8125),[plate['id'],rod['id']])
    for oid in finish['openings']:
        o=next(o for o in b.openings if o['id']==oid)
        lower=[o['x_ft']*12,o['y_ft']*12,118.5];upper=[(o['x_ft']+o['width_ft'])*12,(o['y_ft']+o['height_ft'])*12,120]
        for m in b.members:
            if m['level']==2 and m['kind'] in ('stud','chord','hold_down_rod','bottom_track','strap') and crosses_box(axis(m),lower,upper):
                o['penetrating_member_ids'].append(m['id'])
        if not o['penetrating_member_ids']:raise ValueError('Gypsum holdback has no actual wall steel '+oid)
        o['penetration_basis']='Only the named actual upper-wall studs, chords, bottom tracks, straps and rods whose finite worklines intersect this1.5in gypsum holdback. These walls bear on WSP below the finish. No architectural opening or unrelated framing is exempted.'
    # Source horizontal transfer groups. Located rims and actual collector
    # plies define every screw grip; the WSP-only layer defines the bolt grip.
    for side,rim in rims.items():
        along=0 if side in 'SN' else 1;normal=1-along;sg=1 if side in 'SW' else -1
        label='MEZZ-'+side;upper=lookup[label+'2BT'];lower=lookup[label+'1TT'];wall=next(w for w in b.walls if w['id']==label+'2')
        runs=[(r['start_in'],r['end_in']) for r in wall['runs']]
        pos=rim['axis'][0][normal];pad_connections={p['id']:[] for p in pads[side]};rim_connections=[]
        def world(u,v,z):return [u,pos+sg*v,z] if along==0 else [pos+sg*v,u,z]
        for j,(lo,hi) in enumerate(runs):
            c=make_connection(b,rim['id']+'-SHEAR'+str(j),'transfer',world((lo+hi)/2,1,WSP_TOP),[upper,rim],(SHEAR,),
                along=along,sg=sg,bolt_stations=[-48,-24,0,24,48],panel=panel['id'])
        # Eight stations x two rows =16 screws inside each120in panel.
        stations=[(lo+6+(108/7)*i,True) for lo,hi in runs for i in range(8)]
        ra,rb=axis(rim);lo,hi=sorted((ra[along],rb[along]))
        stations += [(lo+2+6*i,False) for i in range(math.floor((hi-lo-4)/6)+1) if not any(a-1<=lo+2+6*i<=d+1 for a,d in runs)]
        for j,(u,in_panel) in enumerate(stations):
            # Rim-flange interruptions contain the squash bearing path instead.
            if any(abs(u-v)<2 for a,d in runs for v in (a,d)):continue
            outer=next((m for m in b.members if m['id'].startswith(label+'1TT-COLLECTOR') and min(v[along] for v in axis(m))+.25<=u<=max(v[along] for v in axis(m))-.25),None)
            if outer is None:continue
            pad=next(p for p in pads[side] if min(v[along] for v in axis(p))<u<max(v[along] for v in axis(p)))
            c=make_connection(b,rim['id']+'-LOWER'+str(j),'lower',world(u,0,RIM_BOTTOM+RT),[rim,pad,outer,lower],(SHEAR,),along=along,sg=sg,two_rows=in_panel)
            pad_connections[pad['id']].append(c);rim_connections.append(c)
        for member,connections in [(rim,rim_connections)]+[(p,pad_connections[p['id']]) for p in pads[side]]:
            for end,fn in (('start',min),('end',max)):
                link(b,member,fn(connections,key=lambda c:c['point'][along]),end)
        attach(b,rim,RID,'Source1000T200-68 rim with actualcatalogdepth, retainedweb and cutflanges at source10.25in chord squash blocks; pack and outer-face set-out explicitly adopted.')
    # Replace the generic floor-stack detail at these same perimeter tracks.
    b.connections[:]=[c for c in b.connections if not(c['detail_ref']['id'] in ('review_cfs_floor','review_cfs_sill') and c['member_ids'][0].startswith(('MEZZ-','BEARING-')) and ((lookup.get(c['member_ids'][0],{}).get('level')==1 and c['member_ids'][0].endswith('TT')) or (lookup.get(c['member_ids'][0],{}).get('level')==2 and c['member_ids'][0].endswith('BT'))))]
    b.note('MEZZ-FLOOR-ZONE','S:1000T200-68 rim,9.62in600S162-43 stiffener at each source floor joist end with3No10 web screws,10.25in2x600S162-54 chord blocks and3/4x3.5x6inA36 bearing plates in WSP cut-outs. S five5/8inA325-N per10ft panel at24in through uppertrack/WSP/rim;16No12 in two rows perpanel to lower97miltrack andNo12 at6in elsewhere. A: actual rim position3.2in outsidewall, cornercuts, stiffener top packing, retention/lap screws, plywood/finish clearances, rod edge-notches, catalogrim packing and local source-to-fit differences. No new capacity verification.')


def draw(ctx):
    a,par=ctx.a,ctx.params;purpose=par['purpose']
    if purpose in ('transfer','lower'):
        along=par['along'];sg=par['sg'];axes=horizontal_frame([1,0,0] if along==0 else [0,1,0])
    elif purpose=='squash':axes=horizontal_frame(ctx.ms[0]['local_y'])
    else:axes=([1,0,0],[0,1,0],[0,0,1])
    parts=[extract(ctx,m,'M'+str(i),axes,64 if purpose=='transfer' else 18) for i,m in enumerate(ctx.ms)]
    if purpose=='stiffener':
        block,joist,receiver=ctx.ms;sg=joist['local_y'][0];bp,jp,rp=parts
        x=point(axis(block)[0],ctx.c['point'],axes)[0];st=.0451
        zs=[-4.81+1.5,0,4.81-1.5]
        a.fastener('STIFF-S',[[x+sg*st/2,0,z] for z in zs],[-sg,0,0],.19,st+JT,['M0','M1'],'S3No10 to joist web; A set-out, first screw more than d/8 from flanges',screw=True)
        top=jp['bounds'][2][1]-JT;bottom=bp['bounds'][2][1];xx=bp['bounds'][0][0];ww=bp['bounds'][0][1]-xx
        a.box('STIFF-TOP-PACK',[xx,-3,bottom],[ww,6,top-bottom],'A','A tight-bearing pack above source9.62in stiffener')
        a.interfaces += [dict(id='STIFF-BEAR',kind='compression_bearing',connects=['M0','M1','STIFF-TOP-PACK'],basis='A',description='Source stiffener retained; explicit packing fills remaining joist cavity')]
        if par['perimeter']:
            z=rp['bounds'][2][0]+RT;h=jp['bounds'][2][0]-z
            # A finite end bearing pad on the actual rim lower flange.
            yy=rp['bounds'][1][1]-1.5 if ctx.c['point'][1]<300 else rp['bounds'][1][0]+.25
            a.box('JOIST-END-PACK',[jp['bounds'][0][0],yy,z],[2.5,1.25,h],'A','A1/16in rim bearing clearance filled beneath source joist')
            a.interfaces.append(dict(id='RIM-BEAR',kind='compression_bearing',connects=['M1','JOIST-END-PACK','M2'],basis='A',description='Actual rim lower flange and joist bottom flange joined by the finite bearing pad'))
        a.front_axes=(1,2);a.front_depth_sign=-sg
        a.section_axis=2;a.section_at=0;a.dim([x,0,bp['bounds'][2][0]],[x,0,bp['bounds'][2][1]],'S stiffener length',basis='S')
    elif purpose=='top_pack':
        p0,p1=parts;z=p1['bounds'][2][1];x=sum(p1['bounds'][0])/2
        a.fastener('PACK-S',[[x,0,z]],[0,0,-1],.19,RT+JT,['M0','M1'],'A No10 pack retention at actual joist flange',basis='A',screw=True)
    elif purpose=='lap':
        a.fastener('LAP-S',[[JT,y,z] for y in (-1.5,1.5) for z in (-2,2)],[-1,0,0],.19,2*JT,['M0','M1'],'A fourNo10 lap retention; source lapped joist arrangement retained',basis='A',screw=True)
        a.dim([0,-3.125,0],[0,3.125,0],'A lap length',basis='A');a.section_axis=1;a.section_at=0
        a.front_axes=(1,2);a.front_depth_sign=-1
    elif purpose=='interior_transfer':
        ut=ctx.p[ctx.ms[0]['profile_id']]['dimensions']['t'];top=parts[0]['bounds'][2][0]+ut;t=23/32
        pp=a.box('WSP',[-3,-2,-t],[6,4,t],'S thickness; A context extent','Actual23/32in WSP beneath interior bearing wall',kind='wood_panel')
        pp.update(representation_role='context_only',source_panel_parameter='panel',drawing_style='outline',show_in_section=True)
        for i,j in ((1,3),(2,4)):
            x=sum(parts[j]['bounds'][0])/2
            a.fastener('WALL-S'+str(i),[[x,0,top]],[0,0,-1],.216,ut+t+RT+JT,['M0','WSP','M'+str(j),'M'+str(i)],'A No12 interior wall retention through actual WSP/pack into source joist flange',basis='A',screw=True)
        a.interfaces.append(dict(id='LOWER-BEAR',kind='compression_bearing',connects=['M1','M2','M5'],basis='S',description='Actual lapped joists bear on the lower interior wall track'))
        a.section_axis=1;a.section_at=0
    elif purpose=='squash':
        a.interfaces += [dict(id='LOWER-BEAR',kind='compression_bearing',connects=['M0','M2'],basis='S',description='Source squash block bears on actual lower collector web'),dict(id='UPPER-BEAR',kind='compression_bearing',connects=['M0','M1','M3','M4'],basis='S',description='Source plate carries upper wall compression through actual block; WSP cut out')]
        # Two real formed retention clips sit inside the block flanges and
        # return onto the collector web. They do not replace compression
        # bearing or acquire the saved chord/collector strength.
        t=.0566;z=BEARING-113
        for side in (-1,1):
            face=side*(3-t);foot='RETAIN-FOOT'+str(side);leg='RETAIN-LEG'+str(side)
            a.box(foot,[-1.375,1.4434 if side>0 else -2.9434,z],[2.75,1.5,t],'A','A54mil formed block retention foot on actual collector web')
            a.box(leg,[-1.375,face-t if side>0 else face,z+t],[2.75,t,2-t],'A','A retention return against actual inside squash-block flange')
            a.fastener('RETAIN-BLOCK'+str(side),[[x,face-side*t,z+1] for x in (-.9,.9)],[0,side,0],.19,2*t,[leg,'M0'],'A twoNo10 retention screws to actual block flanges',basis='A',screw=True)
            a.fastener('RETAIN-TRACK'+str(side),[[x,side*2.2,z+t] for x in (-.9,.9)],[0,0,-1],.19,2*t,[foot,'M2'],'A twoNo10 retention screws to actual collector web',basis='A',screw=True)
            a.weld('RETAIN-FOLD'+str(side),[-1.375,face,z+t],[1.375,face,z+t],[foot,leg],kind='BEND',basis='A',description='A continuous formed retention clip, not a site weld')
        a.dim([0,0,BEARING-113],[0,0,BEARING+10.25-113],'S squash length',basis='S');a.section_axis=2;a.section_at=0
        a.front_depth_sign=1 if sum(parts[6]['bounds'][1])>0 else -1
        parts[6]['drawing_style']='outline_iso'
        a.notes.append('S3/4x3.5x6inA36 plate and10.25in source block. A7/8in rod edge-notch,1/16in WSP clearance and two54mil retention clips/fourNo10 each. Rim flanges are cut clear; rim web remains continuous. Retention is not a verified uplift or shear transfer design.')
    elif purpose=='transfer':
        upper,rim=parts;ut=ctx.p[ctx.ms[0]['profile_id']]['dimensions']['t'];top=upper['bounds'][2][0]+ut
        host=next(p for p in ctx.model['panels'] if p['id']==par['panel']);t=host['thickness_in']
        pp=a.box('WSP',[-57,-.75,-t],[114,1.5,t],'S thickness; A context extent','Source23/32in WSP transfer layer',kind='wood_panel');pp.update(representation_role='context_only',source_panel_parameter='panel',drawing_style='outline',show_in_section=True)
        a.fastener('TRANSFER-B',[[u,0,top] for u in par['bolt_stations']],[0,0,-1],.625,ut+t+RT,['M0','WSP','M1'],'S five5/8inA325-N at24in; A actual rim-flange gauge')
        a.dim([-48,0,top],[-24,0,top],'S transfer bolt pitch',basis='S');a.section_axis=0;a.section_at=0
        a.front_axes=(0,1);a.front_depth_sign=-1
    elif purpose=='lower':
        # horizontal_frame Y points left of the wall; map inward correctly.
        into=sg*(1 if along==0 else -1);z=parts[0]['bounds'][2][0]+RT
        lt=ctx.p[ctx.ms[3]['profile_id']]['dimensions']['t']
        grip=z-(parts[3]['member']['axis'][0][2]-lt/2)
        ys=[1,1.5] if par['two_rows'] else [1]
        a.fastener('RIM-S',[[0,into*y,z] for y in ys],[0,0,-1],.216,grip,['M0','M1','M2','M3'],'S No12 to source97mil lower track through real packing and54mil collector; A row gauge',screw=True)
        a.section_axis=0;a.section_at=0
        a.front_axes=(0,1);a.front_depth_sign=-1
        if len(ys)>1:a.dim([0,into,z],[0,into*1.5,z],'A row gauge',basis='A')
        a.notes.append('S sixteenNo12 per120in strap panel: eight stations, two rows. A stations6in from ends with108/7in pitch; detail shows one station. Outside panels source maximum6in field schedule, with physical cut-outs at squash blocks.')
    else:raise ValueError('Unknown mezzanine floor detail '+purpose)
    a.notes.append('Source sizes and selected fastening are retained. All packing, local fit, added retention and altered setting-out are A proposals; saved capacities are not recertified for them.')
