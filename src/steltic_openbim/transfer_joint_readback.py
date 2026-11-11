"""Measure the delivered flange-tip contacts and effective sections of a transfer-truss node."""
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from .joint_mesh_readback import TOL, transform, unit
from .selected_plate_readback import grade


def transfer_sources(handoff):
    roles={prefix+suffix for prefix in ('transfer_chord','transfer_diagonal','transfer_support')
           for suffix in ('_gusset_weld','_gusset')}
    roles.update(('transfer_post_gusset','transfer_post_gusset_weld','transfer_post_splice','transfer_support_transition'))
    selection={rid:{i for i,f in enumerate(r.get('fields',[])) if f['role'] in roles}
               for rid,r in handoff.get('records',{}).items()}
    return {cid for cid,occurrence in handoff.get('occurrences',{}).items()
            if any(not selection.get(a['record_id'],set()).isdisjoint(a.get('selected',[]))
                   for a in occurrence.get('applications',[]))}


def arm_selections(handoff,cid,bindings,members):
    expected,errors={},[]
    choices={'transfer_chord':'transfer_chord','transfer_diagonal':'transfer_diagonal','transfer_support':'column'}
    for app in handoff.get('occurrences',{}).get(cid,{}).get('applications',[]):
        rec=handoff['records'][app['record_id']]
        chosen=[rec['fields'][i] for i in app.get('selected',[])]
        for prefix,kind in choices.items():
            gusset={v['field']:v['value'] for v in chosen if v['role']==prefix+'_gusset'}
            weld={v['field']:v['value'] for v in chosen if v['role']==prefix+'_gusset_weld'}
            if not gusset and not weld:
                continue
            try:
                if gusset.get('count')!=2 or weld.get('count')!=4:
                    raise ValueError('Unsupported number of selected plates or fillets')
                spec=dict(thickness=gusset['thickness_in'],count=weld['count'],length=weld['length_in'],size=weld['size_in'],
                          material=gusset.get('material'),whitmore=gusset.get('whitmore_effective_width_in'),
                          metal=weld['material'])
                if kind!='column' and not spec['whitmore']:
                    raise ValueError('Missing selected transfer section width')
                section=rec.get('member_section',{}).get('value')
                ids=app.get('transfer_members',{}).get(prefix,[])
                if not ids or len(set(ids))!=len(ids) or any(mid not in bindings.values() or mid not in members or
                        members[mid]['kind']!=kind or (section and members[mid]['profile_id'].upper()!=section.upper())
                        for mid in ids):
                    raise ValueError('Transfer source has no applicable physical receiver')
                for mid in ids:
                    if mid in expected and spec!=expected[mid]:
                        raise ValueError('Different selected transfer requirements for the same arm')
                    expected[mid]=spec
            except (KeyError,ValueError) as exc:
                errors.append(dict(source=app['record_id'],issue=str(exc)))
    source={}
    for app in handoff.get('occurrences',{}).get(cid,{}).get('applications',[]):
        record=handoff['records'][app['record_id']]
        for i in app.get('selected',[]):
            f=record['fields'][i]
            if f['role']=='transfer_post_gusset_weld':source.setdefault(f['field'],set()).add(f['value'])
    if source:
        posts=[m for m in bindings.values() if members.get(m,{}).get('kind')=='transfer_vertical']
        double_plate=next((v for m,v in expected.items() if members[m]['kind']=='transfer_chord'),None)
        if len(posts)!=1 or not double_plate or any(len(values)!=1 for values in source.values()):
            errors.append(dict(issue='Cannot bind post weld to its physical transfer post and the two selected gussets'))
        else:
            try:
                values={k:next(iter(v)) for k,v in source.items()}
                if values['count']!=4:raise ValueError('Expected one fillet per physical flange tip')
                expected[posts[0]]=dict(thickness=double_plate['thickness'],material=double_plate['material'],
                    count=values['count'],size=values['size_in'],length=values['length_in'],metal=values['material'],
                    whitmore=None,start_in=values['start_in'])
            except (KeyError,ValueError) as exc:errors.append(dict(issue=str(exc)))
    for mid in bindings.values():
        if members.get(mid,{}).get('kind') in ('transfer_chord','transfer_diagonal') and mid not in expected:
            errors.append(dict(member=mid,issue='Transfer arm lacks bound HR flange-tip and plate selections'))
    return expected,errors


