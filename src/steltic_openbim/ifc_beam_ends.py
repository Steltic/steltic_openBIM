"""Fit HR steel member bodies to the receivers at their physical end joints.

The saved workline and source entity remain the design/analysis reference.
Detail receiver extracts supply the end station, never the length of the span.
All clipping planes here are in the physical source frame, in inches.
"""
from collections import defaultdict
from math import dist

from .bim_assemblies import transformed
from .pilots.geometry import strips
from .pilots.model import add, cross, dot, mul, sub, unit


BEAMS = {'beam', 'moment_beam', 'girder', 'joist', 'rafter', 'infill',
         'opening_header', 'opening_trimmer', 'equipment_beam'}
COLUMNS = {'column', 'col', 'post', 'endwall_post', 'rocking_post', 'transfer_vertical'}
BEAM_DETAILS = {'review_beam', 'test_floor_opening', 'review_existing_joint', 'review_pin_beam'}


def ends(member):
    return [add(p, o) for p, o in zip(member['axis'], member['end_offsets'])]


def plane(normal, point):
    return {'normal': list(normal), 'offset_in': dot(normal, point)}


def receiver_frame(member):
    a, b = ends(member)
    axis = unit(sub(b, a))
    return a, axis, member['local_y'], cross(axis, member['local_y'])


def has_section(member, profiles):
    profile = profiles.get(member.get('profile_id'), {})
    return (len(member.get('end_offsets', [])) == 2 and member.get('local_y') is not None
            and bool(profile.get('dimensions') or profile.get('components')))


def end_connections(physical):
    """Use joint topology to distinguish a branch end from a through member.

    At a node with two pairs of opposing ends, a continuous unreleased line
    carries the released branches. A single corner follows its drawing roles.
    """
    members = {m['id']: m for m in physical['members']}
    profiles = {p['id']: p for p in physical['profiles']}
    joints = {j['id']: j for j in physical.get('joints', [])}
    templates = {t['id']: t for t in physical.get('assemblies', [])}
    groups = defaultdict(list)
    for c in physical.get('connections', []):
        frame = c.get('assembly_instance', {})
        template = templates.get(frame.get('template_id'), {})
        family = c.get('detail_ref', {}).get('legacy_family', '')
        ids = [mid for mid in c.get('member_ids', []) if mid in members]
        if len(ids) < 2 or not template.get('receivers'):
            continue
        bindings = frame.get('bindings', {})
        if family in BEAM_DETAILS:
            # Equal sections can be bound to the opposite drawing roles. The
            # joint identifies which member actually ends on the through beam.
            joint = joints.get(c.get('joint_id'), {})
            at_end = {e['member_id'] for e in joint.get('member_ends', [])}
            branch, support = bindings.get('M2', ids[0]), bindings.get('M1', ids[1])
            if ids[0] in at_end and (branch not in at_end or members.get(branch,{}).get('kind') not in BEAMS):
                branch, support = ids[:2]
            role = 'M2'
        elif family in {'review_chamfer', 'review_pg_seat', 'review_pg_collar'}:
            role = 'BEAM' if family == 'review_chamfer' else 'PG'
            branch, support = bindings[role], bindings['COLUMN']
        elif family == 'review_hr_gable_knee':
            role = 'RAFTER'
            branch, support = bindings[role], bindings['COLUMN']
        elif family == 'review_hr_gable_ridge':
            for role, other in [('RAFTER0', 'RAFTER1'), ('RAFTER1', 'RAFTER0')]:
                groups[c['joint_id']].append((c, family, bindings[role], bindings[other], role, template))
            continue
        else:
            continue
        if (members.get(branch,{}).get('kind') in BEAMS and members.get(support,{}).get('kind') in BEAMS | COLUMNS
                and has_section(members[branch],profiles) and has_section(members[support],profiles)):
            groups[c.get('joint_id', c['id'])].append((c, family, branch, support, role, template))

    for jid, rows in groups.items():
        joint = joints.get(jid, {})
        end_ids = {e['member_id'] for e in joint.get('member_ends', [])}
        crossing = [m for m in end_ids if members[m]['kind'] in BEAMS]
        through = set()
        if len(crossing) >= 3 and not any(members[r[3]]['kind'] in COLUMNS for r in rows):
            released = {r[2] for r in rows if r[0].get('parameters', {}).get('released_major_end')}
            rays = {mid: unit(sub(*reversed(members[mid]['axis']))) for mid in crossing}
            candidates = []
            for i, a in enumerate(crossing):
                for b in crossing[i+1:]:
                    if abs(dot(rays[a], rays[b])) < .99999:
                        continue
                    depth = min(profiles[members[mid]['profile_id']]['dimensions'].get('d', 0) for mid in (a,b))
                    candidates.append((len({a,b} - released), depth, sorted((a,b))))
            if candidates:
                through = set(max(candidates)[2])
        for row in rows:
            c, family, branch, support, role, template = row
            if branch in through and support in end_ids and support not in through:
                continue
            yield row


