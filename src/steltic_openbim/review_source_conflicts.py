"""Explicit fictional coordination decisions where saved selections disagree.

Original selections and calculation results are retained. A changed receiving
condition is a separately recorded proposal, never a new capacity check.
"""
import copy
import math
from .pilots.model import add, sub, mul, dot, cross, unit


def apply(b):
    if b.key == 'hr9':
        transition(b)
        return
    if b.key != 'hr14':
        return
    lookup = {m['id']: m for m in b.members}
    for c in b.connections:
        if c['detail_ref']['id'] != 'review_brace' or c['id'] != 'hr:element:610:0':
            continue
        brace, column, beam = [lookup[i] for i in c['member_ids']]
        origin = c['point']
        rb = sub(max(brace['axis'], key=lambda q: math.dist(q, origin)), origin)
        rh = sub(max(beam['axis'], key=lambda q: math.dist(q, origin)), origin)
        if dot(unit([*rb[:2], 0]), unit([*rh[:2], 0])) > -.999:
            raise ValueError('HR14 boundary-corner proposal requires the actual opposite-side beam')
        record = b.records[c['design_record_ids'][0]]['data']
        if 'corner gusset at the column base' not in record.get('type', ''):
            raise ValueError('HR14 source corner condition changed')
        previous = list(c['member_ids'])
        basis = ('A: the saved story-2 selection describes a column-base gusset, '
                 'but this basement-boundary column continues below the joint and '
                 'the only beam is on the opposite side. Retain the selected brace, '
                 '3/4 in gusset and original weld dimensions. Propose a 1 in steel '
                 'seat with two 1/2 in triangular stiffeners on the actual column '
                 'flange beneath the gusset. This replaces the absent receiving '
                 'beam at the gusset edge. Seat, column local effects and the changed '
                 'load path require engineering verification; the saved capacity '
                 'checks do not verify this proposal.')
        c['member_ids'] = [brace['id'], column['id']]
        c['parameters']['unsupported_base_corner'] = dict(
            opposite_beam_id=beam['id'], source_beam_profile=beam['profile_id'],
            seat_thickness_in=1., seat_width_in=12., stiffener_thickness_in=.5,
            stiffener_depth_in=12., basis=basis)
        c['engineering_status'] = 'source_condition_mismatch_proposed_fit_not_verified'
        c.setdefault('coordination_requirements', []).append(basis)
        b.changes.append(dict(kind='accepted_boundary_corner_seat', connection_id=c['id'],
            previous_member_ids=previous, member_ids=list(c['member_ids']), basis=basis,
            source_record_ids=list(c['design_record_ids']), capacity_status='not_verified'))
        b.note('BOUNDARY-CORNER-SEAT', basis)


def transition(b):
    lookup = {m['id']: m for m in b.members}
    c = next(v for v in b.connections if v['id'] == 'hr:element:332:splice')
    upper, lower = [lookup[i] for i in c['member_ids']]
    if (upper['profile_id'], lower['profile_id']) != ('W14X48', 'W14X550'):
        raise ValueError('HR9 special splice source sections changed')
    if abs(dot(upper['local_y'], lower['local_y'])) > .001:
        raise ValueError('HR9 transition proposal requires the perpendicular source sections')
    basis = ('A: the source places W14X48 over W14X550 with perpendicular webs. '
             'The selected ordinary W14X48 splice describes aligned W14X48 pieces '
             'and does not verify this transition. Retain both source sections '
             'and orientations; propose a 1-1/2 x 22 x 22 in transfer plate, '
             'with CJP welds at both column flange ends and webs. The plate, '
             'welds, local column effects and force transfer require a separate '
             'design check. Original splice calculation remains source context.')
    original = list(c['design_record_ids'])
    c.setdefault('source_context_records', []).extend(original)
    c['source_record_applicability'] = [dict(record_id=r, applies=False, reason=basis) for r in original]
    c['design_record_ids'] = []
    c['detail_ref']['id'] = 'review_transition_splice'
    c['parameters'].update(plate_thickness_in=1.5, plate_width_in=22., proposal_basis=basis)
    c['engineering_status'] = 'source_condition_mismatch_proposed_fit_not_verified'
    for m, sign in ((upper, 1), (lower, -1)):
        end = min(range(2), key=lambda i: math.dist(m['axis'][i], c['point']))
        previous = copy.deepcopy(m['end_offsets'])
        m['end_offsets'][end][2] = sign*.75
        b.changes.append(dict(kind='transition_plate_end_fit', member_id=m['id'],
            previous_end_offsets=previous, end_offsets=copy.deepcopy(m['end_offsets']), basis=basis))
    b.changes.append(dict(kind='accepted_perpendicular_column_transition', connection_id=c['id'],
        source_context_record_ids=original, basis=basis, capacity_status='not_verified'))
    b.note('COLUMN-TRANSITION', basis)


def draw_transition(ctx):
    from .review_receiver_geometry import extract
    a = ctx.a
    axes = ([1,0,0], [0,1,0], [0,0,1])
    thickness=ctx.params['plate_thickness_in'];width=ctx.params['plate_width_in']
    a.box('TRANSFER',[-width/2,-width/2,-thickness/2],[width,width,thickness],
          'A','A perpendicular-section transfer plate; original ordinary splice not applicable')
    for m,label,sign in zip(ctx.ms,('UPPER','LOWER'),(1,-1)):
        extract(ctx,m,label,axes,30)
        dims=ctx.p[m['profile_id']]['dimensions']
        flange=m['local_y'];depth=cross([0,0,1],flange)
        z=sign*thickness/2
        for side in (-1,1):
            centre=add(mul(depth,side*(dims['d']/2-dims['tf']/2)),[0,0,z])
            a.weld(label+'-F'+str(side),add(centre,mul(flange,-dims['bf']/2)),
                   add(centre,mul(flange,dims['bf']/2)),[label,'TRANSFER'],
                   dims['tf'],kind='CJP',basis='A',description='A column flange-end CJP to transfer plate; capacity unverified')
        a.weld(label+'-WEB',add(mul(depth,-dims['d']/2+dims['tf']),[0,0,z]),
               add(mul(depth,dims['d']/2-dims['tf']),[0,0,z]),[label,'TRANSFER'],
               dims['tw'],kind='CJP',basis='A',description='A web-end CJP to transfer plate; capacity unverified')
    a.dim([-width/2,0,-thickness/2],[width/2,0,-thickness/2],'Transfer-plate width',basis='A',offset=-48)
    a.section_axis=1;a.section_at=0
    a.dim([width/2,0,-thickness/2],[width/2,0,thickness/2],'Plate thickness',basis='A',view='section',offset=-55)
    a.notes.append(ctx.params['proposal_basis'])
