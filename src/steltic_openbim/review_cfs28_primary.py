"""Three independent source channel pairs, with actual finite portal joints."""
import math
from shapely.geometry import LineString
from .pilots.model import add,sub,mul,unit
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract

AXES=([1,0,0],[0,1,0],[0,0,1])
CENTRES=(-6.375,0.,6.375)


def apply(b):
    if b.key!='cfs28':return
    b.endpoint_links=getattr(b,'endpoint_links',[])
    lookup={m['id']:m for m in b.members}
    for m in b.members:
        if m['kind']=='column' and m['id'].startswith('F'):
            m['end_offsets']=[[0,0,2.375],[0,0,-10]]
            m['design_record_ids']=['members/frame-col-solid' if m['id'].endswith('C1') else 'members/frame-col']
        elif m['kind']=='rafter' and m['id'].startswith('F'):
            u=unit(sub(*m['axis'][::-1]));left=m['id'].endswith('R0')
            m['end_offsets']=[mul(u,10 if left else 2),mul(u,-2 if left else -10)]
            m['design_record_ids']=['members/frame-raf']
        else:continue
        m['physical_fit_basis']='S six channels, three independent back-to-back pairs with3/8in web gaps. A square knee10in/ridge2in end clearances. Source54in column/36in horizontal rafter bracket-end worklines and all source analyses remain separate from these cuts.'
    for c in list(b.connections):
        f=c['detail_ref']['id']
        if f not in ('review_next_portal_base','review_next_portal_joint'):continue
        purpose='base' if f.endswith('_base') else c['parameters']['joint']
        c['detail_ref']['id']='review_ag_primary';c['parameters']=dict(actual_ag_primary=True,purpose=purpose)
        for mid in c['member_ids']:
            m=lookup[mid];end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']))
            b.endpoint_links.append(dict(member_id=mid,end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual three-pair portal end attached by its source three continuous gussets and bolt groups; finite cut is explicitly adopted.'))
    # Source 24in web stitches are separate from the node gussets. Do not put
    # a pack on top of a continuous source gusset in a knee, ridge or base.
    for m in [m for m in b.members if m['kind'] in ('column','rafter') and m['id'].startswith('F')]:
        a,d=axis(m);u=unit(sub(d,a));length=math.dist(a,d);stations=[]
        if m['kind']=='column':
            stations=[z for z in range(24,163,24)]
            positions=[[m['axis'][0][0],m['axis'][0][1],z] for z in stations if z<160]
        else:
            left=m['id'].endswith('R0');start=36/math.sqrt(16/17) if left else 26
            stop=length-26 if left else length-36/math.sqrt(16/17)
            positions=[add(a,mul(u,s)) for s in range(math.ceil(start+3),math.floor(stop),24)]
        for i,q in enumerate(positions):
            b.connection(m['id']+'-PAIR-STITCH'+str(i),'review_ag_primary',q,[m],m['design_record_ids'],parameters=dict(actual_ag_primary=True,purpose='stitch'))
    b.note('AG-PRIMARY','S: three independent back-to-back channel pairs; three3/8in gussets,16 three-quarter-inch bolts per knee leg/pair and12 per ridge leg/pair,3in pitch/3.5in gauge/2in plate end. Column bracket ends54in below eaves; rafter bracket ends36in horizontally from columns and24in from ridge. Source7/8x16x22in base,1.5in grout,three3/8in base gussets,four3/4in web bolts per pair,four7/8in F1554 anchors. Source1/2in web stitches with3/8in packs at maximum24in outside node plates. A: continuous L/chevron outlines,10in knee/2in ridge cuts, pair centres6.375in, local stitch stations/pack sizes, welds and anchor embedment; saved capacities do not certify modified fit.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;purpose=par['purpose']
    if purpose=='base':return base(ctx)
    if purpose=='stitch':
        m=ctx.ms[0];u=unit(sub(*m['axis'][::-1]));axes=(u,[0,1,0],[-u[2],0,u[0]])
        extract(ctx,m,'MEMBER',axes,8);t=p[p[m['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
        pid='A-AG-STITCH-PACK';p[pid]=dict(id=pid,family='flat',dimensions=dict(width=10,thickness=.375),basis='S thickness / A footprint')
        for i,y in enumerate(CENTRES):
            tag='PACK'+str(i);a.member(tag,pid,[-1,y,0],[1,y,0],y=[0,0,1],representation_role='assembly_component',basis='S thickness / A footprint',description='Source3/8in solid stitch pack; A2x10in outline')
            a.fastener('B'+str(i),[[0,y-.1875-t,z] for z in (-3.5,3.5)],[0,1,0],.5,.375+2*t,['MEMBER',tag],'S1/2in A325 through each actual pair with3/8in pack,24in maximum; A two bolts and7in gauge',basis='S diameter / A group')
        a.title='AG PORTAL / THREE INDEPENDENT PAIR STITCHES';a.section_axis=0;a.section_at=0
        return
    knee=purpose=='knee';origin=ctx.c['point'];directions=[];lengths=[]
    for j,m in enumerate(ctx.ms):
        far=max(m['axis'],key=lambda q:math.dist(q,origin));v=unit(sub(far,origin));directions.append(v)
        lengths.append(54 if m['kind']=='column' else 36/abs(v[0]) if knee else 24)
        extract(ctx,m,'M'+str(j),AXES,65)
    # Source outer bolt line coincides with the named design section. The
    # plate continues two inches past that line for the specified edge.
    ends=[mul(v,L+2) for v,L in zip(directions,lengths)]
    shape=LineString([(ends[0][0],ends[0][2]),(0,0),(ends[1][0],ends[1][2])]).buffer(7,cap_style=2,join_style=2)
    outline=list(shape.exterior.coords)[:-1];rows=4 if knee else 3
    for i,yy in enumerate(CENTRES):
        tag='G'+str(i);a.polygon(tag,[[x,yy-.1875,z] for x,z in outline],.375,basis='S thickness/depth / A perimeter',description='Source3/8in A572Gr50 gusset, one between this independent pair; continuous14in leg outline')
        for j,(m,v,L) in enumerate(zip(ctx.ms,directions,lengths)):
            tw=p[p[m['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];across=[-v[2],0,v[0]]
            pts=[add(mul(v,L-r*3),add(mul(across,(g-1.5)*3.5),[0,yy-.1875-tw,0])) for r in range(rows) for g in range(4)]
            a.fastener(f'B{i}-{j}',pts,[0,1,0],.75,.375+2*tw,['M'+str(j),tag],f'S{4*rows} A325-N bolts through this pair/gusset,3in pitch/3.5in gauge; hardened washers both sides',basis='S')
    a.dim(mul(directions[0],lengths[0]-3*(rows-1)),mul(directions[0],lengths[0]),f'S{rows-1} @3in')
    a.title='AG PORTAL / THREE CONTINUOUS '+('KNEE' if knee else 'RIDGE')+' GUSSETS'
    a.section_axis=2;a.section_at=-44 if knee else -3
    a.notes.append('Source three independent pairs and one continuous3/8in plate per pair. Source bolt groups lie at the actual54in column /36in horizontal rafter bracket-end design stations. A square end cuts and connected L/chevron perimeter; original calculations are retained and do not verify these adopted local cuts.')


def base(ctx):
    a,p=ctx.a,ctx.p;m=ctx.ms[0];tw=p[p[m['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
    extract(ctx,m,'COLUMN',AXES,38)
    a.box('CONC',[-14,-17,-20],[28,34,20],'A','Delegated foundation envelope',kind='concrete')
    a.box('GROUT',[-8,-11,0],[16,22,1.5],'S','Source1.5in nonshrink grout')
    a.box('BASE',[-8,-11,1.5],[16,22,.875],'S','Source7/8x16x22in A572Gr50 base plate')
    a.fastener('ANCHORS',[[x,y,-12] for x in (-6.25,6.25) for y in (-9.25,9.25)],[0,0,1],.875,14.375,['CONC','BASE'],'S four7/8in F1554Gr36 anchors; A12in embedment/1.75in plate edge set-out',basis='S diameter / A fit')
    for i,y in enumerate(CENTRES):
        tag='G'+str(i);a.box(tag,[-6,y-.1875,2.375],[12,.375,10],'S thickness / A footprint','Source3/8in base gusset; A12x10in outline')
        a.fastener('B'+str(i),[[x,y-.1875-tw,z] for x in (-3,3) for z in (5.375,8.375)],[0,1,0],.75,.375+2*tw,['COLUMN',tag],'S four3/4in A325-N bolts per actual pair; A6x3in gauge/pitch')
        for side in (-1,1):a.weld(f'W{i}-{side}',[-6,y+side*.1875,2.375],[6,y+side*.1875,2.375],['BASE',tag],.25,basis='A',description='A1/4in gusset/base fillet; source requires welded gussets')
    a.title='AG PORTAL / SOURCE THREE-PAIR BASE';a.section_axis=2;a.section_at=1.9375
    a.notes.append('All three actual channel pairs terminate on the source base plate. Four source anchors serve the whole column; each pair has its own source gusset and four web bolts. A local weld size, gusset outline, washers/anchor fit and embedment remain proposals; foundation design and source reactions are retained separately.')
