"""Single-channel barn end-wall posts, source bases, headers and slip heads."""
import math
from .pilots.model import add,sub,mul,unit
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .review_endwall_posts import lower_surface
from .review_cfs_strut_ends import section_points

AXES=([1,0,0],[0,1,0],[0,0,1])
RID='schedules/sched-endwall'


def prepare(b):
    if b.key!='cfs27':return
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for m in b.members:
        if m['id'].startswith(('DOOR-JAMB-','CENTRE-POST-')):
            m['local_y']=[1,0,0]
            if m['id'].startswith('DOOR-JAMB-'):m['end_offsets'][0][2]=.5
            else:m['end_offsets'][0][2]=4.25
            m['physical_fit_basis']='S paired wind-post channel. A strong depth normal to the end-wall wind, base/header clearance and source clip fitting.'
    # The source16x14ft door height is clear opening, so its HSS header sits
    # above that elevation instead of projecting2in into the opening.
    for m in b.members:
        if m['id'].startswith('DOOR-HEAD-'):
            for q in m['axis']:q[2]=170
            m['end_offsets']=[[2.625,0,0],[-2.625,0,0]]


def apply(b):
    if b.key!='cfs27':return
    lookup={m['id']:m for m in b.members};b.endpoint_links=getattr(b,'endpoint_links',[])
    for c in b.connections:
        first=lookup[c['member_ids'][0]];mid=first['id'];family=c['detail_ref']['id'];purpose=None
        if mid.startswith('DOOR-JAMB-'):
            if family=='review_endpost_base':purpose='base'
            elif family=='review_endpost_top':purpose='head'
        elif mid.startswith('DOOR-HEAD-') and family=='review_angle_clip':
            purpose='header';end=int(c['id'][-1]);jamb=lookup[f'DOOR-JAMB-{mid.rsplit("-",1)[-1]}-{end}']
            c['point']=list(first['axis'][end]);c['member_ids']=[mid,jamb['id']];c['parameters']=dict(end=end)
        elif mid.startswith('CENTRE-POST-') and family=='review_endpost_top':
            purpose='head' if c['id'].endswith(':1') else 'centre_base'
            if purpose=='centre_base':c['member_ids']=[mid,'DOOR-HEAD-'+mid.rsplit('-',1)[-1]]
        if purpose is None:continue
        par=c.setdefault('parameters',{});par.update(actual_single_endwall=True,purpose=purpose)
        if purpose=='head':
            frame=0 if first['axis'][0][1]==0 else 30;x=first['axis'][0][0];side=0 if x<216 else 1
            roof=lookup[f'F{frame}-R{side}'];foot_sign=-1 if x<216 else 1
            # Near the ridge the foot reaches beyond the explicit2in rafter
            # cut; the post stays below the theoretical roof underside.
            halfx=max(abs(q[0]) for poly in section_points(first,b.profiles) for q in poly)
            top=min(lower_surface(roof,b.profiles,[x+sg*halfx,first['axis'][0][1]]) for sg in (-1,1))-1
            first['end_offsets'][1][2]=top-first['axis'][1][2]
            c['member_ids']=[mid,roof['id']];par.update(side=foot_sign,into=-1 if frame==30 else 1,post_top=top-c['point'][2])
        c['detail_ref']['id']='review_single_endwall'
        end=1 if purpose=='head' else par.get('end',0)
        b.endpoint_links.append(dict(member_id=mid,end='end' if end else 'start',connection_id=c['id'],basis='Actual source end-wall assembly, explicit head/base/receiving hardware.'))
    for m in list(b.members):
        if not m['id'].startswith(('DOOR-JAMB-','CENTRE-POST-')):continue
        aa,dd=axis(m)
        for i in range(math.ceil((dd[2]-aa[2])/24)):
            z=aa[2]+12+24*i
            if z>dd[2]-4:continue
            b.connection(m['id']+'-STITCH'+str(i),'review_single_stitch',[aa[0],aa[1],z],[m],[RID],parameters=dict(actual_single_endwall=True,purpose='stitch'),title='SINGLE CHANNEL / PAIRED POST STITCH')
    b.note('PAIRED-POST-STITCHES','S door-jamb channels stitched at24in; source C1513 stitching screws. A twoNo12 through-web screws with solid1/8in fit packs per station, exact gauge/end offset; centre-post stitching at24in is an adopted proposal. Saved capacities are not extended to this fitted built-up arrangement.')
    b.note('SINGLE-ENDWALL','S:16x14ft centred doors, HSS4x4x1/8 headers,2x800S25097 jambs,2x362S16254 centre posts, L4x4 clips/two1/2in bolts, jamb L4x4x1/2x6.5in bases with two3/4in rods3in apart and welded plate washers. A: clear-opening header datum, actual post roll,3in clip lengths, one accessible web-side head clip,1in head clearance,1.5in slots, web packs, header angles and exact gauges. Supplier door/guide attachment and foundation concrete remain delegated. Saved checks do not certify these local fitting choices.')


