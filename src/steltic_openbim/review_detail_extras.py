"""Explicit assembled ancillary interfaces for the varied review buildings."""
import math
from .review_assemblies import *


def draw(ctx):
    {'review_kicker':kicker,'review_guard_connection':guard,'review_stair_clip':stair}[ctx.family](ctx)


def kicker(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params
    source=ctx.ms[0];v0=sub(source['axis'][1],source['axis'][0]);rise=abs(v0[2]);run=math.hypot(v0[0],v0[1]);length=math.hypot(run,rise)
    low=ctx.ms[1];high=ctx.ms[2];ld=effective(p,low['profile_id']);hd=effective(p,high['profile_id'])
    # Local Y is the kicker plane normal. Actual length and inclination come from its occurrence.
    a.member('LOW',low['profile_id'],[-24,0,ld/2],[24,0,ld/2])
    a.member('HIGH',high['profile_id'],[run,-24,rise],[run,24,rise],y=[1,0,0])
    vec=unit([run,0,rise]);perp=[-vec[2],0,vec[0]]
    a.member('K',ctx.pid,[0,.2,0],[run,.2,rise],y=[0,1,0],basis='A',description='Source kicker section; A length/fit '+ctx.pid)
    # Bent feet form an explicit load path from the angle leg to the two hosts.
    a.box('LOW-TAB',[-3,-2,-.125],[6,4,.125],'A','A 12 ga bent lower attachment foot')
    a.polygon('LOW-LEG',[[0,.075,-1],[6*vec[0],.075,6*vec[2]-1],[6*vec[0],.075,6*vec[2]+1],[0,.075,1]],.125,basis='A')
    a.box('HIGH-TAB',[run-.125,-2,rise-3],[.125,4,6],'A','A bent upper purlin-web attachment')
    a.polygon('HIGH-LEG',[[run-6*vec[0],.075,rise-6*vec[2]-1],[run,.075,rise-1],[run,.075,rise+1],[run-6*vec[0],.075,rise-6*vec[2]+1]],.125,basis='A')
    lower=int(par.get('lower_count',4));upper=int(par.get('upper_count',4));dia=.25 if par.get('stainless') else .216
    screw_label='1/4-14 stainless bi-metal' if par.get('stainless') else 'No.12'
    for tag,count,origin,step,tab in [('L',lower,[1,.2,0],vec,'LOW-LEG'),('U',upper,[run-1,.2,rise],mul(vec,-1),'HIGH-LEG')]:
        pts=[add(origin,mul(step,1+i)) for i in range(count)]
        a.fastener(tag,pts,[0,-1,0],dia,.25,['K',tab],f'{count} {screw_label} source end screws; A local stations',basis='A',screw=True)
    a.fastener('LF',[[-1,0,-.125],[1,0,-.125]],[0,0,1],dia,.25,['LOW','LOW-TAB'],'A lower bent foot attachment',basis='A',screw=True)
    a.fastener('UF',[[run-.125,y,rise] for y in (-1,1)],[1,0,0],dia,.25,['HIGH','HIGH-TAB'],'A upper bent foot attachment',basis='A',screw=True)
    a.weld('BL',[0,0,0],[2,0,0],['LOW-TAB','LOW-LEG'],kind='BEND',basis='A',description='Continuous bent sheet; no site weld')
    a.weld('BU',[run,0,rise-1],[run,0,rise+1],['HIGH-TAB','HIGH-LEG'],kind='BEND',basis='A',description='Continuous bent sheet; no site weld')
    a.dim([0,0,0],[run,0,rise],f'{length:g} in adopted kicker length',basis='A');a.section_axis=2;a.section_at=rise/2
    a.notes.append('Local bent-tab geometry is an A fit proposal. Source kicker counts/sections and corrosion requirements remain attached. Repeat on each explicitly modelled side of the frame; end-wall restraint is separate from the vertical-slip shoe.')


def guard(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params
    post=ctx.select(('guard_post',),ctx.pid);beam=ctx.select(('girder','walkway_edge_beam'),ctx.default_w());bd=effective(p,beam);bw=effective(p,beam,'width')
    if par.get('rail'):
        a.member('POST',post,[0,0,-24],[0,0,4]);a.member('RAIL',ctx.pid,[-24,0,0],[24,0,0],y=[0,0,1])
        a.box('CLIP',[-2,-.25,-3],[4,.25,6],'A','A rail-to-post face clip')
        a.fastener('F1',[[0,0,z] for z in (-2,2)],[0,-1,0],.216,.4,['POST','CLIP'],'A two No.12 rail clip screws',basis='A',screw=True)
        a.fastener('F2',[[x,0,0] for x in (-1,1)],[0,-1,0],.216,.4,['RAIL','CLIP'],'A two No.12 rail screws',basis='A',screw=True)
    else:
        a.member('EDGE',beam,[-24,0,-bd/2],[24,0,-bd/2]);pd=effective(p,post);pw=effective(p,post,'width');yy=bw/2+pd/2+.125
        a.member('POST',post,[0,yy,-10],[0,yy,42],y=[1,0,0]);grip=bw+pd+.125
        for j,z in enumerate((-3,-7)):a.cylinder('TUBE'+str(j),[0,-bw/2,z],[0,1,0],.75,grip,'A','A crush tube through source beam/post pack')
        a.fastener('F',[[0,-bw/2,z] for z in (-3,-7)],[0,1,0],.5,grip,['EDGE','POST','TUBE0','TUBE1'],'Source two 1/2 in through bolts; 4 in vertical pitch; A crush-tube cut length')
        a.dim([0,yy,-7],[0,yy,-3],'4 in bolt pitch');a.dim([0,yy,0],[0,yy,42],'42 in guard above floor');a.section_axis=2;a.section_at=-3
    a.notes.append('Guard/stair layout is an adopted test answer. Source guard post, bolt size and crush-tube requirement retained; top rail and infill fit are A. Guard infill/egress approval remains a design-review requirement.')


def stair(ctx):
    a,p=ctx.a,ctx.p;beam=ctx.select(('girder',),ctx.default_w());bd=effective(p,beam)
    if ctx.params.get('lower_landing'):
        member=a.member('STRINGER',ctx.pid,[-8,0,5.25],[30,0,30.5833],basis='A')
        clip_part(member,[0,0,1],.25)
        a.box('SLAB',[-16,-14,-6],[48,28,6],'S','Source 6 in existing slab; A local landing footprint',kind='concrete')
        for j,(yy,sign,t) in enumerate(web_faces(p,ctx.pid)):
            y=yy if sign>0 else yy-.25;tag='L'+str(j)
            a.box(tag,[-2,y,.25],[12,.25,12],'A','L4x4x1/4 source clip thickness; A fitted base leg')
            foot=y if sign>0 else y-3.75;a.box(tag+'F',[-2,foot,0],[12,4,.25],'A','A horizontal landing foot')
            a.fastener('B'+str(j),[[x,y+.25 if sign>0 else y,10.5833+x*2/3] for x in (0,2)], [0,-sign,0],.5,.25+t,['STRINGER',tag],'Source two 1/2 in stringer bolts; A fitted stations')
            a.fastener('A'+str(j),[[x,foot+2,-4] for x in (0,8)],[0,0,1],.5,4.25,['SLAB',tag+'F'],'A two 1/2 in landing anchors per clip, 4 in embedment; check slab reinforcement and edge distances',basis='A')
            a.weld('BEND'+str(j),[-2,y,.25],[10,y,.25],[tag,tag+'F'],kind='BEND',basis='A',description='A continuous formed base clip, no field weld')
        a.section_at=1;a.dim([0,0,-4],[0,0,0],'Adopted anchor embedment',basis='A');a.notes.append('Lower landing detail uses the existing slab. Anchor selection and the notched stringer foot are A test fit; source slab verification remains required.');return
    v=unit([18,0,12]);a.member('EDGE',beam,[-20,0,-bd/2],[20,0,-bd/2]);a.member('STRINGER',ctx.pid,mul(v,-36),[-2,0,-4],basis='A')
    # Source L4x4x1/4 clip, with each leg and its attachment visible.
    a.box('CLIP-V',[-4,.25,-10],[4,.25,8],'S','L4x4x1/4 receiving leg');a.box('CLIP-R',[-4,.25,-10],[.25,4,8],'S','L4x4x1/4 return leg')
    a.fastener('F1',[[-2,.5,z] for z in (-4,-8)],[0,-1,0],.5,.5,['STRINGER','CLIP-V'],'Source two 1/2 in through-bolts to stringer; A stations')
    a.fastener('F2',[[-4,y,z] for y,z in ((1.5,-4),(2.5,-8))],[1,0,0],.5,.6,['EDGE','CLIP-R'],'A two receiving-member bolts',basis='A')
    a.section_at=-3;a.dim([-2,0,-8],[-2,0,-4],'4 in adopted pitch',basis='A')
    a.notes.append('Upper landing interface; the lower landing has a separate anchored slab detail. Stair geometry and bearing support are fictional test inputs; no stair/egress capacity approval is inferred.')


def endpost(ctx,base=False):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);w=effective(p,pid,'width');faces=web_faces(p,pid)
    a.member('POST',pid,[0,0,0],[0,0,30],y=[1,0,0]);xfaces=[(xx,sg,t) for xx,sg,t in faces]
    if base:
        a.box('CONC',[-14,-14,-12],[28,28,12],'A','Slab context',kind='concrete')
        for j,(xx,sg,web) in enumerate(xfaces):
            label='L'+str(j);x=xx if sg>0 else xx-.25
            a.box(label,[x,-2,0],[.25,4,8],'S','L4x4x1/4 upright leg at actual post web');foot=x if sg>0 else x-3.75
            a.box(label+'F',[foot,-2,0],[4,4,.25],'S','Angle foot')
            a.fastener('B'+str(j),[[x+.25 if sg>0 else x,0,z] for z in (2,5)],[-sg,0,0],.5,.25+web,['POST',label],'2 x 1/2 in bolts into actual post web per clip')
            a.fastener('A'+str(j),[[foot+2,0,-7]],[0,0,1],.625,7.25,['CONC',label+'F'],'5/8 in anchor; A 7 in embedment',basis='A')
    else:
        rp=ctx.select(('rafter','beam'),ctx.default_w());rd=effective(p,rp);source=next((m for m in ctx.ms if m['kind'] in ('rafter','beam')),None)
        pitch=(source['axis'][1][2]-source['axis'][0][2])/max(.001,math.dist(source['axis'][0][:2],source['axis'][1][:2])) if source else 0
        centre=30+rd/2+abs(pitch)*max(4,w/2)+.5
        a.member('RAFTER',rp,[-24,0,centre-24*pitch],[24,0,centre+24*pitch]);a.box('SHOE',[-5,-d/2-.5,30],[10,d+1,.25],'A','A level slip-shoe head; roof-slope packer above')
        # Wedge packer follows the actual roof slope and maintains post clearance.
        low=centre-rd/2
        a.polygon('PACKER',[[-5,-d/2,30.25],[5,-d/2,30.25],[5,-d/2,low+5*pitch],[-5,-d/2,low-5*pitch]],d,basis='A',description='A fitted roof-slope wedge')
        for j,(xx,sg,web) in enumerate(xfaces):
            x=xx if sg>0 else xx-.25;label='SLIP'+str(j);a.box(label,[x,-2,18],[.25,4,12],'A','Vertical slip leg; 1-1/2 in vertical slots (A)')
            a.fastener('F'+str(j),[[x+.25 if sg>0 else x,0,z] for z in (22,26)],[-sg,0,0],.5,.25+web,['POST',label],'Source post-top restraint; A bolt stations/slot travel')
            a.weld('W'+str(j),[x,-2,30],[x,2,30],[label,'SHOE'],.1875,basis='A')
        a.fastener('TOP',[[x,0,30] for x in (-3,3)],[0,0,1],.5,low-30+.15,['SHOE','PACKER','RAFTER'],'A top-shoe fixing; local grip follows slope envelope',basis='A')
        a.notes.append('Post-top shoe is vertically slotted: source lateral reaction transfers through the separately detailed kicker to the end-bay purlin. The wedge follows the actual roof pitch. No moment connection or gravity support of the rafter is implied.')
    a.section_axis=2;a.section_at=2 if base else 22;a.dim([0,-d/2,0],[0,d/2,0],f'{d:g} in post depth',view='section')


def beam_clip(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;host=ctx.select(('column','walkway_post','prop','chord','opening_jamb','endwall_post'),ctx.default_w());hd=effective(p,host);bd=effective(p,pid);hw=effective(p,host,'width')
    a.member('POST',host,[-hd/2,0,-bd-12],[-hd/2,0,16]);a.member('BEAM',pid,[.25,0,-bd/2],[30,0,-bd/2]);bt=p[pid]['dimensions'].get('tw',p[pid]['dimensions'].get('t',.1017))
    faces=web_faces(p,pid);count=par.get('count',2);dia=par.get('diameter',.5);pc=par.get('post_count',4)
    for j,(yy,sg,web) in enumerate(faces):
        side='L'+str(j);t=.375 if dia==.75 else .25;height=min(8,bd-1);z=-bd/2-height/2
        y=yy if sg>0 else yy-t;a.box(side,[.25,y,z],[6,t,height],'A','Source clip angle / A web leg fit');a.box(side+'R',[0,y if sg>0 else y-4,z],[t,4,height],'A','Receiving leg')
        a.fastener('B'+str(j),[[3,y+t if sg>0 else y,z+height/2+(r-(count-1)/2)*3] for r in range(count)],[0,-sg,0],dia,t+web,['BEAM',side],f'{count} x {dia:g} in web bolts per clip; A stations')
        a.fastener('P'+str(j),[[t,y+sg*2,z+1+(r*(height-2)/max(1,pc-1))] for r in range(pc)],[-1,0,0],dia,t+.15,['POST',side+'R'],f'{pc} x {dia:g} in receiving-post bolts; A local fit',basis='A')
    a.section_at=3;a.dim([.25,0,0],[6.25,0,0],'6 in clip leg (A)',basis='A');a.notes.append('Clip pattern is repeated at every actual web/ply. Source bolt size and listed counts retained where scheduled; receiving attachment geometry is explicitly A where the source delegates it.')


def joist_clip(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;host=ctx.select(('girder','walkway_edge_beam','beam'),ctx.default_w());hd=effective(p,host);jd=effective(p,pid);t=.0566;web=p[pid]['dimensions'].get('t',.0713)
    a.member('BEAM',host,[0,-24,-hd/2],[0,24,-hd/2],y=[1,0,0]);host_t=p[host]['dimensions'].get('tw',p[host]['dimensions'].get('t',.1017));face=host_t/2
    # Clip seats between host flanges; joist top is below their underside.
    drop=p[host]['dimensions'].get('tf',.15)+.125
    a.member('JOIST',pid,[face+.25,0,-jd/2-drop],[face+30,0,-jd/2-drop]);a.box('CLIP-J',[face,web/2,-jd+1-drop],[3,t,jd-2],'A','L3x3x54 mil clip / A fitted length');a.box('CLIP-B',[face,web/2,-jd+1-drop],[t,3,jd-2],'A','Receiving clip leg')
    n=par.get('screws',4);dia=screw_diameter(par.get('screw_size',10));z0=-jd+2-drop
    a.fastener('J',[[face+1.5,web/2+t,z0+r*(jd-4)/max(1,n-1)] for r in range(n)],[0,-1,0],dia,t+web,['JOIST','CLIP-J'],f'{n} No.{par.get("screw_size",10)} source joist-leg screws',screw=True)
    a.fastener('B',[[face+t,1.5,z0+r*(jd-4)/max(1,n-1)] for r in range(n)],[-1,0,0],dia,t+host_t,['BEAM','CLIP-B'],f'{n} source receiving-leg screws; A set-out',screw=True)
    a.section_at=face+1.5;a.dim([face,0,-jd],[face+3,0,-jd],'3 in clip leg')


def roof_seat(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;cp=next((m['profile_id'] for m in ctx.ms if m['kind']=='truss_chord'),pid);depth=effective(p,cp)
    sp=ctx.select(('stud','chord','column'),channel(p,'ASSEMBLY-WALL600',6,1.625,.0713,.5));tp=channel(p,'ASSEMBLY-TRACK600',6.2,1.5,.0713,0)
    if ctx.model['pilot'].startswith('hr'):
        sp=ctx.select(('beam','rafter','girder'),ctx.default_w());sd=effective(p,sp);a.member('STUD',sp,[-24,0,-sd/2],[24,0,-sd/2]);a.member('TRACK',sp,[24,0,-sd/2],[32,0,-sd/2],description='Continuation of source rafter')
    else:
        a.member('STUD',sp,[0,0,-30],[0,0,-.1],y=[1,0,0]);a.member('TRACK',tp,[-24,0,0],[24,0,0],y=[0,0,-1])
    a.member('CHORD',cp,[0,-6,depth/2+.25],[0,30,depth/2+.25],y=[1,0,0]);a.box('SEAT',[-4,-4,0],[8,8,.25],'A','A bearing/hold-down seat')
    if ctx.model['pilot'].startswith('hr'):
        basis='S' if ctx.model['pilot']=='hr33' else 'A'
        for j,x in enumerate((-2,2)):a.weld('UPLIFT'+str(j),[x,-1,0],[x,1,0],['SEAT','STUD'],.25,basis=basis,description=basis+': two 1/4 x 2 in joist seat uplift welds')
        a.weld('CHORD-SEAT',[-2,0,.25],[2,0,.25],['CHORD','SEAT'],.1875,basis='A',description='A supplier chord-to-seat weld');a.section_axis=1;a.section_at=0;return
    from .assembly_templates import group
    count,size=group(ctx.text,(4,12));dia=screw_diameter(size);faces=web_faces(p,cp);t=.0713 if '68' in ctx.text else .0566
    strap='strap' in ctx.text.lower();studfaces=web_faces(p,sp)
    for j,(xx,sg,web) in enumerate(faces):
        n=count//len(faces)+(j<count%len(faces));x=xx if sg>0 else xx-t;label='CLIP'+str(j);z0=.25 if not strap else -12
        a.box(label,[x,-2,z0],[t,4,depth-1-z0],'A','Source uplift '+('strap' if strap else 'clip')+' at actual chord web; A local fit')
        pts=[[x+t if sg>0 else x,-1+(r%2)*2,1+(r//2)*(depth-2)/max(1,math.ceil(n/2)-1)] for r in range(n)]
        a.fastener('SC'+str(j),pts,[-sg,0,0],dia,t+web,[label,'CHORD'],f'{n} of {count} source No.{size} screws into actual truss plies',screw=True)
        if strap:
            sx,ss,st=studfaces[min(j,len(studfaces)-1)];sx=sx if ss>0 else sx-t
            a.box(label+'LOW',[sx,-2,-12],[t,4,10],'A','Strap lower leg at actual stud web')
            a.box(label+'OFFSET',[min(x,sx),-2,-2],[abs(x-sx)+t,4,t],'A','A formed offset across top-track zone')
            pts=[[sx+t if ss>0 else sx,-1+(r%2)*2,-10+(r//2)*2] for r in range(n)]
            a.fastener('ST'+str(j),pts,[-ss,0,0],dia,t+st,[label+'LOW','STUD'],f'{n} of {count} source No.{size} screws into studs',screw=True)
        else:
            footx=x if sg>0 else x-3+t;a.box(label+'FOOT',[footx,-2,.25],[3,4,t],'A','Formed uplift clip foot')
            pts=[[footx+.5+(r%2),-1+(r//2)*.7,.25+t] for r in range(n)]
            a.fastener('ST'+str(j),pts,[0,0,-1],dia,t+.25+.0713,[label+'FOOT','SEAT','TRACK'],f'{n} of {count} source No.{size} screws through seat to top track; A longer procurement length',screw=True)
            a.weld('BEND'+str(j),[x,-2,.25],[x,2,.25],[label,label+'FOOT'],kind='BEND',basis='A',description='One formed clip; no site weld')
    a.section_axis=1;a.section_at=0;a.dim([0,-4,0],[0,4,0],'8 in adopted seat',basis='A');a.notes.append('Explicit roof/floor truss-to-bearing interface. Supplier anchorage demand is retained; seat and uplift attachment fit is A pending supplier approval.')
