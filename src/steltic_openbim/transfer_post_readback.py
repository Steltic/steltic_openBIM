"""Measure the fan, outboard slope and original flat bearing face from actual transfer plate steel."""
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from .joint_mesh_readback import TOL, unit
from .transfer_joint_readback import face_region


def measure(mesh, pin, normal, axis, schedule, post_weld):
    n=unit(normal);v=unit(axis);d=unit(np.cross(n,v))
    basis=np.column_stack((d,v))
    xy=np.asarray(pin)@basis
    distances=mesh.vertices@n
    contact=float(min(distances))
    footprint=face_region(mesh,n,contact,basis)
    facts=dict(stock_depth_in=float(max(distances)-contact))
    errors=[]
    base=schedule['arm_thickness_in'];depth=schedule['thickness_in']
    ratio=schedule['outside_taper_run_per_rise'];radius=schedule['blend_radius_in']
    if not mesh.closed or footprint.geom_type!='Polygon' or footprint.interiors:
        return facts,['The post plate is open, perforated or lacks its single inner bearing face']
    if abs(facts['stock_depth_in']-depth)>TOL:
        errors.append('The full post stock thickness differs from the issued local selection')
    u0=post_weld['start_in'];u1=u0+post_weld['length_in']
    w=schedule['weld_root_width_in']/2
    b=schedule['joint_side_fan_width_in']/2
    if abs((b-w)/(u1-u0)-math.tan(math.radians(schedule['fan_angle_deg'])))>TOL:
        errors.append('The post shoulder and the checked spread angle disagree')
    free=footprint.bounds[1]-xy[1]-2*radius-(depth-base)*ratio-1.
    boundary=Polygon(np.asarray([[-b,free],[b,free],[b,u0],[w,u1],[-w,u1],[-b,u0]])+xy)
    required=boundary.intersection(footprint)
    # The engineering spread is a minimum throughout the joint. The drawing's
    # outboard blend preserves a full blend radius of stock outside that spread.
    slope_samples=[];xz=(d,v)
    for h in (base*.25,base-.001,base+(depth-base)*.1,(base+depth)/2,depth-.001):
        actual=mesh.section(n,contact+h,xz)
        minimum=footprint if h<base else boundary.buffer(radius+(depth-h)*ratio-.002,quad_segs=24).intersection(footprint)
        maximum=footprint if h<base else boundary.buffer(radius+(depth-h)*ratio+.006,quad_segs=24).intersection(footprint)
        missing=minimum.difference(actual.buffer(TOL)).area
        excess=actual.difference(maximum.buffer(TOL)).area
        slope_samples.append(dict(depth_in=h,area_in2=actual.area,missing_minimum_stock_in2=missing,excess_in2=excess))
        # Chordal approximations of the one-inch radius affect its curved
        # boundary only. The straight stock, full shoulder and slope are checked below.
        if missing>.005*max(1.,minimum.length) or excess>.005*max(1.,maximum.length):
            errors.append('Actual post plate section differs from its original stock and local taper')
    full=mesh.section(n,contact+depth-.002,xz)
    near=LineString([xy+[-b,u0],xy+[b,u0]])
    far=LineString([xy+[-w,u1],xy+[w,u1]])
    facts.update(checked_fan_area_in2=required.area,missing_full_fan_in2=required.difference(full.buffer(TOL)).area,
                 joint_side_fan_span_in=full.intersection(near).length,far_fan_span_in=full.intersection(far).length,
                 depth_slices=slope_samples)
    if (facts['missing_full_fan_in2']>TOL*required.length or
            not full.buffer(TOL).covers(near) or not full.buffer(TOL).covers(far)):
        errors.append('The thick post fan is discontinuous or narrower than the checked flange spread')
    slopes=[]
    for face in mesh.polygons:
        vector=np.cross(face[1]-face[0],face[2]-face[0])
        if np.linalg.norm(vector)<1e-8:continue
        direction=unit(vector)
        if abs(direction@n)<1e-5:
            if footprint.boundary.distance(Point(np.mean(face,axis=0)@basis))>2*TOL:
                errors.append('The plate has an unselected internal step')
            continue
        rise=float(np.linalg.norm(direction@basis)/abs(direction@n))
        if rise>1.e-4:slopes.append(rise)
    if not slopes or any(abs(r*ratio-1)>.004 for r in slopes):
        errors.append('Actual post fan slope differs from the issued run-to-rise ratio')
    facts['minimum_taper_run_per_rise']=1/max(slopes) if slopes else None
    facts['maximum_taper_run_per_rise']=1/min(slopes) if slopes else None
    return facts,list(dict.fromkeys(errors))
