"""Independent, bounded geometry checks for the synthetic IFC sweep."""
import re
import math
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from steltic_openbim.pilots.geometry import strips


def scheduled_anchor_spacing(physical, records, rules):
    """Check reviewed horizontal sill runs against their own anchor schedule.

    Rules identify existing wall-panel bottom edges and selected spacing. They
    supply no new design. Count distinct shafts crossing the attachment plane,
    excluding washers, other storeys, unrelated records and duplicate solids.
    """
    record_ids = {r['id'] for r in records}
    panels = {p['id']: p for p in physical.get('panels', [])}
    results = []
    tolerance = .25
    for rule in rules:
        rid = rule['design_record_id']
        spacing = rule['maximum_spacing_in']
        assert spacing > 0
        segments = []
        for segment in rule['segments']:
            a, b = np.asarray(segment['axis_in'], dtype=float)
            delta = b - a
            length = float(np.linalg.norm(delta))
            assert length > 0 and abs(delta[2]) < 1e-6
            direction = delta / length
            panel = panels.get(segment['panel_id'])
            vertices = np.asarray(panel.get('vertices', []), dtype=float) if panel else np.empty((0, 3))
            identity_ok = bool(len(vertices) and all(np.min(np.linalg.norm(vertices - point, axis=1)) <= tolerance for point in (a, b)))
            shafts = {}
            for connection in physical.get('connections', []):
                if rid not in connection.get('design_record_ids', []):
                    continue
                for part in connection.get('parts', []):
                    if not re.search(rule['part_kind_pattern'], part.get('kind', ''), re.I):
                        continue
                    geometry = part.get('geometry', {})
                    if geometry.get('type') != 'cylinder':
                        continue
                    origin = np.asarray(geometry['origin'], dtype=float)
                    axis = np.asarray(geometry['axis'], dtype=float)
                    if abs(axis[2]) < .9:
                        continue
                    station = (a[2] - origin[2]) / axis[2]
                    if not -tolerance <= station <= geometry['length'] + tolerance:
                        continue
                    point = origin + station * axis
                    along = float(np.dot(point - a, direction))
                    transverse = float(np.linalg.norm(point - a - along * direction))
                    if -tolerance <= along <= length + tolerance and transverse <= rule['maximum_transverse_offset_in']:
                        shafts[tuple(np.round(point, 6))] = (max(0., min(length, along)), connection['id'], part['id'])
            positions = sorted({v[0] for v in shafts.values()})
            gaps = np.diff([0.] + positions + [length]).tolist()
            minimum = math.ceil(length / spacing - 1e-9)
            passed = identity_ok and len(shafts) >= minimum and max(gaps) <= spacing + tolerance
            segments.append(dict(panel_id=segment['panel_id'], axis_in=segment['axis_in'],
                                 panel_edge_retained=identity_ok, minimum_anchors=minimum,
                                 actual_distinct_anchors=len(shafts), maximum_gap_in=max(gaps),
                                 maximum_spacing_in=spacing, passed=passed))
        results.append(dict(design_record_id=rid, basis=rule['basis'], record_missing=rid not in record_ids,
                            segments=segments, passed=rid in record_ids and bool(segments) and all(s['passed'] for s in segments)))
    return dict(rules=results, passed=all(r['passed'] for r in results),
                method='Reviewed own-design sill-anchor spacing and minimum quantity on named physical wall-panel bottom edges. Distinct cylindrical shafts must cross the attachment plane, carry the selected record and lie within the reviewed transverse corridor. 0.25-inch location tolerance. This does not certify embedment, edge distance, concrete design or fastening capacity.')


