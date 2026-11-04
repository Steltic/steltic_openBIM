"""Located plan-angle fittings for the fictional equipment platform.

Saved sections, plates and bolt counts remain source selections. The face fit,
angle handedness and the crossing spacer are explicitly accepted A geometry.
"""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import extract,point

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='hr35':return
    lookup={m['id']:m for m in b.members};levels={k:z for k,_,z in b.levels}
    # Original levels are supplied after this builder stage in some cases.
    if not levels:
        for m in b.members:
            if m['kind'] in ('beam','girder'):levels.setdefault(m['level'],m['axis'][0][2])
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for m in b.members:
        for rid in list(m.get('design_record_ids',[])):
            member_record=rid.replace('connections/conn-','members/',1)
            if member_record in b.records and member_record not in m['design_record_ids']:
                m['design_record_ids'].append(member_record);b.used_records.add(member_record)
    for m in b.members:
        if m['kind']!='plan_brace':continue
        old=dict(axis=copy.deepcopy(m['axis']),local_y=list(m['local_y']),end_offsets=copy.deepcopy(m['end_offsets']))
        u=unit(sub(m['axis'][1],m['axis'][0]));lower=m['id'].startswith('PLAN-') and m['id'].endswith('-A')
        y=mul(cross([0,0,1],u),-1 if lower else 1);m['local_y']=y
        d=b.profiles[m['profile_id']]['dimensions'];z=levels[m['level']]+(0 if lower else .375)
        for end in range(2):
            m['end_offsets'][end]=add(mul(y,-d['b']/2),[0,0,z-m['axis'][end][2]])
        m['plan_fit']=dict(lower_face=lower,plate_thickness_in=.375)
        b.changes.append(dict(kind='plan_angle_leg_orientation',member_id=m['id'],previous=old,
            basis='S selected single angle and source workline. A horizontal connected leg centred on that workline; A diagonals below the quadrant plate, B diagonals above. Their outstanding legs face away at the crossing; no brace is cut at the centre.'))
    beams=[m for m in b.members if m['kind'] in ('beam','girder','moment_beam','equipment_beam')]
    for c in b.connections:
        if c['detail_ref']['id'] not in ('review_plan_angle','review_angle_crossing'):continue
        c['point'][2]=levels[lookup[c['member_ids'][0]]['level']]
        if c['detail_ref']['id']=='review_angle_crossing':
            c.setdefault('parameters',{})['physical_plan_brace']=True
            continue
        m=lookup[c['member_ids'][0]];origin=c['point'];end=min(range(2),key=lambda i:math.dist(m['axis'][i][:2],origin[:2]));ray=unit(sub(m['axis'][1-end],m['axis'][end]));ray[2]=0;ray=unit(ray)
        par=c.setdefault('parameters',{});count=par.get('count',2);quadrant=par.get('joint')=='column_quadrant'
        if quadrant:
            hosts=[lookup[mid] for mid in c['member_ids'][1:] if lookup[mid]['kind']=='column']
            for axis in (0,1):
                choices=[]
                for beam in beams:
                    aa,bb=beam['axis'];far=max((aa,bb),key=lambda q:math.dist(q,origin));direction=sub(far,origin)
                    if min(math.dist(aa[:2],origin[:2]),math.dist(bb[:2],origin[:2]))>.01 or abs(aa[2]-origin[2])>.01:continue
                    if abs(direction[axis])<1 or abs(direction[1-axis])>.01 or direction[axis]*ray[axis]<=0:continue
                    choices.append(beam)
                if not choices:raise ValueError('Missing actual quadrant girder '+c['id'])
                hosts.append(min(choices,key=lambda q:q['id']))
            first=13.5/max(abs(ray[0]),abs(ray[1]))-3*(count-1)
        else:
            hosts=[lookup[mid] for mid in c['member_ids'][1:] if lookup[mid]['kind'] in ('beam','girder','equipment_beam')]
            if len(hosts)!=1:raise ValueError('Missing actual leg-point support '+c['id'])
            first=1.5
        m['end_offsets'][end]=add(m['end_offsets'][end],mul(ray,max(0,first-1.5)))
        c['member_ids']=[m['id']]+[q['id'] for q in hosts]
        par.update(physical_plan_brace=True,bolt_first_in=first)
        b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual angle end setback, 1.5 in from first source bolt; the original workpoint and its source quadrant remain explicit'))
    b.note('PLAN-CROSSING-FIT','S: uncut single-angle diagonals, source quadrant/leg plates and one 3/4 in centre bolt. A: alternate angles lap opposite faces of the 3/8 in end plates, with their outstanding legs facing away; a 3/8 in centre spacer closes the same gap at the crossing. This preserves source bolt count and avoids intersecting angle legs. Detailed fit and capacity remain unverified.')
    supplier_heads(b)