def draw(ctx):
    purpose=ctx.params['purpose']
    if purpose=='base':return base(ctx)
    if purpose=='head':return head(ctx)
    if purpose=='header':return header(ctx)
    return centre_base(ctx)


def web_bounds(m,p):
    polys=section_points(m,p);webs=[]
    for poly in polys:
        xs=[q[0] for q in poly];ys=[q[1] for q in poly]
        if max(xs)-min(xs)<.3 and max(ys)-min(ys)>2:webs.append((min(xs),max(xs)))
    return sorted(webs)


def base(ctx):
    a,p=ctx.a,ctx.p;m=ctx.ms[0];webs=web_bounds(m,p);left=webs[0][0];right=webs[-1][1];t=.5
    extract(ctx,m,'POST',AXES,30)
    a.box('CONC',[-12,-12,-18],[24,24,18],'A','Delegated slab/foundation envelope',kind='concrete')
    a.box('CLIP-W',[left-t,-3.25,t],[t,6.5,3.5],'S stock / A fit','SourceL4x4x1/2x6.5in vertical leg')
    a.box('CLIP-F',[left-4,-3.25,0],[4,6.5,t],'S','Source4in foot,6.5in clip length')
    a.interfaces.append(dict(id='BEND',kind='continuous_angle',connects=['CLIP-W','CLIP-F'],basis='S/A',description='Source angle; A sharp bend envelope'))
    packs=[]
    for i,((_,lo),(hi,_)) in enumerate(zip(webs,webs[1:])):
        name='PACK'+str(i);a.box(name,[lo,-3.25,.5],[hi-lo,6.5,3.5],'A','A actual paired-web gap pack');packs.append(name)
    a.fastener('POST-BOLTS',[[left-t,y,2.5] for y in (-1.5,1.5)],[1,0,0],.5,t+right-left,['POST','CLIP-W']+packs,'S two1/2in A325-N bolts through jamb webs; A3in gauge',basis='S group / A gauge')
    for i,y in enumerate((-1.5,1.5)):
        name='WASHER'+str(i);x=left-2.25;a.box(name,[x-1,y-1,.5],[2,2,.25],'A','A2in plate washer; source welded washer and1-5/16in angle hole')
        a.fastener('ANCH'+str(i),[[x,y,-12]],[0,0,1],.75,12.75,['CONC','CLIP-F',name],'S3/4in F1554Gr36 cast-in rod; S3in spacing /1.75in clip-end distance; A12in embedment',basis='S group / A embedment')
        a.weld('W'+str(i),[x-1,y-1,.5],[x+1,y-1,.5],['CLIP-F',name],.1875,basis='A',description='A3/16in washer fillet; source requires welded plate washers')
    a.title='SINGLE CHANNEL END WALL / SOURCE JAMB BASE';a.front_axes=(1,2);a.section_axis=2;a.section_at=2.5
    a.notes.append('Source L4x4x1/2x6.5in, paired-web bolt group and two3/4in rods3in apart. A web-gap pack, washer size, weld and embedment. The foundation engineer retains concrete and local slab checks; this is not a fixed column base.')


