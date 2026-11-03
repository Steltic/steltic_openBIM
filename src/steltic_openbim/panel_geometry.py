"""Planar source panels with explicitly related opening boundaries, in inches."""
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def panel_rings(panel, openings):
    """Return exterior/interior rings without inventing hosts or projected cuts.

    A recorded opening may meet the panel edge (a door/notch) or split a panel.
    Invalid/non-coplanar/outside boundaries remain references with a finding.
    """
    vertices=np.asarray(panel['vertices'],dtype=float)
    normal=np.zeros(3)
    for a,b in zip(vertices,np.roll(vertices,-1,axis=0)):
        normal+=np.cross(a,b)
    length=np.linalg.norm(normal)
    if length<1e-10:raise ValueError('Panel '+panel['id']+' has a degenerate boundary')
    normal/=length;origin=vertices[0]
    tolerance=1e-4  # inches, not an architectural location allowance
    if np.max(np.abs((vertices-origin)@normal))>tolerance:
        raise ValueError('Panel '+panel['id']+' is not planar')
    # Stable orthonormal coordinates also work for vertical walls and slopes.
    u=vertices[1]-origin;u-=normal*np.dot(u,normal)
    if np.linalg.norm(u)<1e-10:raise ValueError('Panel '+panel['id']+' repeats its first vertex')
    u/=np.linalg.norm(u);v=np.cross(normal,u)
    project=lambda points:[(float(np.dot(p-origin,u)),float(np.dot(p-origin,v))) for p in points]
    polygon=Polygon(project(vertices))
    if not polygon.is_valid or polygon.area<1e-10:
        raise ValueError('Panel '+panel['id']+' has an invalid boundary')
    applied=[];findings=[];result=polygon
    for opening in openings:
        points=np.asarray(opening['vertices'],dtype=float)
        reason=None
        if np.max(np.abs((points-origin)@normal))>tolerance:
            reason='Opening is not coplanar with its declared host panel'
        else:
            cut=Polygon(project(points))
            if not cut.is_valid or cut.area<1e-10:
                reason='Opening boundary is invalid'
            elif not polygon.buffer(tolerance).covers(cut):
                reason='Opening extends outside its declared host panel'
            elif polygon.intersection(cut).area<1e-10:
                reason='Opening does not intersect its declared host panel'
            else:
                result=result.difference(cut);applied.append(opening['id'])
        if reason:findings.append(dict(id=opening['id'],host_id=panel['id'],message=reason+'; kept as a boundary reference'))
    rings=[]
    def restore(coords):
        return [(origin+float(x)*u+float(y)*v).tolist() for x,y in list(coords)[:-1]]
    for part in ([result] if result.geom_type=='Polygon' else getattr(result,'geoms',[])):
        if part.is_empty:continue
        part=orient(part,sign=1.)
        rings.append(dict(exterior=restore(part.exterior.coords),holes=[restore(r.coords) for r in part.interiors]))
    if not rings:raise ValueError('Openings remove the entire panel '+panel['id'])
    return rings,applied,findings
