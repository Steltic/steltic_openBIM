"""Located mezzanine assemblies; source groups with explicit adopted fitting."""
import math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point,horizontal_frame
from .review_cfs29_model import TOP,STEEL,TT,JT,PT

GLOBAL=([1,0,0],[0,1,0],[0,0,1])


def box(a,label,lo,hi,description,basis='A'):
    lower=[min(x,y) for x,y in zip(lo,hi)];size=[abs(x-y) for x,y in zip(lo,hi)]
    return a.box(label,lower,size,basis,description)


def bend(a,label,parts):
    a.interfaces.append(dict(id=label,kind='formed_bend',connects=parts,basis='A exact fit',description='One continuous formed angle; sharp-corner representation, production bend radius to verify.'))


def draw(ctx):
    purpose=ctx.params['purpose'];a=ctx.a
    a.title='MEZZANINE / '+purpose.replace('_',' ').upper()
    if purpose=='base':base(ctx)
    elif purpose=='post_cap':post_cap(ctx)
    elif purpose=='box_seams':seams(ctx)
    elif purpose=='beam_end':beam_end(ctx)
    elif purpose=='joist_end':joist_end(ctx)
    elif purpose=='deck_screws':deck_screws(ctx)
    else:
        from .review_cfs29_wall_details import draw as wall_draw
        if not wall_draw(ctx):
            from .review_cfs29_access_details import draw as access_draw
            access_draw(ctx)
    a.notes.append('S denotes saved source dimensions/counts/requirements. A denotes adopted fictional set-out, cuts, packing and local details. Source capacities remain attached to their original conditions; they have not been recalculated for these fittings.')


