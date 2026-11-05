"""Source two-foot fascia below the canopy, with actual boxed posts.

Rail attachments, kicker stock and end brackets are adopted fit. The source
sign-vendor and local capacity verification requirements remain explicit.
"""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_cfs_occurrences import axis
from .review_cfs26_primary import GLOBAL,COL_HALF,RAF_HALF,through
from .review_cfs26_purlins import AXES,U,N,bolted
from .review_receiver_geometry import extract,point,vector
from .review_assemblies import hull
from .drawing_workflow import fingerprint

RID='schedules/sched-girt';PT=.0713;RT=.0566;PH=2+PT/2


def apply(b):
    if b.key!='cfs26':return
    old={m['id'] for m in b.members if m['kind'] in ('fascia_post','fascia_rail')}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in old]
    lookup={m['id']:m for m in b.members};postpid=b.profile('2X600S200-68/BOX');kpid=b.custom('A-CANOPY-KICKER-2X.25','flat',dict(width=2,thickness=.25),basis='A kicker stock, no source section selected')
    new=[]
    for side,x in enumerate((-44.5,404.5)):
        out=-1 if side==0 else 1;z=168+.1*x;posts=[]
        for frame in range(4):
            y=frame*288
            post=b.member(f'FASCIA-BOX-{side}-{frame}',postpid,'fascia_post',[x,y,z-24],[x,y,z+3],1,'A',records=[RID],local_y=[0,1,0],
                physical_fit_basis='S2x600S20068 boxed post,2ft below rafter. A3.5in inward tip shift and3in top extension for source four-bolt group; capacities not rerun.')
            posts.append(post);new.append(post['id']);host=lookup[f'F{frame+1}-R0']
            c=b.connection(post['id']+'-TIP','review_canopy_fascia',[x,y,z],[post,host],[RID],parameters=dict(actual_canopy_fascia=True,purpose='post',axes=GLOBAL),title='CANOPY / SOURCE FOUR-BOLT BOXED FASCIA POST')
            b.endpoint_links.append(dict(member_id=host['id'],end='start' if side==0 else 'end',connection_id=c['id'],basis='Source4ft cantilever tip projects3.5in beyond this actual fascia-post attachment; no separate rafter-tip support or splice is specified.'))
            for end in ('start','end'):b.endpoint_links.append(dict(member_id=post['id'],end=end,connection_id=c['id'],basis='Source cantilever post anchored by this source four-bolt top group; free lower tip is not an invented support.'))
            b.connection(post['id']+'-SEAMS','review_canopy_fascia',[x,y,z],[post],[RID],parameters=dict(actual_canopy_fascia=True,purpose='seams',axes=GLOBAL),title='CANOPY / ADOPTED BOX-POST SEAM STITCHES')
        for bay in range(3):
            for h in (-6,-18):
                rx=x+out*(3+RT/2)
                rail=b.member(f'FASCIA-RAIL-{side}-{bay}-{abs(h)}','800S200-54','fascia_rail',[rx,bay*288+.125,z+h],[rx,(bay+1)*288-.125,z+h],1,'A',records=[RID],local_y=[out,0,0],
                    physical_fit_basis='S two800S20054 rails at1ft tributary spacing. A centres6/18in below rafter,1/4in butt gap and web against actual outer post flange.')
                new.append(rail['id'])
                for end in (0,1):
                    into=1 if end==0 else -1;y=(bay+end)*288
                    c=b.connection(rail['id']+'-END'+str(end),'review_canopy_fascia',[rx,y,z+h],[rail,posts[bay+end]],[RID],parameters=dict(actual_canopy_fascia=True,purpose='rail',out=out,into=into,axes=GLOBAL),title='CANOPY / ACTUAL FASCIA RAIL TO POST')
                    b.endpoint_links.append(dict(member_id=rail['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Adopted screws through actual rail web and actual box-post flange.'))
                for st in (72,144,216):
                    y=bay*288+st;purlin=lookup[f'P-SIMPLE-{0 if side==0 else 8}-{bay}'];pa,pd=axis(purlin);pc=add(pa,mul(unit(sub(pd,pa)),dot(sub([0,y,0],pa),unit(sub(pd,pa)))))
                    target=add(add(pc,mul(U,1.5)),mul(N,-6))
                    begin=[rx,y,z+h];direction=unit(sub(target,begin));length=math.dist(begin,target)
                    if length<12:raise ValueError('Insufficient physical kicker length')
                    kicker=b.member(rail['id']+'-K'+str(st),kpid,'fascia_kicker',add(begin,mul(direction,3)),sub(target,mul(direction,3)),1,'A',records=[RID],local_y=cross([0,1,0],direction),
                        physical_fit_basis='S kicker location at6ft. A2x1/4in flat, exact inclination and3in workline end setbacks; stiffness and capacity unverified.')
                    new.append(kicker['id'])
                    for end,host,q,axes,purpose in ((0,rail,begin,GLOBAL,'kicker_rail'),(1,purlin,target,AXES,'kicker_purlin')):
                        c=b.connection(kicker['id']+'-END'+str(end),'review_canopy_fascia',q,[kicker,host],[RID],parameters=dict(actual_canopy_fascia=True,purpose=purpose,end=end,out=out,axes=axes),title='CANOPY / ADOPTED FASCIA KICKER ATTACHMENT')
                        b.endpoint_links.append(dict(member_id=kicker['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Adopted two-bolt kicker end to actual source rail or purlin flange.'))
    b.used_records.add(RID)
    b.physical_interfaces=getattr(b,'physical_interfaces',[])+[dict(id='CFS26-SIGN-VENDOR',kind='delegated_component',scope='delegated',member_ids=new,
        responsible_party='Sign vendor / project engineer',representation='Source fascia supporting steel is explicit; sign panels, edge closures and their proprietary fixings remain delegated.',
        detail_ref=dict(id='gold/cfs26/sign-vendor',revision=fingerprint(b.records[RID]['data'])),requirements=b.records[RID]['data'])]
    b.note('CANOPY-FASCIA','S:2x600S20068 boxed posts at rafter tips,2ft cantilever below each tip; two800S20054 rails at1ft spacing; four1/2in A325 post bolts with4in couple; kickers at6ft to edge purlins. A: posts3.5in inward of theoretical tips, exact box closure stitches, half-inch-bolt hollow spacers, rail end screws,2x1/4in flat kicker stock and end brackets. Kicker inclination, stiffness, post shift and all added attachments require local design verification; gold rail/post capacities are not reassigned to these proposals. Sign panels and proprietary connections remain vendor design for source61.7psf; source44.2psf rail load is retained. End-overhang fascia/closures require vendor coordination.')


def draw(ctx):
    a=ctx.a;par=ctx.params;purpose=par['purpose'];axes=par['axes']
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),axes,40)
    if purpose=='post':post(ctx)
    elif purpose=='seams':seams(ctx)
    elif purpose=='rail':
        out=par['out'];into=par['into']
        pts=[[out*RT/2,into*1.25,z] for z in (-1.5,1.5)]
        a.fastener('RAIL-SCREWS',pts,[-out,0,0],.216,RT+PT,['M0','M1'],'A twoNo12 rail-end screws into actual post flange; exact product and capacity unverified',basis='A',screw=True)
        a.front_axes=(1,2);a.section_axis=2;a.section_at=1.5
    else:kicker(ctx)
    a.notes.append('S selected fascia rails/posts and four-bolt post group; source sign-vendor scope retained. All unstated rail/kicker attachments, spacers and exact set-out are adopted fictional fit and require engineering verification. No new capacity check is implied.')


