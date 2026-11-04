"""Distinct HR brace ends, rocking posts and embedded wall interfaces."""
import math,re
from .review_assemblies import *

def draw(ctx):
    if ctx.family in ('review_brace','review_brb'):brace(ctx)
    elif ctx.family=='review_rocker':rocker(ctx)
    elif ctx.family=='review_core_base':core_base(ctx)
    elif ctx.family=='review_plate_base':plate_base(ctx)
    elif ctx.family in ('review_chamfer','review_column_box'):boxed(ctx)
    elif ctx.family=='review_deck_studs':deck_studs(ctx)
    elif ctx.family=='review_edge_bars':edge_bars(ctx)

def edge_bars(ctx):
    a,p=ctx.a,ctx.p;n=ctx.params['bar_count'];pid=ctx.pid;lap=66
    a.box('SLAB',[-8,-2,-2],[82,14,3.5],'A','Source slab topping context; A 2 in bar centre below top',kind='concrete')
    for j in range(n):
        y=j*1.5;left='B'+str(j)+'a';right='B'+str(j)+'b'
        a.member(left,pid,[-8,y,0],[66,y,0],basis='S',description='Source #5 Grade 60 continuous edge bar')
        a.member(right,pid,[0,y+.625,0],[74,y+.625,0],basis='S',description='Source #5 lap bar; A contact set-out')
        a.parts[-1]['representation_role']='assembly_component'
        a.interfaces.append(dict(id='L'+str(j),kind='reinforcement_bond_lap',basis='S',connects=[left,right,'SLAB'],length_in=lap,description='66 in Class B contact lap in concrete; no bar weld; keep outside STMF protected zones'))
    a.front_axes=(0,1);a.section_axis=0;a.section_at=33
    a.dim([0,-1,0],[66,-1,0],'Source Class B lap',offset=-34)
    a.dim([0,-2,0],[0,10,0],'Source edge band',view='section',offset=34)
    a.notes.extend(['S: 6 bars at Grids A/C; 3 at Grids 1/4. Bars remain in the topping above deck ribs. A: 1.5 in centres and local cover/fit.',
                    'Source lap exclusion: every special segment and half a panel either side. Maintain reinforcement around corners; use A standard 90-degree bends with 6db inside diameter. The local extract shows the straight lap; no shear transfer through a bar weld is assumed.'])


