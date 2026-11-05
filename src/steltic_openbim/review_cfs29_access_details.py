"""Source guard/stair groups on actual receivers; adopted access fittings."""
import math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import extract,point,vector,horizontal_frame
from .review_cfs_occurrences import axis
from .review_cfs29_details import box,bend,GLOBAL
from .review_cfs29_model import JT,PT


def draw(ctx):
    purpose=ctx.params['purpose']
    if purpose=='guard_base':guard(ctx)
    elif purpose=='guard_cap':guard_cap(ctx)
    elif purpose=='rail_post':rail(ctx)
    elif purpose=='tread_end':tread(ctx)
    elif purpose=='stair_end':stair(ctx)
    else:raise ValueError('Unimplemented real mezzanine interface: '+purpose)


def tube(a,label,u,z,lo,hi):
    pid='MEZZ29-CRUSH-TUBE';a.profiles[pid]=dict(id=pid,family='chs',dimensions=dict(d=.875,t=.125),basis='S crush tube / A OD/wall')
    a.member(label,pid,[u,lo,z],[u,hi,z],y=[1,0,0],basis='S tube / A dimensions',description='Hollow compression sleeve; bolt passes through the actual5/8in bore',representation_role='assembly_component')


def guard(ctx):
    a=ctx.a;m,host=ctx.ms;n=m['local_y'];axes=(cross(n,[0,0,1]),n,[0,0,1])
    extract(ctx,m,'GUARD',axes,18);extract(ctx,host,'EDGE',axes,20)
    gp=ctx.p[ctx.p[m['profile_id']]['components'][0]['profile_id']];gt=gp['dimensions']['t'];outer=.125/2+gt
    hp=ctx.p[host['profile_id']];isbox=hp['family']=='built_up'
    if isbox:hp=ctx.p[hp['components'][0]['profile_id']]
    ht=hp['dimensions']['t'];centre=point(axis(host)[0],ctx.c['point'],axes);near=centre[1]+((6+ht)/2 if isbox else ht/2)
    box(a,'POST-PACK',[-1,-.0625,-3],[1,.0625,3],'A1/8in solid pack inside the paired guard webs')
    # Hollow stand-off ends/sides, not an invented solid3in packing block.
    low,high=near,-outer;gap=high-low;ends=[]
    if gap<=.25:
        box(a,'STAND-PACK',[-1.5,low,-3],[1.5,high,3],'A exact-thickness solid packing plate at the small box-beam gap')
        ends=['STAND-PACK']
    else:
        for tag,v in (('STAND-IN',low),('STAND-OUT',high-.125)):
            box(a,tag,[-1.5,v,-3],[1.5,v+.125,3],'A1/8in end plate of guard stand-off');ends.append(tag)
    if gap>.25:
        for u in (-1.5,1.375):box(a,'STAND-SIDE'+str(u),[u,low+.125,-3],[u+.125,high-.125,3],'A1/8in hollow stand-off side')
        for tag in ends:
            for side in (-1.5,1.5):a.weld(tag+'-W'+str(side),[side,low+.125 if tag=='STAND-IN' else high-.125,-3],[side,low+.125 if tag=='STAND-IN' else high-.125,3],[tag,'STAND-SIDE'+str(-1.5 if side<0 else 1.375)],.125,basis='A')
    if isbox:
        far=centre[1]-(6+ht)/2;inside_far=far+ht
        joined=['GUARD','POST-PACK','EDGE',*ends];depth=outer-far
    else:
        # Source guard attaches to a box. This end receiver is the saved
        # single-C rim; a separately adopted backplate and flange returns
        # close the local compression path without relabelling it as a box.
        far=centre[1]-(2.5-JT/2)-.125;inside_far=far+.125
        z0=centre[2]-6;z1=centre[2]+6
        box(a,'BACK',[-1.5,far,z0],[1.5,far+.125,z1],'A1/8in end-joist backplate')
        for tag,z,sg in (('LOW',z0,-1),('HIGH',z1,1)):
            box(a,tag,[-1.5,far+.125,z],[1.5,near,z+sg*.125],'A flange return closes the single-C receiving bracket')
            bend(a,tag+'-BEND',['BACK',tag])
            a.fastener(tag+'-SCREWS',[[u,(far+near)/2,z+sg*.125] for u in (-.75,.75)],[0,0,-sg],.216,.125+JT,[tag,'EDGE'],'A2No12 each actual rim flange',basis='A',screw=True)
        joined=['GUARD','POST-PACK','EDGE','BACK',*ends];depth=outer-far
        a.notes.append('A end-edge guard stand-off and backplate are additional to the saved single-C rim. Original box-beam guard checks are retained as source conditions and do not verify this end-edge bracket.')
    a.fastener('GUARD-BOLTS',[[0,outer,z] for z in (-2,2)],[0,-1,0],.5,depth,joined,'S2x1/2in A325 through bolts at4in vertical pitch; A actual grip',basis='S group / A grip')
    for i,z in enumerate((-2,2)):
        tube(a,'CRUSH'+str(i),0,z,inside_far,near-ht)
        if gap>.25:tube(a,'STAND-TUBE'+str(i),0,z,low+.125,high-.125)
    a.interfaces.append(dict(id='SLEEVE-BEARING',kind='compression_spacer',connects=['EDGE','CRUSH0','CRUSH1'],basis='S crush tube / A fitted lengths',description='Hollow sleeves bear on actual receiving inner faces. Bolts pass through their bores.'))
    a.front_axes=(0,2);a.section_axis=2;a.section_at=2