def post(ctx):
    a=ctx.a;pts=[[x,0,z] for x in (-2,2) for z in (-2,2)]
    through(a,'POST-BOLT',pts,[0,1,0],.5,-RAF_HALF,RAF_HALF,['M0','M1'])
    pid='A-CANOPY-POST-PIPE-.75-.083';a.profiles[pid]=dict(id=pid,family='chs',dimensions=dict(d=.75,t=.083),basis='A hollow post bolt spacer, ID0.584in')
    for i,q in enumerate(pts):
        for j,(lo,hi,joined) in enumerate(((-COL_HALF,-PH,['M0','M1']),(-2+PT/2,2-PT/2,['M0']),(PH,COL_HALF,['M0','M1']))):
            label=f'POST-SPACER-{i}-{j}';a.member(label,pid,add(q,[0,lo,0]),add(q,[0,hi,0]),y=[1,0,0],basis='A',description='A hollow pipe spacer on this source bolt; exact wall and cut length unverified',representation_role='assembly_component')
            a.parts[-1]['annotation_group']='POST-SPACERS'
            a.interfaces.append(dict(id=label+'-BEARING',kind='compression_spacer',connects=[label,*joined],basis='A',description='Hollow spacer bears on the actual receiving web faces; bolt passes through its bore.'))
    a.dim([-2,0,-2],[-2,0,2],'S4in moment couple',basis='S');a.section_axis=2;a.section_at=2


