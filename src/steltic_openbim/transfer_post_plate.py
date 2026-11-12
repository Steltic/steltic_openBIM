"""Make a monolithic transfer plate with a thick post region and an outboard taper."""
import math

import numpy as np
from shapely import constrained_delaunay_triangles, set_precision
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union


def post_plate(assembly, name, outline, contact_y, side, v, schedule, weld):
    outward = np.asarray([v[0], v[2]], dtype=float)
    across = np.asarray([v[2], -v[0]], dtype=float)
    plane = np.column_stack((across, outward))
    border = Polygon(np.asarray(outline) @ plane)
    base = schedule['arm_thickness_in']
    full = schedule['thickness_in']
    slope = schedule['outside_taper_run_per_rise']
    radius = schedule['blend_radius_in'] if 'blend_radius_in' in schedule else schedule['minimum_blend_radius_in']
    near = weld['start_in']
    far = near + weld['length_in']
    width = schedule['weld_root_width_in'] / 2
    shoulder = width + (far - near) * math.tan(math.radians(schedule['fan_angle_deg']))
    if (min(width, base, slope, radius) <= 0 or full <= base or
            abs(2 * shoulder - schedule['joint_side_fan_width_in']) > .001):
        raise ValueError('Inconsistent post fan dimensions at ' + name)
    run = (full - base) * slope
    beyond = border.bounds[1] - run - 2 * radius - 1.
    nominal = Polygon([(-shoulder,beyond),(shoulder,beyond),(shoulder,near),
                       (width,far),(-width,far),(-shoulder,near)])
    # One blend radius of additional stock preserves the complete checked
    # spread and rounds the fan-to-shoulder and far-end corners outboard.
    fan = orient(nominal.buffer(radius,quad_segs=12),sign=1)
    ring = np.asarray(fan.exterior.coords[:-1])
    tangents = np.roll(ring,-1,axis=0) - ring
    normals = np.column_stack((tangents[:,1],-tangents[:,0]))
    normals /= np.linalg.norm(normals,axis=1)[:,None]
    previous = np.roll(normals,1,axis=0)
    extended = ring + run * (normals+previous)/(1+np.sum(normals*previous,axis=1))[:,None]
    # Node the expanding edge strips against the stock outline. Every triangle
    # then lies on a single flat face or on a single 4:1 machined plane.
    lines=[border.boundary,fan.boundary,Polygon(extended).boundary]
    lines.extend(LineString([p,q]) for p,q in zip(ring,extended))
    grid=1e-7
    network=unary_union([set_precision(line,grid) for line in lines])
    cells=[c for c in polygonize(network) if border.covers(c.representative_point()) and c.area>grid**2]
    if abs(sum(c.area for c in cells)-border.area) > 1.e-5*max(1.,border.length):
        raise ValueError('Machined post fan does not cover the stock')
    intercepts=np.sum(normals*ring,axis=1)
    def point(uv,depth):
        x,z=plane @ uv
        return [round(float(x),7), round(float(contact_y+side*depth),7), round(float(z),7)]
    def thick(uv):
        distance=max(0.,float(np.max(normals@uv-intercepts)))
        return max(base,full-distance/slope)
    faces=[]
    boundary={}
    for cell in cells:
        for triangle in constrained_delaunay_triangles(cell).geoms:
            uv=[tuple(round(float(a),7) for a in q) for q in list(orient(triangle,sign=1).exterior.coords)[:-1]]
            if len(uv)!=3 or len(set(uv))!=3:continue
            # Across x outward is right-handed in the local X-Z drawing plane.
            if side>0:uv.reverse()
            faces.append([point(q,thick(q)) for q in uv])
            faces.append([point(q,0.) for q in reversed(uv)])
            for a,b in zip(uv,uv[1:]+uv[:1]):
                if (b,a) in boundary:del boundary[b,a]
                else:boundary[a,b]=True
    for a,b in boundary:
        if border.boundary.distance(LineString([a,b]).interpolate(.5,normalized=True))>2.e-5:
            raise ValueError('Unjoined internal boundary on machined post plate')
        faces.append([point(a,0.),point(b,0.),point(b,thick(b)),point(a,thick(a))])
    part=assembly.part(name,'Monolithic double gusset with a machined post fan and outboard taper',
                       faces,'S','plate',selected_material=schedule['material'])
    part['parameters']=dict(source_role='transfer_post_gusset',description=part['description'],thickness=full,
        arm_thickness_in=base,post_thickness_in=full,minimum_blend_radius_in=radius,
        outside_taper_run_per_rise=slope,inner_bearing_plane_in=contact_y,
        post_shoulder_width_in=2*shoulder,stock_beyond_calculated_fan_in=radius)
    return part