def head(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,roof=ctx.ms;sg=par['side'];origin=ctx.c['point'];webs=web_bounds(m,p);face=webs[0][0] if sg<0 else webs[-1][1];sheet=webs[0][1]-webs[0][0];t=.25
    extract(ctx,m,'POST',AXES,30);extract(ctx,roof,'RAFTER',AXES,30)
    u=unit(sub(*roof['axis'][::-1]));n=unit([-u[2],0,u[0]])
    def lower(x):return lower_surface(roof,p,[origin[0]+x,origin[1]])-origin[2]
    # The foot occupies only the actual positive-Y single-channel flange.
    x0=face;x1=face+sg*4;ys=(0,3);into=par['into']
    a.polygon('POST-LEG',[[face,into*y,z] for y,z in ((0,par['post_top']-3),(3,par['post_top']-3),(3,lower(face)-t/n[2]),(0,lower(face)-t/n[2]))],t,normal=[sg,0,0],basis='S thickness / A fit',description='Source1/4in L4x4 web-side slip clip; A3in length')
    a.polygon('ROOF-LEG',[[x,into*y,lower(x)] for x,y in ((x0+sg*t,0),(x1,0),(x1,3),(x0+sg*t,3))],t,normal=mul(n,-1),basis='S thickness / A slope fold',description='Source4in roof leg folded to actual roof slope')
    a.interfaces.append(dict(id='BEND',kind='continuous_folded_clip',connects=['POST-LEG','ROOF-LEG'],basis='A',description='Continuous bent clip; exact radius omitted'))
    a.fastener('POST-BOLTS',[[face+sg*t,into*y,par['post_top']-1.25] for y in ((.5,1.25) if m['id'].startswith('CENTRE-POST-') else (.75,2.25))],[-sg,0,0],.5,t+sheet,['POST','POST-LEG'],'S two1/2in A325-N bolts, source vertical-slip condition; A finite gauge and slot dimensions',basis='S group / A slots')
    a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=1.5,width_in=.5625,travel_in=1,basis='A')
    rt=p[roof['profile_id']]['dimensions']['t'];x=face+sg*2.5
    a.fastener('ROOF-BOLTS',[sub([x,into*y,lower(x)],mul(n,t)) for y in (.75,2.25)],n,.5,t+rt,['ROOF-LEG','RAFTER'],'S two1/2in roof-leg bolts; A positions within actual3in flange',basis='S group / A gauge')
    a.interfaces.append(dict(id='SLIP',kind='vertical_slotted_connection',connects=['POST','POST-LEG'],travel_in=1,basis='A',description='Source lateral restraint; A1in vertical travel, no roof gravity bearing'))
    a.title='SINGLE CHANNEL END WALL / ACTUAL SLOPED SLIP HEAD';a.front_axes=(0,2);a.section_axis=2;a.section_at=par['post_top']-1.25
    a.notes.append('The post remains below the roof. One fitted clip reaches the actual single-channel flange; a symmetric second clip would miss that flange. Source L4 legs,1/4in stock and bolt groups retained. A clip face/length, exact cuts, gauge and travel need local verification. Separate source post-top kicker carries the roof-bracing load path.')


