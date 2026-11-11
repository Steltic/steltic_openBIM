"""Locate the material transition at a real slotted end and measure its two weld extents."""
import numpy as np
from shapely.geometry import box

from .joint_mesh_readback import TOL


def actual_inner_slot_tip(local,slot):
    center,width=slot['centre_in'],slot['width_in']
    lo,hi=center-width/2+TOL,center+width/2-TOL
    band=box(lo,-1e6,hi,1e6) if slot['section_axis']==0 else box(-1e6,lo,1e6,hi)
    levels=sorted(set(np.round(local.vertices[:,0],6)))
    lower=abs(slot['start_in']-levels[0])<abs(slot['end_in']-levels[-1])
    intervals=[(a,b) for a,b in zip(levels,levels[1:]) if b-a>2*TOL]
    if not lower:intervals.reverse()
    found_open=False
    for a,b in intervals:
        section=local.section([1,0,0],(a+b)/2,([0,1,0],[0,0,1]))
        if section.is_empty:continue
        open_slot=section.intersection(band).area<2*TOL
        if open_slot:
            found_open=True
        elif found_open:
            return float(a if lower else b)
        else:
            break
    raise ValueError('No actual open-to-filled section transition at the bound brace end')


def each_side_extents(lines,origin,axis,tip):
    stations=(np.vstack(lines)-np.asarray(origin))@np.asarray(axis)-tip
    return float(-stations.min()),float(stations.max())
