"""Measure selected anchor holes and edge distances on the located IFC solids."""
import numpy as np
from shapely.geometry import Point,Polygon

from .joint_mesh_readback import TOL,cross_section,unit
from .anchor_pattern_readback import measure_anchor_pattern


def anchor_bores(plate,rods,diameter):
    n=plate.plate_normal
    material,station,axes,_,_=cross_section(plate,n)
    if material.geom_type!='Polygon' or not material.is_valid:
        raise ValueError('The located base plate has no valid continuous section')
    holes=[Polygon(r) for r in material.interiors]
    measured={}
    used=set()
    findings=[]
    for ident,shaft in rods.items():
        section=shaft.section(n,station,axes)
        if section.geom_type!='Polygon' or section.area<=TOL*TOL:
            findings.append(dict(rod=ident,detail='Actual anchor shaft does not cross the plate plane'))
            continue
        center=section.centroid
        at=[i for i,h in enumerate(holes) if h.covers(center)]
        if len(at)!=1 or at[0] in used:
            findings.append(dict(rod=ident,detail='Anchor lacks its own enclosed hole in the actual base plate'))
            continue
        index=at[0]
        used.add(index)
        hole=holes[index]
        boundary=np.asarray(hole.simplify(TOL/10,preserve_topology=True).exterior.coords)[:-1]
        radii=np.linalg.norm(boundary-[center.x,center.y],axis=1)
        sizes=[2*float(min(radii)),2*float(max(radii))]
        measured[ident]=dict(diameter_range_in=sizes,actual_shaft_area_in2=float(section.area))
        if len(radii)<8 or max(abs(v-diameter) for v in sizes)>2*TOL:
            findings.append(dict(rod=ident,detail='Actual base hole differs in size, shape or centering',
                                 diameter_range_in=sizes,selected_in=diameter))
        if not hole.buffer(TOL).covers(section):
            findings.append(dict(rod=ident,detail='Actual anchor steel crosses the base-plate bore wall'))
    return measured,findings


def verify_anchors(rb,entity,template,frame,members,profiles,fields,parts):
    directional={key:values for (role,key),values in fields.items() if role=='anchor_pattern' and
                 key in ('edge_flange_normal_in','edge_along_flange_in','minimum_edge_in','flange_offset_in','spacing_in')}
    diameters=set(fields.get(('anchor_hole','diameter_in'),[]))
    if not (directional or diameters):return {},[]
    plate_ids=[p['id'] for p in parts.values() if p['kind']=='plate' and
               (p['id'].upper() in ('P1','BP','BASE-PLATE','BASE_PLATE') or
                p.get('parameters',{}).get('description','').strip().lower()=='base plate')]
    if len(plate_ids)!=1:raise ValueError('The actual anchor pattern needs one identified base plate')
    plate_id=plate_ids[0]
    _,raw,matrix=rb.mesh(entity)
    solids={}
    for locator in rb.ranges[template]:
        if locator['kind']=='anchor' or locator['id']==plate_id:
            solids[locator['id']]=raw.subset(locator['face_start'],locator['face_count']).transformed(matrix)
    plate=solids.pop(plate_id)
    if not solids:raise ValueError('No IFC rod shafts for the selected base plate')
    facts=dict(anchor_count=len(solids))
    findings=[]
    if diameters:
        if len(diameters)!=1:raise ValueError('Source contains conflicting base anchor hole diameters')
        target=next(iter(diameters))
        holes,issues=anchor_bores(plate,solids,target)
        facts.update(measured_holes=holes,selected_hole_diameter_in=target)
        findings.extend(issues)
    if directional:
        bound=[m for m in set(frame['bindings'].values()) if m in members and members[m]['kind'] in ('column','col')]
        if len(bound)!=1:raise ValueError('The anchor pattern needs one identified IFC column')
        col=members[bound[0]]
        profile=profiles[col['profile_id']]
        axis=unit(np.subtract(*col['axis'][::-1]))
        width=np.asarray(col['local_y'],dtype=float)
        depth=unit(np.cross(axis,width))
        dimension=float(np.ptp(rb.member(bound[0]).vertices@depth))
        actual_profile=dict(profile,dimensions=dict(profile['dimensions'],d=dimension))
        geometries=[dict(id=key,kind='plate' if key==plate_id else 'anchor',
                     geometry=dict(type='mesh',faces=mesh.polygons)) for key,mesh in [(plate_id,plate),*solids.items()]]
        measurements=measure_anchor_pattern(dict(member_ids=bound),geometries,members,{profile['id']:actual_profile})
        for key,values in directional.items():
            for value in set(values):
                observed=measurements[key]
                if not observed or any((x+TOL<value if key=='minimum_edge_in' else abs(x-value)>TOL) for x in observed):
                    findings.append(dict(detail='Actual IFC anchor set-out differs from HR',field=key,
                                         selected_in=value,actual_in=observed))
        facts.update(column=bound[0],measured_column_depth_in=dimension,setout_in=measurements)
    return facts,findings
