"""CFS details built around actual receiving axes, profiles and section rolls."""
import copy,math
from .assembly_templates import effective,channel,screw_diameter,web_faces
from .pilots.geometry import strips
from .pilots.model import cross,unit,sub


def section_bounds(profiles,data):
    """Bounds of each actual strip in the horizontal section of a vertical shaft."""
    u=unit(sub(data['axis'][1],data['axis'][0]));y=data['local_y'];z=cross(u,y);o=data['axis'][0]
    if abs(u[2])<.999:raise ValueError('Wall attachment requires a vertical receiver')
    return [[[min(o[i]+y[i]*v[0]+z[i]*v[1] for v in poly),max(o[i]+y[i]*v[0]+z[i]*v[1] for v in poly)] for i in range(2)]
            for poly in strips(profiles[data['profile_id']],profiles)]


def flange_bounds(profiles,data):
    """Actual channel flanges, excluding the web and lip strips."""
    profile=profiles[data['profile_id']];indices=[];offset=0
    for comp in profile.get('components',[dict(profile_id=profile['id'])]):
        base=profiles[comp['profile_id']]
        if base['family']!='channel':raise ValueError('Jamb foot requires selected channel plies')
        indices.extend([offset+1,offset+(3 if base['dimensions']['lip'] else 2)])
        offset+=len(strips(base,profiles))
    bounds=section_bounds(profiles,data)
    return [bounds[i] for i in indices]


def member(a,label,data):
    return a.member(label,data['profile_id'],*data['axis'],y=data['local_y'],basis=data.get('basis','S'),description='Actual '+data['kind']+' '+data['profile_id'])


def jamb_base(ctx):
    a,p=ctx.a,ctx.p;data=ctx.params['physical_jamb_base'];j=member(a,'JAMB',data['jamb']);track=member(a,'TRACK',data['track']);t=.0566
    tt=p[data['track']['profile_id']]['dimensions']['t'];z=data['track']['axis'][0][2]+tt/2
    for index,bb in enumerate(flange_bounds(p,data['jamb'])):
        n=min(range(2),key=lambda i:bb[i][1]-bb[i][0]);v=1-n;side=1 if sum(bb[n])/2>data['jamb']['axis'][0][n] else -1
        face=bb[n][1 if side>0 else 0];web=bb[n][1]-bb[n][0];width=min(1.25,bb[v][1]-bb[v][0]-.3);centre=sum(bb[v])/2
        if width<.5:raise ValueError('Jamb flange too narrow for the proposed foot clip')
        name='ANGLE'+str(index);origin=[0.,0.,z];size=[0.,0.,4.]
        origin[n]=face if side>0 else face-t;origin[v]=centre-width/2;size[n]=t;size[v]=width
        a.box(name,origin,size,'A','A 54 mil jamb foot clip on the actual ply flange; 4 in upright')
        foot=list(origin);foot[n]=face-1.5 if side>0 else face;fs=list(size);fs[n]=1.5;fs[2]=t
        a.box(name+'F',foot,fs,'A','A 1.5 in inward foot seated on actual bottom-track web')
        screws=[]
        for zz in (2,3):
            q=[0.,0.,z+zz];q[n]=face+side*t;q[v]=centre;screws.append(q)
        normal=[0.,0.,0.];normal[n]=-side
        a.fastener('J'+str(index),screws,normal,.216,t+web,['JAMB',name],'A two No.12 screws into this jamb ply flange',basis='A',screw=True)
        screws=[]
        for delta in (-width/4,width/4):
            q=[0.,0.,z+t];q[n]=face-side*.75;q[v]=centre+delta;screws.append(q)
        a.fastener('T'+str(index),screws,[0,0,-1],.216,t+tt,['TRACK',name+'F'],'A two No.12 foot-to-track-web screws',basis='A',screw=True)
        q0=list(origin);q1=list(origin);q0[n]=q1[n]=face;q1[v]+=width
        a.weld('BEND'+str(index),q0,q1,[name,name+'F'],kind='BEND',basis='A',description='Continuous formed foot angle')
    a.section_axis=2;a.section_at=z+2
    a.notes.append('Jamb foot clips fasten to the actual bottom track. Track anchorage to floor/foundation is shown separately. This A attachment has no new capacity verification; the source header/jamb design is retained on the header joint, not misapplied to the foot.')


