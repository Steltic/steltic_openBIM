"""Assembled plate-girder and tower-interface details from the saved designs."""
from .review_assemblies import effective,rod,flat
FAMILIES={'review_pg_seat','review_pg_pickup','review_pg_collar','review_tower_joint','review_tower_podium'}

def draw(ctx):
    if ctx.family=='review_pg_seat':seat(ctx)
    elif ctx.family=='review_pg_pickup':pickup(ctx)
    elif ctx.family=='review_pg_collar':collar(ctx)
    else:tower(ctx)

def pickup(ctx):
    a,p=ctx.a,ctx.p;cp=ctx.pid;bp=ctx.ms[1]['profile_id'];cd=effective(p,cp);cw=effective(p,cp,'width');tw=p[bp]['dimensions']['tw']
    a.box('PG-TOP',[-48,-15,-4],[96,30,4],'S','S girder top flange 30 x 4 in');a.box('PG-BOTTOM',[-48,-15,-84],[96,30,4],'S','S girder bottom flange 30 x 4 in');a.member('PG-WEB',flat(p,76,tw),[-48,0,-42],[48,0,-42],y=[0,0,1],description='S 76 x 1-1/8 in girder web');a.member('COLUMN',cp,[0,0,0],[0,0,48])
    for j,x in enumerate((-cd/2,cd/2)):
        a.weld('CJP-F'+str(j),[x,-cw/2,0],[x,cw/2,0],['COLUMN','PG-TOP'],kind='CJP',description='S demand-critical column flange CJP to girder top flange')
        for side in (-1,1):
            name=f'ST{j}{side}';y=tw/2 if side>0 else -15
            a.box(name,[x-1.25,y,-80],[2.5,15-tw/2,76],'S','S 2-1/2 in full-depth bearing stiffener, fitted to both girder flanges')
            a.weld('W'+name,[x,side*tw/2,-80],[x,side*tw/2,-4],['PG-WEB',name],.3125,basis='A',description='A stiffener-to-web fillet fit; S fitted bearing at flanges')
    a.weld('CJP-W',[-cd/2,0,0],[cd/2,0,0],['COLUMN','PG-TOP'],kind='CJP',description='S demand-critical column web CJP')
    for z,flange,label in [(-80,'PG-BOTTOM','FW-BOT'),(-4,'PG-TOP','FW-TOP')]:a.weld(label,[-48,0,z],[48,0,z],['PG-WEB',flange],.3125,description='S 5/16 in girder flange-to-web fillets')
    a.dim([0,0,-84],[0,0,0],'S girder depth');a.dim([-cd/2,0,-80],[cd/2,0,-80],'S stiffener pairs below column flanges');a.section_axis=0;a.section_at=cd/2

