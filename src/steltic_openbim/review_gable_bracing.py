"""HR31 source flange braces at actual purlin/girt webs and primary stiffeners.

All supplier section/clip/shim choices remain accepted fictional geometry (A).
Saved primary sizes, brace sections, lengths, stations and stiffeners stay S.
"""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import extract,point

AXES=([1,0,0],[0,1,0],[0,0,1]);X=[1,0,0]


def apply(b):
    if b.key!='hr31':return
    lookup={m['id']:m for m in b.members};old=[m for m in b.members if m['kind']=='flange_brace']
    removed={m['id'] for m in old}
    b.connections[:]=[c for c in b.connections if not any(mid in removed for mid in c['member_ids'])]
    b.members[:]=[m for m in b.members if m['id'] not in removed]
    source=b.record('connections','conn-flange-braces')
    roof=lambda y:312+min(y-480,1440-y)/4
    def roof_frame(y):
        h=unit([0,1,.25 if y<960 else -.25]);return h,cross(X,h)
    changes=[]
    # Purlin lower flange bears on the actual inclined rafter upper flange.
    for m in b.members:
        if m['kind']=='purlin':
            previous=copy.deepcopy(m);y=m['axis'][0][1];h,n=roof_frame(y)
            # Clear the actual knee end plate/column head at both eaves.
            if y==480:y+=18/math.sqrt(1.0625)
            elif y==1440:y-=18/math.sqrt(1.0625)
            offset=mul(n,b.depth('W27X94')/2+6)
            m['axis']=[add([q[0],y,roof(y)],offset) for q in m['axis']];m['local_y']=h
            changes.append(dict(id=m['id'],previous=previous,reason='A source top-bearing purlin datum and roof-plane roll'))
        elif m['kind']=='girt' and m['id'].startswith('GIRT-'):
            previous=copy.deepcopy(m);y=m['axis'][0][1];sg=-1 if y==480 else 1
            h=[0,0,-sg];n=[0,sg,0];offset=mul(n,b.depth('W24X84')/2+5)
            m['axis']=[add(q,offset) for q in m['axis']];m['local_y']=h
            changes.append(dict(id=m['id'],previous=previous,reason='A actual column outer-flange bearing and girt roll'))
    # Added supplier lines coincide with the source brace stations. Keep the
    # original five-foot purlin grid as well; these are explicit extra lines.
    secondary={}
    def line(tag,y,z,h,n,primary):
        stamp=(tag,round(y,6),round(z,6));existing=secondary.get(stamp)
        if existing:return existing
        depth=12 if tag=='PURLIN' else 10;pd=b.depth(primary['profile_id'])
        offset=mul(n,pd/2+depth/2);members=[]
        for bay in range(8):
            a=add([bay*300,y,z],offset);e=add([(bay+1)*300,y,z],offset)
            candidate=next((q for q in b.members if q['kind']==tag.lower() and math.dist(q['axis'][0],a)<1e-5 and math.dist(q['axis'][1],e)<1e-5),None)
            if candidate is None:
                candidate=b.member(f'FB-{tag}-{y:.6f}-{z:.6f}-{bay}', '1200Z300-97' if tag=='PURLIN' else '1000Z250-97',tag.lower(),a,e,2,'A',local_y=h)
            members.append(candidate)
        # Outer pairs require a real supplier cantilever receiver, not a loose
        # flange-brace end beyond the end frame. The added 36 in extensions
        # and their capacities are explicitly delegated.
        members[0]['end_offsets'][0][0]=-36;members[-1]['end_offsets'][1][0]=36
        secondary[stamp]=members;return members
    def braces(tag,i,station,primary,origin,h,n,length):
        rows=line('PURLIN' if tag=='RAFTER' else 'GIRT',origin[1],origin[2],h,n,primary)
        pd=b.profiles[primary['profile_id']]['dimensions'];width=4.5 if tag=='RAFTER' else 4.25;height=9 if tag=='RAFTER' else 8
        for side in (-1,1):
            u=unit(add(mul(X,side),n));normal=mul(h,-side);vy=cross(normal,u)
            foot=add(origin,add(mul(X,side*(pd['tw']/2+.5)),mul(n,-pd['d']/2+pd['tf']+.25)))
            heel=add(foot,mul(normal,.1875));head=add(heel,mul(u,length))
            m=b.member(f'{tag}-FB-ACTUAL-{i}-{station}-{side}','L2-1/2X2-1/2X1/4','flange_brace',heel,head,2,'S',records=[source],local_y=vy)
            sec=rows[max(0,min(7,int((origin[0]+side)/300)))]
            par=dict(actual_gable_brace=True,primary_h=h,depth_axis=n,brace_side=side,plate_width=width,plate_height=height,
                     source_brace_length=length,primary_origin=origin)
            b.connection(m['id']+'-FOOT','review_angle_clip',heel,[m,primary],[source],parameters=dict(par,end='foot'))
            b.connection(m['id']+'-HEAD','review_angle_clip',head,[m,sec],[source],parameters=dict(par,end='head'))
    for i,x in enumerate(range(0,2401,300)):
        for side,y0 in enumerate((480,1440)):
            sg=1 if side==0 else -1;primary=lookup[f'RAFTER-{i}-{side}']
            for j,distance in enumerate((18,120,240,360,480)):
                y=y0+sg*distance/math.sqrt(1.0625);h,n=roof_frame(y)
                braces('RAFTER',i,f'{side}-{j}',primary,[x,y,roof(y)],h,n,41.8)
            for z in (84,168,252,312):
                cols=[m for m in b.members if m['kind']=='column' and math.dist(m['axis'][0][:2],[x,y0])<.01 and min(q[2] for q in m['axis'])-.01<=z<=max(q[2] for q in m['axis'])+.01]
                if not cols:raise ValueError('No actual flange-braced column')
                primary=cols[-1];h=[0,0,sg];n=[0,-sg,0]
                braces('COLUMN',i,f'{side}-{z}',primary,[x,y0,z],h,n,37.8)
    # Replace end-only secondary cartoons with located clips on each actual
    # primary receiver, including support inside a cantilevered end span.
    used={m['id'] for rows in secondary.values() for m in rows}
    used.update(m['id'] for m in b.members if m['kind']=='purlin' or (m['kind']=='girt' and m['id'].startswith('GIRT-')))
    b.connections[:]=[c for c in b.connections if not (c['detail_ref']['id']=='review_angle_clip' and c['member_ids'][0] in used and not c.get('parameters',{}).get('actual_gable_brace'))]
    for m in [q for q in b.members if q['id'] in used]:
        h=m['local_y'];n=cross(X,h);is_roof=m['kind']=='purlin'
        for end,q in enumerate(m['axis']):
            candidates=[p for p in b.members if p['kind']==('rafter' if is_roof else 'column') and abs(p['axis'][0][0]-q[0])<.01]
            def distance(p):
                a,z=p['axis'];u=unit(sub(z,a));v=add(a,mul(u,max(0,min(math.dist(a,z),dot(sub(q,a),u)))));return math.dist(v,q)
            if is_roof:
                # At the ridge choose the roof plane carrying this purlin,
                # not the coincident end of the opposite inclined rafter.
                candidates=[v for v in candidates if abs(dot(unit(sub(*v['axis'][::-1])),h))>1-1e-6]
            host=min(candidates,key=distance)
            b.connection(m['id']+f'-ACTUAL-CLIP-{end}','review_angle_clip',q,[m,host],parameters=dict(actual_gable_secondary=True,primary_h=h,depth_axis=n,span_into=1 if end==0 else -1))
    # End-wall girts attach to actual HSS posts or the actual portal-column
    # web. A flat bracket spans the different receiving-face offsets.
    endgirts=[m for m in b.members if m['id'].startswith('END-GIRT-')]
    endids={m['id'] for m in endgirts}
    b.connections[:]=[c for c in b.connections if c['member_ids'][0] not in endids]
    for m in endgirts:
        previous=copy.deepcopy(m);wall=m['axis'][0][0];sg=-1 if wall==0 else 1
        n=[sg,0,0];h=[0,0,sg];offset=mul(n,b.profiles['W24X84']['dimensions']['bf']/2+5)
        m['axis']=[add(q,offset) for q in m['axis']];m['local_y']=h
        changes.append(dict(id=m['id'],previous=previous,reason='A end-wall girt offset and actual web/post brackets'))
        for end,q in enumerate(m['axis']):
            candidates=[v for v in b.members if v['kind'] in ('column','endwall_post') and math.dist(v['axis'][0][:2],[wall,q[1]])<.01 and min(p[2] for p in v['axis'])<=q[2]<=max(p[2] for p in v['axis'])]
            if not candidates:raise ValueError('End girt has no located post')
            host=candidates[-1]
            b.connection(m['id']+f'-ACTUAL-CLIP-{end}','review_angle_clip',q,[m,host],parameters=dict(actual_gable_secondary=True,endwall_girt=True,primary_h=h,depth_axis=n,span_axis=[0,1,0],span_into=1 if end==0 else -1))
    # Roof cladding now sits on the real purlin upper flanges.
    for panel in b.panels:
        if not panel['id'].startswith('HALL-ROOF-'):continue
        centre=sum(q[1] for q in panel['vertices'])/len(panel['vertices']);h,n=roof_frame(centre)
        panel['vertices']=[add(q,mul(n,b.depth('W27X94')/2+12)) for q in panel['vertices']]
    b.changes.append(dict(kind='source_gable_flange_bracing',previous_braces=old,secondary_changes=changes,first_rafter_brace_station_from_knee_node_in=18,
        basis='S source brace lengths, 10 ft intermediate rafter and 7 ft column stations, angle sections, partial-depth stiffeners and fasteners retained. A first rafter brace and purlin at18 in from the knee analysis node clear the actual column/end plate; the next source station remains120 in, so the maximum unbraced spacing is not increased. A supplier lines/36 in end extensions, fitted web shims, clips and exact interface coordinates; supplier/local/eccentric capacities remain unverified. Knee column brace uses the source 37.8 in upper bound because no shorter checked length is scheduled.'))
    b.note('GABLE-FLANGE-BRACING','S: paired L2-1/2x2-1/2x1/4 at 45 degrees, 41.8 in rafter braces and 37.8 in column braces, 3/8 x 4-1/2 x 9 in rafter and 3/8 x 4-1/4 x 8 in column partial stiffeners, 3/16 in fillets both sides, two 3/4 in pretensioned A325 bolts at 1-3/8 in gage, 3 in pitch and 1.25 in end distance. A: actual purlin/girt positions, extra lines at brace stations, 36 in end cantilevers, fitted web shims and supplier clips/bolts. Source supplier stiffness/strength requirements remain outstanding verification; geometry acceptance does not certify them. Source asks for a shorter knee column brace but gives no length; the scheduled 37.8 in bound is shown explicitly as A fit.')


