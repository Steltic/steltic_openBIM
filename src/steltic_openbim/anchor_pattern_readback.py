"""Measure a column base in its bound flange directions from the plate and rod solids."""
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union


def solid_faces(geometry):
    if geometry.get('type')=='mesh':
        return [np.asarray(f,dtype=float) for f in geometry['faces']]
    if geometry.get('type')=='box':
        a=np.asarray(geometry['origin'])
        x,y=np.asarray(geometry['x_axis']),np.asarray(geometry['y_axis'])
        z=np.cross(x,y)
        dx,dy,dz=geometry['size']
        base=np.array([a,a+dx*x,a+dx*x+dy*y,a+dy*y])
        top=base+dz*z
        return [base,top]+[np.array([base[i],base[i-1],top[i-1],top[i]]) for i in range(4)]
    return []


def unit(vec):
    n=np.linalg.norm(vec)
    if n<1e-8:
        raise ValueError('Column or assembly has a degenerate orientation')
    return vec/n


def measure_anchor_pattern(connection,parts,members,profiles):
    instance=connection.get('assembly_instance',{})
    bindings=instance.get('bindings',{}).values() if instance else connection.get('member_ids',[])
    columns=[members[v] for v in set(bindings) if v in members and members[v]['kind'] in ('column','col','endwall_post')]
    if len(columns)!=1:
        raise ValueError('Cannot identify one bound physical column')
    col=columns[0]
    profile=profiles.get(col['profile_id'],{})
    if profile.get('family') not in ('i','i_tapered') or 'd' not in profile.get('dimensions',{}):
        raise ValueError('Cannot locate the two physical column flange faces')
    a,b=np.asarray(col['axis'],dtype=float)
    long=unit(b-a)
    along=np.asarray(col['local_y'],dtype=float)
    along=unit(along-np.dot(long,along)*long)
    normal=np.cross(long,along)
    x,y=np.asarray(instance.get('x_axis',[1,0,0])),np.asarray(instance.get('y_axis',[0,1,0]))
    local_to_world=np.array([x,y,np.cross(x,y)])
    col_axes=np.array([normal,along]).T
    translation=(np.asarray(instance.get('origin',[0,0,0]))-a)@col_axes
    matrix=local_to_world@col_axes
    plates=[p for p in parts if p['kind']=='plate' and (p['id'].upper() in ('P1','BP','BASE','BASE-PLATE','BASE_PLATE')
            or p.get('parameters',{}).get('description','').strip().lower()=='base plate')]
    if len(plates)!=1:
        raise ValueError('Cannot identify one physical base plate')
    face_projections=[]
    for face in solid_faces(plates[0]['geometry']):
        xy=face@matrix+translation
        if len(xy)>=3:
            shell=Polygon(xy)
            if shell.area>1e-8:face_projections.append(shell)
    footprint=unary_union(face_projections)
    if footprint.geom_type!='Polygon':
        raise ValueError('Base plate has no single measured footprint')
    outer=Polygon(footprint.exterior)
    centers=[]
    for rod in (p for p in parts if p['kind']=='anchor'):
        geom=rod['geometry']
        if geom.get('type')=='cylinder':
            # A rod parallel to the physical column has a unique projected axis.
            if np.linalg.norm(np.asarray(geom['axis'])@matrix)>1e-5:
                raise ValueError('An inclined rod needs its plate-plane intersection located')
            center=np.asarray(geom['origin'])@matrix+translation
        else:
            faces=solid_faces(geom)
            if not faces:
                raise ValueError('Cannot locate a selected rod shaft')
            points=np.vstack(faces)@matrix+translation
            center=(points.max(axis=0)+points.min(axis=0))*.5
        if not outer.covers(Point(center)):
            raise ValueError('Rod centre lies outside the plate')
        centers.append(center)
    if not centers:
        raise ValueError('No physical anchor rods')
    locs=np.array(centers)
    # Measure to the actual first outer boundary along each flange direction.
    # This also catches shifted rows and clipped corners on nonrectangular plates.
    span=max(outer.bounds[2]-outer.bounds[0],outer.bounds[3]-outer.bounds[1])+1.
    edge_values=[]
    for axis in (0,1):
        distances=[]
        for sign in (-1,1):
            direction=np.eye(2)[axis]*sign
            ends=[LineString([c,c+span*direction]).intersection(outer.exterior) for c in centers]
            distances.append(min(Point(c).distance(hit) for c,hit in zip(centers,ends)))
        edge_values.append(distances)
    normal_coords=locs[:,0]
    minus=normal_coords[normal_coords<0]
    plus=normal_coords[normal_coords>0]
    if not len(minus) or not len(plus):
        raise ValueError('Could not locate rows outside both column flanges')
    half_depth=profile['dimensions']['d']*.5
    rod_rows=defaultdict(list)
    for end,across in centers:rod_rows[round(end,4)].append(float(across))
    steps=[]
    for stations in rod_rows.values():
        ordered=sorted(stations)
        steps.extend(b-a for a,b in zip(ordered,ordered[1:]))
    return {'edge_flange_normal_in':edge_values[0],'edge_along_flange_in':edge_values[1],
            'minimum_edge_in':[min(Point(c).distance(outer.exterior) for c in centers)],
            'flange_offset_in':[float(-minus.max()-half_depth),float(plus.min()-half_depth)],
            'spacing_in':steps}
