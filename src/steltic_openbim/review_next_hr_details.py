"""Assembled transfer, crossing, composite and equipment interfaces."""
import math,re
from .review_assemblies import effective,flat,rod,grid,add,sub,mul,unit,dot,cross,NUMBER,number,hull

FAMILIES={'review_transfer_truss','review_transfer_slip','review_transfer_bearing','review_brace_crossing','review_column_cap','review_composite_studs','review_plan_angle','review_angle_crossing','review_equipment_foot','review_equipment_head','review_hr_gable_knee','review_hr_gable_ridge','review_rod_clevis','review_roof_step','review_diaphragm'}

def draw(ctx):
    f=ctx.family
    if f=='review_transfer_truss':transfer_truss(ctx)
    elif f=='review_brace_crossing':crossing(ctx)
    elif f=='review_column_cap':cap(ctx)
    elif f=='review_composite_studs':studs(ctx)
    elif f=='review_transfer_bearing':bearing(ctx)
    elif f=='review_transfer_slip':slip(ctx)
    elif f=='review_plan_angle':plan_angle(ctx)
    elif f=='review_angle_crossing':angle_crossing(ctx)
    elif f=='review_equipment_foot':equipment_foot(ctx)
    elif f=='review_equipment_head':equipment_head(ctx)
    elif f=='review_rod_clevis':clevis(ctx)
    elif f=='review_roof_step':roof_step(ctx)
    elif f=='review_diaphragm':diaphragm(ctx)
    else:gable(ctx)

def transfer_truss(ctx):
    a,p=ctx.a,ctx.p;point=ctx.c['point'];vertices=[];joins=[]
    for j,m in enumerate(ctx.ms):
        other=max(m['axis'],key=lambda q:math.dist(q,point));v=unit(sub(other,point));v=unit([v[0],0,v[2]]);length=118 if m['kind']!='column' else 100
        d=effective(p,m['profile_id']);w=effective(p,m['profile_id'],'width');start=mul(v,30);end=mul(v,length);name='M'+str(j)
        a.member(name,m['profile_id'],start,end,y=[0,1,0],basis='A',description='Source '+m['profile_id']+'; A node cutback/fit');joins.append((name,v,w))
        for q in (start,end):vertices.extend([[q[0]+sg*d*v[2]/2,q[2]-sg*d*v[0]/2] for sg in (-1,1)])
    poly=hull(vertices);width=max(w for _,_,w in joins);t=1.5
    for side in (-1,1):
        y=side*width/2-(t if side<0 else 0);name='G'+str(side);a.polygon(name,[[x,y,z] for x,z in poly],t,basis='A',description='S: 1.5 in double gusset; A fitted free-edge outline')
        for i,(member,v,w) in enumerate(joins):
            length=42 if ctx.ms[i]['kind']=='column' else 76 if ctx.ms[i]['kind']=='transfer_diagonal' else 71
            for edge in (-1,1):
                d=effective(p,ctx.ms[i]['profile_id']);off=[-v[2]*d*edge/2,side*width/2,v[0]*d*edge/2];start=add(mul(v,35),off)
                a.weld(f'W{i}{side}{edge}',start,add(start,mul(v,length)),[member,name],1,description=f'Source 1 in E70 fillet, {length:g} in; flange-tip interface')
    chord=next((v for (name,v,w),m in zip(joins,ctx.ms) if m['kind']=='transfer_chord'),joins[0][1]);ends=sorted([mul(chord,35),mul(chord,106)],key=lambda q:q[0]);a.dim(*ends,'Source chord weld',offset=-230);a.section_axis=2;a.section_at=50
    a.notes.append('S: transfer truss is not an SCBF brace. Double gussets at flange tips; chord 4 x 71 in, diagonal 4 x 76 in and support-column 4 x 42 in welds. A shared node outline and end cutbacks; source Whitmore widths and column stiffening remain required.')

def roof_step(ctx):
    from .review_hr_seats import step
    return step(ctx)