def brace(ctx):
    a,p,pid,txt,par=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params;kind=par.get('joint','corner');upper=kind in ('apex','link_end');isbrb=ctx.family=='review_brb'
    full_text=txt
    cp=ctx.select(('column',));bp=ctx.select(('beam','moment_beam','girder','transfer_chord'));cd=effective(p,cp);bd=effective(p,bp);bf=effective(p,bp,'width')
    beam_z=par.get('beam_centroid_z',-bd/2);beam_top=beam_z+bd/2;beam_bottom=beam_z-bd/2
    # The connection datum is the building work point, not the support face.
    # Keep its exact source slope; the rounded display angle is not geometry.
    bm=ctx.ms[0]
    far=max(bm['axis'],key=lambda q:math.dist(q,ctx.c['point']))
    delta=sub(far,ctx.c['point']);horizontal=math.hypot(delta[0],delta[1])
    v=unit([horizontal,0,delta[2]]);sign=1 if v[2]>=0 else -1
    interface_z=(beam_bottom if sign<0 else beam_top) if kind!='base' else 0
    # End-specific source text can prescribe different UFM edges at the two ends.
    if par.get('upper_end') and 'upper end:' in txt and not par.get('interface_length'):
        txt=txt.split('upper end:',1)[1];ctx.text=txt
    t=par.get('gusset_thickness',ctx.n(r'(?:corner|apex|base) gusset '+NUMBER+r' in',ctx.n(r'slotted for a '+NUMBER+r' in',.75)));lx=ctx.n(r'(?:beam-edge weld length|beam edge|base-plate weld length|upper-end beam-edge weld) '+NUMBER+r' in',24);lz=ctx.n(r'(?:column-edge weld length|column edge|upper-end column-edge weld) '+NUMBER+r' in',24)
    if upper:
        length=ctx.n(r'(?:both sides x|flange over) '+NUMBER+r' in',ctx.n(r'apex gusset '+NUMBER+r' in along',36))
        if kind=='link_end':length=ctx.n(r'flange over '+NUMBER+r' in',length)
        length=par.get('interface_length',length)
        a.member('BEAM',bp,[-length/2-10,0,beam_z],[length/2+10,0,beam_z]);lx=length;lz=max(24,length*.65)
        vertices=[[-length/2,-t/2,interface_z],[length/2,-t/2,interface_z],[length/2-3,-t/2,interface_z+sign*lz*.4],[3,-t/2,interface_z+sign*lz],[-length/2+3,-t/2,interface_z+sign*lz*.4]]
        a.polygon('GUSSET',vertices,t,basis='A',description=f'Source gusset t={t:g}, beam interface L={length:g}; A free-edge outline')
        w=ctx.n(r'\('+NUMBER+r'-in fillets both sides x',.5);a.weld('WGB',[-length/2,0,interface_z],[length/2,0,interface_z],['BEAM','GUSSET'],w,description='Source apex/link-end interface weld, both sides')
        # Source web stiffeners at both brace work lines and ends.
        tw=p[bp]['dimensions'].get('tw',.4);tf=p[bp]['dimensions'].get('tf',.6)
        if par.get('doubler_thickness'):
            dt=par['doubler_thickness'];a.box('DOUBLER',[-length/2-2,tw/2,beam_bottom+tf+.0625],[length+4,dt,bd-2*tf-.125],'S','Source apex beam web doubler; A corner clipping envelope')
            a.weld('WD',[-length/2-2,tw/2,beam_bottom+tf],[length/2+2,tw/2,beam_bottom+tf],['BEAM','DOUBLER'],max(.125,dt-.125),kind='PJP',description='Source doubler-to-flange PJP; both flanges, matching source record')
        for i,x in enumerate((-length/2+2,0,length/2-2)):
            for j,sg in enumerate((-1,1)):
                yy=tw/2 if sg>0 else -bf/2+.25;label=f'ST{i}{j}'
                a.box(label,[x-.25,yy,beam_bottom+tf],[.5,bf/2-tw/2-.25,bd-2*tf],'A','Source-required stiffener, A thickness/station where unspecified');a.weld('W'+label,[x,yy,beam_bottom+tf],[x,yy,beam_top-tf],['BEAM',label],.25,basis='A')
    else:
        weak=par.get('weak_axis_gusset',False);column_face=p[cp]['dimensions'].get('tw',.375)/2 if weak else cd/2
        a.member('COLUMN',cp,[0,0,0 if kind=='base' else -bd-lz-24],[0,0,lz+24],y=[1,0,0] if weak else [0,1,0])
        if kind=='base':
            a.box('BASE',[-cd-4,-bf/2-6,-1.5],[cd+lx+4,bf+12,1.5],'A','A local extract of source column base plate; see separate base detail')
            a.box('CONC',[-cd-8,-bf/2-10,-12],[cd+lx+12,bf+20,10.5],'A','Foundation context',kind='concrete');host='BASE'
        else:a.member('BEAM',bp,[column_face,0,beam_z],[column_face+lx+24,0,beam_z]);host='BEAM'
        clearance=column_face+(2*t if par.get('beam_only_gusset') else 0)
        vertices=[[clearance,-t/2,interface_z],[lx+clearance,-t/2,interface_z],[max(lx,18)+clearance,-t/2,interface_z+sign*lz*.65],[clearance,-t/2,interface_z+sign*lz]]
        a.polygon('GUSSET',vertices,t,basis='A',description=f'Source gusset t={t:g}; A fitted perimeter, source UFM edges')
        weld=ctx.n(NUMBER+r'-in E70 fillets both sides',.375)
        if not par.get('beam_only_gusset'):a.weld('WGC',[column_face,0,interface_z],[column_face,0,interface_z+sign*lz],['COLUMN','GUSSET'],weld,description='Source column-edge weld, both sides')
        else:a.notes.append('S: beam-only gusset; no gusset-to-column weld. A 2t clear gap is drawn at the column face. Source free-edge and rotation-clearance requirements remain.')
        a.weld('WGB',[clearance,0,interface_z],[lx+clearance,0,interface_z],[host,'GUSSET'],weld,description='Source beam/base edge weld, both sides')
    ctx.text=full_text
    station=max(8,min(lx,lz)*.55,abs(interface_z/v[2])+4 if abs(v[2])>1e-8 else 0,
                (clearance+2)/v[0] if not upper and v[0]>1e-8 else 0)
    start=mul(v,station);wl=ctx.n(r'welds? x '+NUMBER+r' in',12);end=add(start,mul(v,wl+24))
    a.member('BRACE',pid,start,end,description='Source brace section / BRB supplier envelope '+pid)
    if isbrb:
        dia=ctx.n(NUMBER+r' in dia\. pin',4);cheek=ctx.n(r'two '+NUMBER+r' in cheek plates',.875);plate=t+2*cheek;pin=add(start,mul(v,7));breadth=ctx.n(r'width '+NUMBER+r' in',19)
        for j,sg in enumerate((-1,1)):
            yy=t/2 if sg>0 else -t/2-cheek
            a.box('CHEEK'+str(j),[pin[0]-breadth/2,yy,pin[2]-breadth/2],[breadth,cheek,breadth],'A','Source cheek thickness/width; A perimeter and pin position')
            a.weld('WCH'+str(j),[pin[0]-breadth/2,yy,pin[2]-breadth/2],[pin[0]+breadth/2,yy,pin[2]-breadth/2],['GUSSET','CHEEK'+str(j)],.375,basis='A')
            yy=plate/2+.125 if sg>0 else -plate/2-.125-1.25
            a.box('CLEVIS'+str(j),[pin[0]-6,yy,pin[2]-6],[18,1.25,12],'A','A supplier clevis envelope');a.weld('WC'+str(j),[pin[0]+12,yy,pin[2]-6],[pin[0]+12,yy,pin[2]+6],['BRACE','CLEVIS'+str(j)],.375,basis='A')
        a.fastener('PIN',[[pin[0],-plate/2-.125-1.25,pin[2]]],[0,1,0],dia,plate+.25+2.5,['GUSSET','CHEEK0','CHEEK1','CLEVIS0','CLEVIS1'],f'{dia:g} in source 4140 Q&T pin; A supplier retaining envelope')
        a.notes.append('BRB core area retained; casing/clevis and pin-position fit are A supplier assumptions. Source cheek plates, free-edge stiffening and qualification requirements remain in the specification.')
    else:
        weld=ctx.n(r'(?:four |\(four lines\) )'+NUMBER+r' in E70',ctx.n(NUMBER+r'-in \(four lines\)',.375));th=effective(p,pid)/2
        for side in (-1,1):
            for edge in (-1,1):
                # Four distinct slot-edge lines, two at each HSS wall.
                off=[-v[2]*th*side,edge*t/2,v[0]*th*side];aa=add(start,off);a.weld(f'WB{side}{edge}',aa,add(aa,mul(v,wl)),['BRACE','GUSSET'],weld,description=f'Source slot weld L={wl:g}; four lines')
        match=re.search(r'(?:two PL|2 PL) '+NUMBER+r' x '+NUMBER+r'(?: x '+NUMBER+r')?',txt)
        if match:
            rt,rw=number(match[1]),number(match[2]);rl=number(match[3]) if match[3] else 20
            for j,sg in enumerate((-1,1)):
                yy=sg*(effective(p,pid,'width')/2);origin=add(start,mul(v,wl-rl/2));a.box('REINF'+str(j),add(origin,[0,yy,0]),[rl,rt,rw],'A','Source slot reinforcement dimensions; A fitted/rolled envelope',x=v,y=[0,sg,0]);a.weld('WR'+str(j),add(origin,[0,yy,0]),add(add(origin,mul(v,rl)),[0,yy,0]),['BRACE','REINF'+str(j)],.3125,description='Source reinforcement fillets, two lines each side of reduced section')
    # Free edges are authored fit geometry. Enclose the actual brace slot welds
    # while retaining the source support-edge lengths and plate thickness.
    gusset=next(q for q in a.parts if q['id']=='GUSSET')
    outline=[(q[0],q[2]) for q in gusset['polygon']]
    for w in a.welds:
        if w['id'].startswith('WB'):
            for q in (w['a'],w['b']):
                for dx,dz in ((-t,0),(t,0),(0,-t),(0,t)):
                    outline.append((max(clearance if not upper else -lx/2,q[0]+dx),
                                    min(interface_z,q[2]+dz) if sign<0 else max(interface_z,q[2]+dz)))
    a.parts.remove(gusset)
    a.polygon('GUSSET',[[x,-t/2,z] for x,z in hull(outline)],t,basis='A',description=gusset['description'])
    a.section_at=start[0]+6
    edge_start=-lx/2 if upper else clearance
    a.dim([edge_start,0,interface_z],[edge_start+lx,0,interface_z],f'{lx:g} in source interface length')
    a.dim([0,0,interface_z],[0,0,interface_z+sign*lz],basis='A',offset=40)
    a.notes.append('Separate source end condition: '+kind+'. Member slot, gusset clearance and free-edge trim follow the attached source record; drawings show the assembled load path. A geometry remains subject to the unchanged design verification requirements.')