def brace(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,host=ctx.ms;origin=ctx.c['point'];h=par['primary_h'];n=par['depth_axis'];sg=par['brace_side'];normal=mul(h,-sg);u=unit(sub(*m['axis'][::-1]));vy=m['local_y']
    extract(ctx,m,'BRACE',AXES,55);extract(ctx,host,'HOST',AXES,70)
    end=par['end'];t=.375
    if end=='foot':
        centre=point(par['primary_origin'],origin,AXES);d=p[host['profile_id']]['dimensions'];low=-d['d']/2+d['tf'];x=sg*d['tw']/2
        verts=[add(centre,add(add(mul(X,xx),mul(n,zz)),mul(h,-t/2))) for xx,zz in ((x,low),(x+sg*par['plate_width'],low),(x+sg*par['plate_width'],low+par['plate_height']),(x,low+par['plate_height']))]
        a.polygon('STIFFENER',verts,t,normal=h,basis='S',description='Source partial-depth stiffener at actual web and compression flange')
        for face in (-1,1):
            v=add(centre,add(mul(X,x),mul(h,face*t/2)))
            a.weld(f'WEB{face}',add(v,mul(n,low)),add(v,mul(n,low+par['plate_height'])),['HOST','STIFFENER'],.1875,description='S3/16 in fillet both sides along actual web')
            a.weld(f'FLANGE{face}',add(v,mul(n,low)),add(add(v,mul(n,low)),mul(X,sg*par['plate_width'])),['HOST','STIFFENER'],.1875,description='S3/16 in fillet both sides along compression flange')
        pts=[add(add(mul(u,distance),mul(vy,1.375)),mul(normal,-t)) for distance in (1.25,4.25)]
        a.fastener('BOLTS',pts,normal,.75,t+.25,['STIFFENER','BRACE'],'S two 3/4 in A325 pretensioned Class A STD; 3 in pitch,1.25 end,1-3/8 gage')
    else:
        sheet=p[host['profile_id']]['dimensions']['t'];shim=.1875-sheet/2
        # The angle lies on the same source stiffener plane at both ends.
        # Its far end therefore needs an explicit fitted shim at the thin web.
        v=[add(add(mul(u,x),mul(vy,y)),mul(normal,-shim)) for x,y in ((-6,0),(-.25,0),(-.25,2.5),(-6,2.5))]
        a.polygon('SHIM',v,shim,normal=normal,basis='A',description='A fitted supplier web shim; exact thickness closes the source stiffener-to-web plane difference')
        pts=[add(add(mul(u,-distance),mul(vy,1.375)),mul(normal,-shim-sheet)) for distance in (1.25,4.25)]
        a.fastener('BOLTS',pts,normal,.75,sheet+shim+.25,['HOST','SHIM','BRACE'],'A two 3/4 in supplier bolts at source 3 in pitch and1.25 in end distance',basis='A')
    a.front_axes=(0,2) if abs(h[1])>.5 else (0,1);a.section_axis=max(range(3),key=lambda i:abs(u[i]));a.section_at=0
    a.notes.append('S source angle and primary stiffener/bolts; A receiving supplier section, web shim and clip system. Actual member extracts are used at both ends. Source supplier stiffness and local strength checks remain required.')


def secondary(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,host=ctx.ms;h=par['primary_h'];n=par['depth_axis'];sg=par['span_into'];t=.25
    if par.get('endwall_girt'):return endwall_secondary(ctx)
    extract(ctx,m,'SECONDARY',AXES,50);extract(ctx,host,'PRIMARY',AXES,50)
    d=p[m['profile_id']]['dimensions'];face=d['t']/2;bottom=-d['d']/2
    def q(x,y,z):return add(mul(X,x),add(mul(h,y),mul(n,z)))
    # An angle clip outside the Z-section's lower flange: vertical leg bears
    # on the web; the other leg sits on the actual primary flange.
    a.polygon('WEB-LEG',[q(sg*x,face,z) for x,z in ((0,bottom),(6,bottom),(6,bottom+8),(0,bottom+8))],t,normal=h,basis='A',description='A1/4 in supplier clip web leg at actual secondary web')
    a.polygon('SEAT-LEG',[q(sg*x,y,bottom) for x,y in ((0,face+t),(6,face+t),(6,face+3.5),(0,face+3.5))],t,normal=n,basis='A',description='A folded supplier clip seat at primary flange')
    a.fastener('WEB-BOLTS',[q(sg*x,-face,bottom+5) for x in (1.5,4.5)],h,.625,d['t']+t,['SECONDARY','WEB-LEG'],'A two5/8 in supplier web bolts',basis='A')
    # Primary flange finite width limits the weld run at its end support.
    pd=p[host['profile_id']]['dimensions'];run=min(4.5,pd.get('bf',6)/2-.25)
    for i,y in enumerate((face+t,face+3.5)):
        a.weld('SEAT-WELD'+str(i),q(sg*.25,y,bottom),q(sg*run,y,bottom),['PRIMARY','SEAT-LEG'],.1875,basis='A',description='A supplier clip-to-actual-primary-flange fillet')
    a.interfaces.append(dict(id='FOLD',kind='continuous_folded_clip',connects=['WEB-LEG','SEAT-LEG'],basis='A',description='A folded clip envelope; bend radius omitted in design representation'))
    a.front_axes=(0,2) if abs(h[1])>.5 else (0,1);a.section_axis=max(range(3),key=lambda i:abs(h[i]));a.section_at=0


def endwall_secondary(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,host=ctx.ms;h=par['primary_h'];n=par['depth_axis'];span=par['span_axis'];sg=par['span_into'];t=.25
    extract(ctx,m,'SECONDARY',AXES,50);extract(ctx,host,'PRIMARY',AXES,50)
    d=p[m['profile_id']]['dimensions'];pd=p[host['profile_id']]['dimensions'];family=p[host['profile_id']]['family']
    receiver_face=pd['tw']/2 if family=='i' else pd['b']/2
    host_origin=point(host['axis'][0],ctx.c['point'],AXES);face=dot(host_origin,n)+receiver_face;web=d['t']/2
    def q(x,y,z):return add(mul(span,x),add(mul(h,y),mul(n,z)))
    a.polygon('BRACKET',[q(sg*x,web,z) for x,z in ((0,face),(6,face),(6,3),(0,3))],t,normal=h,basis='A',description='A1/4 in end-girt bracket from the actual column web or HSS face to the actual girt web')
    a.fastener('WEB-BOLTS',[q(sg*x,-web,0) for x in (1.5,4.5)],h,.625,d['t']+t,['SECONDARY','BRACKET'],'A two5/8 in supplier web bolts',basis='A')
    run=6 if family=='i' else pd['h']/2-.25
    for i,y in enumerate((web,web+t)):
        a.weld('HOST-WELD'+str(i),q(0,y,face),q(sg*run,y,face),['PRIMARY','BRACKET'],.1875,basis='A',description='A3/16 in end-girt bracket fillet both sides on actual receiver face')
    a.front_axes=(0,1);a.section_axis=2;a.section_at=web+.125