def diaphragm(ctx):
    a,p=ctx.a,ctx.p;transfer=ctx.params['transfer'];d=effective(p,ctx.pid);a.member('BEAM',ctx.pid,[0,0,-d/2],[216,0,-d/2]);a.box('SLAB',[0,-18,0],[216,36,6.25],'A','S 3 in deck + 3.25 in topping; A 36 in strip',kind='concrete')
    pitch=12 if transfer or ctx.params['direction']=='Y' else 36;count=18 if pitch==12 else 6;faces=[]
    for j in range(count):
        for y in (-1.5,1.5) if transfer else (0,):
            a.cylinder('TMP',[pitch/2+j*pitch,y,0],[0,0,1],.75,4.5);faces.extend(a.parts.pop()['faces']);a.cylinder('TMP',[pitch/2+j*pitch,y,4.5],[0,0,1],1.25,.375);faces.extend(a.parts.pop()['faces'])
    a.part('STUDS',f'S 3/4 in studs at {pitch:g} in'+(' in pairs' if transfer else f', {count} per 18 ft clear zone')+'; A height/head',faces,'A','headed_studs')
    rp=rod(p,.5 if transfer else math.sqrt(.16/math.pi));spacing=12 if transfer else 6
    for j,y in enumerate((-spacing/2,spacing/2)):a.member('BAR-X'+str(j),rp,[0,y,4.5],[216,y,4.5],basis='S',description='S #4 at 12 in each way, 24 in laps' if transfer else 'S WWR 6x6-W4.0xW4.0; A local cover')
    for j,x in enumerate((96,96+spacing)):a.member('BAR-Y'+str(j),rp,[x,-18,5],[x,18,5],y=[1,0,0],basis='S')
    if transfer:a.member('LAP',rp,[96,spacing/2+.5,4.5],[120,spacing/2+.5,4.5],description='S #4 24 in lap, A local position');a.dim([96,0,6],[120,0,6],'Source lap')
    for part in a.parts:
        if part['id'].startswith(('BAR-X','BAR-Y')) or part['id']=='LAP':
            part['representation_role']='assembly_component';part['material_category']='reinforcement'
            part['description']+='; '+('S #4 reinforcement' if transfer else 'S welded wire reinforcement WWR')
    if 'deck welded' in ctx.text.lower():
        a.box('DECK',[0,-18,0],[216,36,.0359],'A','A 20 ga flat reference strip for construction-stage metal deck fastening; source composite deck requirement retained')
        for j,x in enumerate(range(6,216,24)):
            a.weld('DECK-W'+str(j),[x-.375,0,0],[x+.375,0,0],['DECK','BEAM'],.25,basis='A',
                   description='A 3/4 in puddle-weld reference at 24 in; source construction-stage support attachment; deck supplier verification required')
        a.notes.append('A: construction-stage deck attachment proposal uses 3/4 in puddle-weld references at 24 in on the actual support. Flat sheet is a reference strip, not a fabricated flute profile; supplier deck fastening review remains explicit.')
    a.interfaces.append(dict(id='BOND',kind='diaphragm_transfer',connects=['BEAM','STUDS','SLAB','BAR-X0','BAR-Y0'],basis='S',description='Source headed-stud fusion / reinforced slab bond; deck construction attachment remains specified'))
    a.dim([pitch/2,0,0],[pitch/2+pitch,0,0],'Source stud pitch');a.section_axis=0;a.section_at=pitch/2
    a.notes.append('S: typical braced-frame stud zones remain clear of gussets. Transfer detail repeats pairs at 12 in on the truss TOP chord / Grid C; Grid A/E collectors use 38 studs over 30 ft. No studs connect the lower truss chord at Level 2. A: shown cover, stud height/head and local pattern origin.')

