"""Local detail extracts of actual physical receivers; no profile substitution."""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross


def horizontal_frame(direction):
    x=unit([direction[0],direction[1],0])
    return (x,cross([0,0,1],x),[0,0,1])


def point(q,origin,axes):
    return [dot(sub(q,origin),v) for v in axes]


def vector(q,axes):
    return [dot(q,v) for v in axes]


def extract(ctx,member,label,axes,extent=36):
    origin=ctx.c['point'];ends=[add(q,o) for q,o in zip(member['axis'],member.get('end_offsets',[[0,0,0],[0,0,0]]))]
    u=unit(sub(ends[1],ends[0]));length=math.dist(*ends)
    station=max(0,min(length,dot(sub(origin,ends[0]),u)))
    lo,hi=max(0,station-extent),min(length,station+extent)
    chosen=[add(ends[0],mul(u,t)) for t in (lo,hi)]
    slots=[]
    for selected in member.get('slots',[]):
        start=max(lo,selected['start_in']);end=min(hi,selected['end_in'])
        if end>start:slots.append(dict(copy.deepcopy(selected),start_in=start-lo,end_in=end-lo))
    return ctx.a.member(label,member['profile_id'],*[point(q,origin,axes) for q in chosen],
                        y=vector(member['local_y'],axes),basis=member.get('basis','S'),
                        description='Actual receiving '+member['kind']+' '+member['profile_id'],
                        source_member_index=ctx.c['member_ids'].index(member['id']),**({'slots':slots} if slots else {}))


def nearest_beam(model,origin,exclude=()):
    candidates=[]
    for member in model['members']:
        if member['id'] in exclude or member['kind'] not in ('beam','girder','moment_beam','rafter','walkway_edge_beam','equipment_beam'):continue
        a,b=member['axis'];v=sub(b,a);length=dot(v,v)
        if not length:continue
        station=max(0,min(1,dot(sub(origin,a),v)/length));q=add(a,mul(v,station))
        candidates.append((math.dist(q,origin),member['id'],member))
    if not candidates or min(candidates)[0]>60:raise ValueError('No actual beam receiver within the detail search envelope')
    return min(candidates)[2]
