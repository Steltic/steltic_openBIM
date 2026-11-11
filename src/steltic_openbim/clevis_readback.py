"""Measure the nominal threaded engagement and forged jaw contacts in exported solids."""
import numpy as np
from shapely.geometry import Point, Polygon

from .joint_mesh_readback import TOL, plane_axes, shared_face_area, unit


def round_section(ring):
    """Fit the circumcircle of the polygon vertices, dropping collinear subdivisions."""
    shape=Polygon(ring).simplify(TOL/10,preserve_topology=True)
    if not shape.is_valid or shape.is_empty or len(shape.interiors):
        return None
    vertices=np.asarray(shape.exterior.coords)[:-1]
    if len(vertices)<6 or shape.convex_hull.area-shape.area>TOL*TOL:
        return None
    offset=vertices.mean(axis=0)
    x,y=(vertices-offset).T
    solved,_,rank,_=np.linalg.lstsq(np.column_stack((2*x,2*y,np.ones(len(x)))),x*x+y*y,rcond=None)
    center=solved[:2]+offset
    radii=np.linalg.norm(vertices-center,axis=1)
    if rank<3 or np.ptp(radii)>TOL or not shape.contains(Point(center)):
        return None
    return center,float(2*radii.mean())


def thread_fit(body,rod,axis,diameter,engagement):
    """Check finite rod occupancy of a real, continuous major-diameter bore."""
    n=unit(axis);axes=plane_axes(n)
    body_z=body.vertices@n;rod_z=rod.vertices@n
    lo=max(float(min(body_z)),float(min(rod_z)))
    hi=min(float(max(body_z)),float(max(rod_z)))
    evidence={'required_engagement_in':float(engagement),'actual_axial_overlap_in':max(0.,hi-lo),'required_major_diameter_in':float(diameter)}
    if diameter<=0 or engagement<=0 or not body.closed or not rod.closed:
        return 'invalid_or_unclosed_threaded_envelope',evidence
    if hi-lo<engagement-TOL:
        return 'actual_rod_clevis_engagement_short',evidence
    # Prove prismatic sides before checking one section in every axial interval.
    # This also rejects a taper which happens to fit the bore at its midpoint.
    for mesh in (body,rod):
        for face in mesh.polygons:
            levels=face@n
            if max(levels)<=lo+TOL or min(levels)>=hi-TOL or np.ptp(levels)<=TOL:
                continue
            normal=np.sum(np.cross(face,np.roll(face,-1,axis=0)),axis=0)
            if np.linalg.norm(normal)<1e-9 or abs(unit(normal)@n)>1e-5:
                return 'nonprismatic_threaded_envelope',evidence
    events=sorted({lo,hi,*(float(z) for z in np.r_[rod_z,body_z] if lo+TOL<z<hi-TOL)})
    for start,stop in zip(events,events[1:]):
        if stop-start<=TOL:
            continue
        station=(start+stop)/2
        wall=body.section(n,station,axes);shaft=rod.section(n,station,axes)
        if wall.geom_type!='Polygon' or wall.is_empty or len(wall.interiors)!=1:
            return 'actual_clevis_thread_bore_missing',dict(evidence,station_in=station)
        if shaft.geom_type!='Polygon' or shaft.is_empty or len(shaft.interiors):
            return 'actual_thread_rod_not_solid_at_connection',dict(evidence,station_in=station)
        bore=Polygon(wall.interiors[0])
        circles=[round_section(shape.exterior) for shape in (bore,shaft)]
        if any(circle is None for circle in circles):
            return 'actual_thread_bore_or_rod_not_round',dict(evidence,station_in=station)
        (bc,bd),(sc,sd)=circles
        evidence.update(station_in=station,actual_bore_diameter_in=bd,actual_rod_diameter_in=sd,
                        actual_center_offset_in=float(np.linalg.norm(bc-sc)),common_material_area_in2=float(wall.intersection(shaft).area))
        if max(abs(bd-diameter),abs(sd-diameter),evidence['actual_center_offset_in'])>TOL:
            return 'actual_thread_major_diameter_or_center_differs',evidence
        if not bore.buffer(TOL).covers(shaft):
            return 'actual_rod_material_inside_clevis_body',evidence
    return None,evidence


def forged_fit(body,jaw,axis):
    """The jaw must terminate on the actual front annular face of the forged body."""
    n=unit(axis)
    gap=float(min(body.vertices@n)-max(jaw.vertices@n))
    evidence={'axial_end_gap_in':gap,'contact_area_in2':0.}
    if not body.closed or not jaw.closed or abs(gap)>TOL:
        return 'forged_clevis_jaw_end_fit_differs',evidence
    evidence['contact_area_in2']=float(shared_face_area(jaw,body))
    if evidence['contact_area_in2']<=TOL:
        return 'forged_clevis_jaw_has_no_finite_end_contact',evidence
    return None,evidence
