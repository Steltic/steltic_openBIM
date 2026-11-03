"""Conservative physical-data screens; these do not repair or approve a design."""
import math
import re

from .pilots.geometry import part_faces, part_lines


def review_physical(physical):
    findings = []

    def add(code, title, rows, severity='needs_review'):
        if rows:
            findings.append(dict(code=code, title=title, severity=severity,
                                 count=len(rows), examples=rows[:100]))

    profiles = {p['id']: p for p in physical.get('profiles', [])}
    plies = []
    for profile in profiles.values():
        if profile.get('family') != 'built_up':
            continue
        components = profile.get('components', [])
        # Only recognise an explicit Nx constituent identifier, including box-Nx.
        # Arbitrary names and mixed constituent assemblies do not establish a count.
        match = re.fullmatch(r'(?:box-)?([1-9][0-9]*)[xX](.+)', profile['id'])
        if match and components and all(c['profile_id'] == match[2] for c in components):
            expected = int(match[1])
            if len(components) != expected:
                plies.append(dict(profile_id=profile['id'],named_count=expected,
                                  component_count=len(components),constituent=match[2]))
    add('physical_ply_count', 'Built-up section labels disagree with constituent counts', plies)

    panels = {p['id']: p for p in physical.get('panels', [])}
    outside = []
    for opening in physical.get('openings', []):
        host = panels.get(opening.get('host_id'), {})
        vertices = host.get('vertices', [])
        if len(vertices) < 3:
            continue
        # A conservative screen: a point outside the host's bounding box cannot
        # be inside its polygon. Passing this is not a concave-polygon fit check.
        bounds = [(min(p[k] for p in vertices), max(p[k] for p in vertices)) for k in range(3)]
        excess = max((max(low-v[k], v[k]-high, 0.) for v in opening.get('vertices', [])
                      for k,(low,high) in enumerate(bounds)), default=0.)
        if excess > 1e-5:
            outside.append(dict(opening_id=opening['id'],host_id=host['id'],outside_distance_in=excess))
    add('physical_opening_host', 'Opening boundaries extend outside their declared host bounds', outside)

    joints = {j['id']: j for j in physical.get('joints', [])}
    remote = []
    for connection in physical.get('connections', []):
        point = joints.get(connection.get('joint_id'), {}).get('point')
        if not point:
            continue
        for part in connection.get('parts', []):
            try:
                points = [p for face in part_faces(part, profiles) for p in face]
                if not points:
                    points = [p for line in part_lines(part) for p in line]
            except (ValueError,KeyError,TypeError,ZeroDivisionError):
                continue  # The exporter reports unsupported geometry separately.
            if not points:
                continue
            bounds = [(min(p[k] for p in points), max(p[k] for p in points)) for k in range(3)]
            distance = math.sqrt(sum(max(low-point[k], point[k]-high, 0.)**2
                                     for k,(low,high) in enumerate(bounds)))
            if distance > 72:
                remote.append(dict(connection_id=connection['id'],joint_id=connection.get('joint_id'),
                                   part_id=part['id'],distance_to_part_bounds_in=round(distance,6)))
    add('physical_remote_part', 'Connection parts are over six feet from their assigned joint', remote)

    return dict(status='needs_review' if findings else 'no_findings_in_limited_screens',
                structural_design_approval=False,findings=findings,
                limits=['Checks screen explicit section-count labels, opening host bounds and remote connection parts.',
                        'These checks do not establish capacity, architectural agreement, complete framing, physical fit or constructability.',
                        'Source geometry is retained unchanged. Findings require source-model review; export remains available.'])
