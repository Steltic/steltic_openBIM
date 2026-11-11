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
from .ifc_readback_session import read_step
from .shared_constituent_readback import linked_braces,resolve_shared
from .clevis_readback import forged_fit, thread_fit
from .weld_extent_readback import actual_inner_slot_tip, each_side_extents
from .joint_mesh_readback import matches_flat_extrusion, matches_rhs_extrusion
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
    params=part.get('parameters', {})
    if params.get('free_edge_bar') or params.get('source_role') in ('base_plate','cap_gusset_support_plate','brb_moving_head','brb_core_extension'):return False
    description = str(params.get('description', '')).lower()
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
    overrides={(row['record_id'],row['field_index']):row['value'] for row in application.get('overrides',[])}
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
            role=field['role'];crossing=field.get('applicability',{}).get('crossing_receiver')
            if crossing and member is not None:
                if member not in link.get('crossing_members',{}).get(crossing,[]):continue
                role=role.removeprefix(crossing+'_')
            result[role,field['field']].append(overrides.get((link['record_id'],index),field['value']))
    return result


class Readback:
    def __init__(self, path):
        self.path = Path(path)
        self.file = read_step(path)
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
    def __init__(self, readback, physical, handoff, design_records=()):
        self.rb = readback
        self.physical = physical
        self.handoff = handoff
        self.members = {m['id']: m for m in physical['members']}
        self.profiles = {p['id']: p for p in physical['profiles']}
        self.templates = {t['id']: t for t in physical.get('assemblies', [])}
        self.connections = {c['id']:c for c in physical.get('connections',[])}
        self.shared_brace_bindings = linked_braces(self.connections)
        self.counts = Counter()
        self.findings = []
        self.covered_ends = set()
        self.checked_members = set()
        self.cache = {}
        self.shared_issues = {}
        self.interface_cache = {}
        self.crossings = {row['id']:row for row in handoff.get('crossing_interfaces',[])}
        self.crossing_occurrences = Counter()
        self.owned_gussets = []
        self.anchor_measurements = []
        from .base_tongue_readback import intended_tongues
        self.required_tongues,tongue_findings=intended_tongues(physical,design_records)
        self.findings.extend(tongue_findings)
        self.tongue_measurements={}
        self.brb_core_measurements = []
        self.brb_bolt_measurements = []
        from .brb_supplier_core import source_requirements
        self.core_requirements = source_requirements(physical['members'],handoff,design_records)
        from .brb_casing import requirements as casing_requirements
        self.casing_requirements=casing_requirements(physical['members'],handoff,design_records,physical.get('materials',[]))
        self.checked_core_ends = Counter()
        self.support_weld_measurements = []
        self.gusset_clearance_measurements = []
        self.crossing_measurements = []
        self.transfer_measurements = []
        from .transfer_joint_readback import transfer_sources
        self.transfer_sources = transfer_sources(handoff)
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
        if mid in self.core_requirements:
            from .brb_core_readback import core_sections
            from .pin_stack_readback import actual_materials
            from .selected_plate_readback import grade
            spec=self.core_requirements[mid]
            required_length=spec['yielding_length_workpoint_ratio']*float(np.linalg.norm(np.subtract(*m['axis'])))
            info,errors=core_sections(local,spec['area_in2'],required_length)
            if mid in self.casing_requirements:
                from .brb_casing_readback import check as check_casing
                casing,problems=check_casing(self.rb.members[mid],local,self.casing_requirements[mid],
                                             self.profiles[m['profile_id']],length,m.get('brb_infill_pockets',[]))
                info['restraint']=casing;self.counts['actual_brb_casings']+=1
                if self.casing_requirements[mid].get('infill_material'):self.counts['actual_selected_brb_infills']+=1
                for detail in problems:self.issue('brb_casing_or_infill_differs',member=mid,detail=detail)
            actual=actual_materials(self.rb.members[mid]).get('YIELDING-CORE','')
            if not grade(actual) or grade(actual)!=grade(spec['material']):
                errors.append('Actual IFC core material differs from HR')
            self.brb_core_measurements.append(dict(info,member=mid,actual_material=actual))
            self.counts['actual_brb_core_sections']+=1
            for detail in errors:self.issue('brb_yielding_core_differs',member=mid,detail=detail)
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
                    if profile.get('family') in ('rhs','rectangular_hollow') and not any(profile['dimensions'].get(k) for k in ('r','radius','outer_radius')):
                        self.counts['actual_formed_rhs_profile_checks']+=1
                        if not matches_rhs_extrusion(placed,geometry,profile['dimensions']):
                            self.issue('formed_rhs_profile_walls_or_position_differ',part=part['id'],profile=profile['id'])
                        continue
                    if profile.get('family')=='flat':
                        self.counts['actual_formed_flat_profile_checks']+=1
                        if not matches_flat_extrusion(placed,geometry,profile['dimensions']):
                            self.issue('formed_flat_profile_shape_or_position_differs',part=part['id'],profile=profile['id'])
                        continue
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
        physical_parts = {p['id']: p for p in template['parts']}
        br = {role: mid for role, mid in inst['bindings'].items() if mid in self.members and brace_kind(self.members[mid])}
        cid, tid = connection['id'], template['id']
        br = {r:m for r,m in br.items() if not (r.startswith('BRACE-OTHER') and m in self.shared_brace_bindings[cid])}
        self.context = {'connection': cid, 'template': tid, 'sheet': connection.get('drawing_ref')}
        self.counts['all_assembly_occurrences'] += 1
        instance = frame(inst['origin'], inst['x_axis'], inst['y_axis'])
        inverse = np.linalg.inv(instance)
        shared_parts,shared_meshes,shared_curves=resolve_shared(self,connection,physical_parts,instance)
        parts={**physical_parts,**shared_parts}
        gussets = {pid for pid, p in parts.items() if gusset_part(p)}
        product = self.rb.assemblies[cid]
        if property_value(product, 'SourceId') != cid:
            raise ValueError('IFC assembly SourceId differs from the occurrence')
        if cid in self.required_tongues:
            from .base_tongue_readback import measure_solid
            source=selected(self.handoff,cid)
            width=set(source.get(('base_plate','width_in'),[]));length=set(source.get(('base_plate','length_in'),[]))
            plates=[loc for loc in self.rb.ranges[tid] if loc['kind']=='plate' and loc['id'] in ('P1','BASE','BP','BASE-PLATE','BASE_PLATE')]
            if len(plates)!=1 or len(width)!=1 or len(length)!=1:
                self.issue('selected_base_tongue_stock_unresolved')
            else:
                _,raw,matrix=self.rb.mesh(product);loc=plates[0]
                sole=raw.subset(loc['face_start'],loc['face_count']).transformed(inverse@matrix)
                data,issues=measure_solid(sole,width.pop(),length.pop(),self.required_tongues[cid])
                self.tongue_measurements[cid]=dict(data,connection=cid,sheet=self.context.get('sheet'))
                self.counts['actual_integral_base_tongues']+=len(self.required_tongues[cid])
                for detail in issues:self.issue('selected_actual_base_tongue_differs',detail=detail)
        if any(p['kind']=='anchor' for p in parts.values()):
            from .ifc_anchor_readback import verify_anchors
            anchor_facts,anchor_issues=verify_anchors(self.rb,product,tid,inst,self.members,self.profiles,
                                                     selected(self.handoff,cid),parts)
            if anchor_facts:
                self.anchor_measurements.append(dict(anchor_facts,connection=cid,sheet=self.context.get('sheet')))
                self.counts['actual_selected_anchor_patterns']+=1
                self.counts['actual_selected_anchor_bores']+=len(anchor_facts.get('measured_holes',{}))
            for row in anchor_issues:self.issue('selected_actual_anchor_geometry',**row)
        transfer=cid in self.transfer_sources or connection.get('detail_ref',{}).get('legacy_family')=='review_transfer_truss'
        if not br and not gussets and not shared_parts and not transfer:
            self.transport_only(cid,tid,template,parts,product,instance,inverse)
            return
        self.counts['connections'] += 1
        if any(p.get('geometry',{}).get('type') != 'polyline' for p in physical_parts.values()):
            map_id, raw, product_matrix = self.rb.mesh(product)
            relative = inverse @ product_matrix
        else:
            map_id,raw,relative = None, Mesh(np.empty((0,3)),()), np.eye(4)
        fields = selected(self.handoff, cid)
        selection_key = tuple(sorted((k, tuple(map(str, values))) for k, values in fields.items()))
        key = (tid, map_id, tuple(relative.round(5).flatten()), selection_key,cid if shared_parts else None)
        if key not in self.cache:
            start = len(self.findings)
            meshes = self.split_actual(tid, raw.transformed(relative), physical_parts)
            meshes.update(shared_meshes)
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
        if gussets:
            from .ifc_shared_gusset_readback import PlacedGusset
            # Only native face ranges belong to this occurrence. A neighbour
            # may refer to its steel to complete a second attachment path.
            for locator in self.rb.ranges.get(tid,[]):
                key=locator['id']
                if key in gussets and locator['face_count'] and key in meshes:
                    self.owned_gussets.append(PlacedGusset(cid,self.context.get('sheet'),key,meshes[key],instance))
        curves = self.rb.curves(cid)+shared_curves
        from .pin_stack_readback import actual_materials,selected_stack_record,verify_pin_stack
        if transfer:
            from .transfer_joint_readback import arm_selections,node
            specs,source_issues=arm_selections(self.handoff,cid,inst['bindings'],self.members)
            rows,failures=node(self,connection,inst,instance,parts,meshes,curves,actual_materials(product),specs)
            self.counts['actual_transfer_flange_fillets']+=sum(len(r['measurements']) for r in rows)
            self.transfer_measurements.append(dict(connection=cid,arms=rows))
            for info in source_issues+failures:self.issue('transfer_truss_joint_fit',**info)
        present=connection.get('parameters',{}).get('pin_stack')
        selected_stacks=selected_stack_record(self.handoff,cid)
        if present or selected_stacks or any(p.get('parameters',{}).get('source_stack_role') for p in parts.values()):
            declared={k:v for k,v in (present or {}).items() if k!='source_record_id'}
            if (len(selected_stacks)!=1 or declared!=selected_stacks[0][1] or
                    (present or {}).get('source_record_id',selected_stacks[0][0])!=selected_stacks[0][0]):
                self.issue('ordered_pin_stack_source_binding_differs',records=[r[0] for r in selected_stacks])
            else:
                rid,stack=selected_stacks[0]
                counts,issues=verify_pin_stack(rid,stack,parts,meshes,actual_materials(product),curves,inverse)
                self.counts.update(counts)
                for finding in issues:self.issue(**finding)
        receivers = {r['id']: r for r in template.get('receivers', [])}
        directional={k[1]:v for k,v in fields.items() if k[0]=='brb_bolt_pattern' and v}
        if directional:
            from .brb_bolt_readback import measure_layout
            if len(br)!=1 or len(gussets)!=1 or any(len(set(v))!=1 for v in directional.values()):
                self.issue('directional_brb_bolt_layout_unresolved')
            else:
                mid=next(iter(br.values()));m=self.members[mid];gusset=next(iter(gussets))
                end=min(range(2),key=lambda i:np.linalg.norm(np.subtract(m['axis'][i],inst['origin'])))
                v=inverse[:3,:3]@np.subtract(m['axis'][1-end],m['axis'][end])
                bolts=[meshes[k] for k,p in parts.items() if p['kind']=='bolt' and gusset in p.get('connects',[])]
                evidence,errors=measure_layout(meshes[gusset],bolts,v,{k:values[0] for k,values in directional.items()})
                self.brb_bolt_measurements.append(dict(evidence,member=mid,end_index=end,connection=cid,sheet=self.context.get('sheet')))
                self.counts['actual_directional_brb_bolt_groups']+=1
                for detail in errors:self.issue('actual_directional_brb_bolt_layout_differs',member=mid,detail=detail)
        self.paths(cid, parts, meshes, inst, instance, curves, br, gussets, fields,template.get('source_interfaces',[]))
        crossing_id = connection.get('source_crossing_id',cid)
        if crossing_id in self.crossings:
            self.crossing_occurrences[crossing_id] += 1
            self.crossing(connection,parts,inst,instance,curves,self.crossings[crossing_id],meshes)
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

    def crossing(self,connection,parts,inst,instance,curves,source,meshes):
        record = self.handoff['records'][source['record_id']]
        selections = {f['field']:f['value'] for i in source['selected'] if (f:=record['fields'][i])['role']=='flat_bar_crossing_fillet'}
        ids=set(source['member_ids']); binds=inst['bindings']
        if len(ids)!=2 or not ids<=set(binds.values()) or np.linalg.norm(np.asarray(connection.get('point',inst['origin']))-source['point_in'])>TOL:
            self.issue('source_crossing_members_or_workpoint_differs',crossing_id=source['id'],expected_members=sorted(ids))
        self.counts['actual_source_crossings'] += 1
        if source.get('kind')=='flat_bar_crossing_plate':
            from .ifc_plate_crossing import delivered_plate_crossing
            if not connection.get('drawing_ref'):
                self.issue('source_crossing_drawing_locator_missing',crossing_id=source['id'])
            facts,issues=delivered_plate_crossing(self.rb,source,record,inst['template_id'],parts,
                (inst,instance),curves,meshes,self.members,connection['id'])
            self.crossing_measurements.append(dict(facts,crossing=source['id']))
            self.counts['actual_plated_crossing_bar_interfaces']+=len(facts.get('interfaces',{}))
            self.counts['actual_plated_crossing_welds']+=facts.get('checked_welds',0)
            for issue in issues:
                self.issue('source_crossing_plate_geometry_differs',crossing_id=source['id'],detail=issue)
            return
        welds = [p for p in parts.values() if p['kind']=='weld' and ids <= {binds.get(role) for role in p.get('connects',[])}]
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
        measured_welds = {}
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
            kind=interface.get('kind')
            if kind in ('threaded_clevis','integral_forged_clevis'):
                roles=interface.get('connects',[])
                bodies=[r for r in roles if parts.get(r,{}).get('parameters',{}).get('source_role')=='threaded_clevis_body']
                if len(roles)!=2 or len(bodies)!=1 or any(r not in support for r in roles):
                    self.issue('clevis_interface_lacks_bound_solid',interface=interface['id'],roles=roles)
                    continue
                body=bodies[0];target=next(r for r in roles if r!=body)
                holes=parts[body].get('parameters',{}).get('holes',[])
                if len(holes)!=1:
                    self.issue('threaded_clevis_lacks_single_located_bore',interface=interface['id'],body=body)
                    continue
                axis=holes[0]['axis'];par=parts[body]['parameters']
                token=(kind,self.context['template'],body,target,member_keys.get(target))
                if kind=='threaded_clevis':
                    member=self.members.get(bound.get(target),{})
                    diameter=self.profiles.get(member.get('profile_id'),{}).get('dimensions',{}).get('d')
                    if not diameter or abs((par.get('thread_major_diameter_in') or 0)-diameter)>TOL or not par.get('thread_engagement_in'):
                        self.issue('clevis_thread_lacks_bound_rod_size_or_declared_engagement',interface=interface['id'],body=body)
                        continue
                    self.counts['actual_threaded_rod_bore_engagements']+=1
                    if token not in self.interface_cache:
                        self.interface_cache[token]=thread_fit(support[body],support[target],axis,diameter,par['thread_engagement_in'])
                else:
                    self.counts['actual_forged_jaw_mating_faces']+=1
                    if token not in self.interface_cache:
                        self.interface_cache[token]=forged_fit(support[body],support[target],axis)
                defect,measurements=self.interface_cache[token]
                if defect:
                    self.issue(defect,interface=interface['id'],target=bound.get(target,target),**measurements)
                else:
                    connected[body].add(target);connected[target].add(body)
                continue
            if kind=='integral_moving_head':
                from .stack_section_readback import check_head_contact
                links=interface.get('connects',[]);mid=bound.get('BRACE')
                leaf=next((k for k in links if k!='END-CAP'),None)
                if len(links)!=2 or 'END-CAP' not in links or leaf not in support or not mid:
                    self.issue('integral_moving_head_lacks_actual_ply',interface=interface['id']);continue
                m=self.members[mid];end=min(range(2),key=lambda i:np.linalg.norm(np.subtract(m['axis'][i],inst['origin'])))
                toward=inverse[:3,:3]@np.subtract(m['axis'][1-end],m['axis'][end])
                detail,failures=check_head_contact(support[leaf],support['END-CAP'],toward)
                for failure in failures:self.issue('integral_moving_head_contact_differs',ply=leaf,detail=failure,**detail)
                if not failures:
                    self.counts['actual_full_clevis_to_head_contacts']+=1
                    connected[leaf].add('END-CAP');connected['END-CAP'].add(leaf)
                continue
            if interface.get('kind')=='brb_core_continuation':
                from .brb_core_readback import meets_axial_core, moving_head_clearance
                mid=bound.get('BRACE');spec=self.core_requirements.get(mid)
                if not spec or 'BRACE' not in support or 'CORE-END' not in support:
                    self.issue('brb_core_continuation_missing',interface=interface['id'])
                    continue
                m=self.members[mid]
                axis=inverse[:3,:3]@np.subtract(*m['axis'][::-1])
                info,errors=meets_axial_core(support['BRACE'],support['CORE-END'],axis,spec['area_in2'])
                end=min(range(2),key=lambda i:np.linalg.norm(np.subtract(m['axis'][i],inst['origin'])))
                pinned=('brb_pinned' in fields.get(('connection','variant'),[]) or
                        any(p['kind']=='pin' for p in parts.values()))
                from .pin_stack_readback import selected_stack_record
                stacks=selected_stack_record(self.handoff,cid)
                if len(stacks)==1:
                    from .stack_section_readback import check_plate_sections
                    rid,source=stacks[0];receiver=self.handoff['records'][rid]['data'].get('receiver_selection',{})
                    away=inverse[:3,:3]@np.subtract(m['axis'][1-end],m['axis'][end])
                    hosts={k:support[k] for k in ('COLUMN','BEAM','BASE') if k in support}
                    counts,failures,measurements=check_plate_sections(source,receiver,parts,meshes,away,support['BRACE'],spec['reported_elongation_in'],hosts)
                    self.counts.update(counts);info['source_pin_plate_sections']=measurements
                    for finding in failures:self.issue(**finding)
                if pinned:
                    info.update(moving_head_clearance(support,axis,spec['reported_elongation_in'],errors))
                if any(p['kind']=='weld' and {'BRACE','END-CAP'}<=set(p.get('connects',[])) for p in parts.values()):
                    errors.append('Moving core head is welded to the restraining casing')
                self.counts['actual_brb_core_end_contacts']+=1
                self.brb_core_measurements.append(dict(info,member=mid,end_index=end,connection=cid,
                                                       sheet=self.context.get('sheet')))
                for detail in errors:self.issue('brb_core_end_fit_differs',member=mid,detail=detail,**info)
                if not errors:
                    self.checked_core_ends[mid,end]+=1
                    connected['BRACE'].add('CORE-END');connected['CORE-END'].add('BRACE')
                continue
            if interface.get('kind')!='supplier_interface' or 'CORE-END' not in interface.get('connects',[]):
                continue
            for role in set(interface['connects'])-{'CORE-END'}:
                if role not in support or 'CORE-END' not in support:
                    self.issue('source_supplier_interface_component_missing',interface=interface['id'],target=role)
                    continue
                token=('supplier_fit',self.context['template'],role,member_keys.get(role))
                if token not in self.interface_cache:
                    core,other=support['CORE-END'],support[role]
                    common=common_plate_section(other,core) if role.startswith('SPLICE') else common_plate_section(core,other)
                    self.interface_cache[token]=(shared_face_area(core,other),common)
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
            measured_welds[pid] = actual_curves[matches[0]]
            source_role = None
            logical_id = part.get('parameters',{}).get('source_weld_id',pid)
            attached_members = {br[r] for r in links if r in br}
            attached = next(iter(attached_members)) if len(attached_members)==1 else None
            local_fields = member_fields.get(attached,fields)
            if logical_id == 'WGC':
                source_role = 'gusset_column_weld'
            elif logical_id == 'WGB':
                source_role = 'gusset_base_weld' if 'BASE' in links else 'gusset_beam_weld'
            elif logical_id.startswith('WR') or part.get('parameters',{}).get('attachment_role')=='split_reinforcement_fillet':
                source_role = 'reinforcement_fillet'
            elif attached and set(links) & gussets and part.get('parameters',{}).get('attachment_role')!='continuous_slot_end_return' and (logical_id.startswith('WB') or ('brace_slot_weld','count') in local_fields):
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
                par=part.get('parameters',{})
                plane=(par.get('source_weld_leaf'),par.get('source_weld_side'))
                logical_welds[source_role,attached,logical_id,plane].append(actual_curves[matches[0]])
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
        from .support_weld_readback import selected_support_sides
        face_welds,face_errors=selected_support_sides(parts,meshes,instance,measured_welds,fields,gussets)
        self.counts['actual_two_sided_gusset_support_welds']+=len(face_welds)
        self.support_weld_measurements.extend(dict(row,connection=cid) for row in face_welds)
        for row in face_errors:self.issue('selected_gusset_fillet_faces_differ',**row)
        from .gusset_clearance_readback import selected_clearances
        clearances,issues=selected_clearances(self.members,br,member_fields,parts,(inst,instance),meshes,
                                             measured_welds,self.rb,interfaces)
        self.counts['actual_selected_fold_clearances']+=len(clearances)
        self.gusset_clearance_measurements.extend(dict(row,connection=cid,sheet=self.context.get('sheet')) for row in clearances)
        for row in issues:self.issue('selected_gusset_fold_clearance',**row)
        if len(used) != len(actual_curves):
            self.issue('unassigned_actual_reference_curves', count=len(actual_curves)-len(used))
        for (source_role,attached,logical_id,plane),lines in logical_welds.items():
            length = sum(float(np.linalg.norm(np.diff(line,axis=0),axis=1).sum()) for line in lines)
            local_fields = member_fields.get(attached,fields)
            selected_lengths = local_fields.get((source_role,'length_in'), [])
            for expected_length in set(selected_lengths):
                if abs(length-float(expected_length)) > TOL:
                    self.issue('selected_weld_reference_length_differs', part=logical_id, actual=length, selected=expected_length)
            for each in set(local_fields.get((source_role,'length_each_side_in'),[])):
                member=self.members.get(attached,{})
                slots=[s for s in member.get('slots',[]) if s.get('connection_id')==cid]
                if len(slots)!=1:
                    self.issue('selected_each_side_weld_has_no_located_slot',part=logical_id,member=attached)
                    continue
                basis,ends=self.member_frame(attached)
                token=('actual_slot_tip',attached,cid)
                if token not in self.interface_cache:
                    local=self.rb.member(attached).transformed(np.linalg.inv(basis))
                    self.interface_cache[token]=actual_inner_slot_tip(local,slots[0])
                tip=self.interface_cache[token]
                extents=each_side_extents(lines,ends[0],basis[:3,0],tip)
                self.counts['actual_each_side_weld_extents']+=1
                if any(abs(value-each)>TOL for value in extents) or abs(length-2*each)>2*TOL:
                    self.issue('selected_weld_extents_about_actual_slot_tip_differ',part=logical_id,member=attached,
                               actual_slot_tip_in=tip,measured_sides_in=list(extents),selected_each_in=each,actual_length_in=length)
            if len(lines)>1:
                reachable={0}
                for _ in range(len(lines)):
                    reachable.update(i for i,a in enumerate(lines) if any(np.linalg.norm(pa-pb)<=TOL for j in tuple(reachable) for pa in (a[0],a[-1]) for pb in (lines[j][0],lines[j][-1])))
                if len(reachable)!=len(lines):
                    self.issue('split_weld_segments_disconnected',part=logical_id,segments=len(lines))
        for mid,local_fields in member_fields.items():
            for selected_role in ('brace_slot_weld','flat_bar_end_fillet'):
                for expected_count in set(local_fields.get((selected_role,'count'),[])):
                    count=sum(role==selected_role and target==mid for role,target,_,plane in logical_welds)
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