def reviewed_fastener_quantities(physical, rules):
    """Retain the quantities observed before a correction, even if labels change."""
    def category(part):
        words=set(re.findall(r'[a-z]+',part.get('kind','').lower()))
        if words & {'plate','plates','washer','washers','nut','nuts','head','heads'}:return None
        for category,words_for in [('anchor',{'anchor','anchors'}),('screw',{'screw','screws'}),('bolt',{'bolt','bolts'})]:
            if words & words_for:return category
    def frozen(value):
        if isinstance(value,dict):return tuple((k,frozen(v)) for k,v in sorted(value.items()))
        if isinstance(value,list):return tuple(frozen(v) for v in value)
        return value
    connections={c['id']:c for c in physical.get('connections',[])}
    local={}
    for connection in connections.values():
        for rid in connection.get('design_record_ids',[]):
            local.setdefault((connection.get('joint_id'),rid),[]).extend(connection.get('parts',[]))
    findings=[]
    for rule in rules:
        connection=connections.get(rule['connection_id'],{})
        bound=connection.get('joint_id')==rule['joint_id'] and set(rule['design_record_ids']).issubset(connection.get('design_record_ids',[]))
        pool=list(connection.get('parts',[]))
        for rid in rule['design_record_ids']:pool.extend(local.get((rule['joint_id'],rid),[]))
        actual=len({frozen([p.get('material_id'),p['geometry']]) for p in pool
                    if category(p)==rule['category'] and p.get('geometry',{}).get('type') in ('box','cylinder','extruded_profile')})
        if not bound or actual<rule['minimum_count']:
            findings.append(dict(connection_id=rule['connection_id'],category=rule['category'],
                                 expected_count=rule['minimum_count'],actual_distinct_solids=actual,original_assembly_binding=bound))
    return dict(checked=len(rules),findings=findings,passed=not findings,
                method='Quantities frozen from this fresh job before correction. Removing count metadata cannot satisfy a missing pattern. Changed assembly identities or genuinely changed selections require explicit review against the completed design; no historical structural data is supplied.')


def scheduled_connection_coverage(physical,records,rules):
    """Check reviewed applicability of this job's own connection schedules.

    Rules contain record/member IDs, never historical designs or new geometry.
    A changed identity needs review instead of silently dropping a requirement.
    """
    members={m['id']:m for m in physical.get('members',[])}
    records={r['id']:r for r in records}
    connections={c['id']:c for c in physical.get('connections',[])}
    linked={}
    for c in connections.values():linked.setdefault(c.get('joint_id'),[]).append(c)
    for d in physical.get('joint_dispositions',[]):
        if d.get('kind')=='shared_connection':
            linked.setdefault(d['joint_id'],[]).extend(connections[cid] for cid in d.get('connection_ids',[]) if cid in connections)
    end_joints={(e['member_id'],e['end']):j['id'] for j in physical.get('joints',[]) for e in j.get('member_ends',[])}
    results=[]
    for rule in rules:
        rid=rule['design_record_id'];missing=[];checked=0
        named=set(rule.get('member_ids',[]))|{o['member_id'] for o in rule.get('occurrences',[])}|{o['support_id'] for o in rule.get('occurrences',[]) if o.get('support_id')}
        absent=sorted(mid for mid in named if mid not in members)
        for mid in rule.get('member_ids',[]):
            if mid not in members:continue
            for end in rule.get('ends',['start','end']):
                checked+=1;jid=end_joints.get((mid,end))
                if not any(rid in c.get('design_record_ids',[]) and c.get('parts') for c in linked.get(jid,[])):
                    missing.append(dict(member_id=mid,end=end,joint_id=jid))
        for occurrence in rule.get('occurrences',[]):
            checked+=1;mid=occurrence['member_id'];point=np.asarray(occurrence['point_in'])
            candidates=[j['id'] for j in physical.get('joints',[]) if np.linalg.norm(np.asarray(j['point'])-point)<=.25 and any(a.get('member_id')==mid for a in j.get('member_ends',[])+j.get('attachments',[]))]
            if not any(rid in c.get('design_record_ids',[]) and c.get('parts') for jid in candidates for c in linked.get(jid,[])):
                missing.append(dict(occurrence,joint_ids=candidates))
        results.append(dict(design_record_id=rid,basis=rule['basis'],checked_member_ends=checked,
            record_missing=rid not in records,member_ids_missing=absent,missing_occurrences=missing,
            passed=rid in records and checked>0 and not absent and not missing))
    return dict(rules=results,passed=all(r['passed'] for r in results),
        method='Reviewed applicability of this fresh job\'s own selected connection schedule to member ends and explicitly reviewed interior support stations (0.25-inch joint tolerance). Actual connections or explicitly shared assemblies must carry the required record and located parts. Identity changes require review; this is not a capacity or fabrication check.')