def crossing(ctx):
    if ctx.params.get('crossing'):
        from .review_crossings import draw
        return draw(ctx)
    a,p=ctx.a,ctx.p;pid=ctx.pid;d=effective(p,pid);t=ctx.n(r'slotted on two opposite walls for a '+NUMBER+r' in',.5);width=ctx.n(r'gusset '+NUMBER+r' in wide',40)
    angle=math.atan2(abs(ctx.ms[0]['axis'][1][2]-ctx.ms[0]['axis'][0][2]),math.dist(ctx.ms[0]['axis'][0][:2],ctx.ms[0]['axis'][1][:2]));v=[math.cos(angle),0,math.sin(angle)];u=[-v[0],0,v[2]]
    a.member('CONT',pid,mul(v,-30),mul(v,30),description='Source continuous X diagonal; local slot for crossing gusset')
    end_distance=ctx.n(r'each half ends '+NUMBER+r' in from the crossing',d+1)
    for side in (-1,1):a.member('SPLIT'+str(side),ctx.ms[1]['profile_id'],mul(u,side*end_distance),mul(u,side*38),description='Source split diagonal into crossing gusset')
    a.polygon('GUSSET',[[-width/2,-t/2,-width/2],[width/2,-t/2,-width/2],[width/2,-t/2,width/2],[-width/2,-t/2,width/2]],t,basis='A',description=f'S crossing gusset thickness {t:g}; source width {width:g} where scheduled / A square fit')
    length=ctx.n(r'welds? x '+NUMBER+r' in',6);size=ctx.n(r'four '+NUMBER+r' in E70',.25)
    for i,(name,direction) in enumerate([('CONT',v),('SPLIT-1',mul(u,-1)),('SPLIT1',u)]):
        for side in (-1,1):
            start=add(mul(direction,d+1),[0,side*d/2,0]);a.weld(f'W{i}{side}',start,add(start,mul(direction,length)),[name,'GUSSET'],size,description='Source slotted-HSS crossing welds; both walls, both slot edges')
    matches=list(re.finditer(r'2 PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',ctx.text))
    for i,match in enumerate(matches[:2]):
        rt,rw,rl=map(number,match.groups());direction=v if i==0 else u
        for half in ((0,) if i==0 else (-1,1)):
            mid=mul(direction,0 if half==0 else half*(end_distance+length/2))
            for side in (-1,1):
                normal=[-direction[2]*side,0,direction[0]*side];origin=add(add(mid,mul(direction,-rl/2)),mul(normal,d/2));name=f'R{i}{half}{side}'
                a.box(name,add(origin,[0,-rw/2,0]),[rl,rw,rt],'S','Source slot reinforcement; A edge fit',x=direction,y=[0,1,0]);host='CONT' if i==0 else 'SPLIT'+str(half)
                a.weld('W'+name,origin,add(origin,mul(direction,rl)),[host,name],.1875,description='Source paired longitudinal fillets; source reduced-section/end lengths retained in specification')
    a.dim([-width/2,0,-width/2],[width/2,0,-width/2],'Crossing plate width',basis='S' if 'in wide' in ctx.text else 'A');a.section_axis=0;a.section_at=0
    a.notes.append('The gusset passes through a slot in the continuous diagonal; the second diagonal is interrupted at the plate. Slot clearances and free-edge perimeter are A. Hidden slot faces are diagrammatic; this is not a shop solid.')

