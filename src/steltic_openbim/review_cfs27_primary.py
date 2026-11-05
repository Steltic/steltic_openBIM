"""Saved single-channel portal connections on the actual finite members.

The source specifies two gussets, not a six-channel frame. Worklines remain
unchanged; square end clearances, washers and local stiffener fit are A choices.
"""
import copy,math
from shapely.geometry import LineString
from .pilots.model import add,sub,mul,unit
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point

AXES=([1,0,0],[0,1,0],[0,0,1])


def prepare(b):
    if b.key!='cfs27':return
    for m in b.members:
        if m['kind']=='column':
            m['end_offsets']=[[0,0,2],[0,0,-10]]
            m['design_record_ids']=['members/frame-col']
        elif m['kind']=='rafter':
            u=unit(sub(*m['axis'][::-1]));left=m['id'].endswith('R0')
            m['end_offsets']=[mul(u,10 if left else 2),mul(u,-2 if left else -10)]
            m['design_record_ids']=['members/frame-raf']
        else:continue
        if m['id'].startswith('F30-'):m['local_y']=[0,-1,0]
        m['physical_fit_basis']='S source single channel and native workline. A square cuts clear the knee by10in and ridge by2in; column foot at1.5in grout plus0.5in base. Continuous twin gussets bridge these gaps; source capacities do not certify the adopted cuts.'