def connection_occurrence_coverage(physical,objects,ground_in=None):
    """Check demonstrated gaps in declared free/continuous joint exceptions.

    Nearby parts alone never prove a valid connection; distance is an absence
    screen, combined with explicit hardware notes or an impossible continuity
    claim. Full connection engineering remains outside this geometric screen.
    """
    members={m['id']:m for m in physical['members']}
    joints={j['id']:j for j in physical.get('joints',[])}
    linked={c.get('joint_id') for c in physical.get('connections',[])}
    part_boxes={}
    for obj in objects:
        cid=obj.get('properties',{}).get('Steltic_Coordination',{}).get('ConnectionId')
        if cid:part_boxes.setdefault(cid,[]).append(obj['bounds_m'])
    boxes=np.asarray([box for rows in part_boxes.values() for box in rows])
    column_ids={m['id'] for m in members.values() if m.get('kind','').lower() in ('col','column')}
    problems=[];checked=0
    for declaration in physical.get('joint_dispositions',[]):
        jid=declaration['joint_id']
        if jid in linked or jid not in joints:continue
        checked+=1;joint=joints[jid];point=np.asarray(joint['point'],dtype=float)
        reason=declaration.get('reason','');text=reason.lower();why=[];kind=declaration.get('kind')
        text=re.sub(r'\b(?:no|without)\s+(?:(?:field|shop|additional)\s+)*(?:screws?|clips?|bolts?|welds?|splices?|hangers?|gussets?)\b','',text)
        hardware=bool(re.search(r'\b(screws?|screwed|clips?|bolts?|bolted|welds?|welded|splices?|spliced|hangers?|gussets?)\b|shear[- ]tab|bearing seat|representative.*connection',text))
        vectors=[];base_column=False
        for end in joint.get('member_ends',[]):
            member=members.get(end['member_id'])
            if not member:continue
            axis=np.asarray(member['axis'],dtype=float)
            axis+=np.asarray(member.get('end_offsets',[[0,0,0],[0,0,0]]),dtype=float)
            other=axis[1 if end['end']=='start' else 0];delta=other-point
            if np.linalg.norm(delta)>1e-6:vectors.append(delta/np.linalg.norm(delta))
            if member['id'] in column_ids and ground_in is not None and abs(point[2]-ground_in)<.2:base_column=True
        distance=None
        target_boxes=np.asarray([box for cid in declaration.get('connection_ids',[]) for box in part_boxes.get(cid,[])]) if kind=='shared_connection' else boxes
        if hardware or base_column or kind=='shared_connection':
            if len(target_boxes):
                distances=np.maximum(np.maximum(target_boxes[:,:,0]-point*.0254,point*.0254-target_boxes[:,:,1]),0)
                distance=float(np.linalg.norm(distances,axis=1).min())/.0254
            remote=distance is None or distance>72
            if remote and (hardware or kind=='shared_connection'):why.append('The note/reference describes connection hardware but no applicable returned connection-part bounds are within six feet.')
            if remote and base_column and kind!='bearing_interface':why.append('This is a ground-level column end without nearby located connection parts, not an interior beam subdivision.')
        continuous=kind=='continuous_member' or (not kind and (text.startswith('continuous') or bool(re.search(r'(interior|analysis).*subdivision',text))))
        attachments=joint.get('attachments',[])
        interior=not joint.get('member_ends') and len(attachments)==1 and 0<attachments[0].get('station',0)<1
        through=interior or (len(vectors)==2 and not attachments and float(np.dot(vectors[0],vectors[1]))<-.9999)
        if continuous and not through:why.append('The claimed continuous subdivision lacks opposing collinear physical member ends.')
        if why:problems.append(dict(joint_id=jid,point_in=point.tolist(),reason=reason,minimum_distance_to_part_bounds_in=None if distance is None else round(distance,3),findings=why))
    return dict(checked_exemptions=checked,problems=problems,
        method='Explicit hardware notes and column bases lacking any connection-part bounds within six feet; continuous-subdivision claims must have opposing collinear member ends. Checks returned solid and reference-part bounds. Nearness alone is not connection completeness, fit or capacity certification.')


