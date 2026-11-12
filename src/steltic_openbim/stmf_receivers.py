"""Located gusset support welds and shop stiffeners for a slotted truss web."""
import math


def support_welds(assembly, role, start, end, thickness, spec):
    for sign, suffix in ((-1, 'A'), (1, 'B')):
        p, q = list(start), list(end)
        p[1] += sign * thickness / 2
        q[1] += sign * thickness / 2
        assembly.weld('G-' + role + '-' + suffix, p, q, [role, 'GUSSET'],
                      spec['fillet_in'], basis='S', description='Continuous gusset support fillet on this face')


def stiffen_chord(assembly, role, start, end, toward, dims, spec):
    """A spine underneath the weld delivers load to diaphragms spanning both flanges."""
    lo, hi = sorted((start[0], end[0]))
    length = hi - lo
    web_back = start[2] - toward * dims['tw']
    gap = dims['d'] - 2 * dims['tf']
    y = start[1]
    depth = spec['rib_depth_in']
    rib = spec['rib_t_in']
    diaphragm = spec['diaphragm_t_in']
    clip = spec['flange_root_clip_in']
    if abs(y) > 1.e-5 or depth > (dims['bf']-dims['tw'])/2 or 2 * clip >= min(gap, depth):
        raise ValueError('Selected chord stiffeners do not fit the centered chord web pocket')
    def point(x, dy, dz):
        return [x, y + dy, web_back - toward * dz]
    def seam(name, p, q, first, second):
        assembly.weld(name, p, q, [first, second], kind='CJP', basis='S', description='Shop CJP groove weld')
    count = max(2, math.ceil((length - diaphragm) / spec['max_pitch_in']) + 1)
    pitch = (length - diaphragm) / (count - 1)
    if pitch <= diaphragm:
        raise ValueError('Insufficient clear spacing for selected transverse chord diaphragms')
    for i in range(count):
        x = lo + i * pitch
        key = f'{role}-D{i + 1}'
        border = [(-gap/2 + clip,0), (gap/2 - clip,0), (gap/2,clip), (gap/2,depth),
                  (-gap/2,depth), (-gap/2,clip)]
        part = assembly.polygon(key, [point(x, dy, dz) for dy, dz in border], diaphragm,
                      normal=[1,0,0], basis='S', description='Clipped transverse chord diaphragm')
        part['annotation_group'] = f'{role}-D1..D{count}'
        part['selected_material'] = spec['material']
        for side, suffix in ((-1,'A'),(1,'B')):
            seam(key+'-F'+suffix,point(x+diaphragm/2,side*gap/2,clip),
                 point(x+diaphragm/2,side*gap/2,depth),role,key)
        seam(key+'-WEB',point(x+diaphragm/2,-gap/2+clip,0),point(x+diaphragm/2,gap/2-clip,0),role,key)
        if i == count - 1:
            break
        x0, x1 = x + diaphragm, lo + (i + 1) * pitch
        spine = f'{role}-R{i + 1}'
        plate = assembly.polygon(spine, [point(xx,-rib/2,dz) for xx,dz in
                              ((x0,0),(x1,0),(x1,depth),(x0,depth))],
                              rib,basis='S',description='Longitudinal chord-web backing rib')
        plate['annotation_group'] = f'{role}-R1..R{count - 1}'
        plate['selected_material'] = spec['material']
        seam(spine+'-WEB',point(x0,0,0),point(x1,0,0),role,spine)
        seam(spine+'-D1',point(x0,0,0),point(x0,0,depth),spine,key)
        seam(spine+'-D2',point(x1,0,0),point(x1,0,depth),spine,f'{role}-D{i + 2}')
