"""Cut explicit holes in a planar connection plate and retain their source."""
from .assembly_scene import bounds
from .pilots.model import add, mul, dot, cross, unit


def drill_plate(part, points, axis, diameter, basis):
    """Return real plate-surface triangles and hole walls in the local frame."""
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon, Point
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    axis = unit(axis)
    u = unit(cross(axis, [0,0,1])) if abs(axis[2]) < .9 else unit(cross(axis,[0,1,0]))
    v = cross(axis,u)
    vertices = [q for face in part['faces'] for q in face]
    levels = [dot(q,axis) for q in vertices]
    lo, hi = min(levels), max(levels)
    # Supported plate recipes are prismatic. Recover the real planar outline,
    # including concave perimeter segments, from the cap faces.
    caps = []
    for face in part['faces']:
        if all(abs(dot(q,axis)-lo)<1e-6 for q in face):
            poly=Polygon([(dot(q,u),dot(q,v)) for q in face])
            if poly.area>1e-9:caps.append(poly)
    if not caps or hi-lo<=1e-7:
        raise ValueError('A through-hole needs a planar solid plate: '+part['id'])
    outline = unary_union(caps)
    radius = diameter/2
    holes = [Point(dot(q,u),dot(q,v)).buffer(radius,quad_segs=8) for q in points]
    for hole in holes:
        if not outline.buffer(1e-7).covers(hole):
            raise ValueError('Selected hole leaves plate perimeter: '+part['id'])
    remaining = outline.difference(unary_union(holes))
    if remaining.geom_type!='Polygon' or not remaining.is_valid:
        raise ValueError('Hole pattern disconnects plate: '+part['id'])
    remaining=orient(remaining,sign=1)
    def point(pair,z):
        return add(add(mul(u,pair[0]),mul(v,pair[1])),mul(axis,z))
    faces=[]
    for triangle in constrained_delaunay_triangles(remaining).geoms:
        ring=list(orient(triangle,sign=1).exterior.coords)[:-1]
        faces.append([point(q,lo) for q in reversed(ring)])
        faces.append([point(q,hi) for q in ring])
    for ring in [remaining.exterior,*remaining.interiors]:
        coords=list(ring.coords)
        for a,b in zip(coords,coords[1:]):
            faces.append([point(a,lo),point(b,lo),point(b,hi),point(a,hi)])
    part['faces']=faces
    part['bounds']=bounds(faces)
    part['geometry']={'type':'mesh','faces':faces}
    part.setdefault('holes',[]).extend(dict(point=list(q),axis=list(axis),
        diameter_in=diameter,basis=basis) for q in points)


def drill_joined_plates(assembly, group, diameter, basis):
    lookup={part['id']:part for part in assembly.parts}
    for pid in group['connects']:
        part=lookup[pid]
        if part['kind']=='plate':
            drill_plate(part,group['points'],group['axis'],diameter,basis)