def member_design_record_sections(physical,records):
    """Independently compare explicit catalogue section labels on linked records."""
    index={r['id']:r for r in records};profiles={p['id']:p for p in physical['profiles']}
    findings=[];checked=0;not_screened=0
    def label(value):
        if not isinstance(value,str):return None
        text=''.join(value.upper().split()).replace('\u00d7','X')
        return text if re.fullmatch(r'(?:W|WT|S|HP|C|MC|L|HSS)\d+(?:\.\d+)?(?:X\d+(?:[./]\d+)?){1,3}',text) else None
    for member in physical['members']:
        profile=profiles[member['profile_id']]
        for ref in member.get('design_record_ids',[]):
            record=index.get(ref,{})
            if record.get('table')!='members':continue
            inputs=record.get('data',{}).get('inputs',{})
            actual=label(profile['id']);selected=label(inputs.get('section')) if isinstance(inputs,dict) else None
            if profile['family']=='built_up' or not actual or not selected:
                not_screened+=1;continue
            checked+=1
            if actual!=selected:findings.append(dict(member_id=member['id'],profile_id=profile['id'],record_id=ref,record_section=inputs['section']))
    return dict(checked_links=checked,links_requiring_other_review=not_screened,mismatches=findings,
                method='Actual physical catalogue section label versus every linked member record with an explicit inputs.section. Custom profile aliases and built-up constituent calculations are outside this exact-label screen.')


def part_dimension_consistency(physical):
    """Compare explicit inch-valued part labels with their declared solids."""
    findings=[];checked=0
    for connection in physical.get('connections',[]):
        for part in connection.get('parts',[]):
            g=part.get('geometry',{});parameters=part.get('parameters',{});kind=part.get('kind','').lower()
            dimensions=[]
            if g.get('type')=='box' and any(word in kind for word in ('plate','gusset','stiffener','washer','strap','sheet')):
                dimensions=[(key,g['size']) for key in ('thickness_in','plate_thickness_in') if key in parameters]
            elif g.get('type')=='cylinder' and not any(word in kind for word in ('head','nut','washer')):
                dimensions=[('diameter_in',[2*g['radius']])] if 'diameter_in' in parameters else []
            for key,actual in dimensions:
                expected=parameters[key]
                if isinstance(expected,bool) or not isinstance(expected,(int,float)) or not np.isfinite(expected) or expected<=0:continue
                checked+=1
                if min(abs(v-expected) for v in actual)>max(.005,.02*expected):
                    findings.append(dict(connection_id=connection['id'],part_id=part['id'],kind=part.get('kind'),parameter=key,declared_value_in=expected,geometry_dimensions_in=actual,design_record_ids=connection.get('design_record_ids',[])))
    return dict(checked=checked,mismatches=findings,method='Explicit plate/gusset thickness or cylindrical shaft diameter versus solid dimensions; tolerance max(0.005 in, 2%). Resolve against actual completed design records, not by relabelling an arbitrary solid.')


def sideways_gravity_members(physical):
    profiles={p['id']:p for p in physical['profiles']};findings=[];checked=0
    for member in physical['members']:
        if not re.search(r'(^|_)(beam|girder|joist|rafter|purlin)($|_)',member['kind'].lower()):continue
        profile=profiles[member['profile_id']];dims=profile.get('dimensions',{})
        if profile['family'] not in ('i','i_tapered','channel','z','built_up','rhs'):continue
        section=np.asarray([point for polygon in strips(profile,profiles) for point in polygon],dtype=float)
        width,depth=np.ptp(section,axis=0)
        if not width or depth<1.5*width:continue
        start,end=np.asarray(member['axis'],dtype=float)+np.asarray(member.get('end_offsets',[[0,0,0],[0,0,0]]),dtype=float)
        axis=end-start;axis/=np.linalg.norm(axis)
        vertical=np.array([0.,0.,1.])-axis[2]*axis
        if np.linalg.norm(vertical)<.2:continue
        vertical/=np.linalg.norm(vertical)
        local_depth=np.cross(axis,np.asarray(member['local_y'],dtype=float));local_depth/=np.linalg.norm(local_depth)
        checked+=1;alignment=abs(float(np.dot(local_depth,vertical)))
        # This catches gross 90-degree roll errors, not normal roof inclination.
        if alignment<.25:
            findings.append(dict(member_id=member['id'],kind=member['kind'],profile_id=profile['id'],depth_in=depth,width_in=width,depth_alignment_to_gravity=alignment))
    return dict(checked=checked,suspect_members=findings,method='Deep gravity-framing profiles: detect depth axis nearly perpendicular to projected gravity; inspect intentional weak-axis designs separately.')


