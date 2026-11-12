"""Reconcile previously authored Ex35 skid-bay occurrences with the written layout."""
from functools import lru_cache
from math import dist

from .bim_assemblies import fingerprint
from .hr_connection_frames import place_template
from .pilots.model import add, sub, mul, dot


# Only the reviewed legacy member layout is eligible for this migration.
LEGACY_LAYOUT_SHA256 = '97a832cba80b55407c533f2a2d95c72fc764141865ba0ee22f9531699a0ec191'


@lru_cache(maxsize=1)
def reviewed_bay():
    # Reuse the same source-bound authoring recipe as a fresh review model.
    from .review_cases import build_model, evidence, scenario
    source = evidence('hr35')['package']
    answers = fingerprint(scenario('hr35')['answers'])
    model = build_model(source, {'design_scenario':dict(id='hr35', answers_sha256=answers)})
    return source, model


def reconnect_joints(physical, changed, moved, members):
    joints = {}
    points = {}
    for original in physical['joints']:
        j = dict(original)
        for field in ('member_ends', 'attachments'):
            j[field] = [r for r in j[field] if r['member_id'] not in moved]
        joints[j['id']] = j
        points[tuple(j['point'])] = j
    for c in changed.values():
        pt = c['point']
        j = points.get(tuple(pt))
        if j is None:
            jid = 'skid-bay-' + fingerprint(pt)[:16]
            j = dict(id=jid, point=pt, status='declared', basis='Issued skid-bay framing',
                     member_ends=[], attachments=[])
            joints[jid] = points[tuple(pt)] = j
        c['joint_id'] = j['id']
        linked = {r['member_id'] for r in j['member_ends'] + j['attachments']}
        for mid in sorted(set(c['member_ids']) - linked):
            a,b = members[mid]['axis']
            if min(dist(pt,a),dist(pt,b)) < 1e-6:
                j['member_ends'].append(dict(member_id=mid, end='start' if dist(pt,a)<1e-6 else 'end',
                                             joint_offset=[0.,0.,0.]))
            else:
                d = sub(b,a)
                s = max(0.,min(1.,dot(sub(pt,a),d)/dot(d,d)))
                j['attachments'].append(dict(member_id=mid, station=s, offset=sub(pt,add(a,mul(d,s)))))
    live = {changed.get(c['id'],c)['joint_id'] for c in physical['connections'] if c.get('joint_id')}
    dispositions = [dict(row, joint_id=changed[row['connection_ids'][0]]['joint_id'])
                    if len(row.get('connection_ids',[]))==1 and row['connection_ids'][0] in changed else row
                    for row in physical.get('joint_dispositions',[])]
    return [j for j in joints.values() if j['id'] in live or j['member_ends']], dispositions


def skid_bay_view(physical):
    beam = next((m for m in physical.get('members',[]) if m['id']=='SKID-BEAM-0'), None)
    if not (beam and beam['axis']==[[240,300,312],[480,300,312]]
            and 'members/skid-beam-W16X26' in beam.get('design_record_ids',[])
            and any(t['id'].startswith('hr35-assembly-') for t in physical.get('assemblies',[]))):
        return physical
    from .assembly_templates import build_scene
    from .saved_assemblies import native_parts
    source, model = reviewed_bay()
    members = {m['id']:m for m in physical['members']}
    moved = {m['id'] for m in model['members'] if m['id'].startswith(('SKID-BEAM-', 'SKID-DIAG-', 'INF-FLOOR-9-'))}
    layout = sorted((m['id'],m['profile_id'],m['axis'],m['end_offsets'],m['local_y'])
                    for m in members.values() if m['id'] in moved)
    if fingerprint(layout)!=LEGACY_LAYOUT_SHA256:
        return physical
    for m in model['members']:
        if m['id'] in moved:
            original = members[m['id']]
            if original['profile_id']!=m['profile_id'] or original.get('analysis_ids'):
                raise ValueError('Saved skid bay differs from the reviewed sections or contains an analysis member')
            members[m['id']] = dict(original, **{k:m[k] for k in ('axis','local_y','end_offsets','plan_fit','source_axis') if k in m})
    targets = {c['id']:c for c in model['connections'] if moved.intersection(c['member_ids'])}
    templates = {t['id']:t for t in physical['assemblies']}
    materials = {m['id']:m for m in physical['materials']}
    changed, variants = {}, {}
    for c in physical['connections']:
        drawn = targets.get(c['id'])
        if drawn is None:
            continue
        old = c['assembly_instance']
        template = templates[old['template_id']]
        ids = drawn['member_ids']
        family = drawn['detail_ref']['id']
        # The beam details and the square supplier feet use local +X along
        # the supporting span. Plan-angle scenes already use the world axes.
        if family=='review_plan_angle':
            scene = build_scene(model,source,drawn)
            labels = ['ANGLE'] + ['HOST'+str(i) for i in range(len(ids)-1)]
            bindings = dict(zip(labels, ids))
            local = {p['id']:p['member']['axis'] for p in scene['parts'] if p.get('member')}
            parts = native_parts(scene, template, materials)
            template = dict(template, id=template['id']+'-skid-'+fingerprint(parts)[:12], parts=parts,
                            receivers=[dict(r,source_context_axis=local[r['id']]) for r in template['receivers']],
                            source_context=[p for p in scene['parts'] if p.get('representation_role')=='context_only'])
            x, y = [1.,0.,0.], [0.,1.,0.]
        elif family in ('review_beam','review_equipment_foot'):
            bindings = (dict(M2=ids[0], M1=ids[1]) if family=='review_beam' else dict(LEG=ids[0], BEAM=ids[1]))
            x, y = ([-old['x_axis'][1],old['x_axis'][0],old['x_axis'][2]],
                    [-old['y_axis'][1],old['y_axis'][0],old['y_axis'][2]])
        else:
            raise ValueError('Unexpected connection family in the saved skid bay: '+family)
        frame = dict(old, origin=drawn['point'], x_axis=x, y_axis=y, bindings=bindings)
        changed[c['id']] = dict(c, member_ids=ids, point=drawn['point'],
                                parameters={**c.get('parameters',{}),**drawn.get('parameters',{})},
                                assembly_instance=place_template(template,frame,members,variants))
    if changed.keys()!=targets.keys():
        raise ValueError('Saved skid-bay connection inventory differs from the reviewed layout')
    joints, dispositions = reconnect_joints(physical,changed,moved,members)
    return dict(physical, members=list(members.values()), joints=joints, joint_dispositions=dispositions,
                connections=[changed.get(c['id'],c) for c in physical['connections']],
                assemblies=[*physical['assemblies'], *variants.values()])