def beam_end_fits(physical):
    members = {m['id']: m for m in physical['members']}
    profiles = {p['id']: p for p in physical['profiles']}
    fits = defaultdict(list)
    gusset_welds = beam_weld_points(physical, members)
    for c, family, mid, host, role, template in end_connections(physical):
        m, receiver = members[mid], members[host]
        joint = c['point']
        end = min(range(2), key=lambda i: dist(m['axis'][i], joint))
        start, far = ends(m)[end], ends(m)[1-end]
        inward = unit(sub(far, start))
        frame = c['assembly_instance']
        item = next(r for r in template['receivers'] if r['id'] == role)
        cut = dict(end=end, receiver=host, connection=c['id'], recesses=[])
        if family.startswith('review_hr_gable_'):
            # These square end plates have vertical faces even on a pitched roof.
            normal = frame['x_axis']
            if dot(normal, inward) < 0:
                normal = mul(normal, -1)
            plate_id = 'EP' if role == 'RAFTER' else 'EP'+role[-1]
            plate = next(p for p in template['parts'] if p['id'] == plate_id)
            cap = max(dot(transformed(q, frame), normal)
                      for face in plate['geometry']['faces'] for q in face)
            cut['plane'] = dict(normal=normal, offset_in=cap)
            # A square rafter end does not reach the full-height plumb mitre.
            if family == 'review_hr_gable_ridge':
                cut['extend_in'] = profiles[m['profile_id']]['dimensions']['d']
        else:
            centre, along, width, depth = receiver_frame(receiver)
            dims = profiles[receiver['profile_id']]['dimensions']
            section = profiles[receiver['profile_id']]['family']
            weak = abs(dot(inward, width)) > abs(dot(inward, depth))
            normal = width if weak else depth
            if dot(normal, inward) < 0:
                normal = mul(normal, -1)
            if dot(normal, inward) < .001:
                # Collinear splices retain their declared set-out.
                continue
            axis = item.get('source_context_axis', item['axis'])
            local = min(axis, key=lambda p: sum(v*v for v in p[:2]))
            if family in BEAM_DETAILS:
                # M2 starts at the selected flange/web face plus any detailed
                # erection gap. Measure along the true incoming member even if
                # an equal-profile drawing instance was rotated by 90 degrees.
                point = add(joint, mul(inward, local[0]))
                # Preserve elevation/offset at a sloping or eccentric receiver.
                offset = sub(start, m['axis'][end])
                point = add(point, sub(offset, mul(inward, dot(offset,inward))))
            else:
                point = transformed(local, frame)
                normal = inward
            cut['plane'] = plane(normal, point)
            weld = gusset_welds.get((c.get('joint_id'), mid))
            if weld and receiver['kind'] in COLUMNS and family in BEAM_DETAILS:
                # The longitudinal gusset weld can run all the way to the
                # column. The beam flange must cover that selected weld even
                # where the stand-alone shear detail shows an erection gap.
                if section == 'i':
                    half = dims['tw']/2 if weak else dims['d']/2
                    if weak and c.get('parameters',{}).get('boxing_t'):
                        half = dims['bf']/2+c['parameters']['boxing_t']
                elif section == 'rhs':
                    half = dims['b' if weak else 'h']/2
                else:
                    half = None
                if half is not None:
                    face = dot(centre,normal)+half
                    fit_welded_plies(cut, m, profiles[m['profile_id']], weld, face)
            if family == 'review_chamfer':
                # The approved local detail also trims the column and boxing
                # behind the back of the diagonal face plate, over its height.
                plate = next(p for p in template['parts'] if p['id'] == 'FACE')
                points = [transformed(q,frame) for face in plate['geometry']['faces'] for q in face]
                back = min(dot(q,normal) for q in points)
                recess = [dict(normal=[0,0,-1],offset_in=-min(q[2] for q in points)),
                          dict(normal=[0,0,1],offset_in=max(q[2] for q in points)),
                          dict(normal=mul(normal,-1),offset_in=-back)]
                for slot, ident in frame['bindings'].items():
                    if slot == 'COLUMN' or slot.startswith('BOX'):
                        fits[ident].append(dict(receiver=mid,connection=c['id'],recesses=[recess]))

            if weak and section == 'i' and family != 'review_chamfer':
                # The web can project between receiver flanges. Relieve only
                # material in the flange bands; a shallow branch needs no
                # bottom cope when it already clears the lower flange.
                beam_host = receiver['kind'] in BEAMS
                side_gap = (.5 if family == 'test_floor_opening' else .25) if beam_host else 0.
                vertical_gap = .5 if beam_host else 0.
                edge = dot(centre, normal) + dims['bf']/2 + side_gap
                if edge > cut['plane']['offset_in'] + 1e-7:
                    side = dict(normal=normal, offset_in=edge)
                    clear = dims['d']/2 - dims['tf'] - vertical_gap
                    for sign in (-1, 1):
                        nz = mul(depth, sign)
                        cut['recesses'].append([side, dict(normal=mul(nz,-1), offset_in=-dot(centre,nz)-clear)])
        fits[mid].append(cut)
    add_topological_receivers(physical, members, profiles, fits)
    return dict(fits)