def face_region(mesh, normal, station, basis):
    polygons = []
    for face in mesh.polygons:
        if np.max(np.abs(face @ normal - station)) <= TOL:
            shape = Polygon(face @ basis)
            if shape.is_valid and shape.area > TOL**2:
                polygons.append(shape)
    return unary_union(polygons)


def measure_arm(member_mesh, plates, paths, member_axis, width_axis, workpoint, spec, names,fan=None):
    axis, normal = unit(member_axis), unit(width_axis)
    perpendicular = unit(np.cross(axis, normal))
    plane = np.column_stack((axis, perpendicular))
    center = np.asarray(workpoint) @ plane
    position = member_mesh.vertices @ normal
    sides = [float(min(position)), float(max(position))]
    rows, issues, occupied = [], [], set()
    for part, plate, world, size, weld_grade in paths:
        if plate not in plates:
            issues.append(dict(part=part, issue='Transfer weld lacks an actual plate'))
            continue
        s = world @ normal
        side = next((i for i, y in enumerate(sides) if np.max(np.abs(s-y)) <= TOL), None)
        if side is None:
            issues.append(dict(part=part, issue='Transfer weld leaves its actual flange-tip plane'))
            continue
        y = sides[side]
        ply = plates[plate]
        region = face_region(ply, normal, y, plane)
        contact = region.intersection(face_region(member_mesh, normal, y, plane))
        points = world @ plane
        line = LineString(points)
        actual_length = float(line.length)
        lateral = float(np.mean(points[:, 1])-center[1])
        leg = (side, 1 if lateral > 0 else -1)
        if min(abs(lateral), actual_length) <= TOL or np.ptp(points[:,1]) > TOL or leg in occupied:
            issues.append(dict(part=part, issue='Duplicate or misaligned transfer flange-tip fillet', side=side))
        occupied.add(leg)
        if contact.area <= TOL*TOL or not contact.buffer(TOL).covers(line):
            issues.append(dict(part=part, issue='Transfer fillet is not seated on both actual steel faces for its full length'))
        row = dict(part=part, plate=plate, flange_plane_in=y, weld_length_in=actual_length, weld_size_in=size,
                   contact_area_in2=float(contact.area))
        if spec:
            if size is None or abs(size-spec['size'])>TOL or abs(actual_length-spec['length'])>TOL:
                issues.append(dict(part=part,issue='Transfer fillet size or length differs from HR',measured=row))
            if 'start_in' in spec:
                axial=points[:,0]-center[0]
                actual_start=min(abs(axial))
                row['start_station_from_workpoint_in']=actual_start
                if min(axial)*max(axial)<-TOL or abs(actual_start-spec['start_in'])>TOL:
                    issues.append(dict(part=part,issue='Transfer post weld starts at the wrong station',actual_in=actual_start))
            if spec.get('metal') and spec['metal'].upper() not in str(weld_grade).upper():
                issues.append(dict(part=part,issue='Transfer fillet electrode differs from HR',actual=weld_grade))
            if spec.get('material') and grade(names.get(plate,''))!=grade(spec['material']):
                issues.append(dict(part=plate,issue='Transfer plate material differs from HR',actual=names.get(plate)))
            # Measure gauge between the two parallel faces at this transfer zone.
            z = ply.vertices @ normal
            if fan:
                if abs(fan['arm_thickness_in']-spec['thickness'])>TOL:
                    issues.append(dict(part=plate,issue='Original arm selection and revised post stock gauge disagree'))
            elif abs(abs(float(max(z)-min(z)))-spec['thickness'])>TOL:
                issues.append(dict(part=plate,issue='Transfer plate thickness differs from HR'))
            width = spec.get('whitmore')
            if width:
                # The joint-side end of the physical weld group is its transfer station.
                station = min(points[:,0],key=lambda x:abs(x-center[0]))
                probe = LineString([(station,center[1]-width/2),(station,center[1]+width/2)])
                row['required_centered_section_in'] = width
                if not region.buffer(TOL).covers(probe):
                    issues.append(dict(part=plate,issue='Selected Whitmore section does not fit the actual plate',width_in=width))
        rows.append(row)
    if len(rows)!=(spec or {}).get('count',4) or len(occupied)!=4 or len({q['plate'] for q in rows})!=2:
        issues.append(dict(issue='Transfer arm lacks one distinct longitudinal weld at each of its four flange tips'))
    return rows,issues


