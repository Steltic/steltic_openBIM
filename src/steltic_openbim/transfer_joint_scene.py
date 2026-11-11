"""Double-gusset transfer nodes, located from the physical cuts and HR weld records."""
import math
import re

from .assembly_templates import NUMBER, number
from .pilots.model import add, cross, dot, mul, sub, unit
from .review_assemblies import hull
from .transfer_joint_fit import MOVABLE, joint_rays


def selections(ctx):
    rows = {r['id']: r['data'] for r in ctx.package['design_records']}
    result = {}
    for rid in ctx.c['design_record_ids']:
        row = rows.get(rid, {})
        category = row.get('type', '').lower()
        component = row.get('components', '')
        if 'transfer truss' not in category or 'flange tips' not in component.lower():
            continue
        t = re.search(r'2 PL ' + NUMBER + r' in', component, re.I)
        weld = re.search(r'(\d+) lines of ' + NUMBER + r' in (E\d+) fillet welds x ' + NUMBER + r' in', component, re.I)
        if weld:
            count, size, metal, length = weld.groups()
        else:
            weld = re.search(r'(\d+) lines x ' + NUMBER + r' in, ' + NUMBER + r' in (E\d+)', component, re.I)
            if not weld:
                raise ValueError('Unresolved transfer weld selection in ' + rid)
            count, length, size, metal = weld.groups()
        width = re.search(r'Whitmore width ' + NUMBER + r' in', component, re.I)
        section = re.search(r'(W\d+X\d+)', component, re.I)
        if t is None or section is None or int(count) != 4:
            raise ValueError('Unresolved double-gusset transfer selection in ' + rid)
        kind = 'column' if 'support' in category else 'transfer_diagonal' if 'diagonal' in category else 'transfer_chord'
        result[kind] = dict(section=section[0].upper(), thickness=number(t[1]), size=number(size),
                            length=number(length), metal=metal.upper(), whitmore=number(width[1]) if width else None)
    return result


def draw(ctx):
    a, c = ctx.a, ctx.c
    selected = selections(ctx)
    chord = selected['transfer_chord']
    thickness = chord['thickness']
    if any(abs(r['thickness'] - thickness) > 1e-6 for r in selected.values()):
        raise ValueError('Transfer node has different selected gusset stocks at ' + c['id'])
    width = ctx.p[chord['section']]['dimensions']['bf']
    physical = next((v for v in ctx.package.get('physical', {}).get('connections', []) if v['id'] == c['id']), {})
    frame = physical.get('assembly_instance', {})
    x, y = frame.get('x_axis', [1., 0., 0.]), frame.get('y_axis', [0., 1., 0.])
    axes = (x, y, cross(x, y))
    def local(v):
        return [dot(v, direction) for direction in axes]
    witnesses, joins = [], []
    for index, m in enumerate(ctx.ms):
        role = 'M' + str(index)
        d = ctx.p[m['profile_id']]['dimensions']
        spec = selected.get(m['kind'])
        if spec and spec['section'] != m['profile_id'].upper():
            spec = None
        rays = joint_rays(m, c['point'])
        # Maintain continuous gravity columns and transfer posts. A cropped
        # detail view does not introduce a cut, splice or weld into their solids.
        far = max(rays, key=lambda row: row[2])
        end, axis, available = far
        v = local(axis)
        if abs(v[1]) > 1e-5 or abs(abs(dot(m['local_y'], y)) - 1) > 1e-5:
            raise ValueError('Transfer member lies outside its issued truss plane: ' + m['id'])
        moved = m['kind'] in MOVABLE
        cap = dot(m['end_offsets'][end], axis) if moved else 0.
        # The source support weld is centred about the real support node
        # whenever both sides of a through member are available.
        neg_span = next((r[2] for r in rays if r is not far), 0.)
        start = cap if moved else -min(neg_span, (spec['length'] / 2 if spec else 0.))
        if spec and start + spec['length'] > available + .001:
            raise ValueError('Selected transfer weld exceeds actual receiving steel at ' + c['id'] + ' ' + role)
        lo = cap if moved else -min(neg_span, max(16., -start + 4.))
        hi = min(available, max(24., start + (spec['length'] if spec else 12.) + 4.))
        a.member(role, m['profile_id'], mul(v, lo), mul(v, hi), y=local(m['local_y']),
                 description='Actual ' + m['kind'].replace('_', ' ') + ' at its located workpoint')
        if not spec:
            continue
        perp = [-v[2], 0., v[0]]
        for s, radius in ((start - thickness, d['d']/2 + thickness),
                          (start, max((spec['whitmore'] or 0.)/2, d['d']/2 + thickness)),
                          (start + spec['length'] + thickness, d['d']/2 + thickness)):
            for sign in (-1, 1):
                q = add(mul(v, s), mul(perp, sign*radius))
                witnesses.append((q[0], q[2]))
        joins.append((role, v, perp, start, d, spec))
    outline = hull(witnesses)
    for side in (-1, 1):
        name = 'G' + str(side)
        face = side * width/2
        plate = a.polygon(name, [[x, face - (thickness if side < 0 else 0.), z] for x, z in outline],
                          thickness, description='Source double gusset, A fitted attachment outline and Whitmore sections')
        plate['selected_material'] = 'ASTM A572 Grade 50'
        for role, direction, perp, start, d, spec in joins:
            for sign in (-1, 1):
                pt = add(add(mul(direction, start), mul(perp, sign*d['d']/2)), [0., side*d['bf']/2, 0.])
                a.weld(f'W{role}-{side}-{sign}', pt, add(pt, mul(direction, spec['length'])), [role, name],
                       spec['size'], description=f"Source {spec['metal']} flange-tip fillet, {spec['length']:g} in")
    for role, axis, perp, start, _, spec in joins:
        if spec['whitmore']:
            center = mul(axis, start)
            width_vec = mul(perp, spec['whitmore']/2)
            a.dim(sub(center, width_vec), add(center, width_vec), role + ' source Whitmore width')
    a.section_axis = 1
    a.section_at = width/2 + thickness/2
    a.notes.append('S: double plates and four longitudinal fillets at each selected arm. A: terminal cuts and perimeter are fitted to the located profiles. Vertical posts retain their full physical length.')
    if any(abs(d['bf']-width) > .001 for _, _, _, _, d, _ in joins):
        a.notes.append('Review required: the support-column flange tips and truss flange tips occupy different planes. A support transition and edge stiffener detail must be resolved in the issued connection.')
