"""Locate transfer-truss end cuts in the axes of the actual frame members."""
import math

from .pilots.model import add, cross, dot, mul, sub, unit


MOVABLE = {'transfer_chord', 'transfer_diagonal'}
STATIONARY = {'column', 'transfer_vertical'}


def joint_rays(member, point):
    """Return all occupied directions at this workpoint, including both sides of a through column."""
    a, b = member['axis']
    length = math.dist(a, b)
    axis = unit(sub(b, a))
    station = dot(sub(point, a), axis)
    if math.dist(add(a, mul(axis, station)), point) > .01 or not -.01 <= station <= length + .01:
        raise ValueError('Transfer workpoint is outside its bound member ' + member['id'])
    rays = []
    if station > .01:
        rays.append((1, mul(axis, -1), station))
    if length - station > .01:
        rays.append((0, axis, length - station))
    return rays


def fit_end_offsets(model):
    members = {m['id']: m for m in model['members']}
    profiles = {p['id']: p for p in model['profiles']}
    for c in model['connections']:
        if c['detail_ref']['id'] != 'review_transfer_truss':
            continue
        point = c['point']
        joints = []
        for mid in c['member_ids']:
            member = members[mid]
            if member['kind'] not in MOVABLE | STATIONARY:
                continue
            dims = profiles[member['profile_id']]['dimensions']
            for end, ray, length in joint_rays(member, point):
                joints.append((member, end, ray, length, dims['d'] / 2))
        for m, end, axis, length, half_depth in joints:
            if m['kind'] not in MOVABLE:
                continue
            if math.dist(m['axis'][end], point) > .01:
                raise ValueError('Transfer member crosses a workpoint without a physical splice: ' + m['id'])
            # Separate the square terminal section from the other steel.
            # At a shared cut plane both rays open outwards. For obtuse
            # angles the end of the other half-ray bounds the intersection.
            cut = .25
            for other, _, ray, _, other_half in joints:
                if other is m:
                    continue
                if abs(dot(m['local_y'], other['local_y'])) < 1 - 1e-5:
                    raise ValueError('Transfer frame has incompatible flange planes at ' + c['id'])
                cosine = dot(axis, ray)
                sine = math.sqrt(dot(cross(axis, ray), cross(axis, ray)))
                if sine < 1e-6:
                    if cosine > 0:
                        raise ValueError('Unresolved coincident transfer members at ' + c['id'])
                    continue
                station = (other_half + half_depth * abs(cosine)) / sine
                if cosine < -1e-6:
                    station = min(station, half_depth * sine / -cosine)
                cut = max(cut, station + .25)
            old = m['end_offsets'][end]
            amount = max(cut, dot(old, axis))
            if math.dist(old, mul(axis, dot(old, axis))) > .01 or amount >= length:
                raise ValueError('Transfer end cut conflicts with its existing offset or member span: ' + m['id'])
            m['end_offsets'][end] = mul(axis, amount)
        c.setdefault('parameters', {})['located_transfer_ends'] = True