def apply(b):
    if b.key!='cfs27':return
    b.endpoint_links=getattr(b,'endpoint_links',[]);lookup={m['id']:m for m in b.members}
    for c in b.connections:
        family=c['detail_ref']['id']
        if family not in ('review_next_portal_base','review_next_portal_joint'):continue
        purpose='base' if family.endswith('_base') else c['parameters']['joint']
        c['detail_ref']['id']='review_single_channel_primary'
        c['parameters']=dict(actual_single_channel_primary=True,purpose=purpose)
        for mid in c['member_ids']:
            m=lookup[mid];end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']))
            b.endpoint_links.append(dict(member_id=mid,end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual single-channel web connected through the source twin plates; A local fit.'))
    b.note('SINGLE-CHANNEL-PRIMARY','S:31 single-channel frames at6.5ft,1400S300118 columns,1400S30097 rafters, two1/4in13in-deep gussets at knees/ridge,16 and12 five-eighth-inch bolts per leg respectively. Source1/2x8x16in base on1.5in grout, twin3/8in gussets, four5/8in web bolts and four5/8in F1554-36 anchors. A: finite10in knee/2in ridge square cuts, exact continuous gusset perimeter, thin rafter-web packs, stiffener folds/bolts, washers and anchor embedment. The last complete frame is handed toward the interior for actual torsion-brace access (A); its columns and rafters still face the same way within that frame. All source checks remain separate and do not verify the adopted fit.')


def draw(ctx):
    if ctx.params['purpose']=='base':return base(ctx)
    a,p=ctx.a,ctx.p;origin=ctx.c['point'];knee=ctx.params['purpose']=='knee'
    lengths=(48,36) if knee else (24,24);rows=4 if knee else 3;t=.25
    directions=[]
    for j,m in enumerate(ctx.ms):
        far=max(m['axis'],key=lambda q:math.dist(q,origin));directions.append(unit(sub(far,origin)))
        extract(ctx,m,'M'+str(j),AXES,60)
    # A connected L/chevron perimeter follows both source13in-deep legs.
    # A convex hull would cross the inner channel flanges at the knee.
    ends=[mul(v,L) for v,L in zip(directions,lengths)]
    shape=LineString([(ends[0][0],ends[0][2]),(0,0),(ends[1][0],ends[1][2])]).buffer(6.5,cap_style=2,join_style=2)
    outline=list(shape.exterior.coords)[:-1]
    half=max(p[m['profile_id']]['dimensions']['t']/2 for m in ctx.ms)
    for sign in (-1,1):a.polygon('G'+str(sign),[[x,sign*half,z] for x,z in outline],t,normal=[0,sign,0],basis='S thickness/depth; A outline',description='Source1/4in A572Gr50 twin gusset; A continuous node outline')
    for j,(m,v,L) in enumerate(zip(ctx.ms,directions,lengths)):
        tw=p[m['profile_id']]['dimensions']['t'];across=[-v[2],0,v[0]];joined=['M'+str(j),'G-1','G1']
        if half-tw/2>1e-7:
            # Only the real rafter portion receives the thin pack, never its
            # clear node gap. This is an explicit thickness mismatch, not void.
            start=min(math.dist(q,origin) for q in axis(m));stop=L
            corners=[add(mul(v,s),mul(across,w)) for s,w in ((start,-6.5),(stop,-6.5),(stop,6.5),(start,6.5))]
            for sign in (-1,1):
                name=f'PACK{j}-{sign}';a.polygon(name,[[q[0],sign*tw/2,q[2]] for q in corners],half-tw/2,normal=[0,sign,0],basis='A',description='A thin fit pack between actual97mil web and twin gusset datum');joined.append(name)
        pts=[add(mul(v,L-1.5-r*2.5),add(mul(across,(g-1.5)*3.5),[0,-half-t,0])) for r in range(rows) for g in range(4)]
        a.fastener('B'+str(j),pts,[0,1,0],.625,2*(half+t),joined,f'S {4*rows} five-eighth-inch A325-N bolts per leg; S3.5in gauge/2.5in pitch; A1.5in end distance',basis='S group / A end datum')
        a.dim(mul(v,L-1.5-(rows-1)*2.5),mul(v,L-1.5),f'S{rows-1} @2.5in')
        if knee:
            # One bent stiffener on the closed side of each real web at the
            # bracket end. Two touching plates represent one folded sheet.
            q=mul(v,L+3);lo=add(q,mul(v,-1.5));hi=add(q,mul(v,1.5));tag='ST'+str(j)
            corners=[add(r,mul(across,w)) for r,w in ((lo,-6.5),(hi,-6.5),(hi,6.5),(lo,6.5))]
            a.polygon(tag,[[r[0],-tw/2,r[2]] for r in corners],.25,normal=[0,-1,0],basis='S thickness / A fit',description='Source1/4in bolted stiffener; A3x13in folded web leg')
            corners=[add(q,mul(across,w)) for w in (-6.5,6.5)]
            a.polygon(tag+'-RETURN',[[r[0],y,r[2]] for r,y in ((corners[0],-tw/2-.25),(corners[1],-tw/2-.25),(corners[1],-tw/2-2),(corners[0],-tw/2-2))],.25,normal=v,basis='A',description='A2in stiffener return; local plate/weld capacity unverified')
            a.interfaces.append(dict(id=tag+'-BEND',kind='formed_bend',connects=[tag,tag+'-RETURN'],basis='A',description='One continuous folded stiffener, bend radius omitted'))
            a.fastener(tag+'-B',[[r[0],-tw/2-.25,r[2]] for r in (add(q,mul(across,-3.5)),add(q,mul(across,3.5)))],[0,1,0],.5,.25+tw,['M'+str(j),tag],'A two1/2in stiffener-to-web bolts; source only specifies bolted1/4in plates',basis='A')
    a.title='SINGLE CHANNEL / SOURCE TWIN '+('KNEE' if knee else 'RIDGE')+' GUSSETS'
    a.front_axes=(0,2);a.section_axis=2;a.section_at=-40 if knee else -3
    a.notes.append('Actual finite single-channel webs and source bolt groups. The two continuous gussets bridge the explicit square end cuts. A perimeter, local packs, stiffener bends/bolts and clearance are fictional fit proposals; original checks do not verify those changes. Hardened washers and snug-tight installation remain in the source specification.')


def base(ctx):
    a=ctx.a;m=ctx.ms[0];tw=ctx.p[m['profile_id']]['dimensions']['t'];extract(ctx,m,'COLUMN',AXES,36)
    a.box('CONC',[-14,-10,-18],[28,20,18],'A','Delegated foundation envelope',kind='concrete')
    a.box('GROUT',[-8,-4,0],[16,8,1.5],'S','Source1.5in nonshrink grout')
    a.box('BASE',[-8,-4,1.5],[16,8,.5],'S','Source1/2x8x16in A572Gr50 plate')
    plates=[]
    for sign in (-1,1):
        name='G'+str(sign);plates.append(name)
        a.polygon(name,[[x,sign*tw/2,z] for x,z in ((-6,2),(6,2),(6,12),(-6,12))],.375,normal=[0,sign,0],basis='S thickness / A outline',description='Source3/8in base gusset; A12x10in outline')
        a.weld('W'+name,[-6,sign*(tw/2+.375),2],[6,sign*(tw/2+.375),2],['BASE',name],.25,basis='A',description='A1/4in shop gusset fillet; source welded base assembly')
    a.fastener('WEB',[[x,-tw/2-.375,z] for x in (-3,3) for z in (5,8)],[0,1,0],.625,tw+.75,['COLUMN']+plates,'S four5/8in A325-N web bolts; A6x3in gauge',basis='S group / A gauge')
    for i,(x,y) in enumerate(((-6,-2.25),(-6,2.25),(6,-2.25),(6,2.25))):
        name='WASHER'+str(i);a.box(name,[x-.75,y-.75,2],[1.5,1.5,.25],'A','A1.5in square plate-washer envelope')
        a.fastener('ANCH'+str(i),[[x,y,-12]],[0,0,1],.625,14.25,['CONC','BASE',name],'S5/8in F1554Gr36 anchor; A12in embedment,12x4.5in pattern and washer',basis='S count/diameter / A fit')
    a.title='SINGLE CHANNEL / SOURCE PINNED BASE'
    a.front_axes=(0,2);a.section_axis=2;a.section_at=5
    a.notes.append('S plate, grout, twin gusset thicknesses, source bolt and anchor groups. A outlines, bolt gauges, weld size, washer envelopes and embedment are accepted fictional fit. Concrete breakout, pryout and foundation design remain delegated as in the source; no fixed-base moment resistance is claimed.')