def seat(ctx):
    a,p=ctx.a,ctx.p;bp=ctx.pid;cp=ctx.select(('column',));cd=effective(p,cp);face=cd/2
    a.member('COLUMN',cp,[0,0,-150],[0,0,36]);a.member('PG',bp,[face+1,0,-42],[face+100,0,-42])
    a.box('SEAT',[face,-14,-94],[18,28,2],'S','S 2 x 18 x 28 in seat plate CJP to column')
    a.box('SEAT-ST',[face,-1.25,-136],[28,2.5,42],'S','S 2-1/2 x 28 x 42 in seat stiffener CJP to column')
    a.weld('CJP-SEAT',[face,-14,-93],[face,14,-93],['COLUMN','SEAT'],kind='CJP')
    a.weld('CJP-ST',[face,0,-136],[face,0,-94],['COLUMN','SEAT-ST'],kind='CJP')
    a.weld('WS',[face,0,-94],[face+18,0,-94],['SEAT','SEAT-ST'],kind='CJP',basis='A',description='A local seat/stiffener junction')
    a.box('ROT-SEAT',[face+1,-12,-92],[16,24,4],'A','A supplier concave PTFE-lined rotation-seat envelope')
    from .assembly_scene import clip_part
    cylinder=a.cylinder('CYLINDER',[face+9,-12,-96.25],[0,1,0],24,24,'A','S R12 transverse cylinder; A supplier rotation surface')
    clip_part(cylinder,[0,0,1],-90)
    # Visible bearing envelope is illustrative; no new device capacity or certification.
    a.box('PTFE',[face+.5,-10.5,-84.25],[15,21,.125],'A','S 21 x 15 in confined PTFE plane slider; A thickness')
    a.box('STAINLESS',[face-2.5,-10.5,-84.125],[21,21,.125],'A','A stainless sliding plate with source +/-3 in travel')
    for side in (-1,1):
        a.box('GUIDE'+str(side),[face+1,side*12-(1 if side<0 else 0),-88],[16,1,4],'A','A transverse guide-bar fit; S guided bearing')
    a.box('END-ST',[face+9,-15,-80],[1,30,76],'S','S 1 in full-depth end bearing stiffener; A local station')
    a.box('COLLAR',[face,-14,0],[84,28,2.5],'S','S 2-1/2 x 28 in collar; 48 in unwelded then 36 in welded')
    a.weld('COLLAR-CJP',[face,-14,1.25],[face,14,1.25],['COLUMN','COLLAR'],kind='CJP',description='S demand-critical collar CJP in column hinge zone')
    for side in (-1,1):
        a.weld('COLLAR-F'+str(side),[face+48,side*14,0],[face+84,side*14,0],['PG','COLLAR'],.9375,description='S 15/16 in fillet beyond 48 in unwelded length')
        a.box('SIDE'+str(side),[-cd/2,side*5-(2.5 if side<0 else 0),0],[cd,2.5,24],'A','S collar side plates CJP to web/flanges; A local 24 in depth')
        a.weld('SIDE-CJP'+str(side),[face,side*5,0],[face,side*5,24],['COLUMN','SIDE'+str(side),'COLLAR'],kind='CJP')
    a.weld('COLLAR-END',[face+84,-14,0],[face+84,14,0],['PG','COLLAR'],.9375)
    a.interfaces.append(dict(id='SLIDE',kind='guided_sliding_bearing',connects=['PG','STAINLESS','PTFE','CYLINDER','ROT-SEAT','SEAT'],basis='S',description='S +/-3 in translation; 0.0131 rad rotation; 760 kip service / 1038 kip factored. No seat bolts or axial restraint. Device geometry/testing by supplier.'))
    a.notes.append('S: collar carries axial force, seat carries gravity through a guided sliding bearing. Collar has 72 headed studs with hairpins into slab; see separate collar/stud interface. A supplier envelopes do not specify a procurement-ready bearing.')
    a.dim([face,0,0],[face+48,0,0],'Unwelded',offset=24);a.dim([face+48,0,0],[face+84,0,0],'Fillet',offset=50);a.dim([face,0,-94],[face+18,0,-94],'Seat projection');a.section_axis=0;a.section_at=face+9

def collar(ctx):
    a,p=ctx.a,ctx.p;bp=ctx.pid;cp=ctx.select(('column',));d=effective(p,cp);face=d/2
    a.member('COLUMN',cp,[0,0,-30],[0,0,30]);a.member('PG',bp,[face+1,0,-42],[face+92,0,-42]);a.box('COLLAR',[face,-14,0],[84,28,2.5],'S','S 2-1/2 x 28 in collar; 48 in unwelded plus 36 in welded')
    a.box('SLAB',[face,-24,2.5],[92,48,6],'A','A local slab cover envelope around collar studs',kind='concrete');bar=rod(p,.5)
    for i in range(12):
        for j in range(6):
            x=face+9+i*6;y=-10+j*4;tag=f'{i}-{j}'
            a.cylinder('STUD'+tag,[x,y,2.5],[0,0,1],.75,4.5,'A','S one of 72 collar studs; A diameter/height and 6 x 4 in set-out')
            a.cylinder('HEAD'+tag,[x,y,7],[0,0,1],1.25,.375,'A','A stud-head envelope')
        # Each hairpin encloses a transverse row; bend radius is diagrammatic A.
        x=face+9+i*6
        a.member('HAIR-L'+str(i),bar,[x-1,-18,5.5],[x-1,18,5.5],y=[1,0,0],basis='A',description='S hairpin requirement; A #4 size and fit')
        a.member('HAIR-R'+str(i),bar,[x+1,-18,5.5],[x+1,18,5.5],y=[1,0,0],basis='A')
        a.member('HAIR-U'+str(i),bar,[x-1,18,5.5],[x+1,18,5.5],basis='A')
    a.weld('CJP',[face,-14,1.25],[face,14,1.25],['COLUMN','COLLAR'],kind='CJP',description='S demand-critical hinge-zone collar CJP')
    for y in (-14,14):a.weld('FILLET'+str(y),[face+48,y,0],[face+84,y,0],['PG','COLLAR'],.9375,description='S 15/16 in fillet beyond 48 in free length')
    a.interfaces.append(dict(id='STUD-BOND',kind='headed_stud_fusion_and_embedment',connects=['COLLAR','SLAB']+[f'STUD{i}-{j}' for i in range(12) for j in range(6)],basis='A',description='S 72 studs with hairpins transfer collar force to slab; A source-unspecified diameter, height, set-out and reinforcement fit.'))
    for part in a.parts:
        for prefix in ('STUD','HEAD','HAIR-L','HAIR-R','HAIR-U'):
            if part['id'].startswith(prefix):part['annotation_group']=prefix;break
    a.dim([face,0,0],[face+48,0,0],'S unwelded length');a.dim([face+48,0,0],[face+84,0,0],'S welded length');a.section_axis=0;a.section_at=face+9;a.front_axes=(0,1)