def node(check, connection, inst, instance, parts, meshes, actual_curves, names, specifications):
    from .transfer_fabrication_readback import select_roles
    source=select_roles(check.handoff,connection['id'])
    post_stock=source.get('transfer_post_gusset',{})
    fan=post_stock if post_stock.keys()-{'count','thickness_in','material'} else None
    plates = {k:v.transformed(instance) for k,v in meshes.items() if 'gusset' in
              parts[k].get('parameters',{}).get('description','').lower() and parts[k]['kind'] in ('plate','gusset')}
    paths = defaultdict(list)
    expected = {role for role, mid in inst['bindings'].items() if mid in specifications}
    findings, rows = [], []
    all_world={k:mesh.transformed(instance) for k,mesh in meshes.items() if k in parts and
               parts[k].get('parameters',{}).get('source_role')=='transfer_support_transition'}
    insert_hosts={pid:parts[pid]['parameters'].get('host_role') for pid in all_world}
    for key, part in parts.items():
        if part['kind']!='weld':
            continue
        links=set(part.get('connects',[])); targets=links & plates.keys()
        receivers=(links & inst['bindings'].keys())|{insert_hosts[k] for k in links & insert_hosts.keys()}
        if len(targets)!=1 or len(receivers)!=1:
            continue
        role=next(iter(receivers))
        expected.add(role)
        predicted = transform(part['geometry']['points'],instance)
        lines = [q for q in actual_curves if q.shape==predicted.shape and
                 min(np.max(np.abs(q-predicted)),np.max(np.abs(q[::-1]-predicted)))<=TOL]
        if len(lines)!=1:
            findings.append(dict(part=key,issue='Cannot uniquely locate the actual transfer weld trajectory'))
            continue
        paths[role].append((key,next(iter(targets)),lines[0],part.get('parameters',{}).get('size_in'),names.get(key)))
    for role in sorted(expected):
        mid=inst['bindings'][role]
        if mid not in check.members or mid not in check.rb.members:
            findings.append(dict(role=role,issue='Actual transfer receiver is missing'))
            continue
        m=check.members[mid]
        body=check.rb.member(mid)
        inserts=[all_world[k] for k,v in insert_hosts.items() if v==role]
        if inserts:
            from .transfer_fabrication_readback import combined_mesh
            body=combined_mesh([body,*inserts])
        workpoint=connection.get('point',inst['origin'])
        details,errors=measure_arm(body,plates,paths[role],np.subtract(*m['axis'][::-1]),
                                   m['local_y'],workpoint,specifications.get(mid),names,fan=fan)
        if not fan and post_stock and m['kind']=='transfer_vertical':
            for pname,mesh in plates.items():
                thickness=float(np.ptp(mesh.vertices@unit(m['local_y'])))
                if abs(thickness-post_stock['thickness_in'])>TOL or grade(names.get(pname,''))!=grade(post_stock['material']):
                    errors.append(dict(part=pname,issue='Uniform transfer post stock differs from the issued selection'))
        if fan and m['kind']=='transfer_vertical':
            from .transfer_post_readback import measure
            axis=np.asarray(max(m['axis'],key=lambda x:np.linalg.norm(np.subtract(x,workpoint))))-workpoint
            normal=unit(m['local_y']);stock=[]
            if len(plates)!=2 or not source.get('transfer_post_gusset_weld'):
                errors.append(dict(issue='Post fan lacks its two physical plates or its selected welds'))
            else:
                for pname,mesh in plates.items():
                    side=np.sign(np.mean((mesh.vertices-workpoint)@normal))
                    facts,bad=measure(mesh,workpoint,side*normal,axis,fan,source['transfer_post_gusset_weld'])
                    if grade(names.get(pname,''))!=grade(fan['material']):
                        bad.append('Actual post plate steel differs from HR')
                    stock.append(dict(plate=pname,**facts))
                    errors.extend(dict(part=pname,issue=v) for v in bad)
                check.counts['actual_machined_transfer_post_fans']+=len(stock)
                rows.append(dict(role='post_gusset_fabrication',member=mid,measurements=[],stock_sections=stock))
        rows.append(dict(role=role,member=mid,measurements=details))
        findings.extend(dict(v,role=role,member=mid) for v in errors)
    from .transfer_fabrication_readback import verify_fabrication
    fabricated,problems=verify_fabrication(check,connection,inst,instance,parts,meshes,actual_curves,names)
    rows.extend(fabricated);findings.extend(problems)
    return rows,findings