def header(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,post=ctx.ms;sg=1 if par['end']==0 else -1;webs=web_bounds(post,p);face=webs[-1][1] if sg>0 else webs[0][0];t=.25
    extract(ctx,m,'HEADER',AXES,30);extract(ctx,post,'POST',AXES,24)
    # HSS end clears both actual channel flanges. Source paired angle
    # attachment uses the exposed post flange on each side of the HSS.
    post_faces=section_points(post,p);lo=min(q[0] for poly in post_faces for q in poly);hi=max(q[0] for poly in post_faces for q in poly);endface=hi if sg>0 else lo
    cut=axis(m)[par['end']][0]-ctx.c['point'][0]
    for side in (-1,1):
        tag='ANGLE'+str(side);y=side*2
        a.polygon(tag+'-H',[[x,y,z] for x,z in ((cut,-2),(cut+sg*4,-2),(cut+sg*4,2),(cut,2))],t,normal=[0,side,0],basis='S stock / A fit',description='SourceL4x4 clip; A1/4in stock and4in length')
        a.polygon(tag+'-P',[[face,yy,z] for yy,z in ((y,-2),(side*3.5,-2),(side*3.5,2),(y,2))],t,normal=[sg,0,0],basis='A',description='A trimmed1.5in receiving leg from source L4 stock, clear of jamb flange')
        # A horizontal spacer/extension closes the finite gap from the post
        # web to the header-side leg; it is not an invisible zero-thickness link.
        a.polygon(tag+'-BRIDGE',[[x,y,z] for x,z in ((face,-2),(cut,-2),(cut,2),(face,2))],t,normal=[0,side,0],basis='A',description='A continuous extended angle leg clears actual post flange tips')
        a.interfaces.append(dict(id=tag+'-FOLD',kind='continuous_folded_clip',connects=[tag+'-P',tag+'-BRIDGE',tag+'-H'],basis='A',description='A extended bent clip, source L4 stock with adopted trimmed receiving leg and extended bridge; new local capacity required'))
        # The web extends to +/-4in; receive inside its clear web, never at6in.
        a.fastener(tag+'-POST',[[face+sg*t,side*3,z] for z in (-1,1)],[-sg,0,0],.5,t+(webs[0][1]-webs[0][0]),['POST',tag+'-P'],'A two1/2in bolts on actual jamb web',basis='A')
    a.fastener('HEADER-BOLTS',[[cut+sg*1.5,-2.25,z] for z in (-1,1)],[0,1,0],.5,4.5,['HEADER','ANGLE-1-H','ANGLE1-H'],'S two1/2in A325-N header bolts; A through-HSS arrangement and gauge',basis='S group / A fit')
    a.title='SINGLE CHANNEL END WALL / SOURCE HSS HEADER';a.front_axes=(0,2);a.section_axis=2;a.section_at=1
    a.notes.append('Source HSS4x4x1/8 header and L4 clips/two1/2in header bolts. The14ft opening stays clear below the header. A actual cuts, trimmed receiving legs and extended formed bridges, through-HSS bolt installation and jamb-web bolt groups require local capacity review.')


def centre_base(ctx):
    a,p=ctx.a,ctx.p;post,header=ctx.ms;extract(ctx,post,'POST',AXES,24);extract(ctx,header,'HEADER',AXES,24);webs=web_bounds(post,p);t=.25
    # The source centre post starts on the header. A fitted cap and two small
    # web angles make that physical interface explicit, without a fake base.
    a.box('CAP',[-3,-2,4],[6,4,t],'A','A header cap plate under centre post')
    for side in (-1,1):
        face=webs[-1][1] if side>0 else webs[0][0];name='CLIP'+str(side)
        a.polygon(name,[[face,y,z] for y,z in ((-1.25,4.25),(1.25,4.25),(1.25,8.25),(-1.25,8.25))],t,normal=[side,0,0],basis='A',description='A1/4in centre-post web leg')
        a.fastener(name+'-B',[[face+side*t,0,z] for z in (5.5,7.25)],[-side,0,0],.5,t+(webs[0][1]-webs[0][0]),['POST',name],'A two1/2in bolts into each actual post web',basis='A')
        a.weld(name+'-W',[face,-1.25,4.25],[face,1.25,4.25],['CAP',name],.1875,basis='A',description='A3/16in shop clip fillet')
    for y in (-2,2):a.weld('CAP'+str(y),[-3,y,4],[3,y,4],['HEADER','CAP'],.1875,basis='A',description='A3/16in cap-to-HSS shop fillet')
    a.title='SINGLE CHANNEL END WALL / CENTRE POST TO HEADER';a.section_axis=2;a.section_at=5.5
    a.notes.append('S centre post and actual HSS header. A cap, web clips, bolts and welds complete the located bearing/attachment interface; no checked base or unselected footing is substituted.')