def boxed(ctx):
    a,p=ctx.a,ctx.p;chamfer=ctx.family=='review_chamfer';cp=ctx.select(('column',),ctx.pid);d=effective(p,cp);w=effective(p,cp,'width');t=ctx.params.get('boxing_t',2)
    height=ctx.params.get('full_height_in');z0,z1=(-height/2,height/2) if height else (-42,24)
    plate_width=ctx.params.get('boxing_width_in',d)
    a.member('COLUMN',cp,[0,0,z0],[0,0,z1]);ids=['COLUMN']
    for i,sg in enumerate((-1,1)):
        yy=w/2 if sg>0 else -w/2-t;name='BOX'+str(i);ids.append(name);plate=flat(p,plate_width,t);a.member(name,plate,[0,yy+t/2,z0],[0,yy+t/2,z1],y=[1,0,0],basis='S',description='Source full-tier boxing; actual physical piece')
        for j,x in enumerate((-plate_width/2,plate_width/2)):
            for k,region in enumerate(ctx.params.get('boxing_weld_regions',[dict(z0=z0,z1=z1,kind='CJP')])):
                a.weld(name+'W'+str(j)+'-'+str(k),[x,yy,region['z0']],[x,yy,region['z1']],['COLUMN',name],.25,kind=region['kind'],basis='S joint zones/type; A fillet size',description='Source boxing weld classification; A 1/4 in continuous fillet where the source leaves size unstated')
    if chamfer:
        # Beam local X points away from the 45-degree face of the boxed column.
        column=next(m for m in ctx.ms if m['kind']=='column');beam=ctx.ms[0];origin=ctx.c['point'];far=max(beam['axis'],key=lambda q:math.dist(q,origin));ray=unit(sub(far,origin))
        cy=column['local_y'];cx=cross(cy,[0,0,1]);v=unit([dot(ray,cx),dot(ray,cy),0]);normal=cross([0,0,1],v)
        face=(d/2+w/2+t)/math.sqrt(2)-min(d,w)*.25;width=max(d,w)/math.sqrt(2)+2;bd=effective(p,ctx.pid);bf=effective(p,ctx.pid,'width');start=mul(v,face+1)
        for part in a.parts:clip_part(part,mul(v,-1),-face+1)
        origin=add(mul(v,face-1),mul(normal,-width/2));origin[2]=-bd-4
        a.box('FACE',origin,[2,width,bd+8],'S','Source 2 in face plate across boxed corner',x=v,y=normal)
        a.member('BEAM',ctx.pid,add(start,[0,0,-bd/2]),add(start,[v[0]*42,v[1]*42,-bd/2]),y=normal)
        for i,z in enumerate((0,-bd)):
            a.box('DIA'+str(i),[-d/2,-w/2-t,z-.875],[d,w+2*t,1.75],'S','1-3/4 in source through diaphragm / box continuity')
            # Projecting tongue meets the beam flange and passes through the face plate.
            q=add(mul(v,face-6),mul(normal,-bf/2));q[2]=z-.875
            a.box('TONGUE'+str(i),q,[7,bf,1.75],'S','Source projecting diaphragm tongue',x=v,y=normal)
            a.weld('FLANGE'+str(i),add(start,add(mul(normal,-bf/2),[0,0,z])),add(start,add(mul(normal,bf/2),[0,0,z])),['BEAM','TONGUE'+str(i)],kind='CJP',description='Source beam flange to projecting diaphragm CJP')
        a.weld('WEB',add(start,[0,0,-bd+2]),add(start,[0,0,-2]),['BEAM','FACE'],kind='CJP');a.notes.append('Source 45-degree corner geometry and through diaphragms. Local column-corner trim, face-plate width and tongue overlap are A fits; source cyclic qualification remains a verification requirement.')
    a.section_axis=2;a.section_at=-6;a.dim([-d/2,0,0],[d/2,0,0],f'{d:g} in column depth',view='section')


