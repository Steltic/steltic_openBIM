"""Saved garage wind posts and adopted accessible finite end-wall interfaces."""
import math
from .pilots.model import add,sub,mul,unit,cross
from .review_cfs_occurrences import axis
from .review_cfs_strut_ends import section_points
from .review_cfs28_endwall import web_bounds
from .review_endwall_posts import lower_surface
from .review_receiver_geometry import extract
from .review_cfs17_secondary import roof_at
AXES=([1,0,0],[0,1,0],[0,0,1])
RID='schedules/sched-endwall'


def link(b,m,c,end):
    b.endpoint_links.append(dict(member_id=m['id'],end='end' if end else 'start',connection_id=c['id'],basis='This actual finite end-wall member is attached by the explicitly located physical fitting.'))


def joint(b,cid,q,ms,purpose,**par):
    return b.connection(cid,'review_garage_endwall',q,ms,[RID],parameters=dict(actual_garage_endwall=True,purpose=purpose,**par))


def apply(b):
    if b.key!='cfs17':return
    old={m['id'] for m in b.members if m['id'].startswith('OPEN-ACCESS-')}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old and not r['member_id'].startswith(('END-G-','END-0-POST','END-1-POST'))]
    lookup={m['id']:m for m in b.members}
    for end,y in enumerate((0,2592)):
        # The A42x84in opening remains exact between actual4in HSS jambs.
        posts=[]
        for j,x in enumerate((52,98)):
            m=b.member(f'GAR-ACCESS-{end}-J{j}','HSS4X4X1/8','opening_jamb',[x,y,.375],[x,y,84],1,'A',records=[RID]);posts.append(m)
            c=joint(b,m['id']+'-BASE',[x,y,0],[m],'access_base');link(b,m,c,0)
        h=b.member(f'GAR-ACCESS-{end}-H','HSS4X4X1/8','opening_header',[50,y,86],[100,y,86],1,'A',records=[RID])
        for j,m in enumerate(posts):
            c=joint(b,m['id']+'-HEAD',[m['axis'][0][0],y,84],[m,h],'access_head');link(b,m,c,1);link(b,h,c,j)
        lookup.update({m['id']:m for m in [*posts,h]})
    for c in b.connections:
        if not c['member_ids'][0].startswith(('END-0-POST','END-1-POST')):continue
        m=lookup[c['member_ids'][0]];f=c['detail_ref']['id']
        if f not in ('review_endpost_base','review_endpost_top'):continue
        head=f.endswith('top');m['end_offsets'][0][2]=.25
        par=dict(actual_garage_endwall=True,purpose='head' if head else 'base')
        if head:
            x,y=m['axis'][0][:2];seg,z,u=roof_at(x);frame=1 if y==0 else 19;roof=lookup[f'F{frame}-R{seg}'];sg=-1 if x==300 else 1
            half=max(abs(q[0]) for poly in section_points(m,b.profiles) for q in poly)
            top=min(lower_surface(roof,b.profiles,[x+v*half,y]) for v in (-1,1))-1
            m['end_offsets'][1][2]=top-m['axis'][1][2]
            c['member_ids']=[m['id'],roof['id']];par.update(side=sg,into=1 if y==0 else -1,top=top-c['point'][2])
        c['detail_ref']['id']='review_garage_endwall';c['parameters']=par;link(b,m,c,int(head))
    for m in [m for m in b.members if m['kind']=='endwall_post']:
        for j,z in enumerate(range(12,int(axis(m)[1][2]-4),24)):
            joint(b,m['id']+'-STITCH'+str(j),[m['axis'][0][0],m['axis'][0][1],z],[m],'stitch')
    # End-wall Zs are outside the19in frame envelope. Their real clips span
    # back to the post/prop face; a generic coincident section is never used.
    for end,y in enumerate((0,2592)):
        # The shorter gable also needs its scheduled20ft row, although its
        # two wind posts finish below that row. Both ends use actual rafters.
        b.member(f'END-G-{end}-SMALL-240','800Z250-54','girt',[780,y,240],[852,y,240],1,'A',records=[RID],local_y=[0,0,1],roof_supported_upper_girt=True)
    girts=[m for m in b.members if m['id'].startswith('END-G-')]
    ids={m['id'] for m in girts};b.connections[:]=[c for c in b.connections if not ids.intersection(c['member_ids'])]
    for m in girts:
        endwall=int(m['id'].split('-')[2]);y=2592*endwall;out=1 if endwall else -1
        for q in m['axis']:
            if abs(q[0]-51)<.01:q[0]=52
            if abs(q[0]-99)<.01:q[0]=98
        m['end_offsets']=[[0,14*out,0],[0,14*out,0]]
        for end,q in enumerate(m['axis']):
            sg=1 if end==0 else -1;small=m.get('roof_supported_upper_girt',False);upper=small or (q[2]==240 and q[0] in (150,450))
            if upper:
                # The240in girt lies above these real post heads. Its outer
                # end moves to the actual roof web, clear of the sloping end.
                cut=0 if small else 30;x=q[0]+sg*cut;m['end_offsets'][end][0]=sg*cut;seg,_,_=roof_at(x);host=lookup[f'F{1 if y==0 else 19}-R{seg}'];origin=[x,y,q[2]]
            else:
                options=[v for v in lookup.values() if v['kind'] in ('column','prop','endwall_post','opening_jamb') and abs(v['axis'][0][0]-q[0])<.01 and abs(v['axis'][0][1]-y)<.01]
                if not options:raise ValueError('No actual garage end-girt receiver '+m['id'])
                host=options[0];clear=max(sg*r[0] for poly in section_points(host,b.profiles) for r in poly)+.25;m['end_offsets'][end][0]=sg*clear;origin=list(q)
            c=joint(b,m['id']+'-END'+str(end),origin,[m,host],'girt',end=end,side=sg,out=out,upper=upper);link(b,m,c,end)
        m['physical_fit_basis']='S800Z25054 and source2/8/14/20ft rows. A outside end-wall plane14in from frame, physical clearances and real post/prop/roof brackets. The tall-gable outer ends move30in onto the roof; the short-gable20ft row spans72in between real rafters above the post heads. Source span checks remain separate.'
    b.note('GARAGE-ENDWALL-FIT','S: five paired wind posts at12.5/25/37.5/62/74ft,800S20068 except800S25068 ridge post;24in stitching; L4x4x1/4 clips,two1/2in bolts and two5/8in base anchors, vertical head slip. A:4in clip length, paired-web packs,1.5in slots/1in movement, extended head foot to accessible outside rafter flange, ridge head foot reaches beyond the actual end cut. End-wall Zs outside the frame on explicit brackets; tall-gable upper end-girt30in inset onto roof webs and short-gable20ft row spanning72in between rafters. A42x84in personnel openings have4in HSS jambs/header and explicit base/head joints. All source capacity and delegated foundation/door requirements remain separate from these fit choices.')


