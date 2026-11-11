"""Read published IFC meshes and independently test brace joint fit in inches."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
from shapely.geometry import Polygon, box

from .joint_mesh_readback import Mesh, TOL, common_plate_section, cross_section, frame, outer_polygon, plane_axes, projected, shared_face_area, transform, unit


def property_value(product, name):
    for relation in product.IsDefinedBy:
        definition = relation.RelatingPropertyDefinition
        for prop in getattr(definition, 'HasProperties', ()): 
            if prop.Name == name and prop.is_a('IfcPropertySingleValue'):
                return prop.NominalValue.wrappedValue
    return None


def brace_kind(member):
    kind = str(member.get('kind', '')).lower()
    return any(s in kind for s in ('brace', 'truss_web', 'diagonal', 'lateral_strut')) or str(member.get('profile_id', '')).upper().startswith('BRB')


def gusset_part(part):
    description = str(part.get('parameters', {}).get('description', '')).lower()
    return part.get('kind') in {'plate', 'gusset'} and ('GUSSET' in part['id'].upper() or 'gusset' in description)


def same_face(actual, expected):
    """A face keeps its cyclic ring under a new starting vertex or winding."""
    expected = np.asarray(expected, dtype=float)
    if actual.shape != expected.shape:
        return False
    start = np.where(np.max(np.abs(actual - expected[0]), axis=1) <= TOL)[0]
    for i in start:
        forward = actual[(i + np.arange(len(actual))) % len(actual)]
        reverse = actual[(i - np.arange(len(actual))) % len(actual)]
        if np.max(np.abs(forward-expected)) <= TOL or np.max(np.abs(reverse-expected)) <= TOL:
            return True
    return False


def grip_engages(ply_hits, grip):
    """Positive material length along the finite shaft, excluding face contact."""
    return (len(ply_hits) % 2 == 0 and
            any(min(b, grip) - max(a, 0.) > TOL for a, b in zip(ply_hits[::2], ply_hits[1::2])))


def selected(handoff, connection, member=None, profile=None):
    result = defaultdict(list)
    application = handoff.get('occurrences', {}).get(connection, {})
    for link in application.get('applications', []):
        record = handoff['records'][link['record_id']]
        for index in link.get('selected', []):
            field = record['fields'][index]
            attachment = field.get('applicability',{}).get('attachment')
            if member is not None and attachment == 'slotted_hss' and 'hss_members' in link:
                if link['hss_members'].get(member) != 'selected':
                    continue
            if member is not None and attachment == 'flat_bar_end' and 'flat_bar_members' in link:
                if link['flat_bar_members'].get(member) != 'selected':
                    continue
            if member is not None and attachment == 'flat_bar_end':
                dims = (profile or {}).get('dimensions',{})
                section = field['applicability'].get('section_in')
                if not profile or profile.get('family')!='flat' or (section and
                        (abs(dims.get('width',0)-section[0])>TOL or abs(dims.get('thickness',0)-section[1])>TOL)):
                    continue
            result[field['role'], field['field']].append(field['value'])
    return result


class Readback:
    def __init__(self, path):
        self.path = Path(path)
        self.file = ifcopenshell.open(str(path))
        self.scale = ifcopenshell.util.unit.calculate_unit_scale(self.file) / .0254
        self.raw_meshes = {}
        self.member_views = {}
        self.assemblies = {o.Name: o for o in self.file.by_type('IfcElementAssembly')}
        self.references = {o.Name: o for o in self.file.by_type('IfcAnnotation') if o.Name and o.Name.endswith(':references')}
        self.members = {}
        # Product names are display marks, while the source ID is a typed property.
        for cls in ('IfcBeam', 'IfcColumn', 'IfcMember'):
            for product in self.file.by_type(cls):
                source = property_value(product, 'SourceId')
                if source:
                    if source in self.members:
                        raise ValueError('Duplicate IFC material member SourceId ' + source)
                    self.members[source] = product
        raw = property_value(self.file.by_type('IfcProject')[0], 'AssemblyPartRepresentations')
        self.ranges = json.loads(raw) if raw else {}

    def placement(self, product):
        mat = np.array(ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement), dtype=float)
        mat[:3, 3] *= self.scale
        return mat

    def mesh(self, product):
        representation = next(r for r in product.Representation.Representations if r.RepresentationIdentifier == 'Body')
        geometry = representation.Items[0]
        mat = self.placement(product)
        if geometry.is_a('IfcMappedItem'):
            mapping = ifcopenshell.util.placement.get_mappeditem_transformation(geometry)
            mapping[:3, 3] *= self.scale
            mat = mat @ mapping
            geometry = geometry.MappingSource.MappedRepresentation.Items[0]
        if not geometry.is_a('IfcPolygonalFaceSet'):
            raise ValueError('Unsupported IFC part mesh ' + geometry.is_a())
        key = geometry.id()
        if key not in self.raw_meshes:
            vertices = np.asarray(geometry.Coordinates.CoordList, dtype=float) * self.scale
            faces = tuple(tuple(i - 1 for i in f.CoordIndex) for f in geometry.Faces)
            if any(getattr(f, 'InnerCoordIndices', None) for f in geometry.Faces):
                raise ValueError('Unresolved inner face rings in assembly/member readback')
            self.raw_meshes[key] = Mesh(vertices, faces)
        return key, self.raw_meshes[key], mat

    def member(self, mid):
        if mid not in self.member_views:
            product = self.members[mid]
            _, mesh, mat = self.mesh(product)
            self.member_views[mid] = mesh.transformed(mat)
        return self.member_views[mid]

    def curves(self, connection):
        obj = self.references.get(connection + ':references') or self.assemblies.get(connection)
        if obj is None:
            return []
        mat = self.placement(obj)
        lines = []
        for rep in obj.Representation.Representations:
            for group in rep.Items:
                for curve in getattr(group, 'Elements', ()):
                    if curve.is_a('IfcPolyline'):
                        pts = np.asarray([p.Coordinates for p in curve.Points], dtype=float) * self.scale
                        lines.append(transform(pts, mat))
        return lines


class Assessment:
    def __init__(self, readback, physical, handoff):
        self.rb = readback
        self.physical = physical
        self.handoff = handoff
        self.members = {m['id']: m for m in physical['members']}
        self.profiles = {p['id']: p for p in physical['profiles']}
        self.templates = {t['id']: t for t in physical.get('assemblies', [])}
        self.counts = Counter()
        self.findings = []
        self.covered_ends = set()
        self.checked_members = set()
        self.cache = {}
        self.shared_issues = {}
        self.interface_cache = {}
        self.crossings = {row['id']:row for row in handoff.get('crossing_interfaces',[])}
        self.crossing_occurrences = Counter()
        self.context = {}

    def issue(self, code, **fields):
        self.findings.append(dict(code=code, **self.context, **fields))

    def member_frame(self, mid):
        member = self.members[mid]
        ends = np.asarray(member['axis'], dtype=float) + np.asarray(member.get('end_offsets', [[0, 0, 0], [0, 0, 0]]), dtype=float)
        return frame(ends[0], ends[1] - ends[0], member['local_y']), ends

    def member_checks(self, mid):
        if mid in self.checked_members:
            return
        self.checked_members.add(mid)
        m = self.members[mid]
        basis, ends = self.member_frame(mid)
        local = self.rb.member(mid).transformed(np.linalg.inv(basis))
        length = float(np.linalg.norm(ends[1] - ends[0]))
        if not any(m.get(k) for k in ('miters', 'end_cuts', 'terminal_planes')):
            cap = [float(local.vertices[:, 0].min()), float(local.vertices[:, 0].max())]
            self.counts['actual_member_cap_checks'] += 1
            if max(abs(cap[0]), abs(cap[1] - length)) > TOL:
                self.issue('actual_member_cap_differs_from_physical_end', member=mid, actual_stations=cap, required_stations=[0, length])
        for slot in m.get('slots', []):
            lo, hi = float(slot['start_in']), float(slot['end_in'])
            center, width, axis = float(slot['centre_in']), float(slot['width_in']), int(slot['section_axis'])
            if min(width, hi - lo) <= 0 or lo < -TOL or hi > length + TOL or axis not in (0, 1):
                self.issue('invalid_declared_slot', member=mid, slot=slot)
                continue
            boundaries = sorted({lo, hi, *(float(x) for x in local.vertices[:, 0] if lo + TOL < x < hi - TOL)})
            band = (box(center-width/2+TOL, -1e5, center+width/2-TOL, 1e5) if axis == 0 else box(-1e5, center-width/2+TOL, 1e5, center+width/2-TOL))
            self.counts['actual_slots'] += 1
            for a, b in zip(boundaries, boundaries[1:]):
                if b-a < TOL:
                    continue
                station = (a + b) / 2
                section = local.section([1, 0, 0], station, (np.array([0, 1, 0]), np.array([0, 0, 1])))
                occupied = section.intersection(band).area
                if section.is_empty or occupied > TOL * 2:
                    self.issue('actual_slot_filled_or_member_section_missing', member=mid, station_in=station, occupied_cut_area_in2=float(occupied), slot=slot)
                    break
                halves = (box(-1e5,-1e5,center,1e5),box(center,-1e5,1e5,1e5)) if axis == 0 else (box(-1e5,-1e5,1e5,center),box(-1e5,center,1e5,1e5))
                negative,positive = (section.intersection(region) for region in halves)
                if negative.is_empty or positive.is_empty:
                    self.issue('actual_slot_lacks_two_retained_sides', member=mid, station_in=station)
                    break
                first, last = negative.bounds[axis+2], positive.bounds[axis]
                if max(abs(first-(center-width/2)), abs(last-(center+width/2))) > 2*TOL:
                    self.issue('actual_slot_width_or_position_differs', member=mid, station_in=station, measured_limits_in=[first,last], selected_center_width_in=[center,width])
                    break

    def split_actual(self, tid, mesh, parts):
        locators = self.rb.ranges.get(tid)
        if not isinstance(locators, list):
            raise ValueError('Missing actual constituent face ranges for ' + tid)
        if {r['id'] for r in locators} != set(parts) or len(locators) != len(parts):
            raise ValueError('Constituent ID coverage differs from template ' + tid)
        used = []
        result = {}
        for row in locators:
            part = parts[row['id']]
            if row['kind'] != part['kind'] or row.get('material_id') != part.get('material_id'):
                self.issue('constituent_locator_identity_or_material', part=part['id'])
            start, count = row['face_start'], row['face_count']
            if start < 0 or count < 0 or start + count > len(mesh.faces):
                raise ValueError('Constituent range outside actual IFC faces: ' + part['id'])
            if count:
                used.extend(range(start, start+count))
                placed = mesh.subset(start, count)
                result[part['id']] = placed
                geometry = part.get('geometry', {})
                if geometry.get('type') == 'mesh':
                    reference = [f for f in geometry['faces'] if len({tuple(np.round(p, 6)) for p in f}) >= 3]
                    self.counts['actual_constituent_face_ranges'] += 1
                    if len(reference) != len(placed.faces) or not all(same_face(a,b) for a,b in zip(placed.polygons, reference)):
                        self.issue('constituent_faces_differ_from_declared_part', part=part['id'])
                elif geometry.get('type') == 'extruded_profile':
                    profile = self.profiles[geometry['profile_id']]
                    if profile.get('family') != 'round':
                        self.issue('unverified_formed_profile',part=part['id'],profile=profile['id'])
                        continue
                    axis=unit(geometry['axis']);offsets=placed.vertices-np.asarray(geometry['origin'])
                    u=offsets@axis;diameters=2*np.linalg.norm(offsets-u[:,None]*axis,axis=1)
                    diameter=profile['dimensions']['d']
                    self.counts['actual_formed_round_profile_checks'] += 1
                    # A cap can also have a vertex at the circular section center.
                    rim=diameters[diameters>TOL]
                    if not len(rim) or max(abs(min(u)),abs(max(u)-geometry['length']),np.max(np.abs(rim-diameter)))>TOL:
                        self.issue('formed_profile_length_diameter_or_position_differs',part=part['id'],profile=profile['id'])
                else:
                    self.issue('unverified_constituent_shape_type',part=part['id'],geometry_type=geometry.get('type'))
        if sorted(used) != list(range(len(mesh.faces))):
            raise ValueError('Overlapping or unassigned actual IFC faces in ' + tid)
        return result

    def fastener_checks(self, parts, meshes, fields, gussets):
        bolt_group = []
        shafts = {}
        axial_intervals = defaultdict(list)
        sections = {}
        for pid, p in parts.items():
            if p['kind'] not in {'pin', 'bolt', 'screw', 'anchor'}:
                continue
            par = p.get('parameters', {})
            if pid not in meshes or not all(k in par for k in ('point', 'axis', 'diameter', 'grip')):
                continue
            point, axis = np.asarray(par['point'], dtype=float), unit(par['axis'])
            diameter, grip = float(par['diameter']), float(par['grip'])
            previous = shafts.setdefault(tuple(np.rint(np.r_[point, axis] / TOL).astype('int64')), pid)
            if previous != pid:
                self.issue('coincident_fastener_point_and_direction', fastener=pid, other=previous)
            canonical = axis if axis[np.argmax(np.abs(axis))] > 0 else -axis
            perpendicular = point-(point@canonical)*canonical
            key = tuple(np.rint(np.r_[canonical,perpendicular] / TOL).astype('int64'))
            current = sorted((float(point@canonical),float((point+axis*grip)@canonical)))
            for other,other_axis,interval in axial_intervals[key]:
                overlap = min(current[1],interval[1])-max(current[0],interval[0])
                if np.dot(other_axis,axis)<0 and overlap > TOL:
                    self.issue('opposed_fastener_shafts_occupy_common_axis',fastener=pid,other=other,shaft_overlap_in=overlap)
            axial_intervals[key].append((pid,axis,current))
            is_pin = p['kind'] == 'pin' or pid.upper().startswith('PIN')
            targets = [q for q in p.get('connects', []) if q in meshes and parts[q]['kind'] in {'plate', 'gusset', 'steel_plate'}]
            named_gussets = set(targets) & gussets
            if p['kind'] == 'bolt' and named_gussets:
                bolt_group.append(pid)
            for target in targets:
                mesh = meshes[target]
                section_key = (target, tuple(axis.round(7)))
                if section_key not in sections:
                    sections[section_key] = cross_section(mesh, axis)
                section, station, axes, _, _ = sections[section_key]
                if section.is_empty:
                    self.issue('empty_bearing_ply_section', fastener=pid, ply=target)
                    continue
                if section.geom_type != 'Polygon':
                    self.issue('disconnected_bearing_ply_section', fastener=pid, ply=target)
                    continue
                center = projected(point, axes)
                shaft_station = float(station - point @ axis)
                self.counts['actual_fastener_ply_checks'] += 1
                if not -TOL <= shaft_station <= grip + TOL:
                    self.issue('fastener_shaft_misses_ply', fastener=pid, ply=target, shaft_station_in=shaft_station, grip_in=grip)
                    continue
                footprint = meshes[pid].section(axis, station, axes)
                if footprint.is_empty or not footprint.buffer(TOL).covers(center):
                    self.issue('actual_fastener_shaft_missing_at_ply', fastener=pid, ply=target)
                    continue
                outline = outer_polygon(section)
                outside = footprint.difference(outline.buffer(TOL)).area
                if outside > TOL * max(1, diameter):
                    self.issue('actual_fastener_footprint_leaves_ply', fastener=pid, ply=target, outside_area_in2=float(outside))
                # A self-drilling screw intentionally penetrates the sheet. A
                # source pin/bolt or explicitly declared hole requires an actual void.
                required_bore = is_pin or bool(parts[target].get('parameters', {}).get('holes')) or (p['kind'] == 'bolt' and bool(named_gussets))
                if required_bore:
                    steel = footprint.intersection(section.buffer(-TOL)).area
                    self.counts['actual_bore_checks'] += 1
                    if steel > TOL * max(1, diameter):
                        self.issue('fastener_crosses_uncut_bearing_ply', fastener=pid, ply=target, common_area_in2=float(steel))
                    rings = [Polygon(ring) for ring in section.interiors if Polygon(ring).covers(center)]
                    if len(rings)!=1:
                        self.issue('bearing_ply_lacks_enclosed_bore_at_shaft', fastener=pid, ply=target)
                    else:
                        hole = rings[0].simplify(TOL/10,preserve_topology=True)
                        points = np.asarray(hole.exterior.coords)[:-1]
                        radii = np.linalg.norm(points-[center.x,center.y],axis=1)
                        expected = fields.get(('pin_hole','diameter_in'),[]) if is_pin else []
                        for declaration in parts[target].get('parameters',{}).get('holes',[]):
                            hole_point = projected(declaration['point'],axes)
                            if hole_point.distance(center) <= TOL:
                                expected = [*expected,declaration['diameter_in']]
                        for size in set(expected):
                            if np.max(np.abs(2*radii-float(size))) > 4*TOL:
                                self.issue('actual_bore_diameter_or_center_differs', fastener=pid, ply=target, actual_diameter_range_in=[2*min(radii),2*max(radii)], selected_in=size)
                radius = float(max(np.linalg.norm(np.asarray(x) - [center.x, center.y]) for x in footprint.exterior.coords)) if footprint.geom_type == 'Polygon' else None
                if radius is not None and abs(2 * radius - diameter) > 4*TOL:
                    self.issue('actual_shaft_diameter_differs', fastener=pid, ply=target, measured_in=2*radius, declared_in=diameter)
            if is_pin and 'brb_pinned' in fields.get(('connection', 'variant'), []):
                required = {q for q in parts if q.upper().startswith(('GUSSET','CHEEK','CLEVIS')) and parts[q]['kind'] == 'plate'}
                if not required <= set(targets) or not named_gussets:
                    self.issue('pin_omits_declared_bearing_ply', fastener=pid, missing=sorted(required-set(targets)))
                for expected in fields.get(('pin', 'diameter_in'), []):
                    if abs(diameter - float(expected)) > TOL:
                        self.issue('selected_pin_diameter_differs', fastener=pid, declared_in=diameter, selected_in=expected)
        if any('bolted' in str(v) and 'brb' in str(v) for v in fields.get(('connection', 'variant'), [])):
            for expected in fields.get(('bolt', 'count'), []):
                if len(bolt_group) != int(expected):
                    self.issue('selected_brb_bolt_group_not_through_gusset', actual=len(bolt_group), selected=int(expected))
            for pid in bolt_group:
                if len([q for q in parts[pid]['connects'] if q.upper().startswith('SPLICE')]) != 2:
                    self.issue('selected_brb_bolt_missing_outer_ply', fastener=pid)

    def evaluate(self, connection):
        inst = connection.get('assembly_instance')
        if not inst:
            return
        template = self.templates[inst['template_id']]
        parts = {p['id']: p for p in template['parts']}
        gussets = {pid for pid, p in parts.items() if gusset_part(p)}
        br = {role: mid for role, mid in inst['bindings'].items() if mid in self.members and brace_kind(self.members[mid])}
        cid, tid = connection['id'], template['id']
        self.context = {'connection': cid, 'template': tid, 'sheet': connection.get('drawing_ref')}
        self.counts['all_assembly_occurrences'] += 1
        instance = frame(inst['origin'], inst['x_axis'], inst['y_axis'])
        inverse = np.linalg.inv(instance)
        product = self.rb.assemblies[cid]
        if property_value(product, 'SourceId') != cid:
            raise ValueError('IFC assembly SourceId differs from the occurrence')
        if not br and not gussets:
            self.transport_only(cid,tid,template,parts,product,instance,inverse)
            return
        self.counts['connections'] += 1
        if any(p.get('geometry',{}).get('type') != 'polyline' for p in parts.values()):
            map_id, raw, product_matrix = self.rb.mesh(product)
            relative = inverse @ product_matrix
        else:
            map_id,raw,relative = None, Mesh(np.empty((0,3)),()), np.eye(4)
        fields = selected(self.handoff, cid)
        selection_key = tuple(sorted((k, tuple(map(str, values))) for k, values in fields.items()))
        key = (tid, map_id, tuple(relative.round(5).flatten()), selection_key)
        if key not in self.cache:
            start = len(self.findings)
            meshes = self.split_actual(tid, raw.transformed(relative), parts)
            self.cache[key] = meshes
            self.counts['unique_placed_template_checks'] += 1
            sections = {}
            for pid in gussets:
                mesh = meshes[pid]
                shape, _, _, low, high = cross_section(mesh, mesh.plate_normal)
                sections[pid] = (shape, low, high)
                self.counts['actual_gusset_contours'] += 1
                if not mesh.closed or shape.geom_type != 'Polygon' or shape.is_empty or not shape.is_valid or high-low <= TOL:
                    self.issue('invalid_actual_gusset_solid_or_contour', part=pid, closed=mesh.closed, section_type=shape.geom_type, thickness_in=high-low)
                expected = fields.get(('gusset', 'thickness_in'), [])
                if pid.upper() == 'GUSSET' and expected and all(abs(high-low-float(v)) > TOL for v in expected):
                    self.issue('selected_gusset_thickness_differs', part=pid, actual_in=high-low, selected_in=expected)
                declared = parts[pid].get('parameters', {}).get('thickness')
                if declared is not None and abs(high-low-float(declared)) > TOL:
                    self.issue('actual_plate_thickness_differs', part=pid, actual_in=high-low, declared_in=declared)
            for a,b in combinations(sorted(gussets),2):
                normal = meshes[a].plate_normal
                if abs(normal @ meshes[b].plate_normal) < 1-1e-6:
                    continue
                _, low, high = sections[a]
                other_levels = meshes[b].vertices @ normal
                lo, hi = max(low, float(min(other_levels))), min(high, float(max(other_levels)))
                if hi-lo <= TOL:
                    continue
                axes = plane_axes(normal)
                station = (lo+hi)/2
                common = meshes[a].section(normal, station, axes).intersection(meshes[b].section(normal, station, axes)).area
                if common > TOL:
                    self.issue('distinct_gussets_occupy_common_steel', gussets=[a,b], common_section_in2=common, common_thickness_in=hi-lo)
            self.fastener_checks(parts, meshes, fields, gussets)
            self.shared_issues[key] = [f['code'] for f in self.findings[start:]]
        else:
            meshes = self.cache[key]
            if self.shared_issues[key]:
                self.issue('reused_template_has_constituent_fit_findings', counts=dict(Counter(self.shared_issues[key])))
        curves = self.rb.curves(cid)
        receivers = {r['id']: r for r in template.get('receivers', [])}
        self.paths(cid, parts, meshes, inst, instance, curves, br, gussets, fields,template.get('source_interfaces',[]))
        crossing_id = connection.get('source_crossing_id',cid)
        if crossing_id in self.crossings:
            self.crossing_occurrences[crossing_id] += 1
            self.crossing(connection,parts,inst,instance,curves,self.crossings[crossing_id])
        for role, mid in br.items():
            self.member_checks(mid)
            _, ends = self.member_frame(mid)
            receiver = receivers.get(role, {})
            if len(receiver.get('axis', [])) != 2:
                self.issue('missing_brace_detail_receiver', member=mid, role=role)
                continue
            located = transform(receiver['axis'], instance)
            for end_index, point in enumerate(ends):
                delta = min(float(np.linalg.norm(x-point)) for x in located)
                if delta <= TOL:
                    self.covered_ends.add((mid, end_index))

    def crossing(self,connection,parts,inst,instance,curves,source):
        record = self.handoff['records'][source['record_id']]
        selections = {f['field']:f['value'] for i in source['selected'] if (f:=record['fields'][i])['role']=='flat_bar_crossing_fillet'}
        ids=set(source['member_ids']); binds=inst['bindings']
        if len(ids)!=2 or not ids<=set(binds.values()) or np.linalg.norm(np.asarray(connection.get('point',inst['origin']))-source['point_in'])>TOL:
            self.issue('source_crossing_members_or_workpoint_differs',crossing_id=source['id'],expected_members=sorted(ids))
        welds = [p for p in parts.values() if p['kind']=='weld' and ids <= {binds.get(role) for role in p.get('connects',[])}]
        self.counts['actual_source_crossings'] += 1
        if len(welds)!=selections.get('count') or not connection.get('drawing_ref'):
            self.issue('source_crossing_weld_count_or_drawing_locator_missing',crossing_id=source['id'],actual_welds=len(welds),selected_welds=selections.get('count'))
        for weld in welds:
            size=weld.get('parameters',{}).get('size_in'); ref=transform(weld['geometry']['points'],instance)
            line=next((q for q in curves if q.shape==ref.shape and (np.max(np.abs(q-ref))<=TOL or np.max(np.abs(q[::-1]-ref))<=TOL)),None)
            length=sum(np.linalg.norm(b-a) for a,b in zip(line,line[1:])) if line is not None else None
            if size is None or length is None or abs(size-selections['size_in'])>TOL or abs(length-selections['length_in'])>TOL:
                self.issue('source_crossing_weld_size_length_or_reference_differs',part=weld['id'],size_in=size,actual_length_in=length,selected=selections)

    def transport_only(self,cid,tid,template,parts,product,instance,inverse):
        """Read each remaining placed assembly body and its declared reference curves."""
        solids = [p for p in parts.values() if p.get('geometry',{}).get('type') != 'polyline']
        if solids:
            map_id,raw,placement = self.rb.mesh(product)
            relative = inverse @ placement
            key = ('transport',tid,map_id,tuple(relative.round(6).flatten()))
            if key not in self.cache:
                self.split_actual(tid,raw.transformed(relative),parts)
                self.cache[key] = True
                self.counts['other_unique_assembly_body_checks'] += 1
        expected = [np.asarray(p['geometry']['points']) for p in parts.values() if p.get('geometry',{}).get('type') == 'polyline']
        receivers = {r['id']:r for r in template.get('receivers',[])}
        for bond in template.get('bond_interfaces',[]):
            bars = [np.asarray(receivers[r]['axis'],dtype=float) for r in bond['bar_receivers']]
            if len(bars)==1:
                expected.append(bars[0]); continue
            if len(bars)!=2:
                raise ValueError('Unsupported reinforcement bond receiver count')
            a,b = bars
            direction = unit(a[1]-a[0]); stations = (b-a[0]) @ direction
            overlap = np.asarray([max(0.,min(stations)), min(np.linalg.norm(a[1]-a[0]),max(stations))]);
            expected.extend((a[0]+overlap[:,None]*direction,b[0]+(overlap-stations[0])[:,None]*direction))
        if not expected and cid+':references' not in self.rb.references:
            return
        actual = self.rb.curves(cid)
        for line in expected:
            world = transform(line,instance)
            match = next((i for i,a in enumerate(actual) if a.shape==world.shape and
                          (np.max(np.abs(a-world))<=TOL or np.max(np.abs(a[::-1]-world))<=TOL)),None)
            self.counts['other_actual_reference_curves'] += 1
            if match is None:
                self.issue('missing_or_moved_other_assembly_reference', expected_local=line.tolist())
            else:
                actual.pop(match)
        if actual:
            self.issue('extra_other_assembly_reference', count=len(actual))

    def paths(self, cid, parts, meshes, inst, instance, actual_curves, br, gussets, fields,interfaces=()):
        used = set()
        connected = defaultdict(set)
        logical_welds = defaultdict(list)
        member_fields = {mid:selected(self.handoff,cid,mid,self.profiles.get(self.members[mid].get('profile_id'))) for mid in br.values()}
        inverse = np.linalg.inv(instance)
        bound = {r:mid for r,mid in inst.get('bindings',{}).items() if mid in self.rb.members}
        member_shapes = {}
        member_keys = {}
        for role, mid in bound.items():
            map_id, raw, matrix = self.rb.mesh(self.rb.members[mid])
            relative = inverse @ matrix
            member_keys[role] = (map_id, tuple(relative.round(6).flatten()))
            member_shapes[role] = raw.transformed(relative)
        support = dict(meshes, **member_shapes)
        for interface in interfaces:
            if interface.get('kind')!='supplier_interface' or 'CORE-END' not in interface.get('connects',[]):
                continue
            for role in set(interface['connects'])-{'CORE-END'}:
                if role not in support or 'CORE-END' not in support:
                    self.issue('source_supplier_interface_component_missing',interface=interface['id'],target=role)
                    continue
                token=('supplier_fit',self.context['template'],role,member_keys.get(role))
                if token not in self.interface_cache:
                    core,other=support['CORE-END'],support[role]
                    self.interface_cache[token]=(shared_face_area(core,other),common_plate_section(core,other))
                area,common=self.interface_cache[token]
                self.counts['actual_supplier_interface_mating_faces'] += 1
                if area<=TOL or common:
                    self.issue('supplier_core_mating_face_fit_differs',interface=interface['id'],target=role,contact_area_in2=area,material_overlap=common)
                else:
                    connected[role].add('CORE-END')
                    connected['CORE-END'].add(role)
        for pid, part in parts.items():
            links = part.get('connects', [])
            for target in links:
                connected[target].update(q for q in links if q != target)
            if part['kind'] == 'screw':
                par = part.get('parameters', {})
                for target in set(links) & bound.keys():
                    point = np.asarray(par['point']); axis = unit(par['axis']); grip=float(par['grip'])
                    token = ('screw',member_keys[target],tuple(point.round(6)),tuple(axis.round(6)),grip)
                    hits = self.interface_cache.get(token)
                    if hits is None:
                        hits = member_shapes[target].line_hits(point,axis)
                        self.interface_cache[token] = hits
                    self.counts['actual_screw_to_global_member_ply_checks'] += 1
                    if not grip_engages(hits, grip):
                        self.issue('actual_screw_grip_misses_member_ply', fastener=pid, target=bound[target], grip_in=grip, face_stations_in=hits)
            if part.get('geometry', {}).get('type') != 'polyline':
                continue
            expected = transform(part['geometry']['points'], instance)
            matches = [i for i, line in enumerate(actual_curves) if i not in used and line.shape == expected.shape and (np.max(np.abs(line-expected)) <= TOL or np.max(np.abs(line[::-1]-expected)) <= TOL)]
            self.counts['actual_weld_reference_curves'] += 1
            if not matches:
                self.issue('missing_or_wrong_actual_weld_reference', part=pid)
                continue
            used.add(matches[0])
            if part['kind'] != 'weld':
                continue
            source_role = None
            logical_id = part.get('parameters',{}).get('source_weld_id',pid)
            attached_members = {br[r] for r in links if r in br}
            attached = next(iter(attached_members)) if len(attached_members)==1 else None
            local_fields = member_fields.get(attached,fields)
            if logical_id == 'WGC':
                source_role = 'gusset_column_weld'
            elif logical_id == 'WGB':
                source_role = 'gusset_base_weld' if 'BASE' in links else 'gusset_beam_weld'
            elif logical_id.startswith('WR'):
                source_role = 'reinforcement_fillet'
            elif attached and set(links) & gussets and (logical_id.startswith('WB') or ('brace_slot_weld','count') in local_fields):
                source_role = 'brace_slot_weld'
            elif attached and set(links) & gussets and ('flat_bar_end_fillet','count') in local_fields:
                source_role = 'flat_bar_end_fillet'
            elif logical_id.startswith('WC') and any(q.startswith('CLEVIS') for q in links):
                source_role = 'clevis_outer_fillet'
            if source_role:
                size = part.get('parameters', {}).get('size_in')
                for expected_size in local_fields.get((source_role,'size_in'), []):
                    if size is None or abs(float(size)-float(expected_size)) > TOL:
                        self.issue('selected_attachment_weld_size_differs', part=pid, role=source_role, actual=size, selected=expected_size)
                logical_welds[source_role,attached,logical_id].append(actual_curves[matches[0]])
            # Reference curves do not assert a modeled solid weld. A centerline
            # farther than the modeled fillet leg from a named attachment, at
            # an end or segment midpoint, cannot represent contact at that point.
            parameters = part.get('parameters', {})
            size = parameters.get('size_in')
            reach = float(size) if size is not None else float(parameters.get('root_opening_in',0.))
            if size is not None or parameters.get('weld_type'):
                line = transform(actual_curves[matches[0]], inverse)
                probes = np.vstack((line, (line[1:]+line[:-1])/2))
                for target in set(links) & support.keys():
                    token = ('weld', self.context['template'], pid,target,member_keys.get(target),tuple(np.round(probes.flatten(),5)))
                    distances = self.interface_cache.get(token)
                    if distances is None:
                        distances = [support[target].point_distance(point) for point in probes]
                        self.interface_cache[token] = distances
                    self.counts['actual_weld_attachment_checks'] += 1
                    if max(distances) > reach + TOL:
                        if size is None:
                            self.issue('groove_weld_reference_lacks_contact_or_declared_root_opening',part=pid,target=bound.get(target,target),distance_in=max(distances),root_opening_in=reach)
                        else:
                            self.issue('weld_reference_outside_attachment_reach', part=pid, target=bound.get(target,target), distance_in=max(distances), fillet_leg_in=size)
        if len(used) != len(actual_curves):
            self.issue('unassigned_actual_reference_curves', count=len(actual_curves)-len(used))
        for (source_role,attached,logical_id),lines in logical_welds.items():
            length = sum(float(np.linalg.norm(np.diff(line,axis=0),axis=1).sum()) for line in lines)
            local_fields = member_fields.get(attached,fields)
            selected_lengths = local_fields.get((source_role,'length_in'), []) + local_fields.get((source_role,'length_each_side_in'), [])
            for expected_length in set(selected_lengths):
                if abs(length-float(expected_length)) > TOL:
                    self.issue('selected_weld_reference_length_differs', part=logical_id, actual=length, selected=expected_length)
            if len(lines)>1:
                reachable={0}
                for _ in range(len(lines)):
                    reachable.update(i for i,a in enumerate(lines) if any(np.linalg.norm(pa-pb)<=TOL for j in tuple(reachable) for pa in (a[0],a[-1]) for pb in (lines[j][0],lines[j][-1])))
                if len(reachable)!=len(lines):
                    self.issue('split_weld_segments_disconnected',part=logical_id,segments=len(lines))
        for mid,local_fields in member_fields.items():
            for selected_role in ('brace_slot_weld','flat_bar_end_fillet'):
                for expected_count in set(local_fields.get((selected_role,'count'),[])):
                    count=sum(role==selected_role and target==mid for role,target,_ in logical_welds)
                    if count!=expected_count:
                        self.issue('selected_terminal_weld_count_differs', member=mid, role=selected_role, selected=expected_count, actual=count)
        for pid in gussets:
            for role in bound.keys()-br.keys():
                token=('plate_receiver',self.context['template'],pid,member_keys[role])
                if token not in self.interface_cache:
                    self.interface_cache[token]=common_plate_section(meshes[pid],member_shapes[role])
                common=self.interface_cache[token]
                self.counts['actual_gusset_to_bound_steel_clearances'] += 1
                if common:
                    self.issue('gusset_overlaps_bound_receiver_material',gusset=pid,receiver=bound[role],**common)
        for role, mid in br.items():
            targets = connected[role] & gussets
            seen = {role}; frontier = {role}
            while frontier:
                frontier = set().union(*(connected[q] for q in frontier)) - seen
                seen.update(frontier)
            destinations = gussets or (bound.keys()-br.keys())
            if destinations and not (seen & destinations):
                self.issue('brace_lacks_attachment_path', member=mid, role=role, intended=sorted(destinations))
            elif seen & destinations:
                self.counts['declared_brace_attachment_paths'] += 1
            if not targets:
                continue
            local = member_shapes[role]
            for pid in targets:
                self.counts['brace_gusset_interfaces'] += 1
                plate = meshes[pid]
                normal = plate.plate_normal
                material, station, axes, low, high = cross_section(plate, normal)
                member_at_plate = local.section(normal, station, axes)
                overlap = member_at_plate.intersection(material).area
                if overlap > TOL * max(1, np.sqrt(material.area)):
                    self.issue('actual_brace_material_inside_gusset', member=mid, gusset=pid, common_section_in2=float(overlap))
                levels = local.vertices @ normal
                separation = max(float(min(levels)-high), float(low-max(levels)), 0.)
                if separation > TOL:
                    self.issue('actual_brace_separated_from_attached_gusset', member=mid, gusset=pid, separation_lower_bound_in=separation)
                source_slots = [slot for slot in self.members[mid].get('slots', []) if slot.get('connection_id') in (None,cid)]
                for clearance in member_fields[mid].get(('slot','clearance_in'), []):
                    if not source_slots:
                        self.issue('selected_brace_slot_missing', member=mid, selected_clearance_in=clearance)
                    for slot in source_slots:
                        required = high - low + float(clearance)
                        if abs(float(slot['width_in']) - required) > TOL:
                            self.issue('selected_slot_width_differs', member=mid, actual_declared_width_in=slot['width_in'], required_width_in=required)
                if source_slots:
                    # A drilled or slotted attachment must enter the actual
                    # member envelope. Compare in its axial/depth plane.
                    member_frame, ends = self.member_frame(mid)
                    plate_world = plate.transformed(instance).transformed(np.linalg.inv(member_frame))
                    extent = plate_world.vertices[:,0]
                    self.counts['slotted_engagement_checks'] += 1
                    member_local = self.rb.member(mid).transformed(np.linalg.inv(member_frame))
                    engaged = False
                    for slot in source_slots:
                        axis = int(slot['section_axis']) + 1
                        axes = np.eye(3)[[0,3-axis]]
                        station = plate_world.vertices[:,axis]
                        lo,hi = float(slot['start_in']),float(slot['end_in'])
                        if min(float(max(extent)),hi)-max(float(min(extent)),lo) <= TOL:
                            continue
                        if min(station) < slot['centre_in']-slot['width_in']/2-TOL or max(station) > slot['centre_in']+slot['width_in']/2+TOL:
                            self.issue('actual_gusset_outside_transverse_slot_clearance',member=mid,gusset=pid,actual_sides_in=[min(station),max(station)],slot=slot)
                            continue
                        footprint = plate_world.projection(axes)
                        envelope = member_local.projection(axes).intersection(box(lo,-1e5,hi,1e5))
                        if footprint.intersection(envelope).area > TOL:
                            engaged = True
                    if not engaged:
                        self.issue('actual_gusset_misses_finite_slot', member=mid, gusset=pid, plate_stations_in=[min(extent),max(extent)])


def verify_assembly_fit(ifc_path, physical, source_handoff):
    """Verify every applicable connection and report individual unsupported IDs."""
    try:
        check = Assessment(Readback(ifc_path), physical, source_handoff)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        return {'passed': False, 'findings': [{'code': 'assembly_readback_unavailable', 'message': str(exc)}]}
    for connection in physical.get('connections', []):
        try:
            check.evaluate(connection)
        except (ValueError, RuntimeError, KeyError, IndexError, AttributeError, StopIteration, TypeError) as exc:
            check.issue('assembly_fit_unverified', detail=str(exc), occurrence=connection.get('id'))
    inventory = {m['id'] for m in physical['members'] if brace_kind(m)}
    for key in check.crossings:
        if check.crossing_occurrences[key] != 1:
            check.findings.append({'code':'required_crossing_occurrence_count','crossing_id':key,'actual':check.crossing_occurrences[key]})
    for unresolved in source_handoff.get('unresolved_crossing_interfaces',[]):
        check.findings.append({'code':'required_crossing_geometry_unresolved','source':unresolved})
    missing = sorted((mid, end) for mid in inventory for end in (0,1) if (mid,end) not in check.covered_ends)
    for mid, end in missing:
        check.findings.append({'code':'brace_end_has_no_matching_physical_receiver', 'member':mid, 'end_index':end})
    return {'passed': not check.findings, 'counts': dict(check.counts), 'member_inventory': len(inventory), 'unique_ends': 2*len(inventory), 'mapped_ends': len(check.covered_ends), 'findings': check.findings, 'numeric_tolerance_in': TOL, 'schema': 'steltic.actual_assembly_fit.v1'}
