"""Bind CFS detail receivers to actual pieces before grouping drawing variants.

These are fixture set-out operations. They do not select a new section or run a
capacity calculation; missing receiving framing is left for the fit audit.
"""
from collections import defaultdict
import itertools,math,copy
from .pilots.model import add,sub,mul,dot,cross,unit


def axis(member):return [add(p,o) for p,o in zip(member['axis'],member.get('end_offsets',[[0,0,0],[0,0,0]]))]


def bind(model):
    if not model['pilot'].startswith('cfs'):return
    for c in model['connections']:
        if 'parameters' in c:c['parameters']=copy.deepcopy(c['parameters'])
    from .review_floor_openings import bind as openings
    openings(model)
    bind_sills_and_joists(model)
    members={m['id']:m for m in model['members']};cells=defaultdict(list)
    tracks=[m for m in model['members'] if m['kind'] in ('top_track','bottom_track','ordinary_track','tier_track','parapet_cap')]
    opening_edges=[m for m in model['members'] if m['kind'] in ('opening_header','opening_sill')]
    profiles={p['id']:p for p in model['profiles']}
    for m in tracks:
        aa,bb=axis(m)
        for key in itertools.product(*(range(math.floor(min(a,b)/96),math.floor(max(a,b)/96)+1) for a,b in zip(aa,bb))):cells[key].append(m)
    for c in model['connections']:
        if c['detail_ref']['id']!='cfs_stud':continue
        stud=members[c['member_ids'][0]];aa,bb=axis(stud)
        if abs(unit(sub(bb,aa))[2])<.99999:continue
        point=c['point'];x=unit([*stud['local_y'][:2],0]);y=cross([0,0,1],x);axes=(x,y,[0,0,1]);choices=[];seen=set()
        cell=[math.floor(v/96) for v in point]
        for key in itertools.product(*(range(v-1,v+2) for v in cell)):
            for track in cells[key]:
                if track['id'] in seen:continue
                seen.add(track['id']);a,b=axis(track);v=sub(b,a);length=math.dist(a,b);direction=mul(v,1/length)
                if abs(dot(direction,x))<.99999:continue
                t=dot(sub(point,a),direction)
                # The track corner/end fit can trim its web 1/16 in back from
                # the stud workline. Keep that real receiver instead of falling
                # back to an unrelated generic track at the same node.
                if not -.125<=t<=length+.125:continue
                nearest=add(a,mul(direction,max(0,min(length,t))));delta=sub(nearest,point)
                if abs(dot(delta,y))>.01 or abs(delta[2])>1:continue
                choices.append((math.dist(nearest,point),track['id'],track,nearest))
        if not choices:
            # Cripple studs meet the underside of a sill or the top of a header,
            # not an invented track at the opening boundary.
            from .assembly_templates import effective
            candidates=[]
            for edge in opening_edges:
                a,b=axis(edge);u=unit(sub(b,a));length=math.dist(a,b)
                if abs(dot(u,x))<.99999:continue
                t=dot(sub(point,a),u)
                if not -.01<=t<=length+.01:continue
                near=add(a,mul(u,t));delta=sub(near,point)
                if abs(dot(delta,y))>.01:continue
                gap=abs(abs(delta[2])-effective(profiles,edge['profile_id'])/2)
                if gap<=.25:candidates.append((gap,edge['id'],edge))
            if candidates:
                edge=min(candidates,key=lambda q:(q[0],q[1]))[2]
                ea,eb=axis(edge);u=unit(sub(eb,ea));length=math.dist(ea,eb);s=max(0,min(length,dot(sub(point,ea),u)))
                local=lambda q:[round(dot(sub(q,point),v),7) for v in axes]
                selected=[add(ea,mul(u,t)) for t in (max(0,s-24),min(length,s+24))]
                c.setdefault('parameters',{})['physical_stud_support']=dict(member_id=edge['id'],profile_id=edge['profile_id'],
                    axis=[local(q) for q in selected],local_y=[round(dot(edge['local_y'],v),7) for v in axes],
                    stud_direction=1 if abs(point[2]-aa[2])<=abs(point[2]-bb[2]) else -1)
                c['member_ids']=list(dict.fromkeys([stud['id'],edge['id']]+c['member_ids'][1:]))
            continue
        _,_,track,nearest=min(choices,key=lambda q:(q[0],q[1]));a,b=axis(track);u=unit(sub(b,a));station=dot(sub(nearest,a),u)
        local=lambda p:[round(dot(sub(p,point),v),7) for v in axes]
        ends=[add(a,mul(u,t)) for t in (max(0,station-18),min(math.dist(a,b),station+18))]
        direction=1 if abs(point[2]-aa[2])<=abs(point[2]-bb[2]) else -1
        par=c.setdefault('parameters',{})
        par['physical_track']=dict(profile_id=track['profile_id'],axis=[local(p) for p in ends],local_y=[round(dot(track['local_y'],v),7) for v in axes])
        if track.get('slots'):
            first=max(0,station-18);last=min(math.dist(a,b),station+18)
            slots=[]
            for selected in track['slots']:
                start=max(first,selected['start_in']);end=min(last,selected['end_in'])
                if end>start:slots.append(dict(copy.deepcopy(selected),start_in=start-first,end_in=end-first))
            if slots:par['physical_track']['slots']=slots
        par['stud_end_direction']=direction
        if min(math.dist(point,aa),math.dist(point,bb))>1:
            par['stud_through_track']=True
        # At a cut/spliced track end the usual flange screw can lie outside
        # the actual finite track. A separately labelled web/foot clip bridges
        # that finite end; do not extend the receiving track just for the view.
        if min(station,math.dist(a,b)-station)<3:
            par['physical_track_end_clip']=True
        c['member_ids']=list(dict.fromkeys([stud['id'],track['id']]+c['member_ids'][1:]))


