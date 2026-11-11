"""Lay out a checked pin-bearing eye and the selected developed fillet on each cheek."""
import math

from shapely.geometry import MultiPoint, Polygon, box
from shapely.ops import unary_union


def eye_stock(width, hole, extension, weld_length, leg):
    """Return the cheek outline, actual fillet paths, and supporting primary steel in pin coordinates."""
    if min(width, hole, extension, weld_length, leg)<=0 or width<=hole:
        raise ValueError('Invalid pin, bearing width, end extension or cheek weld')
    half=width/2
    end=hole/2+extension
    nose=min(half,hole/2+max(1.,2*leg))
    length=weld_length/4
    margin=leg+.25
    rear=max(hole/2+1.,length+2*margin)
    front_length=math.hypot(end,half-nose)
    if front_length<length+2*margin:
        raise ValueError('The selected cheek fillets do not fit this tapered end')
    cheek=Polygon([(-rear,-half),(0.,-half),(end,-nose),(end,nose),(0.,half),(-rear,half)])
    runs=[]
    edges=[]
    land=leg+.125
    for side in (-1.,1.):
        first=(-rear+margin,side*half)
        last=(first[0]+length,side*half)
        runs.append((first,last))
        edge=[(-rear,side*(half+land)),(last[0],side*(half+land)),(0.,side*half)]
        vx=end/front_length
        vn=side*(nose-half)/front_length
        start=(front_length-length)/2
        first=(vx*start,side*half+vn*start)
        last=(first[0]+vx*length,first[1]+vn*length)
        runs.append((first,last))
        normal=(-vn*side,vx*side)
        away=lambda q:(q[0]+land*normal[0],q[1]+land*normal[1])
        edges.append(edge+[away(first),away(last),(end,side*nose)])
    primary=Polygon(edges[0]+list(reversed(edges[1])))
    if not primary.is_valid or not primary.buffer(1e-8).covers(cheek):
        raise ValueError('Pin bearing steel and the cheek weld lands do not form a single plate')
    return dict(cheek=cheek,eye=primary,runs=runs,rear=rear,end=end)


def fit_to_support(eye,station,edge_points,transfer_station=None,transfer_width=None):
    """Join the eye to its actual support edges, retaining the selected width across the bore."""
    from shapely.affinity import translate
    bearing=translate(eye['eye'],xoff=station)
    rear=station-eye['rear']
    limits=eye['eye'].bounds
    points=list(edge_points)+[(rear,limits[1]),(rear,limits[3])]
    if transfer_width is not None:
        if transfer_station is None or transfer_station>=rear:
            raise ValueError('The selected transfer strip must lie behind the cheeks')
        points.extend([(transfer_station,-transfer_width/2),(transfer_station,transfer_width/2)])
    tail=MultiPoint(points).convex_hull
    bound=max(1000.,max(abs(x) for row in points for x in row)+100)
    back=tail.intersection(box(-bound,-bound,rear,bound))
    extra=[]
    from shapely.geometry import LineString
    for a,b in zip(edge_points[::2],edge_points[1::2]):
        segment=LineString([a,b])
        if max(a[0],b[0])>rear:
            extra.append(segment.buffer(2.,cap_style='flat').intersection(tail))
    shape=unary_union([back,bearing,*extra])
    if shape.geom_type!='Polygon' or not shape.is_valid:
        raise ValueError('A checked pin eye needs continuous steel back to its receiver')
    return shape