def rail(ctx):
    a=ctx.a;m,post,cap=ctx.ms;u=unit(sub(m['axis'][1-ctx.params['end']],m['axis'][ctx.params['end']]));axes=horizontal_frame(u)
    extract(ctx,m,'RAIL',axes,18);extract(ctx,post,'POST',axes,18)
    extract(ctx,cap,'CAP',axes,18)
    # Orient the screw gauge with the actual channel flange, including the
    # adopted diagonal corner rail rather than a synthetic perpendicular beam.
    direction=1 if dot(m['local_y'],axes[1])>0 else -1
    a.fastener('RAIL-SCREWS',[[.75,direction*v,-1.8125+.0566] for v in (.5,1.1)],[0,0,-1],.19,.0566+.125,['RAIL','CAP'],'A2No10 rail-to-cap screws',basis='A',screw=True)
    a.front_axes=(0,2);a.section_axis=2;a.section_at=-1.75


def guard_cap(ctx):
    a=ctx.a;post,cap=ctx.ms
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,18)
    n=post['local_y'];along=cross(n,[0,0,1]);q=[0,0,-.125]
    for face in (-1,1):
        for side in (-1,1):
            centre=add(q,mul(along,face*1.8125))
            a.weld(f'CAP-{face}-{side}',add(centre,mul(n,side*.0625)),add(centre,mul(n,side*1.6875)),['M0','M1'],.125,basis='A',description='A cap weld to this actual guard-channel flange')
    a.front_axes=(0,2);a.section_axis=2;a.section_at=-.0625


def tread(ctx):
    a=ctx.a;tread,stringer=ctx.ms;side=1 if ctx.params['end']==0 else -1
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,20)
    face=side*(.0625+.1017);t=.25
    box(a,'WEB',[face,-2,-4.25],[face+side*t,2,-.75],'A L4x4x1/4 tread seat on actual stringer web')
    box(a,'SEAT',[face+side*t,-2,-.75],[face+side*4,2,-.5],'A4in seat, clear of actual stringer flanges')
    bend(a,'SEAT-BEND',['WEB','SEAT'])
    a.fastener('STRINGER',[[face+side*t,y,-1.5] for y in (-.5,.5)],[-side,0,0],.5,t+2*abs(face),['WEB','M1'],'A2x1/2in through bolts to paired stringer webs',basis='A')
    a.fastener('TREAD',[[side*3.25,y,.5] for y in (-1,1)],[0,0,-1],.375,1.25,['M0','SEAT'],'A2x3/8in tread fixing bolts',basis='A')
    a.front_axes=(0,2);a.section_axis=1;a.section_at=0


def stair(ctx):
    a=ctx.a;m=ctx.ms[0];end=ctx.params['end'];origin=ctx.c['point']
    for i,q in enumerate(ctx.ms):extract(ctx,q,'M'+str(i),GLOBAL,24)
    face=.0625+.1017;t=.25
    if end==0:
        base=-origin[2];box(a,'SLAB',[-8,-8,base-6],[8,8,base],'S6in existing slab / A stair shoe context');a.parts[-1]['kind']='concrete'
        box(a,'BASE',[-4,-5,base],[4,5,base+.375],'A3/8x8x10in stair shoe')
        for side in (-1,1):
            box(a,'WEB'+str(side),[side*face,-3,base+.375],[side*(face+t),8,12],'A stair shoe side plate on real stringer web')
            a.weld('W'+str(side),[side*(face+t),-3,base+.375],[side*(face+t),8,base+.375],['BASE','WEB'+str(side)],.1875,basis='A')
        u=unit(sub(*axis(m)[::-1]));qs=[mul(u,s) for s in (2,5)]
        a.fastener('SHOE',[[face+t,q[1],q[2]] for q in qs],[-1,0,0],.5,2*(face+t),['M0','WEB1','WEB-1'],'A2x1/2in shoe through bolts',basis='A')
        a.fastener('ANCHORS',[[x,0,base-4] for x in (-3,3)],[0,0,1],.5,4.375,['BASE','SLAB'],'A2x1/2in adhesive stair anchors,4in embedment',basis='A')
    else:
        host=ctx.ms[1];hcentre=point(host['axis'][0],origin,GLOBAL);hface=hcentre[1]-(6+PT)/2
        z0=hcentre[2]-4;z1=hcentre[2]+4
        box(a,'STRINGER-LEG',[face,hface-4,z0],[face+t,hface-t,z1],'S L4x4x1/4 stair clip / A8in vertical length')
        box(a,'BEAM-LEG',[face+t,hface-t,z0],[face+4,hface,z1],'S4in source leg on actual edge box beam')
        bend(a,'STAIR-CLIP',['STRINGER-LEG','BEAM-LEG'])
        a.fastener('BEAM',[[face+1.5,hface-t,z] for z in (hcentre[2]-2,hcentre[2]+2)],[0,1,0],.5,t+PT,['BEAM-LEG','M1'],'S2x1/2in A325 to edge beam; A4in vertical gauge',basis='S group / A fit')
        a.fastener('STRINGER',[[face+t,hface-2,z] for z in (hcentre[2]-2,hcentre[2]+2)],[-1,0,0],.5,t+2*face,['STRINGER-LEG','M0'],'A2x1/2in clip-to-stringer through bolts',basis='A')
    a.front_axes=(1,2);a.section_axis=2;a.section_at=0