def base(ctx):
    a=ctx.a;lines=ctx.params['lines'];extract(ctx,ctx.ms[0],'POST',GLOBAL,24)
    has_y=any(v.startswith('Y') for v in lines);length,width=(12,12) if has_y else ((10,8) if lines else (8,10))
    box(a,'SLAB',[-16,-16,-6],[16,16,0],'S6in existing slab; A local envelope; landlord engineer verification','S depth / A envelope')
    a.parts[-1]['kind']='concrete'
    box(a,'BASE',[-length/2,-width/2,0],[length/2,width/2,.375],'S3/8in A36 source base plate','S')
    anchor_points=[(x,y) for x in (-4,4) for y in (-4,4)] if has_y else ([(-4,0),(4,0)] if lines else [(0,-4),(0,4)])
    foot_t=.1345 if lines else 0
    for i,(x,y) in enumerate(anchor_points):
        washer_z=.375+foot_t
        box(a,'WASH'+str(i),[x-.75,y-.75,washer_z],[x+.75,y+.75,washer_z+.25],'A1.5in square x1/4in washer envelope, above the actual hold-down foot')
        joined=['SLAB','BASE']+(['HD'+str(1 if x>0 else -1)+'-FOOT'] if lines else [])+['WASH'+str(i)]
        a.fastener('ANCH'+str(i),[[x,y,-4]],[0,0,1],.625,4+washer_z+.25,joined,'S5/8in F1554Gr36 adhesive rod,4in embedment; A exact set-out/washer',basis='S rod / A fit')
    for side in (-1,1):
        y=side*(2.5+PT/2);tag='CLIP'+str(side)
        box(a,tag,[-2,y,.375],[2,y+side*.25,4.375],'S1/4in clip thickness and8No12 total; A4in high web')
        box(a,tag+'-FOOT',[-2,y+side*.25,.375],[2,y+side*1.25,.625],'A welded1in foot')
        bend(a,tag+'-BEND',[tag,tag+'-FOOT'])
        for edge in (-2,2):a.weld(tag+'-W'+str(edge),[edge,y+side*.25,.375],[edge,y+side*1.25,.375],['BASE',tag+'-FOOT'],.1875,basis='A',description='Source welded clip; A3/16in foot weld')
        pts=[[x,y+side*.25,z] for x in (-1,1) for z in (1.375,3.375)]
        a.fastener(tag+'-SCREWS',pts,[0,-side,0],.216,.25+PT,[tag,'POST'],'S4No12 on each base clip; A2x2in pitch',basis='S group / A set-out',screw=True)
    if lines:
        count=max(8 if v.startswith('Y') else 6 if v=='XM' else 4 for v in lines);t=.1345
        # Each half of the adopted saddle has one anchor foot. Four-anchor
        # Y plates use two source anchors per foot. Other line screw groups
        # remain separate requirements on the shared physical post.
        for side in (-1,1):
            name='HD'+str(side);x=3*side
            box(a,name,[x,-2,.375],[x+side*t,2,12.375],'S10ga hold-down body / A two-leg saddle envelope')
            yw=5 if has_y else 2
            box(a,name+'-FOOT',[x,-yw,.375],[side*(length/2),yw,.375+t],'S body thickness / A foot reaches actual source anchor group')
            bend(a,name+'-BEND',[name,name+'-FOOT'])
            pts=[[x+side*t,(-.75 if j%2 else .75),5+1.5*j] for j in range(count//2)]
            a.fastener(name+'-POST',pts,[-side,0,0],.216,t+PT,[name,'POST'],f'S{count}No12 total governing hold-down group; A separate source line requirements retained',basis='S group / A body',screw=True)
            # The anchors already occur once; declare the actual steel-bearing
            # interface without inventing a second coincident anchor set.
            a.interfaces.append(dict(id=name+'-ANCHOR-FOOT',kind='anchor_bearing',connects=[name+'-FOOT','BASE'],basis='A fitted source device',description='Foot bears on source base plate and shares the explicitly drawn source anchor group; combined line demand verification remains required.'))
        a.notes.append('Shared X/Y posts use one governing larger base and an adopted saddle body. All individual source device screw counts and demands remain in the source schedule; the combined anchor/device design is not reverified.')
    a.front_axes=(0,2);a.section_axis=2;a.section_at=2.375
    a.dim([-length/2,0,0],[length/2,0,0],f'S{length}in base',basis='S')


def post_cap(ctx):
    a=ctx.a
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,18)
    for x in (-3,3):a.weld('CAP-X'+str(x),[x,-2.5,-.25],[x,2.5,-.25],['M0','M1'],.125,basis='A',description='A1/8in bearing-cap edge weld, source post capacity not reassigned')
    for y in (-2.5-PT/2,2.5+PT/2):a.weld('CAP-Y'+str(y),[-3,y,-.25],[3,y,-.25],['M0','M1'],.125,basis='A')
    a.section_axis=2;a.section_at=-.125


def seams(ctx):
    a=ctx.a;m=ctx.ms[0];post=ctx.params['post'];u=unit(sub(*axis(m)[::-1]));v=m['local_y'];n=cross(u,v)
    axes=(u,v,n);extract(ctx,m,'BOX',axes,math.dist(*axis(m)))
    p=ctx.p[ctx.p[m['profile_id']]['components'][0]['profile_id']];t=p['dimensions']['t'];depth=p['dimensions']['d']
    ends=[point(q,ctx.c['point'],axes)[0] for q in axis(m)];lo,hi=sorted(ends)
    stations=[lo+12*i for i in range(1,math.ceil((hi-lo)/12))]
    ranges=[(lo,hi)] if not post else [(lo,lo+8),(hi-8,hi)]+[(v-.75,v+.75) for v in stations if lo+8<v-.75 and v+.75<hi-8]
    # Source channels meet at their lips. In the sharp-corner model a t-wide
    # groove remains between the flange tips; explicit weld metal fills it.
    for side in (-1,1):
        for i,(left,right) in enumerate(ranges):
            label=f'FILL{side}-{i}';z=side*(depth/2-t/2)
            pid='MEZZ29-SEAM-FILL-'+str(t)
            a.profiles[pid]=dict(id=pid,family='flat',dimensions=dict(width=t,thickness=t),basis='A square filled groove envelope for source weld metal')
            a.member(label,pid,[left,0,z],[right,0,z],y=[0,1,0],basis='S weld / A geometry',description='S flare V-groove seam / A square filled-flush envelope',representation_role='assembly_component')
            a.parts[-1]['material_category']='weld'
            a.weld('SEAM'+label,[left,0,side*depth/2],[right,0,side*depth/2],['BOX',label],kind='CJP',description='S ER70S-6 GMAW filled-flush flare V-groove, AWS D1.3; exact qualified groove preparation retained in source requirements.')
    a.front_axes=(0,2);a.section_axis=0;a.section_at=(lo+hi)/2
    a.notes.append('S post seams1.5in long at12in plus8in continuous at each end; beam seams continuous on both sides. Drawing weld envelope is A and does not replace the qualified flare-groove procedure.')


def beam_end(ctx):
    a=ctx.a;m,post=ctx.ms;end=ctx.params['end'];into=unit(sub(m['axis'][1-end],m['axis'][end]));axes=horizontal_frame(into)
    extract(ctx,m,'BEAM',axes,24);extract(ctx,post,'POST',axes,20)
    comp=ctx.p[ctx.p[m['profile_id']]['components'][0]['profile_id']];t=comp['dimensions']['t'];face=(6+t)/2
    for side in (-1,1):
        tag='ANGLE'+str(side);z0,z1=(-5.5,0) if side<0 else (0,5.5)
        box(a,tag+'-BEAM',[3.375,side*face,z0],[9.375,side*(face+.375),z1],'S6in leg x3/8in; A staggered5.5in vertical extent','S leg / A fit')
        box(a,tag+'-POST',[3,side*(face-4),z0],[3.375,side*face,z1],'S4in leg x3/8in; A staggered fit to actual post flange','S leg / A fit')
        bend(a,tag+'-BEND',[tag+'-BEAM',tag+'-POST'])
        zs=[side*1.25,side*4.25]
        a.fastener(tag+'-WEB',[[6,side*(face+.375),z] for z in zs],[0,-side,0],.75,.375+t,[tag+'-BEAM','BEAM'],'S2x3/4in A325 per beam web; A local gauge',basis='S group / A gauge')
        a.fastener(tag+'-COLUMN',[[3.375,side*1.25,z] for z in zs],[-1,0,0],.75,.375+PT,[tag+'-POST','POST'],'S4x3/4in A325 total into actual post flange; A staggered heights',basis='S group / A gauge')
    a.front_axes=(0,2);a.section_axis=2;a.section_at=1.25
    a.notes.append('S twoL6x4x3/8 per end,2 bolts per beam web and4 to post, F436 washers both head/nut. A upper/lower staggered angle lengths avoid overlapping4in post legs on the narrower box; source capacities are not a check of this staggered arrangement. Beam reaction workline remains4.5in from the post centre.')


def joist_end(ctx):
    a=ctx.a;m,host=ctx.ms;end=ctx.params['end'];into=unit(sub(m['axis'][1-end],m['axis'][end]));axes=horizontal_frame(into)
    extract(ctx,m,'JOIST',axes,24);extract(ctx,host,'RECEIVER',axes,24)
    hand=1 if dot(m['local_y'],axes[1])>0 else -1;side=-hand;face=ctx.params['receiver_face'];t=.0566
    box(a,'CLIP-WEB',[face+t,side*JT/2,-4],[face+3,side*(JT/2+t),4],'S L3x3x54mil / A8in length')
    box(a,'CLIP-FOOT',[face,side*JT/2,-4],[face+t,side*(JT/2+3),4],'S3in source foot / A actual receiving face')
    bend(a,'CLIP-BEND',['CLIP-WEB','CLIP-FOOT'])
    a.fastener('JOIST-SCREWS',[[face+u,side*(JT/2+t),z] for u in (1,2) for z in (-2,2)],[0,-side,0],.19,t+JT,['CLIP-WEB','JOIST'],'S4No10 to joist web; A gauge',basis='S group / A gauge',screw=True)
    ht=PT if host['kind'] in ('column','chord') else ctx.p[ctx.p[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
    a.fastener('RECEIVER-SCREWS',[[face+t,side*u,z] for u in (1,2) for z in (-2,2)],[-1,0,0],.19,t+ht,['CLIP-FOOT','RECEIVER'],'S4No10 receiver group; A real post face at on-grid joist',basis='S group / A receiver',screw=True)
    a.front_axes=(0,2);a.section_axis=2;a.section_at=2
    if host['kind'] in ('column','chord'):a.notes.append('A on-grid joist uses the actual post web rather than a beam web which ends4.5in from that post centre. Source joist/beam clip count retained; this receiver change has not been capacity-checked.')


def deck_screws(ctx):
    a=ctx.a;qs=ctx.params['points'];extent=max(math.dist(q,ctx.c['point']) for q in qs)+8
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,extent)
    host=ctx.ms[1];p=ctx.p[host['profile_id']]
    if p['family']=='built_up':p=ctx.p[p['components'][0]['profile_id']]
    t=p['dimensions'].get('t',p['dimensions'].get('thickness'))
    a.fastener('DECK',[sub(q,ctx.c['point']) for q in qs],[0,0,-1],.19,1.125+t,['M0','M1'],'SNo10 at'+str(ctx.params['spacing'])+'in; A exact locations on physical support',basis='S spacing / A set-out',screw=True)
    a.front_axes=(0,1);a.section_axis=0;a.section_at=qs[0][0]-ctx.c['point'][0]