def beam_weld_points(physical, members):
    """Located weld extents shared by the gusset and a named beam occurrence."""
    templates = {t['id']: t for t in physical.get('assemblies', [])}
    by_template = {}
    result = defaultdict(list)
    for c in physical.get('connections', []):
        frame = c.get('assembly_instance', {})
        tid = frame.get('template_id')
        if tid not in templates:
            continue
        params = c.get('parameters', {})
        quadrant = params.get('physical_plan_brace') and params.get('joint')=='column_quadrant'
        key = (tid, bool(quadrant))
        if key not in by_template:
            by_template[key] = [(p.get('connects', []), p['geometry']['points']) for p in templates[tid].get('parts', [])
                if p.get('kind') == 'weld' and p.get('geometry',{}).get('type') == 'polyline'
                and (p.get('parameters',{}).get('attachment_role') == 'gusset_beam_weld'
                     or (quadrant and 'PLATE' in p.get('connects', []))
                     or any('GUSSET' in tag.upper() for tag in p.get('connects', [])))]
        for roles, points in by_template[key]:
            for role in roles:
                mid = frame.get('bindings', {}).get(role)
                if members.get(mid,{}).get('kind') in BEAMS:
                    result[c.get('joint_id'),mid].extend(transformed(q,frame) for q in points)
    return result


def fit_welded_plies(cut, member, profile, weld, column_face):
    """Carry each welded ply to its weld and preserve the other plies' fit-up."""
    normal = cut['plane']['normal']
    gap_station = cut['plane']['offset_in']
    if profile['family'] != 'i' or column_face >= gap_station:
        return
    origin, _, _, z = receiver_frame(member)
    half_depth = profile['dimensions']['d']/2
    clear = half_depth - profile['dimensions']['tf']
    z0 = dot(origin,z)
    stops = [gap_station]*3  # bottom flange, web, top flange
    for point in weld:
        height = dot(sub(point,origin),z)
        ply = 0 if height <= -clear+1e-6 else 2 if height >= clear-1e-6 else 1
        stops[ply] = min(stops[ply], max(column_face,dot(point,normal)))
    nearest = min(stops)
    cut['plane']['offset_in'] = nearest
    above_lower = dict(normal=z,offset_in=z0-clear)
    below_lower = dict(normal=mul(z,-1),offset_in=-z0+clear)
    above_upper = dict(normal=z,offset_in=z0+clear)
    below_upper = dict(normal=mul(z,-1),offset_in=-z0-clear)
    for stop, other_plies in zip(stops, ([above_lower],[below_lower,above_upper],[below_upper])):
        if stop > nearest+1e-7:
            cut['recesses'].append([dict(normal=normal,offset_in=stop),*other_plies])


