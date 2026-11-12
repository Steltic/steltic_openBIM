"""Seat a rod gusset's adopted web edge on the finite rafter behind its knee plate."""
from copy import deepcopy

from shapely import set_precision
from shapely.geometry import MultiPoint, Polygon

from .assembly_scene import Assembly
from .bim_assemblies import fingerprint, transformed
from .connection_cuts import drill_plate
from .pilots.model import add, sub, mul, dot, cross, unit


def half_polygon(ring, value):
    """Clip a convex planar ring to value >= 0."""
    out = []
    for a,b in zip(ring,ring[1:]+ring[:1]):
        va,vb = value(a),value(b)
        if va >= 0:
            out.append(a)
        if va*vb < 0:
            out.append(add(a,mul(sub(b,a),va/(va-vb))))
    return out


def rod_gusset_view(physical, fits=None):
    knees = {c['id']:c for c in physical.get('connections',[]) if c.get('parameters',{}).get('actual_gable_knee')}
    if not knees:
        return physical
    if fits is None:
        from .ifc_beam_ends import beam_end_fits
        fits = beam_end_fits(physical)
    members = {m['id']:m for m in physical['members']}
    profiles = {p['id']:p for p in physical['profiles']}
    templates = {t['id']:t for t in physical['assemblies']}
    variants = {}
    connections = []
    for c in physical['connections']:
        frame = c.get('assembly_instance',{})
        host = frame.get('bindings',{}).get('HOST')
        if c.get('parameters',{}).get('actual_rod_end') and host in fits:
            for cut in fits[host]:
                knee = knees.get(cut['connection'])
                if not knee or c.get('joint_id')!=knee.get('joint_id'):
                    continue
                original = templates[frame['template_id']]
                variant = seat_web_edge(original,c,knee,cut['plane'],members,profiles,templates)
                if variant:
                    variants[variant['id']] = variant
                    frame = dict(frame,template_id=variant['id'],revision=variant['revision'])
                    c = dict(c,assembly_instance=frame)
                break
        connections.append(c)
    return dict(physical,connections=connections,assemblies=[*physical['assemblies'],*variants.values()])


def seat_web_edge(original, connection, knee, cut, members, profiles, templates):
    frame = connection['assembly_instance']
    parts = {p['id']:p for p in original['parts']}
    lines = [p for p in parts.values() if p['kind']=='weld' and set(p.get('connects',[]))=={'HOST','GUSSET'}]
    if len(lines)!=2:
        raise ValueError('Expected both faces of the rod gusset web weld at '+connection['id'])
    local_axes = (frame['x_axis'],frame['y_axis'],cross(frame['x_axis'],frame['y_axis']))
    vector = lambda world: [dot(world,axis) for axis in local_axes]
    front = vector(cut['normal'])
    station = cut['offset_in']-dot(frame['origin'],cut['normal'])
    endpoints = [p['geometry']['points'] for p in lines]
    distance = station-min(dot(q,front) for line in endpoints for q in line)
    if distance<=1e-6:
        return None
    along = unit(sub(endpoints[0][-1],endpoints[0][0]))
    if dot(along,front)<0:
        along = mul(along,-1)
    move = mul(along,distance/dot(along,front))
    moved = [[add(q,move) for q in line] for line in endpoints]
    root = [mul(add(a,b),.5) for a,b in zip(*moved)]

    gusset = parts['GUSSET']
    depth = gusset['parameters']['thickness']
    hole, = gusset['parameters']['holes']
    n = unit(hole['axis'])
    u = unit(vector(connection['parameters']['into']))
    v = unit(cross(n,u))
    offset = dot(root[0],n)
    pin = add(hole['point'],mul(n,offset-dot(hole['point'],n)))
    # Retain the pin end of the accepted outline, its bore, and the supplier grip.
    outline = root+[add(pin,mul(v,-3)),add(pin,mul(v,3)),add(pin,mul(u,3))]
    uv = lambda q: (dot(q,u),dot(q,v))
    xyz = lambda xy: add(add(mul(u,xy[0]),mul(v,xy[1])),mul(n,offset))
    plate = MultiPoint([uv(q) for q in outline]).convex_hull

    # Relieve the inside corner over the real column and end-plate width.
    # Include both gusset faces in the clearance at the plumb end plate.
    kframe = knee['assembly_instance']
    ep = next(p for p in templates[kframe['template_id']]['parts'] if p['id']=='EP')
    host = members[frame['bindings']['HOST']]
    side = host['local_y']
    if dot(side,sub(transformed(pin,frame),kframe['origin']))<0:
        side = mul(side,-1)
    column = members[kframe['bindings']['COLUMN']]
    flange = profiles[column['profile_id']]['dimensions']['bf']/2
    width = max(dot(kframe['origin'],side)+flange,
                max(dot(transformed(q,kframe),side) for face in ep['geometry']['faces'] for q in face))
    side_local = vector(side)
    border = width-dot(frame['origin'],side)+depth/2*abs(dot(n,side_local))
    front_limit = station+depth/2*abs(dot(front,n))
    ring = list(plate.exterior.coords)[:-1]
    blocked = half_polygon(ring,lambda a:front_limit-dot(xyz(a),front))
    blocked = half_polygon(blocked,lambda a:border-dot(xyz(a),side_local))
    if len(blocked)>=3:
        plate = set_precision(plate,1e-7).difference(set_precision(Polygon(blocked),1e-7))
    if plate.geom_type!='Polygon' or not plate.is_valid:
        raise ValueError('Gusset edge fitting disconnects the plate at '+connection['id'])
    vertices = [sub(xyz(q),mul(n,depth/2)) for q in list(plate.exterior.coords)[:-1]]
    shaped = Assembly('IFC knee gusset',{}).polygon('GUSSET',vertices,depth,normal=n)
    drill_plate(shaped,[hole['point']],hole['axis'],hole['diameter_in'],hole['basis'])
    corrected = deepcopy(original)
    adjusted = {p['id']:p for p in corrected['parts']}
    adjusted['GUSSET']['geometry'] = shaped['geometry']
    for p,line in zip(lines,moved):
        adjusted[p['id']]['geometry'] = dict(type='polyline',points=line)
    corrected['ifc_fit_source_template'] = original['id']
    corrected['id'] = original['id']+'-ifc-'+fingerprint(corrected['parts'])[:12]
    corrected['revision'] = fingerprint({k:v for k,v in corrected.items() if k!='revision'})
    return corrected
