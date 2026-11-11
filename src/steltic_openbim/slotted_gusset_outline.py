"""Complete an unfixed slotted gusset perimeter from its finite attachments."""
from shapely.geometry import MultiPoint,box
from shapely.geometry.polygon import orient
import math


def width_station(axis,width,limits):
    """First workline station where the full selected transfer width clears the supports."""
    if width is None:return float('-inf')
    if width<=0:raise ValueError('Selected gusset effective width must be positive')
    ux,uz=axis[0],axis[2]
    cross=(-uz,ux)
    station=float('-inf')
    for index,sign,edge in limits:
        rate=sign*(ux,uz)[index]
        minimum=sign*edge+abs(cross[index])*width/2
        if rate>1e-8:station=max(station,minimum/rate)
        elif minimum>1e-7:raise ValueError('Selected gusset transfer width cannot clear the receiving face')
    return station


def fitted_outline(support,welds,start,axis,t,width,limits=()):
    """Use straight cuts on the envelope of weld runs, support edges and selected width."""
    if not support or not welds or t<=0:raise ValueError('A fitted slotted gusset needs finite supports, slot welds and plate stock')
    direction=(axis[0],axis[2])
    cross=(-axis[2],axis[0])
    if abs(math.hypot(*direction)-1)>1e-6:raise ValueError('Brace is outside the selected gusset plane')
    points=[(p[0],p[2]) for p in support]
    for w in welds:
        for p in w:
            for dx,dz in (direction,cross):
                for sg in (-1,1):
                    points.append((p[0]+sg*t*dx,p[2]+sg*t*dz))
    if width is not None:
        for sg in (-1,1):
            q=(start[0]+sg*width*cross[0]/2,start[2]+sg*width*cross[1]/2)
            if any(sign*(q[k]-edge)<-1e-6 for k,sign,edge in limits):
                raise ValueError('Selected effective width crosses a restrained support face')
            points.append(q)
    hull=MultiPoint(points).convex_hull
    for k,sign,edge in limits:
        bounds=list(hull.bounds)
        pad=max(bounds[2]-bounds[0],bounds[3]-bounds[1],1.)
        bounds=[bounds[0]-pad,bounds[1]-pad,bounds[2]+pad,bounds[3]+pad]
        bounds[k if sign>0 else k+2]=edge
        hull=hull.intersection(box(*bounds))
    if hull.geom_type!='Polygon':raise ValueError('Slotted gusset attachments do not enclose a finite area')
    return list(orient(hull,sign=1.).exterior.coords)[:-1]