def overlapping_constituents(physical):
    profiles={p['id']:p for p in physical['profiles']};findings=[];checked=0
    for profile in profiles.values():
        if profile['family']!='built_up':continue
        components=[]
        for part in profile['components']:
            angle=np.deg2rad(part['rotation_deg']);rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            polygons=[Polygon(np.asarray(p)@rotation.T+np.asarray(part['offset'])) for p in strips(profiles[part['profile_id']],profiles)]
            components.append(unary_union(polygons))
        checked+=1
        for i,first in enumerate(components):
            for j in range(i+1,len(components)):
                second=components[j];overlap=first.intersection(second).area;ratio=overlap/min(first.area,second.area)
                # Preview strips omit fillets. Flag gross interpenetration, not
                # tiny corner differences from bend-radius simplification.
                if overlap>.005 and ratio>.05:findings.append(dict(profile_id=profile['id'],components=[i,j],overlap_area_in2=overlap,overlap_fraction_of_smaller_component=ratio))
    return dict(checked_profiles=checked,overlaps=findings,method='Separate built-up constituents must not substantially occupy the same section area; threshold >0.005 in2 and >5% of a constituent, allowing preview fillet simplifications.')


def triangle_box(triangle,bounds):
    """Triangle/AABB overlap using separating axes in all three dimensions."""
    center=bounds.mean(axis=1);half=(bounds[:,1]-bounds[:,0])/2
    vertices=np.asarray(triangle,dtype=float)-center
    if np.any(vertices.min(axis=0)>half) or np.any(vertices.max(axis=0)<-half):return False
    edges=np.roll(vertices,-1,axis=0)-vertices
    axes=[np.cross(edges[0],edges[1])]
    axes.extend(np.cross(edge,basis) for edge in edges for basis in np.eye(3))
    for axis in axes:
        if np.linalg.norm(axis)<1e-12:continue
        radius=float(np.dot(half,np.abs(axis)));projection=vertices@axis
        if projection.min()>radius+1e-10 or projection.max()<-radius-1e-10:return False
    return True


def opening_solid_clashes(objects,openings,source_ids,shrink_all=False):
    # Panels represent architectural/diaphragm reference planes, so this tests
    # actual framing and connection components, not an uncut context surface.
    classes={'IfcBeam','IfcColumn','IfcMember','IfcPlate','IfcMechanicalFastener','IfcDiscreteAccessory','IfcBuildingElementPart'}
    solids=[o for o in objects if o['ifc_class'] in classes and o.get('faces')]
    all_bounds=np.asarray([o['bounds_m'] for o in solids]);findings=[]
    if not solids:return dict(checked_solids=0,clashes=[])
    for opening in openings:
        box=np.asarray(opening['bounds_m'],dtype=float).copy();normal=int(np.argmin(box[:,1]-box[:,0]))
        for k in range(3):
            if shrink_all or k!=normal:box[k,0]+=.005;box[k,1]-=.005
        if np.any(box[:,1]<=box[:,0]):continue
        candidates=np.where(np.all(all_bounds[:,:,1]>=box[:,0],axis=1)&np.all(all_bounds[:,:,0]<=box[:,1],axis=1))[0]
        for index in candidates:
            obj=solids[index];vertices=np.asarray(obj['vertices'],dtype=float)
            if any(triangle_box(vertices[face],box) for face in obj['faces']):
                findings.append(dict(opening_guid=opening['guid'],opening_name=opening['name'],product_guid=obj['guid'],source_id=source_ids.get(obj['guid']),ifc_class=obj['ifc_class']))
    method='Returned IFC mesh triangles against explicit clear volumes, with 5 mm boundary tolerance.' if shrink_all else 'Returned IFC mesh triangles against source axis-aligned opening volumes, with 5 mm tolerance at jamb/sill/head. All door/window fixtures in this sweep have axis-aligned hosts or are axis-aligned freestanding reservations.'
    return dict(checked_solids=len(solids),clashes=findings,method=method)
