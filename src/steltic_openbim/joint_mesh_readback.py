"""Independent section and face measurements on decoded IFC polygon meshes."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import polygonize, unary_union


TOL = 1e-4  # inch, coordinate/serialization allowance only


def unit(vector):
    result = np.asarray(vector, dtype=float)
    length = np.linalg.norm(result)
    if length < 1e-10:
        raise ValueError('zero direction')
    return result / length


def plane_axes(normal):
    n = unit(normal)
    reference = np.eye(3)[np.argmin(np.abs(n))]
    u = unit(np.cross(n, reference))
    return u, np.cross(n, u)


def transform(points, matrix):
    points = np.asarray(points, dtype=float)
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def frame(origin, x_axis, y_axis):
    x = unit(x_axis)
    raw_y = np.asarray(y_axis, dtype=float)
    y = unit(raw_y - np.dot(raw_y, x) * x)
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack((x, y, np.cross(x, y)))
    matrix[:3, 3] = origin
    return matrix


@dataclass
class Mesh:
    vertices: np.ndarray
    faces: tuple

    def subset(self, start, count):
        faces = self.faces[start:start + count]
        indices = sorted({i for face in faces for i in face})
        remap = {old: new for new, old in enumerate(indices)}
        return Mesh(self.vertices[indices], tuple(tuple(remap[i] for i in face) for face in faces))

    def transformed(self, matrix):
        return Mesh(transform(self.vertices, matrix), self.faces)

    @cached_property
    def polygons(self):
        return [self.vertices[list(f)] for f in self.faces]

    @cached_property
    def planes(self):
        result = []
        for face in self.polygons:
            cross = np.sum(np.cross(face, np.roll(face, -1, axis=0)), axis=0)
            if np.linalg.norm(cross) < 1e-9:
                continue
            normal = unit(cross)
            u, v = plane_axes(normal)
            flat = Polygon(np.column_stack((face @ u, face @ v)))
            result.append((normal, float(face[0] @ normal), u, v, flat, flat.buffer(TOL)))
        return result

    @cached_property
    def closed(self):
        counts = Counter()
        for face in self.faces:
            for a, b in zip(face, (*face[1:], face[0])):
                counts[a, b] += 1
        return bool(counts) and all(total == counts.get((b, a), 0) for (a, b), total in counts.items())

    @cached_property
    def plate_normal(self):
        areas = Counter()
        directions = {}
        for points in self.polygons:
            cross = np.sum(np.cross(points, np.roll(points, -1, axis=0)), axis=0) / 2
            area = float(np.linalg.norm(cross))
            if area < 1e-9:
                continue
            normal = cross / area
            if normal[np.argmax(np.abs(normal))] < 0:
                normal = -normal
            key = tuple(np.round(normal, 5))
            areas[key] += area
            directions[key] = normal
        if not areas:
            raise ValueError('empty plate face area')
        return directions[max(areas, key=areas.get)]

    def section(self, normal, station, axes=None):
        """Return actual material at a plane, retaining nested voids and compound seams."""
        n = unit(normal)
        u, v = axes if axes is not None else plane_axes(n)
        heights = self.vertices @ n - station
        segments = Counter()
        for face in self.faces:
            indices = list(face)
            h = heights[indices]
            if min(h) >= -1e-8 or max(h) <= 1e-8:
                continue
            hits = []
            for ia, ib in zip(indices, indices[1:] + indices[:1]):
                a, b = self.vertices[ia], self.vertices[ib]
                ha, hb = heights[ia], heights[ib]
                if abs(ha) <= 1e-8:
                    hits.append(a)
                elif ha * hb < 0:
                    hits.append(a + (b - a) * ha / (ha - hb))
            coords = {tuple(np.round([np.dot(p, u), np.dot(p, v)], 6)) for p in hits}
            if len(coords) < 2:
                continue
            order = int(np.argmax(np.ptp(np.asarray(list(coords)), axis=0)))
            points = sorted(coords, key=lambda q: (q[order], q[1-order]))
            for a, b in zip(points[::2], points[1::2]):
                if a != b:
                    segments[tuple(sorted((a, b)))] += 1
        boundary = [s for s, count in segments.items() if count % 2]
        if not boundary:
            return Polygon()
        cells = list(polygonize(unary_union(MultiLineString(boundary))))
        kept = []
        for cell in cells:
            point = cell.representative_point()
            px, py = point.x, point.y
            crossings = 0
            for (ax, ay), (bx, by) in boundary:
                if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
                    crossings += 1
            if crossings % 2:
                kept.append(cell)
        return unary_union(kept) if kept else Polygon()

    def projection(self, axes):
        """Finite footprint of actual faces in this plane, including setbacks."""
        u,v = axes
        shapes = []
        for face in self.polygons:
            polygon = Polygon(np.column_stack((face @ u, face @ v)))
            if polygon.area > 1e-8:
                shapes.append(polygon if polygon.is_valid else polygon.buffer(0))
        return unary_union(shapes) if shapes else Polygon()

    def line_hits(self, point, direction):
        """Stations where an infinite fastener axis intersects actual material faces."""
        point = np.asarray(point, dtype=float)
        direction = unit(direction)
        hits = []
        for n, plane, u, v, _, buffered in self.planes:
            denominator = np.dot(n, direction)
            if abs(denominator) < 1e-8:
                continue
            t = float((plane - np.dot(n, point)) / denominator)
            hit = point + t * direction
            if buffered.covers(Point(float(hit @ u), float(hit @ v))):
                hits.append(t)
        return sorted({round(t, 6) for t in hits})

    def point_distance(self, point):
        point = np.asarray(point, dtype=float)
        best = float('inf')
        for n, plane, u, v, polygon, _ in self.planes:
            signed = np.dot(point, n) - plane
            if abs(signed) > best:
                continue
            planar = polygon.distance(Point(float(point @ u), float(point @ v)))
            best = min(best, float(np.hypot(signed, planar)))
        return best


def cross_section(mesh, normal, fraction=0.49991):
    n = unit(normal)
    levels = mesh.vertices @ n
    lo, hi = float(min(levels)), float(max(levels))
    station = lo + fraction * (hi - lo)
    axes = plane_axes(n)
    return mesh.section(n, station, axes), station, axes, lo, hi


def outer_polygon(section):
    if section.geom_type != 'Polygon' or section.is_empty or not section.is_valid:
        raise ValueError('plate section is empty, disconnected or invalid')
    return Polygon(section.exterior)


def projected(point, axes):
    return Point(float(np.dot(point, axes[0])), float(np.dot(point, axes[1])))


def common_plate_section(plate, member):
    """Find an interior material intersection, retaining real profile and bore voids."""
    if np.min(np.minimum(plate.vertices.max(0),member.vertices.max(0))-
              np.maximum(plate.vertices.min(0),member.vertices.min(0)))<=TOL:
        return None
    normal=plate.plate_normal; axes=plane_axes(normal)
    pp=plate.vertices@normal; mp=member.vertices@normal
    lo,hi=max(float(min(pp)),float(min(mp))),min(float(max(pp)),float(max(mp)))
    if hi-lo<=TOL:
        return None
    stops=sorted({lo,hi,*(float(k) for k in np.r_[pp,mp] if lo+TOL<k<hi-TOL)})
    for a,b in zip(stops,stops[1:]):
        if b-a<=TOL:
            continue
        station=(a+b)/2
        area=plate.section(normal,station,axes).intersection(member.section(normal,station,axes)).area
        if area>TOL:
            return {'common_material_area_in2':float(area),'interior_station_in':station,'station_interval_in':[a,b],
                    'closed_plate':plate.closed,'closed_member':member.closed}
    return None


def shared_face_area(a,b):
    """Area of actual coplanar mating faces. A shared edge or point has zero area."""
    total=0.
    for normal,station,u,v,flat,_ in a.planes:
        for face in b.polygons:
            if np.max(np.abs(face@normal-station))>TOL:
                continue
            projected_face=Polygon(np.column_stack((face@u,face@v)))
            if projected_face.area>TOL and projected_face.is_valid:
                total+=flat.intersection(projected_face).area
    return float(total)