def supplier_heads(b):
    """Explicit mock supplier frames, including every leg-to-frame interface."""
    from collections import defaultdict
    rows=defaultdict(list)
    for m in b.members:
        if m['kind']!='equipment_leg':continue
        c=next(c for c in b.connections if c['detail_ref']['id']=='review_equipment_foot' and c['member_ids'][0]==m['id'])
        b.endpoint_links.append(dict(member_id=m['id'],end='start',connection_id=c['id'],basis='Actual supplier leg foot on its 3/4 in plate at this same source workpoint'))
        top=m['axis'][1];group=m['id'].split('-LEG-')[0] if '-LEG-' in m['id'] else m['id'].split('-FOOT-')[0]
        rows[group,top[1],top[2]].append(m)
    for (group,y,z),legs in rows.items():
        if len(legs)!=2:raise ValueError('Supplier support row needs its two actual legs')
        legs.sort(key=lambda m:m['axis'][1][0]);x0,x1=[m['axis'][1][0] for m in legs];k=legs[0]['level']
        rail=b.member(f'{group}-SUPPLIER-RAIL-{y:g}','HSS6X4X1/4','equipment_base_rail',[x0,y,z+3.5],[x1,y,z+3.5],k,'A',
            setout_basis='A fictional supplier rail and cap arrangement. Original equipment mass/reactions remain source requirements; supplier body and attachment verification remain delegated.')
        for side,leg in zip((1,-1),legs):
            c=b.connection(leg['id']+'-HEAD','review_equipment_head',leg['axis'][1],[leg,rail],parameters=dict(rail_side=side))
            b.endpoint_links.append(dict(member_id=leg['id'],end='end',connection_id=c['id'],basis='Actual leg cap supports the declared fictional supplier frame'))
            b.endpoint_links.append(dict(member_id=rail['id'],end='start' if side==1 else 'end',connection_id=c['id'],basis='Actual supplier rail terminates on this leg cap; centroid offset is 3.5 in'))
    b.note('SUPPLIER-FRAMES','A: vessel, skid and pump support legs terminate on explicit HSS6x4x1/4 supplier rails with 1/2 in cap plates and two 1/2 in attachment bolts at each leg. Source masses and support reactions are unchanged. Equipment bodies, operating loads and certified supplier attachments remain delegated; these mock rails are not newly verified structural designs.')