def deck_studs(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);pitch=ctx.n(r' at '+NUMBER+r' in',12);diameter=.75
    a.member('BEAM',pid,[-30,0,-d/2],[30,0,-d/2]);a.box('SLAB',[-30,-18,0],[60,36,6.25],'A','Floor/deck context',kind='concrete')
    xs=[-24+i*pitch for i in range(int(48/pitch)+1)];a.fastener('STUD',[[x,0,0] for x in xs],[0,0,1],diameter,4.5,['BEAM','SLAB'],'Source 3/4 in headed studs; A height envelope / longitudinal datum')
    for j,x in enumerate(xs):a.weld('W'+str(j),[x-.375,0,0],[x+.375,0,0],['BEAM','STUD'],kind='STUD',description='Automatic headed-stud weld per source')
    a.dim([xs[0],0,0],[xs[1],0,0],f'{pitch:g} in source spacing');a.section_axis=0;a.section_at=xs[0];a.notes.append('Keep studs outside source RBS protected zones. Extract shows repeated interface; source chord/diaphragm forces and local exclusions govern the full run.')


def plate_base(ctx):
    a,p=ctx.a,ctx.p;plate=flat(p,36,.1875);a.member('WALL',plate,[0,.28125,0],[0,.28125,28],y=[1,0,0]);embed=flat(p,36,1)
    a.member('EMBED',embed,[0,0,-12],[0,0,0],y=[1,0,0]);a.box('FISH',[-18,-.1875,-2],[36,.375,4],'S','3/8 x 4 in boundary fishplate');a.box('CONC',[-24,-18,-20],[48,36,20],'A','Mat context',kind='concrete')
    a.fastener('STUDS',[[x,-.5,-6] for x in (-16.5,-13.5,-10.5,-7.5,-4.5,-1.5,1.5,4.5,7.5,10.5,13.5,16.5)],[0,-1,0],.875,5,['EMBED','CONC'],'Source 7/8 in headed studs, 4 per foot; A longitudinal origin')
    a.weld('WF',[-18,0,0],[18,0,0],['FISH','EMBED'],.25,description='Source fishplate-to-embedded plate shop fillets');a.weld('WW',[-18,.375,1],[18,.375,1],['WALL','FISH'],.1875,description='Source wall-panel lap welds, both edges');a.section_axis=0;a.section_at=1.5;a.dim([0,0,-12],[0,0,0],'12 in embedded plate depth')


