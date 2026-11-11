"""Measure directional bolt layout and the loaded gusset edge on placed STEP solids."""
import numpy as np
from shapely.geometry import LineString, Polygon

from .joint_mesh_readback import TOL, unit


def stations(values):
    groups=[]
    for value in sorted(values):
        if groups and abs(value-groups[-1][0])<=TOL:
            groups[-1].append(value)
        else:
            groups.append([value])
    return np.array([np.mean(g) for g in groups])


def measure_layout(plate,bolts,direction,pattern):
    normal=plate.plate_normal
    axis=unit(direction)
    if abs(float(normal@axis))>TOL:
        return {},['The actual gusset plane does not contain the brace workline']
    across=unit(np.cross(normal,axis))
    station=float(np.mean([min(plate.vertices@normal),max(plate.vertices@normal)]))
    section=plate.section(normal,station,(axis,across))
    if section.geom_type!='Polygon':
        return {},['No continuous gusset on the actual bolt-group plane']
    border=Polygon(section.exterior)
    uv=[]
    for shaft in bolts:
        cut=shaft.section(normal,station,(axis,across))
        if cut.geom_type!='Polygon' or cut.area<=TOL**2:
            return {},['Actual fastener does not cross the gusset plane']
        uv.append(tuple(cut.centroid.coords[0]))
    if not uv:return {},['No bolt shafts through the selected gusset']
    long=stations(u for u,v in uv);lines=stations(v for u,v in uv)
    n,line_count=pattern['longitudinal_stations'],pattern['transverse_lines']
    findings=[]
    occupied={(int(np.argmin(abs(long-u))),int(np.argmin(abs(lines-v)))) for u,v in uv}
    if (len(long),len(lines))!=(n,line_count) or len(occupied)!=n*line_count or len(uv)!=n*line_count:
        findings.append('Actual bolt stations, lines or occupancy differ from HR')
    pitch=pattern['longitudinal_pitch_in']
    if any(abs(v-pitch)>TOL for v in np.diff(long)):
        findings.append('Actual bolt pitch along the brace differs from HR')
    gauge=pattern['transverse_shear_plane_spacing_in']
    if abs(float(np.ptp(lines))-gauge)>TOL:
        findings.append('Actual transverse block-shear plane spacing differs from HR')
    if 'transverse_pitch_in' in pattern and any(abs(v-pattern['transverse_pitch_in'])>TOL for v in np.diff(lines)):
        findings.append('Actual transverse pitch differs from HR')
    edges=[];paths=[]
    for v in lines:
        trace=LineString([(long[-1],v),(max(border.bounds[2],long[-1])+1.,v)])
        hit=border.intersection(trace)
        pieces=[p for p in getattr(hit,'geoms',[hit]) if p.geom_type=='LineString' and not p.is_empty and
                abs(p.bounds[0]-long[-1])<=TOL]
        if len(pieces)!=1:
            findings.append('No continuous gusset to a loaded free edge')
            continue
        edge=float(pieces[0].bounds[2]-long[-1]);path=edge+float(np.ptp(long))
        edges.append(edge);paths.append(path)
        if abs(edge-pattern['loaded_end_distance_in'])>TOL or abs(path-pattern['block_shear_path_length_in'])>TOL:
            findings.append('Actual loaded end distance or longitudinal block-shear path differs from HR')
    return dict(longitudinal_stations_in=long.tolist(),transverse_lines_in=lines.tolist(),
                loaded_end_distances_in=edges,block_shear_paths_in=paths,actual_bolts=len(uv)),list(dict.fromkeys(findings))
