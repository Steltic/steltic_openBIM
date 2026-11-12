"""Measure equal-section shear hardware against the actual branch and through beam."""
import numpy as np

from .joint_mesh_readback import TOL, unit


def measure(rb, connection, template, branch, support, profile):
    cid = connection['id']
    _, assembly, placement = rb.mesh(rb.assemblies[cid])
    ranges = {r['id']:r for r in rb.ranges[template['id']]}
    branch_solid = rb.member(branch['id'])
    support_solid = rb.member(support['id'])
    normal = unit(branch['local_y'])
    along = unit(np.subtract(*branch['axis']))
    bolts, welds, issues = 0, 0, []
    curves = iter(rb.curves(cid))
    for part in template['parts']:
        pid = part['id']
        if part['geometry']['type']=='polyline':
            line = next(curves, [])
            if part['kind']=='weld' and 'M1' in part.get('connects', []):
                welds += 1
                attached = [support_solid]
                for target in part['connects']:
                    if target in ranges and ranges[target].get('face_count',0):
                        span = ranges[target]
                        attached.append(assembly.subset(span['face_start'],span['face_count']).transformed(placement))
                if len(line)<2 or any(ply.point_distance(q)>TOL for ply in attached for q in
                                      (line[0], (line[0]+line[-1])/2, line[-1])):
                    issues.append((pid,'weld misses a connected ply'))
        if part['kind']!='bolt' or 'M2' not in part.get('connects', []):
            continue
        bolts += 1
        span = ranges[pid]
        solid = assembly.subset(span['face_start'],span['face_count']).transformed(placement)
        params = part['parameters']
        axis = unit(placement[:3,:3] @ params['axis'])
        centre = (solid.vertices.min(axis=0)+solid.vertices.max(axis=0))/2
        shaft = solid.line_hits(centre,axis)
        # Probe just outside the nominal bore for the two material faces.
        faces = branch_solid.line_hits(centre+along*float(params['diameter']),axis)
        if (abs(axis @ normal)<.99999 or len(shaft)<2 or len(faces)!=2
                or abs(faces[1]-faces[0]-profile['dimensions']['tw'])>TOL
                or shaft[0]>faces[0]+TOL or shaft[-1]<faces[-1]-TOL):
            issues.append((pid,'bolt misses the terminating web'))
    return bolts,welds,issues
