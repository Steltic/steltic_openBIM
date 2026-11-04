"""Remove tessellation seams from drawings without changing exported solids.

Opposite coincident caps separate the closed segments used by the mesh builder.
Coplanar faces then share a single exterior boundary. A face group with a hole
or branching boundary is retained, so this never fills a real section opening.
"""
from collections import defaultdict
import math
from .pilots.model import sub,cross,dot,unit


def normal(face):
    for a,b in zip(face[1:],face[2:]):
        n=cross(sub(a,face[0]),sub(b,face[0]))
        if dot(n,n)>1e-16:return unit(n)
    return None


def display_faces(faces):
    points=lambda f:[tuple(round(float(v),7) for v in p) for p in f]
    identical=defaultdict(list)
    for f in faces:
        n=normal(f)
        if n is not None:identical[tuple(sorted(points(f)))].append((f,n))
    groups=defaultdict(list)
    for rows in identical.values():
        if len(rows)==2 and dot(rows[0][1],rows[1][1])<-.999999:continue
        for f,n in rows:
            key=tuple(round(v,7) for v in n)+(round(dot(n,f[0]),7),)
            groups[key].append(f)
    result=[]
    for plane,polys in groups.items():
        if len(polys)==1:result.extend(polys);continue
        edges=defaultdict(list)
        for f in polys:
            ps=points(f)
            for a,b in zip(ps,ps[1:]+ps[:1]):edges[tuple(sorted((a,b)))].append((a,b))
        if any(len(v)>2 for v in edges.values()):result.extend(polys);continue
        boundary=[v[0] for v in edges.values() if len(v)==1]
        outgoing=defaultdict(list);incoming=defaultdict(list)
        for a,b in boundary:outgoing[a].append(b);incoming[b].append(a)
        if not boundary or any(len(outgoing[p])!=1 or len(incoming[p])!=1 for p in set(outgoing)|set(incoming)):
            result.extend(polys);continue
        remaining=set(boundary);loops=[]
        while remaining:
            first,next_point=min(remaining);loop=[first];previous=first
            while True:
                remaining.remove((previous,next_point))
                if next_point==first:break
                loop.append(next_point);previous=next_point;next_point=outgoing[previous][0]
            loops.append(loop)
        # Opposite winding denotes a hole. Keep its source polygons instead.
        signed=[sum(dot(cross(a,b),plane[:3]) for a,b in zip(f,f[1:]+f[:1])) for f in loops]
        if any(area<=1e-8 for area in signed):result.extend(polys)
        else:result.extend(loops)
    return result


def feature_edges(faces,angle_degrees=20):
    """Hide approximation edges on a selected smooth surface, keep silhouettes."""
    key=lambda p:tuple(round(float(v),7) for v in p)
    edges=defaultdict(list)
    for f in faces:
        n=normal(f)
        for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((key(a),key(b))))].append(n)
    cutoff=math.cos(math.radians(angle_degrees));result=[]
    for f in faces:
        flags=[]
        for a,b in zip(f,f[1:]+f[:1]):
            ns=edges[tuple(sorted((key(a),key(b))))]
            flags.append(not(len(ns)==2 and None not in ns and dot(*ns)>cutoff))
        result.append(flags)
    return result