def seams(ctx):
    a=ctx.a
    pid='A-FASCIA-SEAM-1.5X68';a.profiles[pid]=dict(id=pid,family='flat',dimensions=dict(width=1.5,thickness=PT),basis='A68mil closure splice plate')
    for side in (-1,1):
        for j,z in enumerate((-23,-12,2)):
            label=f'SEAM-{side}-{j}';x=side*(3+PT/2)
            a.member(label,pid,[x,0,z-.75],[x,0,z+.75],y=[0,1,0],basis='A',description='A68mil seam stitch plate, clear of fascia rails',representation_role='assembly_component')
            pts=[[side*(3+PT),y,z] for y in (-.5,.5)]
            a.fastener(label+'-SCREWS',pts,[-side,0,0],.216,2*PT,[label,'M0'],'A twoNo12 screws, one into each actual box-channel flange; source boxed form retained, closure detail unverified',basis='A',screw=True)
    a.section_axis=2;a.section_at=-12


def kicker(ctx):
    a=ctx.a;par=ctx.params;m,h=ctx.ms;end=par['end'];axes=par['axes'];origin=ctx.c['point'];ends=axis(m)
    start=point(ends[end],origin,axes);along=vector(unit(sub(ends[1-end],ends[end])),axes);pts=[add(start,mul(along,s)) for s in (1.25,3.75)]
    roof=par['purpose']=='kicker_purlin';g=.25
    if roof:
        anchors=[[-1.2,0,-.25],[1.2,0,-.25]]
        a.box('SEAT',[-1.2,-3,-.25],[2.4,6,.25],'A','A1/4in receiving seat below actual purlin bottom flange')
        bolted(a,'PURLIN',[[0,y,-.25] for y in (-1.5,1.5)],[0,0,1],.25+.1242,['SEAT','M1'],'A two1/2in purlin-flange bolts; local design unverified','A')
    else:
        inside=-par['out'];face=inside*(RT/2+.25);anchors=[[face,0,z] for z in (-2.5,2.5)]
        lo=RT/2 if inside>0 else -RT/2-.25
        a.box('SEAT',[lo,-2,-3],[.25,4,6],'A','A shop-welded end plate against actual rail inner web face')
        a.fastener('RAIL',[[face,y,z] for y in (-1.25,1.25) for z in (-2,2)],[-inside,0,0],.216,.25+RT,['SEAT','M1'],'A fourNo12 screws through end plate and actual rail web; local design unverified',basis='A',screw=True)
    outline=hull([(q[0]+dx,q[2]+dz) for q in pts for dx,dz in ((-1,-1),(-1,1),(1,-1),(1,1))]+[(q[0],q[2]) for q in anchors])
    if roof:outline=hull([(x,min(z,-.25)) for x,z in outline])
    else:outline=hull([(inside*max(abs(face),inside*x),z) for x,z in outline])
    a.polygon('GUSSET',[[x,.125,z] for x,z in outline],g,normal=[0,1,0],basis='A',description='A1/4in kicker end gusset alongside actual flat kicker')
    bolted(a,'KICKER',[[q[0],.125+g,q[2]] for q in pts],[0,-1,0],.25+g,['GUSSET','M0'],'A two1/2in kicker bolts; stock, gauge and capacity unverified','A')
    aa,dd=anchors
    for y in (.125,.375):a.weld('SEAT-W'+str(y),[aa[0],y,aa[2]],[dd[0],y,dd[2]],['SEAT','GUSSET'],.1875,basis='A',description='A3/16in shop weld; added bracket capacity unverified')
    a.front_axes=(0,2);a.section_axis=2;a.section_at=pts[0][2]
    a.dim(pts[0],pts[1],'A2.5in bolt pitch',basis='A')
