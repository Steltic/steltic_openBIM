"""Source simple-span canopy purlins with located anti-roll clips.

The finite notched clip, stock/gauges and4in tip-row shift are accepted
fictional fit choices. Their local capacities are not the gold purlin checks.
"""
import math
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_receiver_geometry import extract,point
from .review_cfs_occurrences import axis

RID='schedules/sched-purlin'
U=unit([1,0,.1]);V=[0,1,0];N=cross(U,V);AXES=(U,V,N)


def apply(b):
    if b.key!='cfs26':return
    old={m['id'] for m in b.members if m['kind']=='purlin'}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in old]
    lookup={m['id']:m for m in b.members}
    for row,x in enumerate(-44+56*i for i in range(9)):
        base=[x,0,168+.1*x]
        for bay,(lo,hi) in enumerate((( -48,287.875),(288.125,575.875),(576.125,912))):
            centre=add(base,mul(N,13.5));ends=[add(centre,[0,lo,0]),add(centre,[0,hi,0])]
            if row%2:ends.reverse()
            m=b.member(f'P-SIMPLE-{row}-{bay}','1200Z300-118','purlin',*ends,1,'A',records=[RID],local_y=mul(U,-1),lap_in=0,
                source_span_in=288,source_cantilever_in=48,physical_fit_basis='S9 lines, selected12x3x118mil Z,24ft simple spans and4ft end cantilevers, alternate up/down-slope facing. A1/4in butt clearance,56in horizontal row pitch,4in end-row shift and1/2in clearance above rafter top; no source lap or continuity invented.')
            for support,into in ((bay,1),(bay+1,-1)):
                y=support*288;q=add(base,[0,y,0]);host=lookup[f'F{support+1}-R0']
                c=b.connection(m['id']+'-SUPPORT'+str(support),'review_canopy_purlin',q,[m,host],[RID],
                    parameters=dict(actual_canopy_purlin=True,purpose='clip',axes=AXES,hand=-1 if row%2 else 1,into=into),title='CANOPY / SOURCE TWO-BOLT ANTI-ROLL CLIP')
                endpoint=min(range(2),key=lambda i:abs(m['axis'][i][1]-y))
                b.endpoint_links.append(dict(member_id=m['id'],end='start' if endpoint==0 else 'end',connection_id=c['id'],basis='Source simple-span end or4ft cantilever served by its own actual anti-roll clip; no lap or moment continuity specified.'))
    b.changes.append(dict(kind='canopy_source_simple_purlins',removed_member_ids=sorted(old),source_count=9,source_span_in=288,source_cantilever_in=48,
        adopted_horizontal_stations=[-44+56*i for i in range(9)],basis='A4in inward tip-row shift keeps clip bolts on actual finite rafters; remaining roof-edge sheet overhang requires manufacturer verification.'))
    b.note('CANOPY-PURLINS','S: nine1200Z300118 purlin lines, simple24ft spans,4ft end cantilevers, alternate up/down-slope facing and two1/2in web bolts at every anti-roll support. A:1/4in butt gaps,56in horizontal spacing and4in inward tip-row shifts,1/2in clearance above the rafter,1/4in bent clip with a notch clearing the actual rafter flange and two receiving-web bolts. Purlin reactions pass through the source web bolts into the clip; no fictitious bearing cap intersects the roof straps. Source purlin capacities do not verify these local attachments, changed spacing/edge overhangs or procurement. The source description of strap panels over two purlin spaces is approximate; exact adopted stations remain explicit.')


def draw(ctx):
    a=ctx.a;origin=ctx.c['point']
    a.title='CANOPY / SOURCE TWO-BOLT ANTI-ROLL CLIP'
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),AXES,24)
    hand=ctx.params['hand'];into=ctx.params['into'];t=.1242;sx=-hand;near=sx*t/2;hy=into*(3.5+.1242/2)
    # Full-height bent plate on the inside rafter-web face. Its purlin leg is
    # notched above the rafter flange, leaving both source receivers uncut.
    outline=[(hy-into*.25,-4),(hy,-4),(hy,7.05),(hy+into*3,7.05),(hy+into*3,19.25),(hy-into*.25,19.25)]
    a.polygon('CLIP-W',[[near,y,z] for y,z in outline],.25,normal=[sx,0,0],basis='A',description='A1/4in notched anti-roll leg; actual rafter-top flange has0.05in clearance')
    a.polygon('CLIP-R',[[near+sx*x,hy,z] for x,z in ((.25,-4),(3.5,-4),(3.5,19.25),(.25,19.25))],.25,normal=[0,-into,0],basis='A',description='A1/4in folded receiving leg against inside face of actual rafter web')
    a.interfaces.append(dict(id='CLIP-BEND',kind='formed_bend',connects=['CLIP-W','CLIP-R'],basis='A',description='One continuous bent and notched clip; bend radius omitted, local capacity unverified'))
    bolted(a,'WEB-BOLTS',[[near+sx*.25,hy+into*1.5,z] for z in (10.5,16.5)],[-sx,0,0],t+.25,['M0','CLIP-W'],'S two1/2in A325 purlin web bolts; A6in gauge and exact finite clip fit','S')
    bolted(a,'FRAME-BOLTS',[[near+sx*1.75,hy-into*.25,z] for z in (-2,2)],[0,into,0],.25+.1017,['CLIP-R','M1'],'A two1/2in A325 receiving-web bolts; local capacity unverified','A')
    a.dim([0,0,10.5],[0,0,16.5],'A6in web gauge',basis='A');a.front_axes=(0,2);a.section_axis=2;a.section_at=10.5
    a.notes.append('Actual finite purlin and rafter shown together. S selected simple span and two web bolts. A full-height bent/notched clip, receiving bolts, clearances and row shifts require local capacity and installation checks. Source anti-roll and manufacturer panel requirements remain in the source record.')


def bolted(a,label,points,n,grip,joined,description,basis):
    from .review_cfs26_primary import washers
    for i,q in enumerate(points):
        start=sub(q,mul(n,.125));end=add(q,mul(n,grip));w0=label+'-WA'+str(i);w1=label+'-WB'+str(i)
        washers(a,w0,start,n,.5);washers(a,w1,end,n,.5)
        a.parts[-1]['annotation_group']=label+'-WASHERS';a.parts[-2]['annotation_group']=label+'-WASHERS'
        a.fastener(label+str(i),[start],n,.5,grip+.25,[*joined,w0,w1],description,basis=basis)
        a.parts[-1]['annotation_group']=label