def draw_selected_eye(ctx,axis,horizontal_role,limits,diameter,material,hole):
    """Apply an ordinary authenticated pin selection to the existing finite HR receiver."""
    from .assembly_templates import effective
    from .brb_supplier_core import moving_head_projection,show_core
    from .connection_cuts import drill_joined_plates
    from .gusset_support_welds import place_faces
    from .pilots.model import dot
    from .slotted_gusset_outline import width_station
    assembly=ctx.a
    fields=ctx.selected
    w=fields['gusset','width_at_hole_in']
    ext=fields['gusset','extension_in']
    leg=fields['cheek_fillet','size_in']
    perimeter=fields['cheek_fillet','perimeter_each_in']
    original=next(p for p in assembly.parts if p['id']=='GUSSET')
    t=original['thickness']
    cheek_t=fields['cheek_plate','thickness_in']
    clevis_t=fields['clevis_plate','thickness_in']
    side_gap=fields['clevis_plate','side_gap_in']
    eye=eye_stock(w,hole,ext,perimeter,leg)
    width=fields.get(('gusset','whitmore_effective_width_in'))
    offset=fields.get(('gusset','whitmore_distance_beyond_cheek_in'))
    if (width is None)!=(offset is None):
        raise ValueError('Incomplete HR transfer width or distance for '+ctx.c['id'])
    section=width_station(axis,width,limits) if width else None
    pres=width_station(axis,w,limits)+eye['rear']
    station=max(pres,section+offset+eye['rear']) if width else pres
    n=(-axis[2],0.,axis[0])
    def at(s,d,y=0.):
        return [s*axis[0]+d*n[0],y,s*axis[2]+d*n[2]]
    def polygon(key,shape,y,thick,desc):
        return assembly.polygon(key,[at(s,d,y) for s,d in list(shape.exterior.coords)[:-1]],thick,
                                basis='S dimensions; A located contour',description=desc)
    supports=[(dot(pt,axis),dot(pt,n)) for weld in assembly.welds if 'GUSSET' in weld['connects']
              for pt in (weld['a'],weld['b'])]
    shape=fit_to_support(eye,station,supports,section,width)
    assembly.parts.remove(original)
    primary=polygon('GUSSET',shape,-t/2,t,'Selected composite bearing eye and fitted contour to the finite receivers')
    if fields.get(('gusset','material')):
        primary['selected_material']=fields['gusset','material']
    brace=ctx.ms[0]
    core=brace.get('supplier_core')
    travel=core['reported_elongation_in'] if core else 0.
    clearance=travel+.25
    from shapely.affinity import translate
    cheek_shape=translate(eye['cheek'],xoff=station)
    last_fixed=station+eye['end']
    stiffener=fields.get(('gusset_edge_stiffener','width_in'))
    if stiffener is not None:
        from .ordinary_pin_stiffeners import add_face_stock
        specification=dict(width=stiffener,thickness=fields['gusset_edge_stiffener','thickness_in'],
            faces=fields['gusset_edge_stiffener','faces'],material=primary.get('selected_material'),
            primary_thickness=t,cheek_fillet=leg)
        supported=[weld for weld in assembly.welds if 'GUSSET' in weld['connects']]
        last_fixed=max(last_fixed,add_face_stock(assembly,shape,cheek_shape,supported,specification,at,limits,axis))
    cap_s=last_fixed+clearance
    cap_t=1.
    cap_depth=effective(ctx.p,ctx.pid)/2
    cap_width=effective(ctx.p,ctx.pid,'width')/2
    grip=t+2*(cheek_t+clevis_t+side_gap)
    if abs(grip-fields['pin','grip_in'])>1.e-5:
        raise ValueError('HR ordinary pin grip differs from the selected joined stock')
    if cap_width<grip/2:
        cap_width=grip/2
    tongue_half=max(hole/2+1.,min(w/2,cap_depth))
    if tongue_half>cap_depth:
        cap_depth=tongue_half
    assembly.polygon('END-CAP',[at(cap_s,d,y) for d,y in ((-cap_depth,-cap_width),(-cap_depth,cap_width),
        (cap_depth,cap_width),(cap_depth,-cap_width))],cap_t,normal=axis,basis='A',
        description='Moving head joining the two outer clevis plates to the axial core')
    parts=['GUSSET']
    from shapely.geometry import box
    for i,sg in enumerate((-1,1)):
        name='CHEEK'+str(i)
        parts.append(name)
        y=t/2 if sg>0 else -t/2-cheek_t
        p=polygon(name,cheek_shape,y,cheek_t,
                  f'Selected {cheek_t:g}-in cheek with {w:g}-in bearing width and {ext:g}-in clear extension')
        if primary.get('selected_material'):p['selected_material']=primary['selected_material']
        for j,(a,b) in enumerate(eye['runs'],1):
            assembly.weld(f'W-{name}-{j}',at(station+a[0],a[1],sg*t/2),at(station+b[0],b[1],sg*t/2),
                ['GUSSET',name],leg,description=f'Selected cheek fillet, {perimeter:g} in developed on this cheek')
            assembly.welds[-1]['attachment_role']='cheek_perimeter_fillet'
        name='CLEVIS'+str(i)
        parts.append(name)
        y=(t/2+cheek_t+side_gap) if sg>0 else -grip/2
        tongue=polygon(name,box(station-hole/2-2.,-tongue_half,cap_s,tongue_half),y,clevis_t,
                       f'Selected {clevis_t:g}-in outer clevis, {side_gap:g}-in clear to adjacent cheek')
        for j,face in enumerate((y,y+clevis_t),1):
            assembly.weld(f'W-{name}-HEAD-{j}',at(cap_s,-tongue_half,face),at(cap_s,tongue_half,face),
                [name,'END-CAP'],.375,basis='A',description='Supplier clevis to moving head, fitted double-sided fillets')
    casing_s=cap_s+cap_t+clearance if core else cap_s+cap_t
    start=at(casing_s,0)
    casing=assembly.member('BRACE',ctx.pid,start,at(casing_s+24.,0),
                           description='BRB restraint casing and separate yielding steel core')
    if core:
        show_core(ctx,brace,casing)
        moving_head_projection(assembly,axis,at(cap_s+cap_t,0),clearance,core)
    pin=assembly.fastener('PIN',[at(station,0,-grip/2)],[0,1,0],diameter,grip,parts,
                         f'{diameter:g}-in selected pin through both outer clevis plies and the composite gusset')
    pin.update(functional_kind='pin',selected_material=material)
    drill_joined_plates(assembly,pin,hole,'Selected concentric pin hole')
    place_faces(assembly,fields,horizontal_role)
    assembly.dim(at(station,-w/2),at(station,w/2),'Bearing width across the pin',basis='S')
    assembly.dim(at(station,0,-grip/2),at(station,0,grip/2),'Complete pin grip',basis='S',view='section')
    if width:assembly.dim(at(section,-width/2),at(section,width/2),'Whitmore section behind the cheeks',basis='S')
    assembly.section_at=at(station,0)[0]
    return start
