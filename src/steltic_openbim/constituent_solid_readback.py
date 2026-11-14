"""Measure box and cylinder constituents of a placed HR assembly in the actual IFC faces.

The physical contract allows a connection part to be an oriented box (a plate) or a cylinder (a bolt,
anchor rod or pin shaft). The exporter writes a cylinder as a prism whose vertices lie on the declared
circle. Both are measured here from the IFC vertices against the declared numbers, in template coordinates.
"""
import numpy as np

from .joint_mesh_readback import TOL


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def matches_box(mesh, geometry):
    """Six faces whose vertices are exactly the eight corners of the declared box."""
    x, y = _unit(geometry['x_axis']), _unit(geometry['y_axis'])
    frame = np.stack([x, y, np.cross(x, y)])
    size = np.asarray(geometry['size'], dtype=float)
    local = (mesh.vertices - np.asarray(geometry['origin'], dtype=float)) @ frame.T
    at_low, at_high = np.abs(local) <= TOL, np.abs(local - size) <= TOL
    if len(mesh.faces) != 6 or np.any(size <= TOL) or not np.all(at_low | at_high):
        return False
    return len({tuple(row) for row in at_high.tolist()}) == 8


def matches_cylinder(mesh, geometry):
    """A prism between the declared end planes with every vertex on the declared circle."""
    axis = _unit(geometry['axis'])
    length, radius = float(geometry['length']), float(geometry['radius'])
    offsets = mesh.vertices - np.asarray(geometry['origin'], dtype=float)
    station = offsets @ axis
    radial = np.linalg.norm(offsets - station[:, None] * axis, axis=1)
    start, end = np.abs(station) <= TOL, np.abs(station - length) <= TOL
    if length <= TOL or radius <= TOL or not np.all(start | end) or np.max(np.abs(radial - radius)) > TOL:
        return False
    sides = int(start.sum())
    return sides >= 6 and sides == int(end.sum()) and len(mesh.faces) == sides + 2