def cap(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);w=effective(p,pid,'width');t=.75;match=re.search(r'PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in (?:closure|cap)',ctx.text)
    if match:t,bx,by=map(number,match.groups())
    else:bx,by=d+2,w+2
    a.member('COLUMN',pid,[0,0,-30],[0,0,0]);cap_pid=flat(p,bx,t);a.member('CAP',cap_pid,[0,-by/2,t/2],[0,by/2,t/2],y=[-1,0,0],basis='S' if match else 'A',representation_role='assembly_component',description='Column closure / cap plate');a.weld('WC',[-d/2,-w/2,0],[d/2,-w/2,0],['COLUMN','CAP'],.25 if ctx.params.get('bearing_girder') else .3125,description='Source continuous cap perimeter weld')
    if ctx.params.get('bearing_girder'):
        bp=ctx.ms[1]['profile_id'];bd=effective(p,bp);bt=p[bp]['dimensions']['tf'];a.member('GIRDER',bp,[-24,0,t+bd/2],[24,0,t+bd/2]);a.fastener('BG',[[0,y,t+bt] for y in (-2,2)],[0,0,-1],.75,bt+t,['GIRDER','CAP'],'S two 3/4 in A325 bearing bolts; A gauge');a.interfaces.append(dict(id='BEARING',kind='bearing',connects=['GIRDER','CAP'],basis='S',description='Source girder flange bearing on cap'))
    if ctx.params.get('stiffened'):
        tf=p[pid]['dimensions'].get('tf',.5);tw=p[pid]['dimensions'].get('tw',.3)
        for j,sg in enumerate((-1,1)):
            y=tw/2 if sg>0 else -w/2;a.box('ST'+str(j),[-d/2+tf,y,-8],[d-2*tf,w/2-tw/2,.375],'S','Source top-tier transverse stiffener')
            a.weld('WS'+str(j),[-d/2+tf,y,-8],[d/2-tf,y,-8],['COLUMN','ST'+str(j)],.3125,description='Source stiffener weld to web and both flanges')
    a.dim([-bx/2,0,t],[bx/2,0,t],basis='S');a.section_axis=2;a.section_at=-7.9

