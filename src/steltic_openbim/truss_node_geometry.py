"""Actual local truss pieces and explicitly proposed short-end screw layouts."""
import math
from .pilots.model import add,sub,mul,unit,dot


def receivers(members,origin,extent=24):
    spans=[max(abs(q[i]-origin[i]) for m in members for q in m['axis']) for i in (0,1)]
    horizontal=0 if spans[0]>=spans[1] else 1;other=1-horizontal
    local=lambda q:[q[horizontal]-origin[horizontal],q[other]-origin[other],q[2]-origin[2]]
    result=[]
    for index,m in enumerate(members):
        a,b=[add(q,o) for q,o in zip(m['axis'],m.get('end_offsets',[[0,0,0],[0,0,0]]))]
        u=unit(sub(b,a));length=math.dist(a,b);at=max(0,min(length,dot(sub(origin,a),u)))
        ends=[local(add(a,mul(u,t))) for t in (max(0,at-extent),min(length,at+extent))]
        ends.sort(key=lambda q:dot(q,q))
        ly=m['local_y']
        result.append(dict(axis=ends,local_y=[ly[horizontal],ly[other],ly[2]],
            profile_id=m['profile_id'],source_member_index=index,kind=m['kind']))
    return result


def short_screw_layout(direction,normals,last_station,usual_start):
    """Keep the usual six when they fit; otherwise propose a smaller real group.

    All groups are A geometry, never supplier or structural capacity selections.
    The 3/8 in clearance applies to actual end and mitre planes.
    """
    across=[-direction[2],0,direction[0]]
    end=last_station-.375
    if usual_start+3<=end+1e-8:return [usual_start+i*1.5 for i in range(3)],[-.75,.75],False
    options=[]
    for offsets in ([-.75,.75],[0]):
        start=1.0
        for normal in normals:
            along=dot(normal,direction)
            if along<=1e-8:continue
            start=max(start,*[(.5-dot(normal,across)*s)/along for s in offsets])
        start=math.ceil(start*8)/8
        count=min(3,math.floor((end-start)/1.0+1e-8)+1)
        if count>0:options.append((count*len(offsets),[start+i for i in range(count)],offsets))
    if not options:raise ValueError('Short truss end has no screw station clear of its actual mitre and end cut')
    _,stations,offsets=max(options,key=lambda row:row[0])
    return stations,offsets,True