def core_base(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;t=par['plate_thickness'];pid=flat(p,36,t)
    for j,sg in enumerate((-1,1)):a.member('FACE'+str(j),pid,[0,sg*(18-t)/2,-72],[0,sg*(18-t)/2,24],y=[1,0,0])
    a.box('MAT',[-30,-24,-84],[60,48,84],'A','Mat context / reinforcement delegated',kind='concrete');a.box('BASE',[-20,-11,-74],[40,22,2],'A','A base bearing plate thickness/footprint')
    for j,sg in enumerate((-1,1)):
        pts=[[x,sg*9,z] for x in (-15,-9,-3,3,9,15) for z in range(-3,-72,-6)]
        a.fastener('STUDS'+str(j),pts,[0,sg,0],.875,5,['FACE'+str(j),'MAT'],'Source 7/8 x 5 in headed studs at 6 x 6 in; A 3 in extract margins')
        a.weld('WB'+str(j),[-18,sg*9,-72],[18,sg*9,-72],['FACE'+str(j),'BASE'],kind='CJP',basis='A',description='A plate development weld fit; source mat design handoff retained')
    a.section_axis=2;a.section_at=-36;a.dim([24,0,-72],[24,0,0],'72 in source wall embedment')


def rocker(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;beam=ctx.select(('beam','moment_beam','girder'),ctx.default_w());bd=effective(p,beam);bf=effective(p,beam,'width');pw=effective(p,pid,'width');depth=effective(p,pid)
    a.member('HBE',beam,[-28,0,-bd/2],[28,0,-bd/2]);radius=(70 if pid=='W14X283' else 60)*(1.5 if beam=='W24X146' else 1)
    verts=[[-3.5,-(bf-.5)/2,0],[3.5,-(bf-.5)/2,0]]+[[3.5-i*7/24,-(bf-.5)/2,2-radius+math.sqrt(radius*radius-(3.5-i*7/24)**2)] for i in range(25)]
    a.polygon('ROCKER',verts,bf-.5,basis='S',description=f'Source 7 in rocker / crown radius {radius:g} in')
    a.box('INSERT',[-3.5,-(bf-.5)/2,2],[7,bf-.5,1.5],'S','1-1/2 in bearing insert');a.box('ENDPL',[-pw/2,-12,3.5],[pw,24,6.5],'S','Source 6.5 x 24 in post end plate');a.member('POST',pid,[0,0,10],[0,0,40])
    anchor=2.75 if pid=='W14X283' else 3.25
    a.box('ANCHOR',[-3.5,-12,-bd-anchor],[7,24,anchor],'S','Source far-flange anchor bar')
    a.fastener('RODS',[[0,y,-bd-anchor] for y in (-9.5,9.5)],[0,0,1],2,bd+10+anchor,['ENDPL','ANCHOR'],'Source two 2 in A193 B7 rods on rocking axis, +/-9.5 in; no holes in HBE flanges')
    tw=p[beam]['dimensions'].get('tw',.5);tf=p[beam]['dimensions'].get('tf',.75)
    for i,x in enumerate((-4,4)):
        for j,sg in enumerate((-1,1)):
            yy=tw/2 if sg>0 else -bf/2+.25;name=f'S{i}{j}';a.box(name,[x-.375,yy,-bd+tf],[.75,bf/2-tw/2-.25,bd-2*tf],'A','Source paired full-depth stiffeners; A thickness fit');a.weld('W'+name,[x,yy,-bd+tf],[x,yy,-tf],['HBE',name],.3125,basis='A')
    a.weld('WR',[-3.5,-(bf-.5)/2,0],[3.5,-(bf-.5)/2,0],['HBE','ROCKER'],.3125,description='Source shop fillets on long sides only');a.weld('WP',[-depth/2,-pw/2,10],[depth/2,-pw/2,10],['POST','ENDPL'],kind='CJP',description='Source demand-critical shop CJP flange/web');a.section_axis=0;a.section_at=0;a.dim([-9.5,0,10],[9.5,0,10],'19 in rod centres')
    a.notes.append('Source rocking interface, not a moment splice. Reverse for the post below. Crown geometry uses the source radius; bearing insert and metallurgy remain explicit in the source specification. A stiffener thickness and local plate fit.')
    if ctx.params.get('inverted'):
        from .assembly_scene import reflect_z
        reflect_z(a)
        # Reflection is about the bearing face. Move it from beam top to bottom
        # while keeping the assembly origin at the saved top-of-steel datum.
        a.translate([0,0,-bd])
