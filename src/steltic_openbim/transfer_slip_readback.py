"""Measure travel, clamping clearances and the load path on reopened STEP solids."""
import numpy as np
from shapely.affinity import translate
from shapely.geometry import Polygon

from .joint_mesh_readback import TOL


XZ=(np.array([1.,0.,0.]),np.array([0.,0.,1.]))


def landed(curve, first, second, length):
    if curve is None or len(curve)!=2 or abs(np.linalg.norm(curve[-1]-curve[0])-length)>TOL:
        return False
    return all(max(first.point_distance(p),second.point_distance(p))<=TOL for p in np.linspace(*curve,11))


def measure(meshes, welds, s):
    problems=[];runs={};sides=[]
    backing=meshes['DIAPHRAGM']
    face=float(backing.vertices[:,0].max())
    gap=float(meshes['M2'].vertices[:,0].min()-face)
    if (abs(gap-s['beam_gap_in'])>TOL or
        meshes['M2'].vertices[:,0].min()-meshes['BACKING'].vertices[:,0].max()<s['travel_each_in']+.125-TOL):
        problems.append('Girder does not have its specified end setback at full travel')
    web=meshes['M2'].section([0,1,0],0.,XZ)
    bores=[Polygon(r) for r in web.interiors if abs(Polygon(r).centroid.x-s['bolt_line_in']-face)<TOL]
    if len(bores)!=s['bolt_count'] or any(abs(p.bounds[2]-p.bounds[0]-s['beam_bore_in'])>TOL for p in bores):
        problems.append('Moving girder web lacks its six full-size round bolt holes')
    for key in ('FAN-L','FAN-R'):
        name=key+'-CJP'
        if not landed(welds.get(name),backing,meshes[key],s['diaphragm_height_in']):
            problems.append('Diaphragm groove misses its actual fan or diaphragm at '+name)
        else:runs[name]=round(float(np.linalg.norm(welds[name][1]-welds[name][0])),5)
    for side,tab_id in ((-1,'P1'),(1,'P2')):
        steel=meshes[tab_id];y=steel.vertices[:,1]*side
        section=steel.section([0,1,0],side*(y.min()+y.max())/2,XZ)
        rings=sorted((Polygon(r) for r in section.interiors),key=lambda p:p.centroid.y)
        if len(rings)!=s['bolt_count']:
            problems.append('Wrong number of actual longitudinal slots on '+tab_id);continue
        name=tab_id+'-CJP'
        if not landed(welds.get(name),steel,backing,s['tab_depth_in']):
            problems.append('Tab root misses its own diaphragm or plate at '+name)
        measured=[]
        for j,hole in enumerate(rings):
            bush=meshes[tab_id+'-BUSH'+str(j)];keeper=meshes[tab_id+'-KEEP'+str(j)]
            by=bush.vertices[:,1]*side;ky=keeper.vertices[:,1]*side
            sec=bush.section([0,1,0],side*(by.max()+by.min())/2,XZ)
            keep=keeper.section([0,1,0],side*(ky.max()+ky.min())/2,XZ)
            if len(sec.interiors)!=1 or len(keep.interiors)!=1:
                problems.append('Sleeve or keeper lacks its round bore');continue
            shape=Polygon(sec.exterior);x0,z0,x1,z1=hole.bounds
            required=s['travel_each_in']
            if (abs(x1-x0-s['slot_length_in'])>TOL or abs(z1-z0-s['slot_width_in'])>TOL or
                abs(shape.bounds[2]-shape.bounds[0]-s['sleeve_od_in'])>TOL or abs(ky.min()-by.max())>TOL or
                abs(by.min()-s['web_in']/2)>TOL or abs(by.max()-by.min()-s['sleeve_length_in'])>TOL or
                min(y.min()-by.min(),ky.min()-y.max())<s['running_gap_in']-TOL):
                problems.append('Slot, spacer stack or sliding clearance differs at '+tab_id+str(j))
            for shift in (-required,required):
                if not hole.buffer(TOL).covers(translate(shape,xoff=shift)):
                    problems.append('Sleeve collides with slot through issued travel')
                if not translate(Polygon(keep.exterior),xoff=shift).buffer(TOL).covers(hole):
                    problems.append('Moving keeper uncovers the slot at full travel')
            measured.append(dict(length_in=round(x1-x0,5),width_in=round(z1-z0,5),
                                 web_side_clear_in=round(float(y.min()-by.min()),5),
                                 keeper_side_clear_in=round(float(ky.min()-y.max()),5)))
        sides.append(dict(tab=tab_id,slots=measured))
    return dict(girder_setback_in=round(gap,5),fan_welds=runs,tabs=sides,travel_each_in=s['travel_each_in']),problems