def draw(ctx):
    purpose=ctx.params['purpose']
    if purpose=='stitch':
        from .review_cfs27_stitches import draw as stitch
        stitch(ctx);ctx.a.title='GARAGE END WALL / SOURCE24in POST STITCH';return
    return {'head':head,'base':base,'girt':girt,'access_base':access_base,'access_head':access_head}[purpose](ctx)


def base(ctx):
    a,p=ctx.a,ctx.p;m=ctx.ms[0];webs=web_bounds(m,p);left=webs[0][0];right=webs[-1][1];t=.25
    extract(ctx,m,'POST',AXES,28);a.box('CONC',[-10,-8,-18],[20,16,18],'A','Delegated foundation envelope',kind='concrete')
    a.box('CLIP-F',[left-4,-2,0],[4,4,t],'S stock / A length','S4in foot,1/4in thick; A4in clip length')
    a.box('CLIP-W',[left-t,-2,t],[t,4,3.75],'S stock / A length','S4in vertical leg,1/4in thick')
    a.interfaces.append(dict(id='FOLD',kind='continuous_angle',connects=['CLIP-W','CLIP-F'],basis='S/A',description='Source L4x4x1/4, A sharp bend envelope'))
    pack=webs[1][0]-webs[0][1];a.box('PACK',[webs[0][1],-2,t],[pack,4,3.75],'A','A paired-web gap pack')
    a.fastener('POST-B',[[left-t,y,2] for y in (-1,1)],[1,0,0],.5,t+right-left,['POST','PACK','CLIP-W'],'S two1/2in A325-N through-web bolts; A2in gauge',basis='S group / A gauge')
    a.fastener('ANCHORS',[[left-2.5,y,-10] for y in (-1,1)],[0,0,1],.625,10.25,['CONC','CLIP-F'],'S two5/8in F1554Gr36 anchors; A10in embedment/2in gauge',basis='S group / A fit')
    a.title='GARAGE END WALL / SOURCE POST BASE';a.front_axes=(1,2);a.section_axis=2;a.section_at=2


