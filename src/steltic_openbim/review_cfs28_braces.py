"""Source flange braces, six-flange cross plates and separate post kickers."""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point,vector
from .review_cfs25_secondary import sections
from .review_sbmf_girts import cross_section
from .review_cfs_frame_straps import face_intervals
from .review_assemblies import hull
from .review_cfs28_secondary import STATIONS

CT=.1046


def apply(b):
    if b.key!='cfs28':return
    old={m['id'] for m in b.members if m['id'].startswith('FB-')}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old]
    lookup={m['id']:m for m in b.members};plates={}
    def build(tag,host,base,axes,direction,low_v,targets,side=1,count=4,post=False,length=30,cross_plate=True,width=3):
        u,v,n=axes;ht=b.profiles[host['profile_id']]['dimensions'].get('t')
        if ht is None:ht=b.profiles[b.profiles[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
        probe=low_v+direction*20
        hs=[m for m in targets if min(point(q,base,axes)[1] for q in axis(m))<=probe<=max(point(q,base,axes)[1] for q in axis(m))]
        if not hs:raise ValueError('No finite secondary for '+tag)
        if post and len(hs)>1:hs=[min(hs,key=lambda m:side*point(axis(m)[0],base,axes)[0])]
        webs=[]
        for m in hs:
            poly=max((q for q in sections(m,b.profiles,base,axes) if max(v[0] for v in q)-min(v[0] for v in q)<.3),key=lambda q:max(v[2] for v in q)-min(v[2] for v in q))
            webs.append((min(q[0] for q in poly),max(q[0] for q in poly),min(q[2] for q in poly),max(q[2] for q in poly)))
        face=min(w[0] for w in webs) if side<0 else max(w[1] for w in webs)
        low=min(q[2] for poly in cross_section(host,b.profiles,axes) for q in poly)+ht
        foot_t=.25 if post else .125
        heel=[face,low_v,low+foot_t+1.75];middle=(max(w[2] for w in webs)+min(w[3] for w in webs))/2
        rise=middle-heel[2]
        for _ in range(25):
            if not 0<rise<length:raise ValueError('Source brace length cannot reach '+tag)
            run=rise if post else math.sqrt(length**2-rise**2);along=unit([0,direction*run,rise]);across=cross([side,0,0],along)
            rise=middle+(1+(count-1)*.75/2)*along[2]-across[2]-heel[2]
        if post:run=rise;actual_length=math.sqrt(2)*rise
        else:run=math.sqrt(length**2-rise**2);actual_length=length
        along=unit([0,direction*run,rise]);across=cross([side,0,0],along);head=add(heel,mul(along,actual_length))
        world=lambda q:add(base,add(mul(u,q[0]),add(mul(v,q[1]),mul(n,q[2]))))
        wy=add(mul(u,across[0]),add(mul(v,across[1]),mul(n,across[2])))
        rid='schedules/sched-endwall' if post or host['kind'] in ('opening_jamb','endwall_post') else 'schedules/sched-strap'
        angle=b.member(tag,'L2X2X1/8','flange_brace',world(heel),world(head),1,'A',records=[rid],local_y=wy,source_kicker_length_in=26.9 if post else length,source_kicker_angle_deg=45 if post else None,
            physical_fit_basis='S angle and source end-screw groups. S30in ordinary brace; post S26.9in/45deg source check, A fitted45deg length with raised physical purlin. Saved capacities are not reassigned to changed post fit.')
        plate=None
        if cross_plate:
            centre=[2.125,0,-7-CT/2];stamp=(host['id'],tuple(round(q,5) for q in base))
            if stamp not in plates:
                pid=b.custom('AG-SOURCE-CROSS-PLATE','flat',dict(width=4,thickness=CT),basis='S12ga nominal0.1046in representation')
                plate=b.member('AG-CROSS-'+str(len(plates)),pid,'flange_cross_plate',world(add(centre,[0,-9.5,0])),world(add(centre,[0,9.5,0])),1,'S',records=[rid],local_y=u,source_plate_size_in=[4,19])
                cc=b.connection(plate['id'],'review_ag_flybrace',base,[plate,host],[rid],parameters=dict(actual_ag_flybrace=True,purpose='plate',axes=axes,centre=centre,host_t=ht))
                for end in ('start','end'):b.endpoint_links.append(dict(member_id=plate['id'],end=end,connection_id=cc['id'],basis='One source4x19in cross plate and two sourceNo12 screws to each of the six actual inside flanges.'))
                plates[stamp]=plate
            plate=plates[stamp]
        c=b.connection(tag,'review_ag_flybrace',base,[angle,host,*hs]+([plate] if plate else []),[rid],parameters=dict(actual_ag_flybrace=True,purpose='brace',axes=axes,heel=heel,head=head,side=side,webs=webs,count=count,post=post,lower_face=low,host_t=ht,foot_t=foot_t,foot_width=width,plate_id=plate['id'] if plate else None,source_length=26.9 if post else length))
        for end in ('start','end'):b.endpoint_links.append(dict(member_id=angle['id'],end=end,connection_id=c['id'],basis='Actual finite angle with complete lower folded foot and secondary-web screw group.'))
    # Retain source maximum10ft bottom-flange restraint interval and exact
    # knee/ridge bracket-end worklines; additional source-jamb rows included.
    rows=(36,114,168,264,312,408,462,540)
    for i in range(11):
        y=i*211.2
        for x in rows:
            side=int(x>288);host=lookup[f'F{i}-R{side}'];u=unit(sub(*host['axis'][::-1]));axes=(u,[0,1,0],cross(u,[0,1,0]));base=[x,y,216+min(x,576-x)/4];targets=[m for m in b.members if m['id'].startswith(f'AG-P-{x}-')]
            for hand in (-1,1):build(f'AG-FLY-R-{i}-{x}-{hand}',host,base,axes,1 if i==0 else -1 if i==10 else hand,hand*8,targets)
        host=lookup[f'F{i}-C1'];axes=([0,0,-1],[0,1,0],[1,0,0])
        for z in (24,96,168):
            targets=[m for m in b.members if m['id'].startswith(f'AG-G-{z}-')]
            for hand in (-1,1):build(f'AG-FLY-C-{i}-{z}-{hand}',host,[576,y,z],axes,1 if i==0 else -1 if i==10 else hand,hand*8,targets)
        if i in (0,10):
            for x in (168,280,408):
                side=int(x>288);host=lookup[f'F{i}-R{side}'];u=unit(sub(*host['axis'][::-1]));axes=(u,[0,1,0],cross(u,[0,1,0]));base=[x,y,216+min(x,576-x)/4];targets=[m for m in b.members if m['id'].startswith(f'AG-P-{x}-')];direction=1 if i==0 else -1
                for hand in ((-1,1) if x!=280 else (-1,)):
                    build(f'AG-POST-KICKER-{i}-{x}-{hand}',host,base,axes,direction,direction*8,targets,side=hand,count=3,post=True,cross_plate=False)
    b.note('AG-SOURCE-FLANGE-BRACES','S:ordinary L2x2x1/8 braces30in, fourNo12 each end, paired at every girt and maximum10ft rafter stations plus bracket ends. One source12ga4x19in cross plate joins all six inside flanges with twoNo12 per flange. A:exact station/foot/gauge and inward end-frame hands. Jamb top has two separate source angles, source sixNo12 at each interface represented as three per angle; centre post has one angle/threeNo12. Source post-kicker26.9in/45deg check retained; raised actual purlin needs A fitted45deg length and local recheck. No old generic fly-brace receiver remains.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes']
    if par['purpose']=='plate':
        plate,host=ctx.ms;extract(ctx,plate,'PLATE',axes,30);extract(ctx,host,'FRAME',axes,20);centre=par['centre'];_,bands=face_intervals(host,p,mul(axes[2],-1));across=cross(unit(sub(*host['axis'][::-1])),mul(axes[2],-1));ys=[]
        for i,(lo,hi,tt) in enumerate(bands):
            yy=(lo+hi)/2/dot(across,axes[1]);ys.append(yy)
            a.fastener('FLANGE'+str(i),[[centre[0]+x,yy,-7-CT] for x in (-1,1)],[0,0,1],.216,CT+par['host_t'],['PLATE','FRAME'],'S twoNo12 screws into this actual inside flange',basis='S count / A gauge',screw=True)
        assert len(ys)==6
        a.title='AG PORTAL / SOURCE SIX-FLANGE CROSS PLATE';a.front_axes=(0,1);a.section_axis=0;a.section_at=centre[0]+1;return
    angle,host=ctx.ms[:2];hs=[m for m in ctx.ms[2:] if m['id']!=par['plate_id']];side=par['side'];heel=par['heel'];head=par['head'];ct=par['foot_t'];width=par['foot_width'];count=par['count'];at=.125
    extract(ctx,angle,'ANGLE',axes,60);extract(ctx,host,'PRIMARY',axes,45)
    for i,m in enumerate(hs):extract(ctx,m,'SECONDARY'+str(i),axes,60)
    plate=next((m for m in ctx.ms if m['id']==par['plate_id']),None)
    if plate:extract(ctx,plate,'CROSS-PLATE',axes,30)
    along=unit(sub(head,heel));across=vector(angle['local_y'],axes)
    lowpts=[add(heel,add(mul(along,1+i*.75),across)) for i in range(count)];highpts=[add(head,add(mul(along,-1-i*.75),across)) for i in range(count)]
    x=heel[0]+side*at;z=par['lower_face'];vy=heel[1];corners=[(vy-width/2,z+ct),(vy+width/2,z+ct)]+[(q[1]+dy,q[2]+dz) for q in lowpts for dy,dz in ((-.35,-.35),(-.35,.35),(.35,-.35),(.35,.35))]
    a.polygon('LOW-W',[[x,y,zz] for y,zz in hull(corners)],ct,normal=[side,0,0],basis='S thickness / A outline' if par['post'] else 'A',description='Source post1/4in bent foot or A ordinary1/8in foot, actual angle leg plane')
    a.polygon('LOW-F',[[xx,y,z] for xx,y in ((x,vy-width/2),(x+side*4,vy-width/2),(x+side*4,vy+width/2),(x,vy+width/2))],ct,normal=[0,0,1],basis='S stock / A outline' if par['post'] else 'A',description='Source post3in foot width; actual outer-flange upper face')
    a.interfaces.append(dict(id='FOLD',kind='formed_bend',connects=['LOW-W','LOW-F'],basis='A',description='One continuous bent foot; exact radius omitted'))
    a.fastener('LOW-ANGLE',[[q[0]+side*(at+ct),q[1],q[2]] for q in lowpts],[-side,0,0],.216,at+ct,['ANGLE','LOW-W'],f'S {count} No12 per angle; A gauge',basis='S group / A fit',screw=True)
    stations=[(1.25,-.5),(2.75,-.5),(1.25,.5),(2.75,.5)] if count==4 else [(1.25,-.5),(2.75,-.5),(2,.5)]
    a.fastener('LOW-FRAME',[[x+side*xx,vy+yy,z+ct] for xx,yy in stations],[0,0,-1],.216,ct+par['host_t']+(CT if plate else 0),['LOW-F','PRIMARY']+(['CROSS-PLATE'] if plate else []),f'S {count} No12 per angle at source foot/actual flange; A set-out',basis='S group / A fit',screw=True)
    left=min(w[0] for w in par['webs']);right=max(w[1] for w in par['webs'])
    a.fastener('HIGH',[[q[0]+side*at,q[1],q[2]] for q in highpts],[-side,0,0],.216,at+right-left,['ANGLE']+['SECONDARY'+str(i) for i in range(len(hs))],f'S {count} No12 per angle at actual secondary web; A nested-web fit',basis='S group / A fit',screw=True)
    a.title='AG PORTAL / '+('SOURCE POST-TOP KICKER' if par['post'] else 'SOURCE30in FLANGE BRACE');a.front_axes=(1,2);a.section_axis=2;a.section_at=lowpts[0][2]
    a.dim(heel,head,'S26.9in source / A fitted45deg length' if par['post'] else 'S30in brace',basis='S/A' if par['post'] else 'S')
    a.notes.append('Source angles and total interface screw counts retained. The jamb pair has three screws per separate angle, six per interface; centre post three. A actual receiver geometry, source-pair screw distribution and folded foot fit require verification. Source26.9in post-kicker check remains distinct from its adopted fitted45deg length. One physical cross plate is shared by ordinary paired braces.')
