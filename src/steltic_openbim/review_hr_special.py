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
    from .review_hr_brace_ends import draw_brace
    return draw_brace(ctx)


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
    from .review_wall_bases import plate
    plate(ctx)


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