def head(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,roof=ctx.ms;origin=ctx.c['point'];sg=par['side'];into=par['into'];t=.25;webs=web_bounds(m,p)
    face=webs[-1][1] if sg>0 else webs[0][0];extract(ctx,m,'POST',AXES,30);extract(ctx,roof,'RAFTER',AXES,32)
    u=unit(sub(*roof['axis'][::-1]));n=unit([-u[2],0,u[0]]);lower=lambda x:lower_surface(roof,p,[origin[0]+x,origin[1]])-origin[2]
    a.polygon('POST-LEG',[[face,y,z] for y,z in ((-2,par['top']-3),(2,par['top']-3),(2,lower(face)-t/n[2]),(-2,lower(face)-t/n[2]))],t,normal=[sg,0,0],basis='S stock / A fit',description='S1/4in vertical-slip leg; A4in length and fitted slope')
    a.polygon('ROOF-LEG',[[x,y,lower(x)] for x,y in ((face+sg*t,-2),(face+sg*4,-2),(face+sg*4,2),(face+sg*t,2))],t,normal=mul(n,-1),basis='S stock / A fit',description='S4in roof leg folded to actual slope')
    ys=(into*2,into*9.25)
    a.polygon('EXTENSION',[[x,y,lower(x)] for x,y in ((face+sg*t,ys[0]),(face+sg*4,ys[0]),(face+sg*4,ys[1]),(face+sg*t,ys[1]))],t,normal=mul(n,-1),basis='A',description='A integral extension to accessible outer-channel flange; capacity requires checking')
    a.interfaces.append(dict(id='FOLD',kind='continuous_folded_plate',connects=['POST-LEG','ROOF-LEG','EXTENSION'],basis='A',description='One connected bent-plate clip with adopted outside-flange extension'))
    a.box('PACK',[webs[0][1],-2,par['top']-3],[webs[1][0]-webs[0][1],4,2.5],'A','A paired-web slot spacer')
    a.fastener('POST-B',[[face+sg*t,y,par['top']-1.25] for y in (-1,1)],[-sg,0,0],.5,t+webs[-1][1]-webs[0][0],['POST','PACK','POST-LEG'],'S two1/2in A325-N bolts, vertical slip; A2in gauge/slot fit',basis='S group / A fit')
    a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=1.5,width_in=.5625,travel_in=1,basis='A')
    rt=p[p[roof['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];x=face+sg*2.5
    a.fastener('ROOF-B',[sub([x,y,lower(x)],mul(n,t)) for y in (into*7.25,into*8.75)],n,.5,t+rt,['EXTENSION','RAFTER'],'S two1/2in roof interface bolts; A actual outer-flange gauge',basis='S group / A fit')
    a.title='GARAGE END WALL / ACTUAL OUTER-FLANGE SLIP HEAD';a.front_axes=(0,2);a.section_axis=2;a.section_at=par['top']-1.25
    a.notes.append('Source vertical slip and original bolt/clip stock. A slot length, paired-web spacer and integral roof-leg extension reach the real accessible outside flange, including the ridge end clearance. Saved source capacity does not certify the extension; separate post-top kickers retain their own source duty.')


def girt(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,h=ctx.ms;out=par['out'];sg=par['side'];origin=ctx.c['point'];t=.25;web=p[m['profile_id']]['dimensions']['t'];z=web/2
    extract(ctx,m,'GIRT',AXES,36);extract(ctx,h,'RECEIVER',AXES,40)
    cut=axis(m)[par['end']][0]-origin[0];far=cut+sg*5;normal=[0,out,0]
    if par['upper']:
        hp=p[h['profile_id']];ht=p[hp['components'][0]['profile_id']]['dimensions']['t'];face=out*(6.375+.1875+ht)
        xs=(cut+sg*1.5,cut+sg*3.5);boltz=(4.,6.)
    else:
        choices=[]
        for poly in section_points(h,p):
            lo,hi=min(q[1] for q in poly),max(q[1] for q in poly);x0,x1=min(q[0] for q in poly),max(q[0] for q in poly)
            if .001<hi-lo<.3 and x1-x0>1.5 and x0<=sg*1.25<=x1:choices.append((out*(hi if out>0 else lo),hi if out>0 else lo,hi-lo))
        if not choices:raise ValueError('No real broad end-girt receiving face')
        _,face,ht=max(choices);xs=(sg*1.25,sg*1.25);boltz=(-1.,-3.)
    start=min(sg*.5,cut,far) if sg>0 else max(sg*.5,cut,far);xlo,xhi=sorted((start,far))
    if par['upper']:xlo,xhi=sorted((cut,far))
    yfar=out*15
    a.polygon('GIRT-LEG',[[x,y,z] for x,y in ((xlo,face),(xhi,face),(xhi,yfar),(xlo,yfar))],t,normal=[0,0,1],basis='A',description='A1/4in actual end-girt web leg spans back to real receiver')
    low,high=(z+t,7) if par['upper'] else (-4,z)
    a.polygon('HOST-LEG',[[x,face,zz] for x,zz in ((xlo,low),(xhi,low),(xhi,high),(xlo,high))],t,normal=normal,basis='A',description='A upstand at actual sloping roof web' if par['upper'] else 'A downstand at real post/prop receiving face')
    a.interfaces.append(dict(id='FOLD',kind='formed_bend',connects=['GIRT-LEG','HOST-LEG'],basis='A',description='One continuous folded bracket; exact radius omitted'))
    a.fastener('GIRT-B',[[cut+sg*d,out*14,-web/2] for d in (1.5,3.5)],[0,0,1],.5,web+t,['GIRT','GIRT-LEG'],'A two1/2in actual girt-web bolts',basis='A')
    a.fastener('HOST-B',[[x,face+out*t,zz] for x,zz in zip(xs,boltz)],[0,-out,0],.5,t+ht,['RECEIVER','HOST-LEG'],'A two1/2in bolts in actual receiving steel',basis='A')
    a.title='GARAGE END WALL / ACTUAL '+('ROOF' if par['upper'] else 'POST')+' GIRT RECEIVER';a.front_axes=(0,1);a.section_axis=0;a.section_at=cut+sg*1.5
    a.notes.append('Source girt section retained. A14in outside end-wall plane and explicitly connected bracket avoid overlapping the six-ply frame. Upper ends move to real roof steel because the post terminates below them. All local bracket/cut/bolt capacity remains unverified.')


def access_base(ctx):
    a=ctx.a;extract(ctx,ctx.ms[0],'JAMB',AXES,28);a.box('CONC',[-8,-9,-12],[16,18,12],'A','Delegated slab/foundation envelope',kind='concrete');a.box('BASE',[-4,-5,0],[8,10,.375],'A','A8x10x3/8in personnel-frame base')
    a.fastener('ANCHORS',[[x,y,-6] for x in (-3,3) for y in (-4,4)],[0,0,1],.5,6.375,['BASE','CONC'],'A four1/2in anchors,6in embedment',basis='A')
    for i,(aa,dd) in enumerate((((-2,-2),(2,-2)),((2,-2),(2,2)),((2,2),(-2,2)),((-2,2),(-2,-2)))):a.weld('W'+str(i),[*aa,.375],[*dd,.375],['BASE','JAMB'],.1875,basis='A',description='A3/16in perimeter fillet')
    a.title='GARAGE / ADOPTED PERSONNEL-JAMB BASE';a.section_axis=2;a.section_at=.1875


def access_head(ctx):
    a=ctx.a
    for tag,m in zip(('JAMB','HEADER'),ctx.ms):extract(ctx,m,tag,AXES,30)
    for i,(aa,dd) in enumerate((((-2,-2),(2,-2)),((2,-2),(2,2)),((2,2),(-2,2)),((-2,2),(-2,-2)))):a.weld('W'+str(i),[*aa,0],[*dd,0],['JAMB','HEADER'],.1875,basis='A',description='A3/16in jamb-to-header fillet,42x84in clear opening')
    a.title='GARAGE / ADOPTED PERSONNEL-FRAME HEAD';a.section_axis=2;a.section_at=0