def verify_assembly_fit(ifc_path, physical, source_handoff, design_records=()):
    """Verify every applicable connection and report individual unsupported IDs."""
    try:
        check = Assessment(Readback(ifc_path), physical, source_handoff, design_records)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        return {'passed': False, 'findings': [{'code': 'assembly_readback_unavailable', 'message': str(exc)}]}
    for connection in physical.get('connections', []):
        try:
            check.evaluate(connection)
        except (ValueError, RuntimeError, KeyError, IndexError, AttributeError, StopIteration, TypeError) as exc:
            check.issue('assembly_fit_unverified', detail=str(exc), occurrence=connection.get('id'))
    from .ifc_shared_gusset_readback import check_shared_gussets
    counts,shared_issues=check_shared_gussets(check.owned_gussets,physical.get('connections',[]))
    check.counts.update(counts)
    check.findings.extend(shared_issues)
    from .base_hardware_clearance import check as check_base_hardware
    total,hardware_issues=check_base_hardware(check)
    check.counts['actual_base_hardware_gusset_pairs']=total
    check.findings.extend(hardware_issues)
    from .gusset_outline_readback import verify_outlines
    outline_rows,outline_issues=verify_outlines(check,physical.get('connections',[]))
    check.counts['checked_gusset_transfer_sections']=sum(len(r['transfer_sections']) for r in outline_rows)
    check.counts['checked_fitted_gusset_outlines']=sum('unsupported_area_in2' in r for r in outline_rows)
    check.findings.extend(outline_issues)
    inventory = {m['id'] for m in physical['members'] if brace_kind(m)}
    for cid in sorted(set(check.required_tongues)-set(check.tongue_measurements)):
        check.findings.append(dict(code='selected_integral_base_tongue_has_no_measured_sole',connection=cid))
    check.context={}
    for mid in check.core_requirements:
        if mid not in check.checked_members:
            check.findings.append(dict(code='selected_brb_core_has_no_verified_section',member=mid))
        for end in (0,1):
            count=check.checked_core_ends[mid,end]
            if count!=1:
                check.findings.append(dict(code='selected_brb_core_end_continuation_count',member=mid,end_index=end,actual=count))
    checked_transfer={r['connection'] for r in check.transfer_measurements}
    for cid in sorted(check.transfer_sources-checked_transfer):
        check.findings.append(dict(code='selected_transfer_node_has_no_actual_assembly',connection=cid))
    for key in check.crossings:
        if check.crossing_occurrences[key] != 1:
            check.findings.append({'code':'required_crossing_occurrence_count','crossing_id':key,'actual':check.crossing_occurrences[key]})
    for unresolved in source_handoff.get('unresolved_crossing_interfaces',[]):
        check.findings.append({'code':'required_crossing_geometry_unresolved','source':unresolved})
    missing = sorted((mid, end) for mid in inventory for end in (0,1) if (mid,end) not in check.covered_ends)
    for mid, end in missing:
        check.findings.append({'code':'brace_end_has_no_matching_physical_receiver', 'member':mid, 'end_index':end})
    return {'passed': not check.findings, 'counts': dict(check.counts), 'member_inventory': len(inventory), 'transfer_measurements': check.transfer_measurements, 'gusset_outline_measurements': outline_rows, 'support_weld_measurements': check.support_weld_measurements, 'brb_core_measurements': check.brb_core_measurements, 'brb_bolt_measurements': check.brb_bolt_measurements, 'anchor_measurements': check.anchor_measurements, 'base_tongue_measurements': list(check.tongue_measurements.values()), 'gusset_clearance_measurements': check.gusset_clearance_measurements, 'unique_ends': 2*len(inventory), 'mapped_ends': len(check.covered_ends), 'crossing_measurements': check.crossing_measurements, 'findings': check.findings, 'numeric_tolerance_in': TOL, 'schema': 'steltic.actual_assembly_fit.v1'}
