"""Measure the opposing steel faces at a selected flat-bar crossing."""
import numpy as np
from shapely import union_all
from shapely.geometry import Point, Polygon


LINEAR_IN=1e-4


def lap_faces(vertices,triangles,origin,basis):
    local=(vertices-origin)@basis.T
    faces={}
    for tri in local[triangles]:
        if np.ptp(tri[:,2])>LINEAR_IN:
            continue
        poly=Polygon(tri[:,:2])
        if poly.area<=1e-9:
            continue
        level=round(float(tri[:,2].mean()),5)
        faces.setdefault(level,[]).append(poly)
    centre=Point(0,0)
    surfaces=[]
    for level,facets in sorted(faces.items()):
        footprint=union_all(facets)
        if footprint.distance(centre)<=LINEAR_IN:
            surfaces.append((level,footprint))
    return surfaces


def check_crossing(crossing,members,meshes,measurements,selection=None):
    ids=crossing["member_ids"]
    axes=[np.asarray(members[k]["axis"],dtype=float) for k in ids]
    directions=[p[1]-p[0] for p in axes]
    normal=np.cross(*directions)
    if np.linalg.norm(normal)<1e-10:
        return {"issue":"source bars do not define a crossing plane"}
    normal/=np.linalg.norm(normal)
    u=directions[0]/np.linalg.norm(directions[0])
    basis=np.array([u,np.cross(normal,u),normal])
    origin=np.asarray(crossing["point_in"],dtype=float)
    surfaces=[lap_faces(*meshes[k],origin,basis) for k in ids]
    if any(len(pair)!=2 for pair in surfaces):
        return {"issue":"two finite plate faces of each IFC bar must cover the specified crossing",
                "faces_at_crossing":[len(p) for p in surfaces]}
    left,right=sorted(surfaces,key=lambda p:p[0][0])
    gap=right[0][0]-left[1][0]
    if gap < -LINEAR_IN:
        return {"issue":"actual flat bars penetrate at the specified crossing","penetration_in":-gap}
    if gap > LINEAR_IN:
        return {"issue":"actual flat bars miss one another at the specified crossing","gap_in":gap}
    lap=right[0][1].intersection(left[1][1])
    if lap.area<=LINEAR_IN**2 or lap.distance(Point(0.,0.))>LINEAR_IN:
        return {"issue":"actual flat bars lack a bearing face at the specified crossing"}
    if lap.geom_type!="Polygon":
        return {"issue":"crossing lacks a single connected lap at the weld location"}
    boundary=np.asarray(lap.exterior.coords)[:-1]
    vertices=[]
    for i,b in enumerate(boundary):
        a,c=boundary[i-1],boundary[(i+1)%len(boundary)]
        line=c-a
        span=np.linalg.norm(line)
        if span>LINEAR_IN and abs(line[0]*(a[1]-b[1])-line[1]*(a[0]-b[0]))/span>LINEAR_IN:
            vertices.append(b)
    lengths=[float(np.linalg.norm(b-vertices[i-1])) for i,b in enumerate(vertices)]
    facts={"crossing":crossing["id"],"lap_area_in2":float(lap.area),
           "exposed_perimeter_in":float(lap.exterior.length),"edge_lengths_in":lengths}
    measurements.append(facts)
    if selection and "count" in selection and "length_in" in selection:
        required=selection["count"]*selection["length_in"]
        facts["selected_total_fillet_in"]=required
        if required>lap.exterior.length+LINEAR_IN:
            return {"issue":"selected direct fillets exceed the available exterior lap perimeter",
                    "selected_length_in":required,"available_length_in":facts["exposed_perimeter_in"]}
    return None
