"""Located fictional corner fit of HR28's source slab-edge reinforcement.

The gold record gives straight-lap requirements, bar counts and protected zones.
It does not resolve the corners. Keep that distinction on the actual geometry.
"""
import math
from collections import defaultdict
from .review_receiver_geometry import extract

DIAMETER = .625
BEND_RADIUS = 3.5 * DIAMETER  # accepted 6db inside bend diameter
TAIL = 66.


def apply(b):
    if b.key != 'hr28':
        return
    groups = defaultdict(dict)
    for m in b.members:
        if m['kind'] != 'diaphragm_chord_bar':
            continue
        _, level, along, side, index = m['id'].split('-')
        groups[int(level[1:])][int(along), int(side), int(index)] = m
    b.endpoint_links = getattr(b, 'endpoint_links', [])
    for level, bars in sorted(groups.items()):
        if len(bars) != 18:
            raise ValueError('HR28 edge chord requires the selected six X and three Y bars on each edge')
        low = [min(q[i] for m in bars.values() for q in m['axis']) - 2 for i in (0, 1)]
        high = [max(q[i] for m in bars.values() for q in m['axis']) + 2 for i in (0, 1)]
        z = bars[0, 0, 0]['axis'][0][2]
        for (along, side, index), m in bars.items():
            before = [q[:] for q in m['axis']]
            if along == 0:
                # Leave the physical bend region to the separate corner bars.
                inset = 2 + 1.5 * index + BEND_RADIUS
                m['axis'][0][0] = low[0] + inset
                m['axis'][1][0] = high[0] - inset
            else:
                m['axis'][0][1] = low[1] + 12
                m['axis'][1][1] = high[1] - 12
            m['corner_fit_basis'] = ('S: source straight bars connect around the corners through same-size corner bars and 66 in laps. '
                'A: trim the straight bar ends outside the bend region; place six corner bars one diameter below. '
                'Three corner tails lap the short-edge bars; the other three develop in concrete. Anchorage capacity is not newly verified.')
            b.changes.append(dict(kind='hr28_edge_bar_corner_fit', member_id=m['id'],
                previous_axis=before, axis=[q[:] for q in m['axis']], basis=m['corner_fit_basis']))
        for sx in (0, 1):
            for sy in (0, 1):
                xs = [bars[0, sy, j] for j in range(6)]
                ys = [bars[1, sx, j] for j in range(3)]
                point = [(low if sx == 0 else high)[0], (low if sy == 0 else high)[1], z]
                cid = f'CHORD-CORNER-L{level}-{sx}-{sy}'
                records = list(dict.fromkeys(r for m in xs + ys for r in m['design_record_ids']))
                b.connection(cid, 'review_edge_chord_corner', point, xs + ys, records,
                    parameters=dict(sign_x=1 if sx == 0 else -1, sign_y=1 if sy == 0 else -1,
                                    bend_radius_in=BEND_RADIUS, tail_in=TAIL),
                    title='SLAB EDGE CHORD CORNER / A FIT')
                for m, end in [(m, 'start' if sx == 0 else 'end') for m in xs] + [
                    (m, 'start' if sy == 0 else 'end') for m in ys
                ]:
                    b.endpoint_links.append(dict(member_id=m['id'], end=end, connection_id=cid,
                        basis='Actual local bent-bar and concrete bond/lap assembly at this corner; '
                              'no rebar weld or new anchorage capacity approval.'))
    # Top chord ends are six inches below the column's top workpoint. The same
    # located chord-to-column flange assembly serves that short terminal end.
    for m in b.members:
        if m['kind'] != 'column':
            continue
        end = max(m['axis'], key=lambda q: q[2])
        if abs(end[2] - max(z for _, _, z in b.levels)) > .001:
            continue
        candidates = [c for c in b.connections if c['detail_ref']['id'] == 'review_stmf_end'
                      and m['id'] in c['member_ids'] and math.dist(c['point'], end) <= 6.001]
        if candidates:
            c = min(candidates, key=lambda c: (math.dist(c['point'], end), c['id']))
            b.endpoint_links.append(dict(member_id=m['id'], end='end', connection_id=c['id'],
                basis='Source roof truss top-chord flange meets the terminal column; its chord centreline '
                      'is six inches below the column top. Use that actual located assembly, not a second joint.'))
    b.note('EDGE-CHORD-CORNERS', 'S: six #5 bars on the long edges, three on the short edges and 66 in Class B straight laps. '
           'A: six separate same-size corner bars turn through 90 degrees with 6db inside bend diameter. '
           'Each laps its long-edge bar by 66 in; three tails contact the short-edge bars for 66 in and three extra tails develop in the concrete. '
           'Corner anchorage and the local vertical layering are fictional coordination inputs, with no new capacity verification. '
           'The source protected-zone lap exclusions remain in force; no rebar weld is shown.')