def header(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;data=par['physical_opening_joint'];h=data['primary'];j=data['support']
    member(a,'HEADER',h);member(a,'JAMB',j);hd=effective(p,h['profile_id'])
    t=par.get('source_header_clip_t',.0566);count=par.get('source_header_screws',6);size=par.get('source_header_screw_size',12);dia=screw_diameter(size)
    # Use the open side of each header web. The back faces of back-to-back
    # channels lie in the narrow inter-ply gap and cannot receive these angles.
    hy=h['local_y'][1]
    if abs(hy)<.999:raise ValueError('Header web orientation needs a fitted local recipe')
    faces=[(h['axis'][0][1]+hy*(yy-sg*web),-sg*hy,web) for yy,sg,web in web_faces(p,h['profile_id'])];z=sum(q[2] for q in h['axis'])/2;lo=z-hd/2+.5
    planes=[bb for bb in section_bounds(p,j) if bb[0][1]-bb[0][0]<.3 and bb[1][1]-bb[1][0]>.8]
    for index,(yy,sg,web) in enumerate(faces):
        available=[bb for bb in planes if all(bb[1][0]+.1<=yy+sg*s<=bb[1][1]-.1 for s in (.35,1.1))]
        if not available:raise ValueError('Header angle has no actual jamb web/flange for its return')
        jb=max(available,key=lambda bb:bb[0][1]);face=jb[0][1];jt=jb[0][1]-jb[0][0];leg=min(1.5,sg*(jb[1][1 if sg>0 else 0]-yy)-.1)
        n=count//len(faces)+(index<count%len(faces));tag='CLIP'+str(index);height=hd-1;start=min(q[0] for q in h['axis']);reach=start-face+2.25
        a.box(tag,[face,yy if sg>0 else yy-t,lo],[reach,t,height],'A','Source clip thickness; A fitted header leg to actual jamb plane')
        a.box(tag+'R',[face,yy-leg if sg<0 else yy,lo],[t,leg,height],'A','A fitted return on actual jamb web/flange')
        zs=[lo+.5+i*(height-1)/max(1,n-1) for i in range(n)]
        a.fastener('H'+str(index),[[start+.75,yy+sg*t,zz] for zz in zs],[0,-sg,0],dia,t+web,['HEADER',tag],f'{n} of {count} No.{size} header screws; A stations',basis='S' if 'source_header_screws' in par else 'A',screw=True)
        a.fastener('J'+str(index),[[face+t,yy+sg*leg/2,zz] for zz in zs],[-1,0,0],dia,t+jt,['JAMB',tag+'R'],f'{n} of {count} No.{size} jamb screws; A stations/grip',basis='S' if 'source_header_screws' in par else 'A',screw=True)
        a.weld('BEND'+str(index),[face+t,yy,lo],[face+t,yy,lo+height],[tag,tag+'R'],kind='BEND',basis='A',description='Continuous formed angle, not a weld')
    a.section_axis=2;a.section_at=z;a.dim([face,0,lo],[face,0,lo+hd-1],basis='A')
    a.notes.append('Header/sill centroid is the actual model datum. The end is cut 1/8 in clear of the actual jamb face. Clip shape, individual-ply distribution and screw stations are accepted A fit; source selection and delegated verification remain attached.')


def bridging(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;data=par['physical_wall_attachment'];bridge=data['primary'];stud=data['stud']
    bp=member(a,'BRIDGE',bridge);sp=member(a,'STUD',stud)
    # A folded end clip reaches from the actual bridging web to the actual stud
    # web. The old recipe displaced the bridging six inches above its workline.
    x=stud['axis'][0][0];t=.0566;z=bridge['axis'][0][2];depth=effective(p,stud['profile_id']);count=par.get('screw_count',2)
    lo,hi=sorted(q[0] for q in bridge['axis']);into=1 if (lo+hi)/2>x else -1
    x=data['web_face_in'];st=data['web_thickness_in'];bt=p[bridge['profile_id']]['dimensions']['t']
    by=bridge['local_y'][1];back=-by;bx=x+into*1.5;y=bridge['axis'][0][1]+back*bt/2;cliplo=x if into>0 else x-3
    a.box('CLIP-B',[cliplo,y if back>0 else y-t,z-.65],[3,t,1.3],'A','A 54 mil bridging-web clip')
    a.box('CLIP-S',[x if into>0 else x-t,-depth/2+.35,z-2],[t,depth-.7,4],'A','A folded return on actual outer stud/chord web')
    a.fastener('BRIDGE-S',[[bx+into*(i-(count-1)/2)*.5,y+back*t,z] for i in range(count)],[0,-back,0],.19,t+bt,['BRIDGE','CLIP-B'],f'{count} No.10 bridging screws; A local positions',basis='A',screw=True)
    a.fastener('STUD-S',[[x+into*t,.75,z-1+i*2/max(1,count-1)] for i in range(count)],[-into,0,0],.19,t+st,['STUD','CLIP-S'],f'{count} No.10 support screws into actual web; A pattern',basis='A',screw=True)
    a.weld('FOLD',[x,y,z-.65],[x,y,z+.65],['CLIP-B','CLIP-S'],kind='BEND',basis='A',description='A formed bridging end clip')
    a.section_axis=2;a.section_at=z;a.notes.append('Actual bridging and receiving stud/chord are located at this workpoint. End clip dimensions and fastening are explicit A coordination inputs; required source bracing force and capacity checks are retained.')


def sheathing(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;data=par['physical_wall_attachment'];stud=data['stud'];track=data['primary']
    sp=member(a,'STUD',stud);tp=member(a,'TRACK',track);t=par['thickness'];edge=max(1,float(par.get('edge_spacing',6)));fs=par.get('fastener_number',8)
    x=stud['axis'][0][0];lo=max(sp['bounds'][2][0],tp['bounds'][2][0]);hi=sp['bounds'][2][1];left=max(tp['bounds'][0][0],x-12);right=min(tp['bounds'][0][1],x+24)
    for side in (1,-1) if par['faces']==2 else (1,):
        name='SHEET'+str(side);surface=sp['bounds'][1][1 if side>0 else 0];yy=surface if side>0 else surface-t
        a.box(name,[left,yy,lo],[right-left,t,hi-lo],'S',str(par.get('material','Sheathing'))+' source thickness / actual wall face',kind='panel')
        # Stud flange centres follow the real built-up/chord section. The outer
        # ply flange provides the exposed sheet fixing face.
        fx=max(left+.5,min(right-.5,x+.75));zs=[];z=lo+.5
        while z<hi-.3:zs.append(z);z+=edge
        if zs:a.fastener('EDGE'+str(side),[[fx,surface+side*t,z] for z in zs],[0,-side,0],screw_diameter(fs),t+.125,['STUD',name],f'No.{fs} at {edge:g} in source edge spacing; A starting station/grip',screw=True)
        trackface=tp['bounds'][1][1 if side>0 else 0];tz=min(tp['bounds'][2][1]-.25,max(tp['bounds'][2][0]+.25,lo+.5));xs=[];xx=left+.5
        while xx<right-.3:xs.append(xx);xx+=edge
        if xs:a.fastener('TRACK-S'+str(side),[[xx,trackface+side*t,tz] for xx in xs],[0,-side,0],screw_diameter(fs),t+.125,['TRACK',name],f'No.{fs} source edge spacing on track; A end margin/grip',screw=True)
    a.section_axis=2;a.section_at=min(hi-.5,lo+12);a.notes.append('Sheet fastening is shown on every specified face. The receiving stud/chord is the actual member at this bay, including its built-up plies; no generic stud is inserted at the wall-segment origin.')


def floor(ctx):
    if ctx.params['physical_floor_stack'].get('truss_ids'):return truss_floor(ctx)
    a,p,par=ctx.a,ctx.p,ctx.params;data=par['physical_floor_stack'];parts={};by_id={};joists=[];tracks=[];studs=[]
    for index,item in enumerate(data['receivers']):
        label='R'+str(index+1);part=member(a,label,item);parts[label]=part;by_id[item['member_id']]=(label,item,part)
        if item['member_id'] in data['joist_ids']:
            # A built-up trimmer has real, separated channel webs. Hardware
            # acts on those plies, while the receiver remains the original
            # built-up physical member. Do not use a fictitious centre web.
            if abs(item['axis'][1][1]-item['axis'][0][1])>abs(item['axis'][1][0]-item['axis'][0][0]):
                joists.extend((label,ply,part) for ply in channel_plies(p,item))
            else:joists.append((label,item,part))
        elif item['member_id'] in data['stud_ids']:studs.append((label,item,part))
        else:tracks.append((label,item,part))
    for index,(label,j,part) in enumerate(joists):
        if abs(j['axis'][1][0]-j['axis'][0][0])>abs(j['axis'][1][1]-j['axis'][0][1]):
            parallel_floor(a,p,index,label,j,part,tracks,studs)
            continue
        jd=effective(p,j['profile_id']);jt=p[j['profile_id']]['dimensions'].get('t',.0713);x=j['axis'][0][0];z=j['axis'][0][2];side=1 if sum(q[1] for q in j['axis'])>0 else -1
        low,high=z-jd/2,z+jd/2;lower=[v for v in tracks if v[1]['axis'][0][2]<=low+.25 and v[1]['local_y'][2]<-.9]
        width_sign=1 if j['local_y'][0]>0 else -1
        screw_xy=[x+width_sign*.75,side*.75]
        def overlaps(row):return all(lo+.25<=q<=hi-.25 for q,(lo,hi) in zip(screw_xy,row[2]['bounds'][:2]))
        support=min(lower,key=lambda v:(not overlaps(v),abs(v[1]['axis'][0][2]-low))) if lower else None
        upper=[v for v in tracks if v[1]['axis'][0][2]>=high-.25 and v[1]['local_y'][2]>.9]
        upper=min(upper,key=lambda v:(not overlaps(v),abs(v[1]['axis'][0][2]-high))) if upper else None
        # Source stiffener channel is an added connection component. It is not
        # falsely claimed as a pre-existing wall member in the receiver list.
        stiff=channel(p,'ASSEMBLY-STIFF362',3.625,1.625,.0566,.5);sname='STIFF'+str(index)
        sx=x+width_sign*(jt/2+3.625/2+.0566/2);sy=side*1.25
        a.member(sname,stiff,[sx,sy,low+.1],[sx,sy,high-.1],y=[0,side,0],basis='S scheduled section; A cut and fit',representation_role='assembly_component',description='362S162-54 bearing stiffener; A local cut length / orientation')
        a.fastener('STIFF-S'+str(index),[[x+width_sign*(jt/2+.0566),sy+side*.75,zz] for zz in (low+1.5,z,high-1.5)],[-width_sign,0,0],.19,.0566+jt,[label,sname],'A three No.10 stiffener flange to actual joist web',basis='A',screw=True)
        if support and not overlaps(support):
            track_end_clip(a,p,index,label,j,support,low,side,-1)
        elif support:
            sl,sm,sp=support;surface=sp['bounds'][2][1];gap=low-surface;joins=[label,sname,sl]
            tt=p[sm['profile_id']]['dimensions']['t']
            if gap>.02:
                pack='PACK'+str(index);px=sorted((x-width_sign*jt/2,x+width_sign*(p[j['profile_id']]['dimensions']['b']-jt/2)))
                a.box(pack,[px[0],min(0,side*2.5),surface],[px[1]-px[0],2.5,gap],'A','A steel bearing packer under this actual channel flange; separate plies do not duplicate overlapping pack solids');joins.append(pack)
            a.interfaces.append(dict(id='BEAR'+str(index),kind='compression_bearing',connects=joins,basis='A',description='Actual joist and lower track; local packer/stiffener fit requires capacity verification'))
            a.fastener('LOWER-S'+str(index),[[x+width_sign*.75,side*.75,low+jt]],[0,0,-1],.216,jt+max(0,gap)+tt,[label,sl]+([pack] if gap>.02 else []),'A No.12 lower flange/track transfer screw; source spacing schedule remains attached',basis='A',screw=True)
        if upper and not overlaps(upper):
            track_end_clip(a,p,index,label,j,upper,high,side,1)
        elif upper:
            ul,um,up=upper;surface=up['bounds'][2][0];gap=surface-high;joins=[label,ul]
            tt=p[um['profile_id']]['dimensions']['t']
            if gap>.02:
                pack='UP-PACK'+str(index);px=sorted((x-width_sign*jt/2,x+width_sign*(p[j['profile_id']]['dimensions']['b']-jt/2)))
                a.box(pack,[px[0],min(0,side*2.5),high],[px[1]-px[0],2.5,gap],'A','A separate upper-wall packer on this actual channel flange; subfloor kept outside bearing strip');joins.append(pack)
            a.fastener('UPPER-S'+str(index),[[x+width_sign*.75,side*.75,surface+tt]],[0,0,-1],.216,jt+max(0,gap)+tt,joins,'A No.12 upper track/joist transfer screw; source diaphragm schedule remains attached',basis='A',screw=True)
    a.section_axis=1;a.section_at=1.25
    a.notes.append('Every wall, track and joist extract is bound to a real member at its actual centroid, elevation and roll. Only the connection stiffeners/packers are added components. Source selected sections and story shear/uplift requirements remain attached; A local fit and transfer fasteners are coordination proposals without new capacity verification. Stud-to-track end screws are shown on their separate located details.')


def channel_plies(profiles,item):
    """Actual horizontal channel constituents in the receiver's local frame."""
    profile=profiles[item['profile_id']]
    if profile['family']=='channel':return [item]
    if profile['family']!='built_up':raise ValueError('Floor attachment requires actual channel plies')
    axis=unit(sub(item['axis'][1],item['axis'][0]));y=item['local_y'];z=cross(axis,y);result=[]
    for comp in profile['components']:
        angle=math.radians(comp['rotation_deg']);ca,sa=math.cos(angle),math.sin(angle)
        if abs(sa)>1e-6:raise ValueError('Rotated floor-channel ply needs its actual web attachment recipe')
        ply=copy.deepcopy(item);ply['profile_id']=comp['profile_id']
        offset=[y[i]*comp['offset'][0]+z[i]*comp['offset'][1] for i in range(3)]
        ply['axis']=[[q[i]+offset[i] for i in range(3)] for q in item['axis']]
        ply['local_y']=[y[i]*ca+z[i]*sa for i in range(3)]
        result.extend(channel_plies(profiles,ply))
    return result


def track_end_clip(a,p,index,label,j,track,edge,side,end):
    """A declared return clip where a joist flange misses the cut track end.

    The screw cannot move through empty space or extend the actual track. A
    separate formed part connects the joist web to the available track web.
    """
    host,tm,tp=track;x=j['axis'][0][0];jt=p[j['profile_id']]['dimensions']['t'];tt=p[tm['profile_id']]['dimensions']['t'];t=.0713
    surface=tp['bounds'][2][1 if end<0 else 0];direction=1 if sum(tp['bounds'][0])/2>x else -1
    face=x+direction*jt/2
    first=tp['bounds'][0][0 if direction>0 else 1]
    reach=max(3.,direction*(first-face)+2.5)
    if reach>12:raise ValueError('Actual track is too far away for this local return-clip proposal')
    xs=sorted((face,face+direction*reach))
    left=max(xs[0],tp['bounds'][0][0])+.5;right=min(xs[1],tp['bounds'][0][1])-.5
    if right-left<.5:raise ValueError('Cut track has no room for the proposed return-clip foot')
    ylo,yhi=sorted((side*.35,side*2.35));y=(ylo+yhi)/2
    if not tp['bounds'][1][0]+.25<y<tp['bounds'][1][1]-.25:raise ValueError('Return clip misses the actual track web')
    tag=f'END-{index}-'+('LOW' if end<0 else 'UP');upright=tag+'-WEB';foot=tag+'-FOOT'
    z0,z1=(surface,edge+3) if end<0 else (edge-3,surface)
    if z1-z0<=0:raise ValueError('Return clip has no upright height')
    a.box(upright,[min(face,face+direction*t),ylo,z0],[t,yhi-ylo,z1-z0],'A','A 68 mil formed return at the actual cut track end; web attachment')
    a.box(foot,[xs[0],ylo,surface if end<0 else surface-t],[reach,yhi-ylo,t],'A','A formed return foot on actual track web; no track extension')
    zs=[edge-end*1.,edge-end*2.]
    a.fastener(tag+'-J',[[face+direction*t,y,z] for z in zs],[-direction,0,0],.216,t+jt,[label,upright],
               'A two No.12 web-to-return screws; local capacity unverified',basis='A',screw=True)
    start=surface+t if end<0 else surface+tt
    a.fastener(tag+'-T',[[q,y,start] for q in (left,right)],[0,0,-1],.216,t+tt,[host,foot],
               'A two No.12 return-foot-to-track screws within the actual cut end',basis='A',screw=True)
    a.weld(tag+'-BEND',[face,ylo,surface],[face,yhi,surface],[upright,foot],kind='BEND',basis='A',description='Continuous formed return, not a weld')
    a.notes.append('A: this joist flange is outside the cut track end. A 68 mil return clip transfers through the actual joist web and track web. No direct flange screw or direct bearing capacity is implied; this added local load path requires capacity verification.')


def truss_floor(ctx):
    """Actual open-web truss chords at the wall, without a fictitious solid joist."""
    a,p=ctx.a,ctx.p;data=ctx.params['physical_floor_stack'];tracks=[];chords=[]
    for index,item in enumerate(data['receivers']):
        name='R'+str(index+1);part=member(a,name,item)
        if item['member_id'] in data['truss_ids']:chords.append((name,item,part))
        elif item['member_id'] in data['track_ids']:tracks.append((name,item,part))
    for side in (-1,1):
        group=[row for row in chords if sum(q[1] for q in row[1]['axis'])*side>0]
        if not group:continue
        for end in (-1,1):
            label,m,part=(min if end<0 else max)(group,key=lambda row:row[2]['bounds'][2][0 if end<0 else 1])
            z=part['bounds'][2][0 if end<0 else 1]
            options=[row for row in tracks if row[1]['local_y'][2]*end>.9
                     and (row[2]['bounds'][2][1 if end<0 else 0]-z)*end>=-.03]
            if not options:continue
            host,tm,tp=min(options,key=lambda row:abs(row[1]['axis'][0][2]-z))
            surface=tp['bounds'][2][1 if end<0 else 0];gap=abs(surface-z)
            if gap>24:raise ValueError('Truss/wall interface has no adjacent physical track')
            x=m['axis'][0][0];yy=side*.75;joins=[label,host];suffix=f'{side}-{end}'
            if gap>.001:
                xl,xh=part['bounds'][0]
                pack='PACK'+suffix;a.box(pack,[xl-.25,-3,min(z,surface)],[xh-xl+.5,6,gap],'A','A fitted steel bearing pack at the actual truss/track gap; capacity unverified');joins.append(pack)
            tt=p[tm['profile_id']]['dimensions']['t'];hy=m['local_y'][0]
            if abs(hy)<.999:raise ValueError('Truss chord requires a fitted web orientation')
            for index,(face,sign,web) in enumerate(web_faces(p,m['profile_id'])):
                xx=x+hy*(face-sign*(web+.65))
                start=z+web if end<0 else surface+tt
                grip=web+gap+tt
                a.fastener('B'+suffix+'-'+str(index),[[xx,yy,start]],[0,0,-1],.375,grip,joins,
                    'A 3/8 in predrilled through-bolt through actual chord flange, bearing pack and track; no source uplift capacity inferred',basis='A')
            a.interfaces.append(dict(id='BEAR'+suffix,kind='compression_bearing',connects=joins,basis='A',
                                     description='Located truss/wall bearing interface; supplier end-node and source force requirements remain attached'))
    a.section_axis=1;a.section_at=.75
    a.notes.append('Both actual horizontal truss chords are shown at their recorded elevations. The open web is not replaced by a full-depth solid joist. End-node gussets and webs are separate located truss details. A bearing packs and predrilled bolts close the explicit track/chord gaps; their local capacity and supplier approval remain unverified.')


def parallel_floor(a,p,index,label,j,part,tracks,studs):
    """Rim joist parallel to the wall: do not rotate it into a bearing joist."""
    jd=effective(p,j['profile_id']);z=j['axis'][0][2];low,high=z-jd/2,z+jd/2
    side=1 if j['local_y'][1]>0 else -1
    for tag,end,surface_z in (('LOW',-1,low),('UP',1,high)):
        candidates=[v for v in tracks if abs(v[1]['axis'][0][2]-surface_z)<12 and v[1]['local_y'][2]*end>.9
                    and min(part['bounds'][0][1],v[2]['bounds'][0][1],7)-max(part['bounds'][0][0],v[2]['bounds'][0][0],-7)>2]
        if not candidates:continue
        host,data,bounds=min(candidates,key=lambda v:abs(v[1]['axis'][0][2]-surface_z))
        trackz=bounds['bounds'][2][1 if end<0 else 0];gap=abs(trackz-surface_z);joins=[label,host]
        xs=[max(part['bounds'][0][0]+1,bounds['bounds'][0][0]+1,-6),min(part['bounds'][0][1]-1,bounds['bounds'][0][1]-1,6)]
        if xs[1]<=xs[0]:raise ValueError('Parallel wall/joist has no physical attachment overlap')
        if gap>.15:
            name='RIM-PACK'+str(index)+tag;a.box(name,[xs[0]-.5,-2,min(trackz,surface_z)],[xs[1]-xs[0]+1,4,gap],'A','A steel rim/track packer; source local capacity remains to verify');joins.append(name)
        top=max(trackz,surface_z)+.15
        a.fastener('RIM-'+str(index)+tag,[[x,side*.75,top] for x in xs],[0,0,-1],.216,gap+.3,joins,'A two No.12 rim/track flange transfer screws; source full-line spacing remains attached',basis='A',screw=True)
    a.notes.append('This wall is parallel to the actual rim joist. No transverse pair of floor joists is invented. A rim/track transfer fit is shown at this station; source diaphragm and uplift force schedules remain applicable.')
