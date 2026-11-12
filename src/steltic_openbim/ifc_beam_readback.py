"""Test actual material intersections at beam end joints in the published IFC."""
from functools import lru_cache
import math

import ifcopenshell.geom
import ifcopenshell.ifcopenshell_wrapper as wrapper
import numpy as np

from .ifc_beam_ends import BEAMS, COLUMNS
from .ifc_shape_readback import INCH_TOL


def joint_pairs(physical):
    kinds = {m['id']: m['kind'] for m in physical['members']}
    pairs = {}
    for j in physical.get('joints', []):
        ends = [e['member_id'] for e in j.get('member_ends', [])]
        attached = [e['member_id'] for e in j.get('attachments', [])]
        for mid in ends:
            if kinds.get(mid) not in BEAMS:
                continue
            for other in ends + attached:
                if other == mid or kinds.get(other) not in BEAMS | COLUMNS | {'column_boxing'}:
                    continue
                pair = tuple(sorted((mid, other)))
                pairs.setdefault(pair, j['id'])
    return pairs


def verify_joint_clearance(physical, products, shapes):
    pairs = joint_pairs(physical)
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    settings.set('iterator-output', wrapper.NATIVE)
    bounds = {}
    findings = []
    span_overlaps = []
    members = {m['id']: m for m in physical['members']}
    cache = {}

    @lru_cache(maxsize=48)
    def solid(mid, kernel):
        product = ifcopenshell.geom.create_shape(settings, products[mid], geometry_library=kernel)
        shape = product.geometry.as_compound(True)
        volume = shape.volume().to_double()
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError('Expected a positive-volume IFC solid')
        return product, shape

    def measure(a, b):
        errors = []
        for kernel in ('manifold', 'cgal'):
            try:
                sa = solid(a, kernel)
                sb = solid(b, kernel)
                value = sa[1].intersect(sb[1]).volume().to_double() / .0254**3
                if not math.isfinite(value) or value < -1e-6:
                    raise ValueError('Invalid IFC common volume')
                return value, None
            except (ValueError, RuntimeError, AttributeError) as exc:
                errors.append(f'{kernel} {exc}')
        return None, ', '.join(errors)

    solid_pairs = 0
    for (a, b), joint in pairs.items():
        if a not in products or b not in products:
            findings.append(dict(code='ifc_beam_receiver_missing', joint=joint, members=[a,b]))
            continue
        for mid in (a,b):
            if mid not in bounds:
                mesh, matrix, vertices, _ = shapes.read(products[mid])
                bounds[mid] = (mesh, matrix, vertices.min(axis=0), vertices.max(axis=0))
        ma, ta, alo, ahi = bounds[a]
        mb, tb, blo, bhi = bounds[b]
        if np.min(np.minimum(ahi,bhi)-np.maximum(alo,blo)) <= INCH_TOL:
            continue
        solid_pairs += 1
        # Relative placement is in IFC native units. Only rigidly identical
        # mapped shape pairs share a volume calculation.
        pose = np.linalg.solve(ta, tb)
        key = ma, mb, tuple(pose.round(9).flat)
        if key not in cache:
            cache[key] = measure(a, b)
        volume, error = cache[key]
        if not error and volume > 1e-6 and members[a]['kind'] in BEAMS and members[b]['kind'] in BEAMS:
            # Overlaid parallel spans can share a joint without framing into
            # one another. Record those separately from terminating end fits.
            aa,ab = np.asarray(members[a]['axis'])
            ba,bb = np.asarray(members[b]['axis'])
            direction = (ab-aa)/np.linalg.norm(ab-aa)
            stations = sorted(np.asarray([ba-aa,bb-aa])@direction)
            parallel = np.linalg.norm(np.cross(direction,(bb-ba)/np.linalg.norm(bb-ba))) < 1e-6
            overlap = min(np.linalg.norm(ab-aa),stations[1])-max(0.,stations[0])
            if parallel and overlap > .5*min(np.linalg.norm(ab-aa),np.linalg.norm(bb-ba)):
                span_overlaps.append(dict(joint=joint,members=[a,b],intersection_in3=volume,
                                          shared_workline_span_in=float(overlap)))
                continue
        if error or volume > 1e-6:
            findings.append(dict(code='ifc_beam_receiver_intersection', joint=joint, members=[a,b],
                                 intersection_in3=volume, detail=error or 'Beam end overlaps receiving steel'))
    solid.cache_clear()
    return dict(beam_joint_pairs=len(pairs), beam_joint_solid_pairs=solid_pairs,
                beam_joint_distinct_solid_pairs=len(cache),parallel_span_clashes=span_overlaps), findings
