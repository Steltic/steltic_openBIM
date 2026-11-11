"""One real gusset per distinct plate plane and one screw group per web ply."""
from collections import defaultdict
from .assembly_templates import web_faces
import math
from .pilots.model import add,mul,sub,dot,unit,cross
from .review_assemblies import hull


def separate_bearing_ends(model):
    """Fit each independent joist's two end-post nodes inside its own span."""
    from .drawing_workflow import fingerprint
    members={m['id']:m for m in model['members']}
    profiles={p['id']:p for p in model['profiles']}
    scenes={s['id']:s for s in model.get('connection_assemblies',[])}
    seats={mid:c for c in model['connections'] if c['detail_ref']['id']=='review_roof_seat'
           for mid in c['member_ids'] if members[mid]['kind']=='truss_web' and
           math.dist(members[mid]['axis'][0][:2],members[mid]['axis'][1][:2])<1e-6}
    groups=defaultdict(list)
    nodes=[c for c in model['connections'] if c['detail_ref']['id'] in ('review_truss_heel','review_truss_node')]
    for c in nodes:
        if 'joist_bearing_setout_in' in c.get('parameters',{}):continue
        bound=[members[mid] for mid in c['member_ids']]
        posts=[m for m in bound if m['kind']=='truss_web' and math.dist(m['axis'][0][:2],m['axis'][1][:2])<1e-6]
        chords=[m for m in bound if m['kind']=='truss_chord']
        if len(posts)==1 and len(chords)==1 and c.get('assembly_id') in scenes:
            axis=tuple(sorted(tuple(round(v,6) for v in q) for q in posts[0]['axis']))
            groups[(axis,tuple(c['point']))].append((c,chords[0],posts[0]))
    moved=set()
    for rows in groups.values():
        if len(rows)!=2 or rows[0][2]['id']==rows[1][2]['id']:continue
        directions=[]
        for c,chord,post in rows:
            far=max(chord['axis'],key=lambda q:math.dist(q,c['point']))
            delta=sub(far,c['point']);directions.append(unit([delta[0],delta[1],0.]))
        if dot(*directions)>-.9999:continue
        for (c,chord,post),direction in zip(rows,directions):
            # The archived plate envelope and the actual end-post depth both
            # belong inside this joist's share of the support. Retain its
            # source bearing datum and leave the adopted 1/8-in node gap.
            scene=scenes[c['assembly_id']]
            horizontal=0 if abs(direction[0])>=abs(direction[1]) else 1
            sign=direction[horizontal]
            extent=max(-q[0]*sign for p in scene['parts'] if p['kind']=='plate'
                       for face in p['faces'] for q in face)
            seat=seats.get(post['id'])
            wall=0.
            if seat:
                host=next((members[mid] for mid in seat['member_ids'] if members[mid]['kind'] in
                          ('beam','girder','moment_beam','rafter')),None)
                if host:
                    wall=bearing_face(host,profiles,post,c['point'],direction)
            shift=mul(direction,max(0.,extent)+wall+.0625)
            c['parameters']['joist_bearing_setout_in']=shift
            if seat:
                seat['parameters']['joist_bearing_setout_in']=shift
                seat['parameters']['bearing_flange_face_in']=wall
            for mid in c['member_ids']:
                m=members[mid];ends=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
                e=min(range(2),key=lambda i:math.dist(ends[i],c['point']))
                if math.dist(ends[e],c['point'])>1e-6:
                    raise ValueError('Joist end set-out has no matching terminal workpoint: '+mid)
                m['end_offsets'][e]=add(m['end_offsets'][e],shift)
                moved.add(mid)
    for c in nodes:
        if not moved.intersection(c['member_ids']):continue
        # An adjacent panel sees the updated web slope even if its own
        # workpoint remains at its original station.
        c['parameters']['joist_receiver_fit']=fingerprint([
            [m['profile_id'],[[round(q[k]+o[k]-c['point'][k],6) for k in range(3)]
                              for q,o in zip(m['axis'],m['end_offsets'])]]
            for m in (members[mid] for mid in c['member_ids'])])


def bearing_face(host,profiles,post,point,direction):
    from .pilots.geometry import strips
    ends=[add(q,o) for q,o in zip(host['axis'],host['end_offsets'])]
    beam_axis=unit(sub(ends[1],ends[0]))
    if abs(dot(beam_axis,direction))>1e-5:
        raise ValueError('A skew shared joist support requires a located bearing face')
    y=host['local_y'];z=cross(beam_axis,y)
    centre=add(ends[0],mul(beam_axis,dot(sub(point,ends[0]),beam_axis)))
    elevations=[q[2]+off[2] for q,off in zip(post['axis'],post['end_offsets'])]
    face=0.
    for strip in strips(profiles[host['profile_id']],profiles):
        world=[add(centre,add(mul(y,a),mul(z,b))) for a,b in strip]
        heights=[q[2] for q in world]
        if max(heights)<min(elevations)-4 or min(heights)>max(elevations)+4:continue
        face=max(face,max(dot(sub(q,point),direction) for q in world))
    return face


def gussets(assembly,profiles,ends,layouts):
    planes=defaultdict(list)
    contour=[(-4.,-4.),(4.,-4.),(4.,4.),(-4.,4.)]
    for n,direction,member in ends:
        across=[-direction[2],0.,direction[0]]
        tip=layouts[n][0][-1]+2
        for side in (-3.,3.):
            q=add(mul(direction,tip),mul(across,side))
            contour.append((q[0],q[2]))
        for i,(face,side,thickness) in enumerate(web_faces(profiles,member['profile_id'])):
            mid=round(face+side*.125/2,6)
            planes[mid].append((n,i,face,side,thickness,direction))
    outline=hull(contour)
    for index,(mid,plies) in enumerate(sorted(planes.items()),1):
        label='P'+str(index)
        assembly.polygon(label,[[x,mid-.0625,z] for x,z in outline],.125,basis='A',
                         description='One continuous 1/8 in gusset shared by the actual adjoining web plies')
        for n,i,face,side,thickness,direction in plies:
            stations,offsets=layouts[n];across=[-direction[2],0.,direction[0]]
            # Opposed screws land at distinct stations in the common plate.
            # Drive from the outer channel web face through the gusset.
            shift=side*.1875 if sum(item[0]==n for item in plies)>1 else 0.
            points=[add(mul(direction,s+shift),add(mul(across,w),[0.,face-side*thickness,0.]))
                    for s in stations for w in offsets]
            assembly.fastener(f'F{index}-{n}-PLY{i+1}',points,[0.,side,0.],.25,.125+thickness,
                ['M'+str(n),label],f'{len(points)} No.14 screws through one channel web ply and shared gusset',
                'A',screw=True)
