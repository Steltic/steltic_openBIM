"""HR33 source eave restraints, received by real eave beams and joist chords."""
import math
from .pilots.model import add,sub,mul,unit,cross
from .pilots.geometry import strips
from .review_receiver_geometry import extract,point
from .review_crossings import slot
from .review_assemblies import hull

AXES=([1,0,0],[0,1,0],[0,0,1])


def ends(m):return [add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]


def apply(b):
    if b.key!='hr33':return
    rid=b.record('connections','conn-rafter-bracing');lookup={m['id']:m for m in b.members}
    source=b.records[rid]['data']['components']
    if 'HSS3' not in source or 'HSS4' not in source:raise ValueError('Eave-bracing source changed')
    eaves=[m for m in b.members if m['profile_id']=='W12X26' and m['axis'][0][1] in (0,840)]
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for eave in eaves:
        start=min(q[0] for q in eave['axis']);y=eave['axis'][0][1];sg=1 if y==0 else -1
        ed=b.profiles[eave['profile_id']]['dimensions'];tos=ends(eave)[0][2]+ed['d']/2
        for station in (100,200):
            x=start+station;jy=y+sg*60;segment=int(station//30)
            top=lookup[f'ROOF-JOIST-{int(start)}-{int(jy)}-T{segment}'];bottom=lookup[f'ROOF-JOIST-{int(start)}-{int(jy)}-B{segment}']
            width=max(abs(q[0]) for poly in strips(b.profiles[top['profile_id']],b.profiles) for q in poly)
            receiver=jy-sg*width;z=tos-1.5-2;name=f'EAVE-BRACE-{int(start)}-{int(y)}-{station}'
            strut=b.member(name+'-STRUT','HSS4X4X1/4','lateral_strut',[x,y,z],[x,jy,z],1,'S',records=[rid],local_y=[1,0,0])
            strut['end_offsets']=[[0,sg*(ed['tw']/2+.375),0],[0,-sg*(width+.375),0]]
            rise=12/math.sqrt(2);head=[x,y+sg*(ed['bf']/2+3+rise),z-4.5];foot=add(head,[0,-sg*rise,-rise])
            kicker=b.member(name+'-KICKER','HSS3X3X1/4','flange_kicker',foot,head,1,'S',records=[rid],local_y=[1,0,0])
            direction=unit(sub(head,foot))
            for q,lo,hi in ((foot,0,3.5),(head,-3.5,0)):
                slot(kicker,q,[1,0,0],lo,hi,.5,name,'A1/2 in clearance for source3/8 in stiffener/clip; source3 in weld lines')
            c=b.connection(name,'review_hr_strut_bracing',[x,y,tos],[eave,top,bottom,strut,kicker],[rid],
                parameters=dict(crane_eave_bracing=True,sign=sg,station_in=station,joist_receiver_y=receiver-y,
                    source_strut_span_in=60,source_kicker_length_in=12),basis='S sections and restraint; A receiver fit')
            for m in (strut,kicker):
                for end in ('start','end'):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Both actual ends are detailed in this eave-restraint assembly'))
    b.note('EAVE-BRACE-FIT','S: HSS4X4X1/4 five-foot eave bracing struts, top1.5 in below eave TOS, with HSS3X3X1/4 twelve-inch45-degree kickers,3/8 in stiffeners/clips and3/16 in welds. A: two stations per25 ft bay at8 ft4 in and16 ft8 in (no interval exceeds source12 ft), end cutbacks, slotted outboard tabs and a dropped receiving plate welded to the actual paired supplier-joist chords. The saved source describes an adjacent beam web; the adopted open-web joist requires this explicit new receiver and supplier/local capacity verification. No beam web is invented inside its void.')


def draw(ctx):
    a,p=ctx.a,ctx.p;eave,top,bottom,strut,kicker=ctx.ms;origin=ctx.c['point'];sg=ctx.params['sign']
    for label,m,extent in (('EAVE',eave,28),('JOIST-TOP',top,35),('JOIST-BOTTOM',bottom,35),('STRUT',strut,70),('KICKER',kicker,20)):
        extract(ctx,m,label,AXES,extent)
    ed=p[eave['profile_id']]['dimensions'];z=ends(strut)[0][2]-origin[2];near=sg*ed['tw']/2;far=ctx.params['joist_receiver_y'];t=.375
    # Real web at the eave; explicit outside side plate at the open-web joist.
    a.box('END-PLATE',[-2.25,min(near,near+sg*t),z-2.25],[4.5,t,4.5],'A','A fitted3/8 in end plate on the actual eave web')
    lo=ends(bottom)[0][2]-origin[2]-1.25;hi=ends(top)[0][2]-origin[2]+1.25
    a.box('JOIST-RECEIVER',[-3,min(far,far-sg*t),lo],[6,t,hi-lo],'A','A dropped receiver plate outside the actual paired joist chord flange/lip faces; supplier capacity unverified')
    for name,m in [('JOIST-TOP',top),('JOIST-BOTTOM',bottom)]:
        centre=ends(m)[0][2]-origin[2]
        chord=p[m['profile_id']];sheet=p[chord['components'][0]['profile_id']]['dimensions']['t']
        for dz in (-1.25+sheet/2,1.25-sheet/2):
            a.weld(name+str(dz),[-3,far,centre+dz],[3,far,centre+dz],[name,'JOIST-RECEIVER'],.125,basis='A',description='A receiver weld at actual supplier chord outside flange/lip corner')
    for x in (-2.25,2.25):a.weld('EP'+str(x),[x,near,z-2.25],[x,near,z+2.25],['EAVE','END-PLATE'],.1875,basis='A')
    for label,yy in [('END-PLATE',near+sg*t),('JOIST-RECEIVER',far-sg*t)]:
        for xx in (-2,2):a.weld(label+str(xx),[xx,yy,z-1.5],[xx,yy,z+1.5],['STRUT',label],.1875,description='S two3 in3/16 in fillet lines at each strut end; A actual receiver')
    foot,head=[point(q,origin,AXES) for q in ends(kicker)];direction=unit(sub(head,foot));normal=cross([1,0,0],direction)
    # Source stiffener with an outboard lower tab clearing the actual flange.
    bd=-ed['d'];coords=[(ed['tw']/2,bd+ed['tf']),(ed['tw']/2,-ed['tf']),
        (ed['bf']/2+2,-ed['tf']),(ed['bf']/2+2,bd+2),(ed['bf']/2+9,bd+2),
        (ed['bf']/2+9,foot[2]-3),(ed['bf']/2+.125,foot[2]-3),(ed['bf']/2+.125,bd+ed['tf'])]
    a.polygon('STIFFENER',[[-t/2,sg*y,z0] for y,z0 in coords],t,normal=[1,0,0],basis='S thickness; A outline',description='S3/8 in stiffener; A outboard/notched receiving tab')
    for zz in (bd+ed['tf'],-ed['tf']):a.weld('SF'+str(zz),[0,near,zz],[0,sg*ed['bf']/2,zz],['EAVE','STIFFENER'],.1875,basis='A')
    a.weld('SW',[0,near,bd+ed['tf']],[0,near,-ed['tf']],['EAVE','STIFFENER'],.1875,basis='A')
    points=[]
    for q in (head,add(head,mul(direction,-3))):
        for side in (-1,1):
            v=add(q,mul(normal,side*1.5));points.extend([(v[1]+dy,v[2]+dz) for dy,dz in ((-1,-1),(-1,1),(1,-1),(1,1))])
    points.extend([(head[1]-3,z-2),(head[1]+3,z-2)])
    a.polygon('HEAD',[[-t/2,y,z0] for y,z0 in hull(points)],t,normal=[1,0,0],basis='A',description='A slotted head clip to actual strut underside')
    a.weld('HW',[0,head[1]-3,z-2],[0,head[1]+3,z-2],['HEAD','STRUT'],.1875,basis='A')
    for tag,q,travel,host in [('FOOT',foot,direction,'STIFFENER'),('HEAD',head,mul(direction,-1),'HEAD')]:
        # Two source3 in fillet lines, one on each side of the receiving plate.
        for side in (-1,1):
            start=add(q,add(mul(normal,1.5),[side*t/2,0,0]))
            a.weld(tag+str(side),start,add(start,mul(travel,3)),['KICKER',host],.1875,description='S two3 in3/16 in kicker end fillets; A slotted fit')
    a.front_axes=(1,2);a.section_axis=0;a.section_at=0
    a.dim([0,0,4],[0,sg*60,4],'S5 ft workline span; A end cutbacks')
    a.notes.append('S source sections, elevation, twelve-inch45-degree kicker and weld sizes/lengths. A smaller station spacing, slotted tab geometry and actual open-web-joist receiver. The source assumes an adjacent beam web; the adopted supplier joist is visibly different. Local/supplier strength and stiffness checks remain required.')