def bend_faces(offset, radius, diameter, sx, sy):
    """Closed quarter-torus mesh; ring tangent is continuous at both straights."""
    rings = []
    for i in range(17):
        angle = -math.pi / 2 - i * math.pi / 32
        ca, sa = math.cos(angle), math.sin(angle)
        centre = [sx * (offset + radius + radius * ca), sy * (offset + radius + radius * sa), 0]
        rings.append([[centre[0] + sx * diameter / 2 * ca * math.cos(j * math.pi / 8),
                       centre[1] + sy * diameter / 2 * sa * math.cos(j * math.pi / 8),
                       diameter / 2 * math.sin(j * math.pi / 8)] for j in range(16)])
    faces = [list(reversed(rings[0])), rings[-1]]
    faces += [[a[j], a[(j + 1) % 16], d[(j + 1) % 16], d[j]]
              for a, d in zip(rings, rings[1:]) for j in range(16)]
    if sx * sy < 0:
        faces = [list(reversed(face)) for face in faces]
    return faces


def draw(ctx):
    a = ctx.a
    sx, sy = ctx.params['sign_x'], ctx.params['sign_y']
    radius, tail = ctx.params['bend_radius_in'], ctx.params['tail_in']
    axes = ([1, 0, 0], [0, 1, 0], [0, 0, 1])
    for j, m in enumerate(ctx.ms):
        extract(ctx, m, ('X' + str(j)) if j < 6 else ('Y' + str(j - 6)), axes, 90)
    for j in range(6):
        offset = 2 + 1.5 * j
        faces = [[[q[0], q[1], q[2] - DIAMETER] for q in f]
                 for f in bend_faces(offset, radius, DIAMETER, sx, sy)]
        bend = 'BEND' + str(j)
        a.part(bend, 'A continuous 90-degree bend of a separate #5 corner bar; 6db inside diameter',
               faces, 'A', 'reinforcement', geometry=dict(type='mesh', faces=faces))
        lx0 = [sx * (offset + radius), sy * offset, -DIAMETER]
        lx1 = [sx * (offset + radius + tail), sy * offset, -DIAMETER]
        a.member('LAPX' + str(j), ctx.ms[j]['profile_id'], lx0, lx1, y=[0, 0, 1], basis='A',
                 representation_role='assembly_component', description='Same-size corner bar with source 66 in contact lap to long-edge bar')
        start = [sx * offset, sy * (offset + radius), -DIAMETER]
        end = [sx * offset, sy * (max(12, offset + radius) + tail), -DIAMETER]
        name = 'TAIL' + str(j)
        a.member(name, ctx.ms[j]['profile_id'], start, end, y=[0, 0, 1], basis='A',
                 representation_role='assembly_component', description='Corner tail extends through the source 66 in lap beyond the short-edge bar end')
        a.interfaces.append(dict(id='CONTINUITY' + str(j), kind='continuous_reinforcement', basis='A',
            connects=['LAPX' + str(j), bend, name], description='One corner bar represented by tangent segments; no splice or weld at the bend'))
        a.interfaces.append(dict(id='LAPX' + str(j), kind='reinforcement_bond_lap', basis='S length; A position',
            connects=['LAPX' + str(j), 'X' + str(j), 'CONCRETE'], length_in=tail,
            description='Actual 66 in contact lap of corner bar and source long-edge bar'))
        joins = [name, 'CONCRETE'] + (['Y' + str(j)] if j < 3 else [])
        a.interfaces.append(dict(id='BOND' + str(j), kind='reinforcement_bond_lap' if j < 3 else 'reinforcement_bond_development',
            basis='S 66 in straight lap; A corner fit' if j < 3 else 'A', connects=joins, length_in=tail,
            description='Actual contact lap into source short-edge bar' if j < 3 else 'A additional tail embedded in concrete; anchorage capacity unverified'))
    xx, yy = sorted((0, sx * 90)), sorted((0, sy * 90))
    a.box('CONCRETE', [xx[0], yy[0], -4.5], [90, 90, 6.25], 'A',
          'Local source slab context; A layer/cover fit at the corner', kind='concrete')
    a.front_axes = (0, 1)
    a.section_axis = 1
    a.section_at = sy * 35
    a.dim([sx * 2, sy * 12, 0], [sx * 2, sy * (12 + tail), 0],
          '66 in source straight lap; A corner placement', basis='S length / A placement')
    a.notes.extend([
        'S: source bar counts and 66 in straight Class B lap. A: corner geometry, bend and vertical layering. '
        'Six corner bars lap the six X bars. First three tails also lap the three Y bars; the remaining three develop into the slab. '
        'Anchorage adequacy has not been newly checked. No bar weld.',
        'Keep laps outside every STMF special segment and half a panel on each side. '
        'This local corner fit retains the source straight-lap requirement; it is not a substitute for development verification.'
    ])