def bind_sills_and_joists(model):
    """Use the real track span and real joist support, not a generic wall stack."""
    from .assembly_templates import effective
    profiles={p['id']:p for p in model['profiles']};members={m['id']:m for m in model['members']}
    supports=[m for m in model['members'] if m['kind'] in ('girder','beam','rim_track','top_track','ordinary_track','floor_rim')]
    index=defaultdict(list)
    for m in supports:
        aa,bb=axis(m)
        for key in itertools.product(*(range(math.floor(min(a,b)/96),math.floor(max(a,b)/96)+1) for a,b in zip(aa,bb))):index[key].append(m)
    for c in model['connections']:
        family=c['detail_ref']['id'];primary=members[c['member_ids'][0]]
        if family not in ('review_cfs_sill','review_cfs_joist'):continue
        point=c['point'];ends=axis(primary);x=unit(sub(ends[1],ends[0]))
        if abs(x[2])>.01:continue
        if family=='review_cfs_joist' and math.dist(point,ends[1])<math.dist(point,ends[0]):x=mul(x,-1)
        y=cross([0,0,1],x);axes=(x,y,[0,0,1]);local=lambda p:[round(dot(sub(p,point),v),7) for v in axes]
        def receiver(m,full=False):
            a,b=axis(m);u=unit(sub(b,a));station=max(0,min(math.dist(a,b),dot(sub(point,a),u)))
            selected=[a,b] if full else [add(a,mul(u,t)) for t in (max(0,station-24),min(math.dist(a,b),station+24))]
            return dict(profile_id=m['profile_id'],axis=[local(p) for p in selected],local_y=[round(dot(m['local_y'],v),7) for v in axes])
        if family=='review_cfs_sill':
            c.setdefault('parameters',{})['physical_sill']=receiver(primary,True)
            continue
        choices=[];seen=set();cell=[math.floor(v/96) for v in point]
        for key in itertools.product(*(range(v-1,v+2) for v in cell)):
            for m in index[key]:
                if m['id'] in seen or m['id']==primary['id']:continue
                seen.add(m['id']);a,b=axis(m);u=unit(sub(b,a))
                if abs(dot(x,u))>.05:continue
                length=math.dist(a,b);s=dot(sub(point,a),u)
                if not -.01<=s<=length+.01:continue
                q=add(a,mul(u,s));delta=sub(q,point)
                if math.hypot(*delta[:2])>.01 or abs(delta[2])>effective(profiles,m['profile_id'])/2+effective(profiles,primary['profile_id'])/2+.25:continue
                choices.append((abs(delta[2]),m['id'],m))
        if choices:
            support=min(choices,key=lambda q:(q[0],q[1]))[2]
            c.setdefault('parameters',{})['physical_joist_end']=dict(joist=receiver(primary),support=receiver(support),support_kind=support['kind'])
            c['member_ids']=list(dict.fromkeys([primary['id'],support['id']]+c['member_ids'][1:]))