def shape(members,origin):
    return [dict(profile=m['profile_id'],kind=m['kind'],axis=[[round(v,6) for v in sub(q,origin)] for q in m['axis']],
                 offsets=m['end_offsets'],local_y=m['local_y']) for m in members]


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;origin=ctx.c['point'];brace=ctx.ms[0]
    if ctx.family=='review_angle_crossing':
        for i,m in enumerate(ctx.ms):extract(ctx,m,'ANGLE'+str(i),AXES,20)
        a.box('SPACER',[-.625,-.625,0],[1.25,1.25,.375],'A','A 3/8 in centre spacer; the two connected legs stay in their end-plate planes')
        t=p[brace['profile_id']]['dimensions']['t']
        a.fastener('B1',[[0,0,-t]],[0,0,1],.75,2*t+.375,['ANGLE0','SPACER','ANGLE1'],'S one 3/4 in A325 crossing bolt; A spacer/grip',basis='S count / A fit')
        a.front_axes=(0,1);a.section_axis=0;a.section_at=0
        a.notes.append('The two source angles remain continuous through the crossing. A: outstanding legs point away; the 3/8 in centre spacer matches the end-gusset gap. No welded centre plate or cut angle is implied.')
        return
    extract(ctx,brace,'ANGLE',AXES,40)
    hosts={}
    for i,m in enumerate(ctx.ms[1:]):hosts['HOST'+str(i)]=(m,extract(ctx,m,'HOST'+str(i),AXES,30))
    end=min(range(2),key=lambda i:math.dist(brace['axis'][i][:2],origin[:2]));ray=unit(sub(brace['axis'][1-end],brace['axis'][end]));ray=unit([*ray[:2],0]);count=par.get('count',2)
    first=par['bolt_first_in'];centres=[mul(ray,first+j*3) for j in range(count)];t=p[brace['profile_id']]['dimensions']['t']
    lower=brace['plan_fit']['lower_face'];z=-t if lower else 0
    if par.get('joint')=='column_quadrant':
        sx=1 if ray[0]>0 else -1;sy=1 if ray[1]>0 else -1
        verts=[[sx*x,sy*y,0] for x,y in ((6,0),(15,0),(15,15),(0,15),(0,6),(6,6))]
        if sx*sy<0:verts.reverse()
        a.polygon('PLATE',verts,.375,normal=[0,0,1],basis='S',description='S 3/8 x 15 x 15 quadrant plate, 6 x 6 column notch; A handedness and bolt stations')
        for axis in (0,1):
            label=next(label for label,(m,_) in hosts.items() if m['kind']!='column' and abs(m['axis'][1][axis]-m['axis'][0][axis])>1)
            v=[sx,0,0] if axis==0 else [0,sy,0]
            a.weld('W'+str(axis),mul(v,6),mul(v,15),[label,'PLATE'],.25,description='S 1/4 in E70 fillet, 9 in along actual girder top flange')
        a.dim([0,sy*15,0],[sx*15,sy*15,0],'Source quadrant width')
    else:
        label,(host,part)=next(iter(hosts.items()));u=unit(sub(host['axis'][1],host['axis'][0]));v=cross([0,0,1],u);width=12 if count==3 else 10
        centre=mul(ray,first+1.5*(count-1))
        vertices=[add(centre,add(mul(u,x),mul(v,y))) for x,y in ((-width/2,-4),(width/2,-4),(width/2,4),(-width/2,4))]
        a.polygon('PLATE',vertices,.375,normal=[0,0,1],basis='S dimensions / A set-out',description=f'S 3/8 x 8 x {width} in leg-point plate; A local orientation/position')
        # Weld only where the plate overlaps the actual supporting top flange.
        along=dot(centre,u);across=dot(sub(host['axis'][0],origin),v);bf=p[host['profile_id']]['dimensions']['bf']
        for j,side in enumerate((-1,1)):
            line=across+side*(bf/2-.25)
            a.weld('W'+str(j),add(mul(u,along-width/2),mul(v,line)),add(mul(u,along+width/2),mul(v,line)),[label,'PLATE'],.25,basis='A',description='A 1/4 in local plate-to-actual-top-flange fit; source connection capacity requirement retained')
        a.dim(vertices[0],vertices[1],'Source plate length')
    a.fastener('BOLTS',[[q[0],q[1],z] for q in centres],[0,0,1],.75,.375+t,['ANGLE','PLATE'],f'S {count} x 3/4 in A325, 3 in pitch; A actual face grip and stations',basis='S count / A fit')
    a.front_axes=(0,1);a.section_axis=0 if abs(ray[0])>abs(ray[1]) else 1;a.section_at=centres[0][a.section_axis]
    a.notes.append('S source angle, plate dimensions and bolt count. A local face fit and bolt stations; the connected angle leg and all receiving girders are the actual physical pieces. Source capacity checks have not been rerun for the accepted fit.')
