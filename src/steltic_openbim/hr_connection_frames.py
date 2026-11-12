"""Place HR shear details using the terminating and through members at the joint."""
from collections import defaultdict
from math import dist

from .bim_assemblies import fingerprint, transformed
from .ifc_beam_ends import BEAMS, ends
from .pilots.model import add, sub, mul, dot, cross, unit
from .saved_assemblies import local_point


def locate_receivers(template, frame, members):
    """Clip the detail extracts to the real members and retain their actual roll."""
    receivers = []
    axes = (frame['x_axis'], frame['y_axis'], cross(frame['x_axis'], frame['y_axis']))
    for r in template['receivers']:
        member = members[frame['bindings'][r['id']]]
        a, b = ends(member)
        direction = unit(sub(b, a))
        context = r.get('source_context_axis', r['axis'])
        points = []
        for q in context:
            world = transformed(q, frame)
            s = dot(sub(world, a), direction)
            if dist(world, add(a, mul(direction, s))) > .02:
                raise ValueError('Detail misses receiver ' + member['id'])
            point = add(a, mul(direction, max(0., min(dist(a,b), s))))
            points.append(local_point(point, frame))
        if dist(*points) < 1e-6:
            raise ValueError('Detail is outside receiver ' + member['id'])
        receivers.append(dict(r, axis=points, local_y=[dot(member['local_y'], v) for v in axes]))
    return receivers


def place_template(template, frame, members, variants):
    receivers = locate_receivers(template, frame, members)
    tid = template['id'] + '-located-' + fingerprint(receivers)[:16]
    if tid not in variants:
        value = {k:v for k,v in template.items() if k != 'revision'}
        value.update(id=tid, receivers=receivers)
        value['revision'] = fingerprint(value)
        variants[tid] = value
    return dict(frame, template_id=tid, revision=variants[tid]['revision'])


def opening_corner_frames(physical,members,joints):
    """Two shear tabs connect the opposed header ends to one finite trimmer."""
    groups=defaultdict(list)
    for c in physical.get('connections',[]):
        if c.get('detail_ref',{}).get('legacy_family')=='test_floor_opening':
            groups[c.get('joint_id')].append(c)
    frames={}
    for joint_id,pair in groups.items():
        joint=joints.get(joint_id,{})
        ends_at_joint=joint.get('member_ends',[])
        if len(pair)!=2 or len(ends_at_joint)!=3 or joint.get('attachments'):continue
        ids={e['member_id'] for e in ends_at_joint}
        if sorted(members[i]['kind'] for i in ids)!=['opening_header','opening_trimmer','opening_trimmer']:continue
        common=set(pair[0]['member_ids']) & set(pair[1]['member_ids'])
        if len(common)!=1 or set(pair[0]['member_ids']) | set(pair[1]['member_ids'])!=ids:continue
        support=common.pop()
        rays={}
        for end in ends_at_joint:
            mid=end['member_id'];i=0 if end['end']=='start' else 1
            axis=members[mid]['axis']
            rays[mid]=unit(sub(axis[1-i],axis[i]))
        left,right=sorted(ids-{support})
        if dot(rays[left],rays[right])>-.99999 or abs(dot(rays[left],rays[support]))>1e-5:continue
        if len({members[i]['profile_id'] for i in ids})!=1:continue
        for c in pair:
            branch=next(i for i in c['member_ids'] if i!=support)
            # P1 lies on the positive local Y face of the branch web. Point
            # that face into the finite supporting web on both sides.
            frames[c['id']]=dict(x_axis=rays[branch],y_axis=rays[support],bindings=dict(M1=support,M2=branch))
    return frames


def beam_connection_view(physical):
    members = {m['id']:m for m in physical.get('members', [])}
    joints = {j['id']:j for j in physical.get('joints', [])}
    templates = {t['id']:t for t in physical.get('assemblies', [])}
    variants, changed = {}, {}
    corners=opening_corner_frames(physical,members,joints)
    for c in physical.get('connections', []):
        if c.get('detail_ref', {}).get('legacy_family') not in ('review_beam','test_floor_opening'):
            continue
        frame = c.get('assembly_instance', {})
        roles = frame.get('bindings', {})
        if c['id'] in corners:
            target=corners[c['id']]
            if not all(frame.get(k)==v for k,v in target.items()):
                frame=place_template(templates[frame['template_id']],dict(frame,**target),members,variants)
            if frame is not c['assembly_instance'] or not c.get('located_shear_joint'):
                changed[c['id']]=dict(c,assembly_instance=frame,located_shear_joint=True)
            continue
        joint = joints.get(c.get('joint_id'), {})
        end = next((e for e in joint.get('member_ends', []) if e['member_id']==roles.get('M1')), None)
        if not end or not any(a['member_id']==roles.get('M2') and 0 < a.get('station',0) < 1
                              for a in joint.get('attachments', [])):
            continue
        branch, through = members[roles['M1']], members[roles['M2']]
        if (branch['kind'] not in BEAMS or through['kind'] not in BEAMS
                or branch['profile_id'] != through['profile_id']):
            continue
        # M2 occupies the positive detail X ray. Preserve the detail's up
        # direction and rotate all its constituents together onto that ray.
        i = 0 if end['end']=='start' else 1
        x = unit(sub(branch['axis'][1-i], branch['axis'][i]))
        z = cross(frame['x_axis'], frame['y_axis'])
        frame = dict(frame, x_axis=x, y_axis=unit(cross(z, x)),
                     bindings=dict(roles, M1=through['id'], M2=branch['id']))
        located = place_template(templates[frame['template_id']], frame, members, variants)
        changed[c['id']] = dict(c, assembly_instance=located, located_shear_joint=True)
    if not changed:
        return physical
    return dict(physical, connections=[changed.get(c['id'], c) for c in physical['connections']],
                assemblies=[*physical['assemblies'], *variants.values()])


def coordinated_connections(physical):
    from .hr_skid_bay import skid_bay_view
    return beam_connection_view(skid_bay_view(physical))
