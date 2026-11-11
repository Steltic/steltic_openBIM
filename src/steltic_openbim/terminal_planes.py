"""Transfer the selected local terminal cuts to the bound global member plies."""
import math
from collections import defaultdict
from .bim_assemblies import transformed
from .pilots.model import add, sub, mul, dot, unit


def apply_planes(member, entries):
    previous = member.get('extrusion_end_offsets',member['end_offsets'])
    a,b = [add(p,o) for p,o in zip(member['axis'],previous)]
    axis = unit(sub(b,a))
    length = math.dist(a,b)
    low, high = 0.,length
    for row in entries:
        direction = dot(axis,row['normal'])
        if abs(direction)<1e-8:
            raise ValueError('Terminal plane parallel to member axis: '+member['id'])
        station = (row['offset_in']-dot(a,row['normal']))/direction
        if direction>0:low=max(low,station)
        else:high=min(high,station)
    if high<=low:
        raise ValueError('Terminal cuts consume member '+member['id'])
    member['extrusion_end_offsets'] = previous
    member['terminal_planes'] = entries
    member['end_offsets'] = [sub(add(a,mul(axis,s)),p) for s,p in zip((low,high),member['axis'])]


def saved_cuts(physical, model):
    drawing_scenes={s['id']:s for s in model['connection_assemblies']}
    source_members={m['id']:m for m in model['members']}
    members={m['id']:m for m in physical['members']}
    planes=defaultdict(list);changed={}
    for c in physical['connections']:
        frame=c.get('assembly_instance')
        scene=drawing_scenes.get(c.get('assembly_id'))
        if not frame or not scene or scene['family'] not in ('review_truss_node','review_truss_heel'):
            continue
        for part in scene['parts']:
            cuts=part.get('cut_planes',[])
            mid=frame['bindings'].get(part['id'])
            if not cuts or mid not in members:continue
            m=members[mid]
            end=min(range(2),key=lambda i:math.dist(m['axis'][i],frame['origin']))
            if math.dist(m['axis'][end],frame['origin'])>.01:
                # A spanning receiver is continuous at this joint.
                continue
            for cut in cuts:
                n=transformed(cut['normal'],frame,True)
                planes[mid].append(dict(normal=n,offset_in=dot(frame['origin'],n)+cut['offset'],
                    end=end,connection_id=c['id'],receiver_id=part['id'],
                    basis='Accepted local truss receiver miter in the actual occurrence frame'))
            changed[c['id']]=scene
    for mid,rows in planes.items():
        apply_planes(members[mid],rows)
        for name in ('terminal_planes','extrusion_end_offsets','end_offsets'):
            source_members[mid][name]=members[mid][name]
    return changed
