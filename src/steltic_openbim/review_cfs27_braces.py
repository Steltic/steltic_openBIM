"""Located source torsion braces, including both end-wall kicker screw groups."""
import math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,point,vector
from .review_cfs25_secondary import sections
from .review_sbmf_girts import cross_section
from .review_assemblies import hull
from .review_cfs27_secondary import STATIONS


def apply(b):
    if b.key!='cfs27':return
    removed={m['id'] for m in b.members if m['id'].startswith('FB-')}
    b.members[:]=[m for m in b.members if m['id'] not in removed]
    b.connections[:]=[c for c in b.connections if removed.intersection(c['member_ids'])==set()]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in removed]
    lookup={m['id']:m for m in b.members};count=0
    def build(tag,host,base,axes,dir,low_v,targets,side=-1,source_post=False,screws=2,foot_width=3):
        nonlocal count
        u,v,n=axes;ht=b.profiles[host['profile_id']]['dimensions'].get('t',.1017)
        if b.profiles[host['profile_id']]['family']=='built_up':ht=b.profiles[b.profiles[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
        hs=[m for m in targets if min(q[1] for q in [point(x,base,axes) for x in axis(m)])<=dir*18<=max(q[1] for q in [point(x,base,axes) for x in axis(m)])]
        if not hs:raise ValueError('No actual secondary receiver for '+tag)
        shapes=[sections(m,b.profiles,base,axes) for m in hs];webs=[]
        for polygons in shapes:
            web=max((p for p in polygons if max(q[0] for q in p)-min(q[0] for q in p)<.3),key=lambda p:max(q[2] for q in p)-min(q[2] for q in p))
            webs.append((min(q[0] for q in web),max(q[0] for q in web),min(q[2] for q in web),max(q[2] for q in web)))
        face=min(w[0] for w in webs) if side<0 else max(w[1] for w in webs)
        zlow=min(q[2] for poly in cross_section(host,b.profiles,axes) for q in poly)+ht
        ct=.25 if source_post else .125;along=unit([0,dir,1]);across=cross([side,0,0],along)
        heel=[face,low_v,zlow+ct+max(0,-2*across[2])+.125]
        if host['kind']=='rafter' or host['kind']=='column':length=25.5
        else:
            mid=sum((max(w[2] for w in webs),min(w[3] for w in webs)))/2
            length=(mid+1.75*along[2]-across[2]-heel[2])/along[2]
        head=add(heel,mul(along,length))
        world=lambda q:add(base,add(mul(u,q[0]),add(mul(v,q[1]),mul(n,q[2]))))
        world_y=add(mul(u,across[0]),add(mul(v,across[1]),mul(n,across[2])))
        rid='schedules/sched-endwall' if source_post or host['kind'] in ('opening_jamb','endwall_post') else 'schedules/sched-torsion-brace'
        m=b.member(tag,'L2X2X1/8','flange_brace',world(heel),world(head),1,'A',records=[rid],local_y=world_y,
            source_kicker_angle_deg=45,source_kicker_length_in=25.5 if source_post else None,
            physical_fit_basis='S L2x2x1/8 and45deg. Source post-top kicker length25.5in and source end counts retained. A exact position, handed end frame and lower folded attachment; source capacities not reassigned.')
        c=b.connection(tag,'review_single_flybrace',base,[m,host,*hs],[rid],parameters=dict(actual_single_flybrace=True,axes=axes,side=side,heel=heel,head=head,
            lower_face=zlow,host_thickness=ht,webs=webs,screws=screws,foot_t=ct,foot_width=foot_width,source_post=source_post),title='SINGLE CHANNEL / ACTUAL SOURCE TORSION BRACE')
        for end in ('start','end'):b.endpoint_links.append(dict(member_id=tag,end=end,connection_id=c['id'],basis='One actual source angle, complete lower flange foot and upper secondary-web screw group.'))
        count+=1
    for i in range(31):
        y=i*78;direction=-1 if i==30 else 1
        for x in (STATIONS[j] for j in (0,2,4,5,7,9)):
            rside=int(x>216);host=lookup[f'F{i}-R{rside}'];u=unit(sub(*host['axis'][::-1]));v=[0,1,0];n=cross(u,v);base=[x,y,192+min(x,432-x)*2/9]
            targets=[m for m in b.members if m['kind']=='purlin' and m['id'].startswith(f'SC-P-{x:g}-')]
            build(f'SC-FLY-R-{i}-{x:g}',host,base,(u,v,n),direction,1.5*direction,targets)
            if i in (0,30) and x in (123,210,309):
                build(f'SC-POST-KICKER-{i}-{x:g}',host,base,(u,v,n),direction,1.5*direction,targets,side=1,source_post=True,screws=2 if x==210 else 5)
        for side in (0,1):
            out=-1 if side==0 else 1;u=[0,0,-out];v=[0,1,0];n=cross(u,v);host=lookup[f'F{i}-C{side}']
            for z in (24,84,144):
                targets=[m for m in b.members if m['kind']=='girt' and m['id'].startswith(f'SC-G-{side}-{z}-')]
                build(f'SC-FLY-C-{i}-{side}-{z}',host,[side*432,y,z],(u,v,n),direction,1.5*direction,targets)
    for host in list(b.members):
        if not host['id'].startswith(('DOOR-JAMB-','CENTRE-POST-')):continue
        end=0 if host['axis'][0][1]==0 else 1;out=-1 if end==0 else 1;x=host['axis'][0][0];n=[0,out,0];v=[1,0,0];u=cross(v,n)
        direction=1 if x<216 else -1;zvalues=(24,84,144,204) if host['kind']=='opening_jamb' else (204,)
        for z in zvalues:
            direction=(-1 if x<216 else 1) if z<168 else (1 if x<216 else -1)
            targets=[m for m in b.members if m['id'].startswith(f'END-G-{end}-') and abs(m['axis'][0][2]-z)<.01]
            build(f'SC-FLY-END-{host["id"]}-{z}',host,[x,host['axis'][0][1],z],(u,v,n),direction,.85*direction,targets,foot_width=1.25)
    b.changes.append(dict(kind='single_channel_source_torsion_restraints',removed_generic_members=sorted(removed),actual_restraints=count,
        basis='Source six roof torsion braces(P1/P3/P5 each slope) and six column braces per frame; source18 end-wall fly braces plus6 separate post-top kickers. Last frame handed inward for clear physical access.'))
    b.note('SINGLE-TORSION-BRACES','S:L2x2x1/8 torsion braces at every column girt and roofP1/P3/P5 each slope, twoNo12 screws each end. End-wall jambs have four fly braces each, centre posts one. Separate source25.5in45deg post-top kickers use FIVE No12 screws at each of three interfaces for jambs, TWO for centre posts, with1/4x3in folded feet. A ordinary brace length/set-out, lower foot shape, flange fasteners and inward last-frame hand are recorded; original member capacities are not extended to this fitted configuration.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=par['axes'];angle,host=ctx.ms[:2];hs=ctx.ms[2:];side=par['side'];heel=par['heel'];head=par['head'];ct=par['foot_t'];width=par['foot_width'];at=.125
    extract(ctx,angle,'ANGLE',axes,60);extract(ctx,host,'PRIMARY',axes,40)
    for i,m in enumerate(hs):extract(ctx,m,'Z'+str(i),axes,60)
    along=unit(sub(head,heel));across=vector(angle['local_y'],axes);count=par['screws'];pitch=.75 if count==5 else 1.5
    lowpts=[add(heel,add(mul(along,1+i*pitch),across)) for i in range(count)]
    highpts=[add(head,add(mul(along,-1-i*pitch),across)) for i in range(count)]
    x=heel[0]+side*at;z=par['lower_face'];vy=heel[1];corners=[(vy-width/2,z+ct),(vy+width/2,z+ct)]+[(q[1]+dy,q[2]+dz) for q in lowpts for dy,dz in ((-.4,-.4),(-.4,.4),(.4,-.4),(.4,.4))]
    a.polygon('LOW-W',[[x,y,zz] for y,zz in hull(corners)],ct,normal=[side,0,0],basis='S thickness / A fit' if par['source_post'] else 'A',description='Source post-kicker1/4in or A ordinary1/8in folded angle-receiving leg')
    a.polygon('LOW-F',[[xx,y,z] for xx,y in ((x,vy-width/2),(x+side*4,vy-width/2),(x+side*4,vy+width/2),(x,vy+width/2))],ct,normal=[0,0,1],basis='S stock / A outline' if par['source_post'] else 'A',description='Source post-kicker3in width; A ordinary foot and4in projection on actual lower-flange upper face')
    a.interfaces.append(dict(id='LOW-BEND',kind='formed_bend',connects=['LOW-W','LOW-F'],basis='A',description='One bent foot; exact outline/bend radius is adopted'))
    a.fastener('LOW-ANGLE',[[q[0]+side*(at+ct),q[1],q[2]] for q in lowpts],[-side,0,0],.216,at+ct,['ANGLE','LOW-W'],f'S {count} No12 angle-to-foot screws; A stations',basis='S group / A set-out',screw=True)
    stations=[(1.25,-.5),(2.25,-.5),(3.25,-.5),(1.75,.5),(2.75,.5)] if count==5 else [(1.5,0),(3,0)]
    a.fastener('LOW-PRIMARY',[[x+side*xx,vy+yy,z+ct] for xx,yy in stations],[0,0,-1],.216,ct+par['host_thickness'],['LOW-F','PRIMARY'],f'{"S" if par["source_post"] else "A"} {count} No12 foot-to-actual-flange screws',basis='S group / A set-out' if par['source_post'] else 'A',screw=True)
    left=min(w[0] for w in par['webs']);right=max(w[1] for w in par['webs'])
    a.fastener('HIGH',[[q[0]+side*at,q[1],q[2]] for q in highpts],[-side,0,0],.216,at+right-left,['ANGLE']+['Z'+str(i) for i in range(len(hs))],f'S {count} No12 screws into actual secondary web(s); A gauge',basis='S group / A set-out',screw=True)
    a.title='SINGLE CHANNEL / '+('SOURCE POST-TOP KICKER' if par['source_post'] else 'SOURCE TORSION FLY BRACE');a.front_axes=(1,2);a.section_axis=2;a.section_at=lowpts[0][2]
    a.dim(heel,head,'S25.5in /45deg' if par['source_post'] else 'S45deg / A cut length',basis='S' if par['source_post'] else 'S/A')
    a.notes.append('Source angle,45deg and each source screw group retained; post-kicker25.5in length is separate from ordinary torsion-brace length adoption. Actual primary flange and finite secondary webs are shown. A exact folds/bolt access/hand and local receiver capacity need verification. No centre weld or invented six-piece track is added.')
