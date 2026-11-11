"""Cut explicit holes in a planar connection plate and retain their source."""
from .assembly_scene import bounds
from .pilots.model import add, mul, dot, cross, unit


def drill_plate(part, points, axis, diameter, basis,radial_reference=None,skip_disjoint=False):
    """Return real plate-surface triangles and hole walls in the local frame."""
    from shapely import constrained_delaunay_triangles,set_precision
    from shapely.geometry import Polygon, Point
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    axis = unit(axis)
    u = unit(cross(axis, [0,0,1])) if abs(axis[2]) < .9 else unit(cross(axis,[0,1,0]))
    if radial_reference is not None:
        u=unit(add(radial_reference,mul(axis,-dot(radial_reference,axis))))
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
    if skip_disjoint and not caps:return False
    if not caps or hi-lo<=1e-7:
        raise ValueError('A through-hole needs a planar solid plate: '+part['id'])
    outline = unary_union(caps)
    radius = diameter/2
    holes = [Point(dot(q,u),dot(q,v)).buffer(radius,quad_segs=8) for q in points]
    if skip_disjoint:
        holes=[h for h in holes if outline.intersection(h).area>1e-8]
        if not holes:return False
    for hole in holes:
        # A member web is split into individual prisms at every cope/slot
        # station. A valid circular bore may cross this internal strip seam.
        # Standalone selected plates still require a fully enclosed hole.
        if not skip_disjoint and not outline.buffer(1e-7).covers(hole):
            raise ValueError('Selected hole leaves plate perimeter: '+part['id'])
    remaining = set_precision(outline.difference(unary_union(holes)),1e-7)
    if (remaining.geom_type!='Polygon' and not (skip_disjoint and remaining.geom_type=='MultiPolygon')) or not remaining.is_valid:
        raise ValueError('Hole pattern disconnects plate: '+part['id'])
    components=[orient(poly,sign=1) for poly in (remaining.geoms if remaining.geom_type=='MultiPolygon' else [remaining])]
    def point(pair,z):
        return add(add(mul(u,pair[0]),mul(v,pair[1])),mul(axis,z))
    faces=[]
    for component in components:
        for triangle in constrained_delaunay_triangles(component).geoms:
            ring=list(orient(triangle,sign=1).exterior.coords)[:-1]
            faces.append([point(q,lo) for q in reversed(ring)])
            faces.append([point(q,hi) for q in ring])
        for ring in [component.exterior,*component.interiors]:
            coords=list(ring.coords)
            for a,b in zip(coords,coords[1:]):
                faces.append([point(a,lo),point(b,lo),point(b,hi),point(a,hi)])
    part['faces']=faces
    part['bounds']=bounds(faces)
    part['geometry']={'type':'mesh','faces':faces}
    part.setdefault('holes',[]).extend(dict(point=list(q),axis=list(axis),
        diameter_in=diameter,basis=basis) for q in points)
    return True


def drill_receivers(assembly,group,diameter):
    """Keep one hole set on the sheet's receiver and the installed member."""
    from .pilots.geometry import member_faces
    drill_joined_plates(assembly,group,diameter,'A selected-bolt fit allowance')
    parts={p['id']:p for p in assembly.parts}
    for role in group['connects']:
        part=parts.get(role,{})
        if not part.get('member'):continue
        member=part['member'];drills=member.setdefault('through_bores',[])
        drills.extend(dict(point=q,axis=group['axis'],diameter_in=diameter,fastener=group['id'])
                      for q in group['points'])
        part['faces']=member_faces(member,assembly.profiles)
        part['bounds']=bounds(part['faces'])


def bind_member_bores(physical,model,scenes):
    from .bim_assemblies import transformed
    drawing={m['id']:m for m in model['members']}
    members={m['id']:m for m in physical['members']}
    for c in physical['connections']:
        scene=scenes.get(c['id'])
        if not scene:continue
        frame=c['assembly_instance']
        for part in scene['parts']:
            holes=part.get('member',{}).get('through_bores')
            if not holes:continue
            mid=frame['bindings'][part['id']];m=members[mid]
            others=[h for h in m.get('through_bores',[]) if h.get('connection_id')!=c['id']]
            m['through_bores']=others+[dict(h,point=transformed(h['point'],frame),axis=transformed(h['axis'],frame,True),
                connection_id=c['id']) for h in holes]
            drawing[mid]['through_bores']=m['through_bores']


def drill_joined_plates(assembly, group, diameter, basis):
    lookup={part['id']:part for part in assembly.parts}
    for pid in group['connects']:
        part=lookup[pid]
        if part['kind']=='plate':
            drill_plate(part,group['points'],group['axis'],diameter,basis)