def add_topological_receivers(physical, members, profiles, fits):
    """Resolve actual steel omitted from a detail, including a through transfer girder."""
    sections = {}
    def projections(m, normal):
        pid = m['profile_id']
        if pid not in sections:
            sections[pid] = [q for strip in strips(profiles[pid],profiles) for q in strip]
        _, _, y, z = receiver_frame(m)
        u, v = dot(normal,y), dot(normal,z)
        stations = [s*u+t*v for s,t in sections[pid]]
        return min(stations), max(stations)

    for j in physical.get('joints', []):
        terminals = j.get('member_ends', [])
        attached = {a['member_id'] for a in j.get('attachments', [])}
        ids = attached | {a['member_id'] for a in terminals}
        for e in terminals:
            m = members[e['member_id']]
            if m['kind'] not in BEAMS or not has_section(m, profiles):
                continue
            end = 0 if e['end'] == 'start' else 1
            start, far = ends(m)[end], ends(m)[1-end]
            inward = unit(sub(far,start))
            detailed = [r for r in fits[m['id']] if r.get('end') == end]
            for ident in sorted(ids - {m['id']}):
                host = members[ident]
                boxing = host['kind'] == 'column_boxing'
                if host['kind'] not in COLUMNS and not boxing and not (ident in attached and host['kind'] in BEAMS):
                    continue
                if not has_section(host, profiles):
                    continue
                if any(r['receiver'] == ident for r in detailed):
                    continue
                if boxing and any(r['receiver'] == m['id'] and 'end' not in r for r in fits.get(ident, [])):
                    # The diagonal plate has its own bounded housing in this boxing.
                    continue
                centre, along, width, depth = receiver_frame(host)
                if abs(dot(along,inward)) > .99999:
                    continue
                a,b = projections(m,along)
                station = dot(sub(start,centre),along)
                if station+b <= 1e-6 or station+a >= dist(*ends(host))-1e-6:
                    continue  # finite bearing or rocking support clears the incoming member
                weak = abs(dot(inward,width)) > abs(dot(inward,depth))
                normal = width if weak else depth
                if dot(normal,inward) < 0:
                    normal = mul(normal,-1)
                profile = profiles[host['profile_id']]
                dims = profile['dimensions']
                extent = projections(host,normal)[1]
                if weak and profile['family'] == 'i':
                    extent = dims['tw']/2
                offset = dot(centre,normal) + extent
                # An attached body may be remote from the work point (e.g. an
                # eccentric post). Check the other cross-section dimension too.
                side = depth if weak else width
                lo,hi = projections(m,side)
                hlo,hhi = projections(host,side)
                lateral = dot(sub(start,centre),side)
                if lateral+hi < hlo-1e-6 or lateral+lo > hhi+1e-6:
                    continue
                if boxing:
                    if dot(sub(centre,start),normal) < 0:
                        continue
                    for prior in detailed:
                        support = members[prior['receiver']]
                        if support['kind'] in COLUMNS and dot(normal,prior['plane']['normal']) > .99999:
                            # Transfer the selected bare-web erection gap to
                            # the actual exterior face of a boxed column.
                            cp = profiles[support['profile_id']]
                            if cp['family'] == 'i' and prior['plane']['offset_in'] < offset:
                                web = dot(ends(support)[0],normal)+cp['dimensions']['tw']/2
                                offset += max(0.,prior['plane']['offset_in']-web)
                recesses = []
                if weak and profile['family'] == 'i' and not boxing:
                    boundary = dict(normal=normal,offset_in=dot(centre,normal)+dims['bf']/2)
                    clear = dims['d']/2-dims['tf']
                    for sign in (-1,1):
                        nz = mul(depth,sign)
                        recesses.append([boundary,dict(normal=mul(nz,-1),offset_in=-dot(centre,nz)-clear)])
                fits[m['id']].append(dict(end=end,receiver=ident,connection=j['id'],
                                         plane=dict(normal=normal,offset_in=offset),recesses=recesses))


def fitted_member(member, fits):
    """A geometry-only view. Keeps RBS cuts and bores at their source stations."""
    if not fits:
        return member
    result = dict(member)
    result['terminal_planes'] = list(member.get('terminal_planes', [])) + [f['plane'] for f in fits if 'plane' in f]
    result['ifc_end_recesses'] = [r for f in fits for r in f['recesses']]
    if any('extend_in' in f for f in fits):
        offsets = list(member.get('extrusion_end_offsets', member['end_offsets']))
        a,b = ends(member)
        for f in fits:
            if 'extend_in' in f:
                i = f['end']
                outward = unit(sub(b,a) if i else sub(a,b))
                offsets[i] = add(offsets[i], mul(outward, f['extend_in']))
        result['extrusion_end_offsets'] = offsets
    return result