def tower(ctx):
    a,p=ctx.a,ctx.p;bp=ctx.pid;d=effective(p,bp);gap=19;podium=ctx.family=='review_tower_podium';thick=9 if podium else 6.25
    for side in (-1,1):
        start=-72 if side<0 else gap;end=0 if side<0 else gap+72;name='EDGE'+str(side)
        a.member(name,bp,[start,0,-d/2],[end,0,-d/2],basis='S' if side<0 else 'A',description='Source tower edge / A adjacent tower section context')
        a.box('SLAB'+str(side),[start,-24,0],[72,48,thick],'S' if podium else 'A','S podium 6 in topping on 3 in deck' if podium else 'A local slab-edge context',kind='concrete')
    if podium:
        a.box('BRIDGE',[0,-24,0],[gap,48,9],'S','S continuous podium slab across joint line',kind='concrete');rp=rod(p,.5)
        for j,y in enumerate((-18,-6,6,18)):a.member('TIE'+str(j),rp,[-48,y,6],[gap+48,y,6],description='S #4 at 12 in each way; A cover and displayed length')
        for j,x in enumerate(range(-48,68,12)):a.member('CROSS'+str(j),rp,[x,-24,6.5],[x,24,6.5],y=[1,0,0],description='S #4 transverse ties at 12 in')
        for side in (-1,1):
            for j,x in enumerate(([-42,-30,-18,-6] if side<0 else [gap+6,gap+18,gap+30,gap+42])):
                a.cylinder(f'STUD{side}-{j}',[x,0,0],[0,0,1],.75,5,'A','S 3/4 in stud at 12 in; A height');a.cylinder(f'HEAD{side}-{j}',[x,0,5],[0,0,1],1.25,.375,'A','A stud head')
        a.notes.append('S: L2 only, continuous tie across both tower lines. Collectors use 3/4 in headed studs at 12 in. No rigid bridge is introduced above the podium.')
        a.interfaces.append(dict(id='TIE-BOND',kind='reinforced_diaphragm',connects=['SLAB-1','BRIDGE','SLAB1','TIE0','TIE1','TIE2','TIE3'],basis='S',description='S continuous #4 ties at 12 in, concrete bond, collector headed-stud fusion and embedment.'))
        for part in a.parts:
            for prefix in ('TIE','CROSS','STUD','HEAD'):
                if part['id'].startswith(prefix):part['annotation_group']=prefix;break
        a.dim([-18,0,6],[-6,0,6],'S bar / stud pitch')
    else:
        a.box('COVER',[-4,-18,thick+.25],[gap+8,36,.125],'A','A flexible joint-cover envelope; attached one side, sliding other side')
        a.interfaces.append(dict(id='MOVEMENT',kind='seismic_movement_joint',connects=['SLAB-1','COVER','SLAB1'],basis='S',description='19 in minimum clear structural separation; A cover envelope. Supplier hardware accommodates source movement range; no structural member spans the gap.'))
        a.notes.append('S: 19 in clear structural gap; column gridlines 39 in apart. Source DE combination 17.55 in and MCE summed motion 58.57 in retained for delegated hardware coordination; the cover is an A envelope, not a selected product.')
        a.dim([0,0,0],[gap,0,0],'S minimum clear seismic gap')
    a.section_axis=1;a.section_at=0