def studs(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;length=par['length_in'];n=par['count'];d=effective(p,pid);w=effective(p,pid,'width')
    a.member('BEAM',pid,[0,0,-d/2],[length,0,-d/2]);a.box('SLAB',[0,-12,0],[length,24,6.25],'A','Source slab build-up / A 24 in detail strip',kind='concrete')
    if n==80:points=[[6+12*j,y,0] for j in range(40) for y in (-1.5,1.5)]
    else:
        end=(n-5)//2;xs=[2.5+5*j for j in range(end)]+[length-2.5-5*j for j in range(end)]+[length/3+12+24*j for j in range(5)];points=[[x,0,0] for x in sorted(xs)]
    shafts=[];heads=[]
    for j,point in enumerate(points):
        a.cylinder('TEMP',point,[0,0,1],.75,4.5);shafts.extend(a.parts.pop()['faces'])
        a.cylinder('TEMP',add(point,[0,0,4.5]),[0,0,1],1.25,.375);heads.extend(a.parts.pop()['faces'])
    a.part('STUDS',f'S {n} x 3/4 in headed studs, source zones/count; A 4.5 in height',shafts,'A','headed_studs',count=n,diameter=.75,points=points)
    a.part('HEADS','A 1.25 x 0.375 in head envelopes; no nuts',heads,'A','headed_studs',count=n)
    a.interfaces.append(dict(id='FUSION',kind='headed_stud_weld',connects=['BEAM','STUDS'],basis='S',description='Source headed-stud fusion to beam through deck; automatic process; no bolt nuts'))
    a.interfaces.append(dict(id='EMBED',kind='headed_stud_embedment',connects=['STUDS','HEADS','SLAB'],basis='A',description='A head and embedment fit in the source slab; supplier geometry'))
    a.dim([0,0,-d],[length,0,-d],f'S workline length; camber {par["camber_in"]:g} in');a.section_axis=0;a.section_at=points[0][0]
    a.notes.append('S: W21X55 two studs per 12 in rib, 80 total; W24X62 22 each end third plus 5 middle; W21X68 24 each end zone plus 5 middle. The longitudinal origin and stud height are A. Camber is a scheduled source value, not scaled in this straight workline view.')

def bearing(ctx):
    a,p=ctx.a,ctx.p;cp=ctx.pid;bp=ctx.ms[1]['profile_id'];bd=effective(p,bp);bw=effective(p,bp,'width');cd=effective(p,cp);cw=effective(p,cp,'width');tw=p[bp]['dimensions']['tw'];tf=p[bp]['dimensions']['tf']
    a.member('GIRDER',bp,[-42,0,-bd/2],[42,0,-bd/2]);a.box('BEARING',[-cd/2-2,-cw/2-2,0],[cd+4,cw+4,1.5],'A','A column bearing plate');a.member('COLUMN',cp,[0,0,1.5],[0,0,40]);a.weld('WC',[-cd/2,-cw/2,1.5],[cd/2,-cw/2,1.5],['COLUMN','BEARING'],.5,basis='A',description='A continuous column bearing-plate fillet')
    for j,x in enumerate((-cd/2,cd/2)):
        for k,sg in enumerate((-1,1)):
            y=tw/2 if sg>0 else -bw/2+.25;name=f'S{j}{k}';a.box(name,[x-.75,y,-bd+tf],[1.5,bw/2-tw/2-.25,bd-2*tf],'A','Source-required bearing stiffener; A 1.5 in thickness/fit');a.weld('W'+name,[x,y,-bd+tf],[x,y,-tf],['GIRDER',name],.5,basis='A')
    a.fastener('BOLTS',[[x,y,-tf] for x in (-cd/2-1,cd/2+1) for y in (-cw/2-1,cw/2+1)],[0,0,1],1,tf+1.5,['GIRDER','BEARING'],'A four 1 in A325 positioning bolts','A');a.dim([-cd/2-2,0,1.5],[cd/2+2,0,1.5],basis='A');a.section_at=cd/2

def slip(ctx):
    from .review_hr_details import draw as standard
    ctx.params['moment']=False;ctx.family='review_beam';standard(ctx);ctx.family='review_transfer_slip'
    ctx.a.notes.append('S: horizontal long slots isolate the Level-2 transfer-truss node from the floor diaphragm. A: 2 in free movement, 3 in long slots with plate washers and snug fit. Gravity shear transfers through the bolt shanks; no axial lock across the slot is assumed.')
    for f in ctx.a.fasteners:f['slot']=dict(direction=[1,0,0],length_in=3,travel_in=2,basis='A')
    ctx.a.interfaces.append(dict(id='SLIP',kind='horizontal_slotted_connection',connects=['M2','P1'],travel_in=2,basis='A',description='Source axial release; A travel and slot dimensions'))

def plan_angle(ctx):
    if ctx.params.get('physical_plan_brace'):
        from .review_plan_bracing import draw
        return draw(ctx)
    a,p,pid=ctx.a,ctx.p,ctx.pid;par=ctx.params;count=par.get('count',2);h=effective(p,pid);bp=ctx.select(('beam','girder','moment_beam','equipment_beam'),ctx.default_w());bd=effective(p,bp);width=12 if count==3 or 'vessel' in ctx.text.lower() else 10
    if par.get('joint')=='column_quadrant':
        cp=ctx.select(('column',),ctx.default_w());a.member('COLUMN',cp,[0,0,-30],[0,0,20])
        beams=[m['profile_id'] for m in ctx.ms if m['kind'] in ('beam','girder','moment_beam')]
        for j,axis in enumerate(([1,0,0],[0,1,0])):
            profile=beams[min(j,len(beams)-1)] if beams else bp;depth=effective(p,profile)
            a.member('GIRDER'+str(j),profile,[axis[0]*6,axis[1]*6,-depth/2],[axis[0]*32,axis[1]*32,-depth/2],y=[-axis[1],axis[0],0])
        vertices=[[6,0,0],[15,0,0],[15,15,0],[0,15,0],[0,6,0],[6,6,0]]
        a.polygon('PLATE',vertices,.375,normal=[0,0,1],basis='S',description='Source 3/8 x 15 x 15 in quadrant gusset; 6 x 6 in column notch')
        v=unit([1,1,0]);side=[-v[1],v[0],0];first=[9,9,.375];start=add(add(first,mul(v,-1.5)),mul(side,-1.75));end=add(start,mul(v,30));t=p[pid]['dimensions']['t']
        a.member('ANGLE',pid,start,end,y=side,description='Source plan/equipment diagonal; A local quadrant orientation')
        points=[add([9,9,0],mul(v,j*3)) for j in range(count)]
        a.fastener('BOLTS',points,[0,0,1],.75,.375+t,['PLATE','ANGLE'],f'S {count} x 3/4 in A325; 3 in pitch; A local datum')
        a.weld('WX',[6,0,0],[15,0,0],['GIRDER0','PLATE'],.25,description='Source 1/4 in E70 fillet, 9 in on X girder')
        a.weld('WY',[0,6,0],[0,15,0],['GIRDER1','PLATE'],.25,description='Source 1/4 in E70 fillet, 9 in on Y girder')
        a.dim([0,15,0],[15,15,0],'Source quadrant width');a.front_axes=(0,1);a.section_axis=0;a.section_at=9
        a.notes.append('S: one notched quadrant per bay corner, shared with equipment diagonals where present; grating cut clear. A: local orientation, bolt datum and girder end fit. Each connected diagonal retains its own occurrence and source record.')
        return
    a.member('SUPPORT',bp,[-24,0,-bd/2],[24,0,-bd/2]);a.box('PLATE',[-width/2,-4,0],[width,8,.375],'S','Source leg-point/gusset plate; A local orientation');a.member('ANGLE',pid,[-width/2,1.75,.375],[width/2+24,1.75,.375],y=[0,-1,0]);t=p[pid]['dimensions']['t']
    a.fastener('BOLTS',[[(-count+1)*1.5+j*3,0,0] for j in range(count)],[0,0,1],.75,.375+t,['PLATE','ANGLE'],f'S {count} x 3/4 in A325; 3 in pitch; A local datum');a.weld('WP',[-width/2,-4,0],[width/2,-4,0],['SUPPORT','PLATE'],.25,description='Source plate perimeter weld / joint-gusset weld');a.front_axes=(0,1);a.section_axis=0;a.section_at=0;a.dim([-width/2,-4,0],[width/2,-4,0],basis='A')

def equipment_foot(ctx):
    a,p=ctx.a,ctx.p;bp=ctx.ms[-1]['profile_id'];d=effective(p,bp);leg=ctx.pid;a.member('BEAM',bp,[-22,0,-d/2],[22,0,-d/2]);a.box('FOOT',[-6,-6,0],[12,12,.75],'A','Fictional supplier base plate');a.member('LEG',leg,[0,0,.75],[0,0,24],basis='A');a.fastener('BOLTS',[[x,y,-p[bp]['dimensions'].get('tf',.5)] for x in (-4,4) for y in (-3,3)],[0,0,1],.75,.75+p[bp]['dimensions'].get('tf',.5),['FOOT','BEAM'],'A 4 x 3/4 in A325 supplier attachment','A');a.weld('WL',[-2,-2,.75],[2,-2,.75],['LEG','FOOT'],.25,basis='A');a.dim([-6,0,0],[6,0,0],basis='A');a.notes.append('A supplier geometry and attachments. Source vessel/skid/pump reactions and delegated supplier checks remain unchanged.')


def equipment_head(ctx):
    a,p=ctx.a,ctx.p;rail=ctx.ms[1];side=ctx.params['rail_side'];depth=effective(p,rail['profile_id']);t=p[rail['profile_id']]['dimensions']['t']
    a.member('LEG',ctx.pid,[0,0,-24],[0,0,0],basis='A')
    a.member('RAIL',rail['profile_id'],[min(0,side*24),0,depth/2+.5],[max(0,side*24),0,depth/2+.5],basis='A')
    a.box('CAP',[-3,-3,0],[6,6,.5],'A','A supplier leg cap plate')
    a.fastener('BOLTS',[[side,yy,.5+t] for yy in (-1.25,1.25)],[0,0,-1],.5,.5+t,['RAIL','CAP'],'A two 1/2 in supplier rail-to-cap bolts; access holes and capacity to verify',basis='A')
    for i,(v,w) in enumerate((([-2,-2,0],[2,-2,0]),([2,-2,0],[2,2,0]),([2,2,0],[-2,2,0]),([-2,2,0],[-2,-2,0]))):a.weld('W'+str(i),v,w,['LEG','CAP'],.25,basis='A',description='A leg-to-cap perimeter weld')
    a.section_axis=2;a.section_at=.5+t/2
    a.notes.append('Explicit fictional supplier base-frame rail and leg interface. Damper mass/reactions retain their source design; supplier dynamics, travel and attachment capacity remain delegated.')

def angle_crossing(ctx):
    if ctx.params.get('physical_plan_brace'):
        from .review_plan_bracing import draw
        return draw(ctx)
    a,p,pid=ctx.a,ctx.p,ctx.pid;t=p[pid]['dimensions']['t'];h=effective(p,pid)
    a.member('A1',pid,[-20,0,0],[20,0,0],y=[0,1,0]);a.member('A2',pid,[0,-20,t],[0,20,t],y=[-1,0,0]);a.fastener('B1',[[0,0,0]],[0,0,1],.75,2*t,['A1','A2'],'S one 3/4 in A325 crossing bolt');a.front_axes=(0,1);a.section_axis=0;a.section_at=0
    a.notes.append('S: horizontal-truss crossing bolt. A: angles occupy adjacent flange planes; flange offsets and local packer fit are coordination geometry. Grating is cut clear and does not act as a diaphragm.')

def clevis(ctx):
    if ctx.params.get('joint')=='turnbuckle':
        from .review_assemblies import tube
        a,p=ctx.a,ctx.p;rp=ctx.pid;dia=effective(p,rp);a.member('ROD-L',rp,[-28,0,0],[-2,0,0]);a.member('ROD-R',rp,[2,0,0],[28,0,0]);body=tube(p,3*dia,3*dia,.25);a.member('BODY',body,[-6,0,0],[6,0,0],basis='A',description='A forged turnbuckle supplier envelope');a.interfaces.append(dict(id='THREADS',kind='threaded_adjuster',connects=['ROD-L','BODY','ROD-R'],basis='A',description='Opposite-hand threaded rod engagement; source turnbuckle requirement'));a.dim([-6,0,0],[6,0,0],'A supplier envelope',basis='A');a.section_at=0;return
    a,p=ctx.a,ctx.p;bp=ctx.select(('rafter','column','beam','girder'),ctx.default_w());d=effective(p,bp);a.member('HOST',bp,[0,0,-d/2],[30,0,-d/2]);a.box('GUSSET',[6,-.25,0],[12,.5,16],'A','S 1/2 in A36 where scheduled; A supplier gusset outline');pid=rod(p,p[ctx.pid]['dimensions']['d'] if p[ctx.pid]['family']=='round' else 1);a.member('ROD',pid,[12,0,20],[12,0,48]);
    for j,y in enumerate((-.875,.375)):a.box('CLEVIS'+str(j),[8,y,9],[8,.5,13],'A','Forged clevis envelope; supplier geometry')
    assumed=ctx.params.get('supplier_hanger',False)
    a.fastener('PIN',[[12,-.875,14]],[0,1,0],1.25,1.75,['GUSSET','CLEVIS0','CLEVIS1'],'1-1/4 in clevis pin',basis='A' if assumed else 'S');a.weld('WG',[6,0,0],[18,0,0],['HOST','GUSSET'],.25,basis='A' if assumed else 'S',description='1/4 in gusset fillets');a.interfaces.append(dict(id='THREAD',kind='threaded_clevis',connects=['ROD','CLEVIS0','CLEVIS1'],basis='A',description='A supplier threaded shank engagement'));a.dim([12,0,0],[12,0,14],basis='A');a.section_axis=2;a.section_at=14

def gable(ctx):
    from .review_next_hr_industrial import gable_detail
    gable_detail(ctx)
