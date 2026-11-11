"""Fit the multi-leaf pin plate and its two-sided face bars to its measured transfer section."""
import math
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from .pilots.model import dot


def selected_outline(source,receiver,edges,v,n,casing_half=None):
    values=receiver.get('ufm_for_one_primary_leaf',{})
    if 'whitmore_clear_station_in' not in values:return None
    s=values['whitmore_clear_station_in'];width=values['whitmore_effective_width_in'];distance=values['whitmore_distance_beyond_cheek_in']
    cheek=source['cheek_side_in'];half=source['primary_width_at_pin_in']/2;pin=s+distance+cheek/2
    if abs(pin-values['minimum_pin_station_in'])>1e-5:raise ValueError('Selected pin and Whitmore stations differ')
    end=pin+source['pin_hole_diameter_in']/2+source['extension_in'];neck=pin-cheek/2
    tail=MultiPoint([(dot(p,v),dot(p,n)) for p in edges]+[(s,-width/2),(s,width/2),(neck,-half),(neck,half)]).convex_hull
    # The full bearing breadth is retained across the pin and square cheek.
    # Beyond that bearing zone a tapered nose clears the hollow casing over its
    # travel. Both longitudinal shear paths beside the bore retain their full length.
    if casing_half is None:
        eye=box(neck,-half,end,half)
    else:
        shoulder=pin+cheek/2;tip_half=min(half,casing_half-1.5)
        if tip_half<source['pin_hole_diameter_in']/2+1.:raise ValueError('Casing gives insufficient gusset bearing nose')
        landing=max(shoulder,end-3.5)
        eye=Polygon([(neck,-half),(shoulder,-half),(landing,-tip_half),(end,-tip_half),
                     (end,tip_half),(landing,tip_half),(shoulder,half),(neck,half)])
    shape=unary_union([tail,eye]);wing=None
    pin_line=LineString([(pin,-1000.),(pin,1000.)]);through=shape.intersection(pin_line)
    if through.length>2*half+1e-5:
        # A selected long horizontal UFM weld extends beyond the separately
        # proportioned narrow bearing eye. Keep its full, finite contact strip
        # on the same sheet and radius the open notch between that strip and the eye.
        uv=[(dot(p,v),dot(p,n)) for p in edges];foot=LineString(uv[-2:]);radius=2.
        rear=tail.intersection(box(-1000,-1000,neck,1000));envelope=unary_union([tail,eye])
        # Closing only the interior notch leaves horizontal/column support lengths
        # and the specified outer cheek/bearing faces untouched.
        for stock_width in (8.,7.5,7.,6.5,6.,5.5,5.,4.5,4.):
            wing=foot.buffer(stock_width,cap_style='flat').intersection(tail);plain=unary_union([rear,eye,wing]);smooth=plain.buffer(radius,join_style='round',quad_segs=8).buffer(-radius,join_style='round',quad_segs=8)
            shape=unary_union([plain,smooth.intersection(envelope)]);cut=shape.intersection(pin_line);segments=[cut] if cut.geom_type=='LineString' else list(cut.geoms)
            if any(abs(segment.length-2*half)<1e-5 and segment.distance(Point(pin,0.))<1e-6 for segment in segments):break
    if shape.geom_type!='Polygon' or not shape.is_valid:raise ValueError('Selected transfer footprint is disconnected')
    minx,miny,maxx,maxy=shape.bounds
    def section(x):return shape.intersection(LineString([(x,miny-10),(x,maxy+10)]))
    cut=section(pin);intervals=[cut] if cut.geom_type=='LineString' else list(cut.geoms)
    actual_eye=next((g.length for g in intervals if g.distance(Point(pin,0.))<1.e-6),0.)
    if section(s).length+1.e-4<width or abs(actual_eye-2*half)>1.e-4:raise ValueError(f'Full transfer width or exact pin-eye width is missing: transfer {section(s).length:g}/{width:g} eye {actual_eye:g}/{2*half:g}')
    return dict(shape=orient(shape,sign=1),pin_station=pin,end_station=end,section_station=s,selected_width=width,casing_half=casing_half,
                stiffener_thickness=values['free_edge_stiffener_thickness_in'],stiffener_width=values['free_edge_stiffener_width_in'],
                mean_permitted=values['selected_mean_thornton_limit_in'],rays=values['actual_three_ray_length_in'],eye_half=half,
                wing_width_in=stock_width if wing is not None else None,notch_radius_in=2. if wing is not None else None)


def _normal(a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    return (dy/length,-dx/length)


def _miter(q,n1,n2,offset):
    scale=offset/(1+n1[0]*n2[0]+n1[1]*n2[1]);return (q[0]+scale*(n1[0]+n2[0]),q[1]+scale*(n1[1]+n2[1]))


def _chord(shape,line):
    cut=shape.intersection(line)
    if cut.is_empty or cut.length<1.e-6:return []
    if cut.geom_type=='LineString':return [list(cut.coords)]
    return [list(p.coords) for p in cut.geoms if p.geom_type=='LineString' and p.length>1e-6]


def add_face_bars(a,primary,row,geometry,at,edges,support_welds,v,n):
    leaf=row['id'];y=row['start'];t=row['thickness_in'];shape=geometry['shape'];ring=list(shape.exterior.coords)[:-1]
    thickness=geometry['stiffener_thickness'];width=geometry['stiffener_width'];inside=min(width/2,geometry['eye_half']-row['cheek_side_in']/2-1.);out=width-inside
    transformed=lambda u: (dot(u,v),dot(u,n))
    hostlines={w['id']:LineString([transformed(w['a']),transformed(w['b'])]) for w in support_welds}
    physical_xz=lambda xy:(v[0]*xy[0]+n[0]*xy[1],v[2]*xy[0]+n[2]*xy[1]);sgn=1 if v[2]>0 else -1
    xmin=min(p[0] for p in edges);zmin=min(sgn*p[2] for p in edges)
    # Clip real face bars exactly to the two support planes. Flat stock is offset
    # outboard by at most two inches to keep the full six-inch width clear of
    # the adjacent cheek, within the available separation of the primary leaves.
    bound=50000.;corners=[(xmin,zmin),(bound,zmin),(bound,bound),(xmin,bound)]
    fit=Polygon([transformed([x,0,sgn*z]) for x,z in corners]);normals=[_normal(q,r) for q,r in zip(ring,ring[1:]+ring[:1])]
    supported=[]
    for q,r in zip(ring,ring[1:]+ring[:1]):
        x0,z0=physical_xz(q);x1,z1=physical_xz(r)
        supported.append(max(abs(x0-xmin),abs(x1-xmin))<1e-5 or max(abs(sgn*z0-zmin),abs(sgn*z1-zmin))<1e-5)
    if not any(supported):raise ValueError('Gusset has no actual supported boundary')
    start=next(i for i,flag in enumerate(supported) if flag);chains=[];chain=[]
    for step in range(len(ring)):
        i=(start+step)%len(ring);j=(i+1)%len(ring)
        if supported[i]:
            if chain:chains.append(chain);chain=[]
        elif not chain:chain=[ring[i],ring[j]]
        else:chain.append(ring[j])
    if chain:chains.append(chain)
    centre=geometry['section_station'];target=LineString([(centre,-1000.),(centre,1000.)])
    cheek=box(geometry['pin_station']-row['cheek_side_in']/2,-row['cheek_side_in']/2,geometry['pin_station']+row['cheek_side_in']/2,row['cheek_side_in']/2)
    stock_shapes=[]
    for number,coords in enumerate(chains,1):
        edge=LineString(coords)
        # A single continuous face strip follows the unrestrained perimeter.
        # Its two offsets meet at mitres and around the radiused wing return.
        broad=edge.buffer(inside,single_sided=True,join_style='mitre',mitre_limit=2.)
        lip=edge.buffer(-out,single_sided=True,join_style='mitre',mitre_limit=2.)
        full=unary_union([broad,lip]).intersection(fit)
        if geometry.get('casing_half') is not None:
            # Turn the 6-in face stock predominantly inboard at the tip. The
            # fitted return stays inside the actual casing opening at full stroke.
            limit=geometry['casing_half']-.125;tip=geometry['end_station'];near=box(tip-3.5,-bound,bound,bound)
            inner=edge.buffer(width-.5,single_sided=True,join_style='mitre',mitre_limit=2.)
            lead=edge.buffer(-.5,single_sided=True,join_style='mitre',mitre_limit=2.)
            turn=unary_union([inner,lead]).intersection(fit).intersection(box(-bound,-limit,tip+.5,limit)).difference(cheek.buffer(.0625))
            full=unary_union([full.difference(near),turn.intersection(near),turn.intersection(box(tip-5.5,-limit,tip-3.5,limit))]).difference(cheek.buffer(.0625))
        for previous in stock_shapes:full=full.difference(previous)
        sections=[full] if full.geom_type=='Polygon' else list(full.geoms)
        for piece,stock in enumerate(sections,1):
            if stock.geom_type!='Polygon' or stock.area<.02:continue
            if stock.intersection(cheek).area>1e-5:raise ValueError('Free-edge bar reaches the selected cheek at '+leaf+' '+str(stock.intersection(cheek).area))
            stock_shapes.append(stock);touch={k:line.intersection(stock.buffer(1e-7)).length for k,line in hostlines.items()};touch={k:round(length,8) for k,length in touch.items() if length>1e-5}
            fp=list(orient(stock,sign=1).exterior.coords)[:-1]
            border=LineString(list(stock.exterior.coords));inner_path=border.intersection(shape.buffer(-1e-6));outer_path=edge.intersection(stock.buffer(1e-7))
            paths=[]
            for curve in (inner_path,outer_path):
                legs=[curve] if curve.geom_type=='LineString' else list(curve.geoms)
                for leg in legs:
                    if leg.geom_type=='LineString' and leg.length>.01:paths.extend((a,b) for a,b in zip(leg.coords,list(leg.coords)[1:]) if math.dist(a,b)>.01)
            if not paths:raise ValueError('Free-edge bar lacks a finite primary attachment')
            for side in (-1,1):
                face=y if side<0 else y+t;z=face-thickness if side<0 else face;label=f'{leaf}-EDGE-{number}-{piece}-{1 if side<0 else 2}'
                description=f'{thickness:g} x {width:g} selected free-edge reinforcement, flush to one face; continuous fitted mitres and curved returns'
                if stock.interiors:
                    from shapely import constrained_delaunay_triangles
                    faces=[];formed=orient(stock,sign=1)
                    for tri in constrained_delaunay_triangles(formed).geoms:
                        loop=list(orient(tri,sign=1).exterior.coords)[:-1];faces.extend([[at(s,d,z) for s,d in loop],[at(s,d,z+thickness) for s,d in reversed(loop)]])
                    for loop in [formed.exterior,*formed.interiors]:
                        coords=list(loop.coords)
                        for first,last in zip(coords,coords[1:]):faces.append([at(*first,z),at(*first,z+thickness),at(*last,z+thickness),at(*last,z)])
                    bar=a.part(label,description,faces,'S','plate',thickness=thickness)
                else:bar=a.polygon(label,[at(s,d,z) for s,d in reversed(fp)],thickness,basis='S',description=description)
                bar.update(selected_material=row['material'],parameters=dict(source_primary_gusset=leaf,free_edge_bar=True,selected_stock_width_in=width,selected_stock_thickness_in=thickness,
                    stock_path_local_sd=[list(pt) for pt in coords],longitudinal_edge_length_in=edge.length,transfer_section_intersection_in=target.intersection(stock).length,
                    restrained_support_intersection_in=touch,source_primitive='two-sided mitered face bars with fitted perimeter return'))
                for k,(first,last) in enumerate(paths,1):
                    a.weld(f'W-{label}-{k}',at(*first,face),at(*last,face),[leaf,label],.3125,basis='A',description='Continuous fitted edge-bar fillet on combined actual footprint')
                    a.welds[-1]['attachment_role']='free_edge_bar_fillet'
    if not stock_shapes:raise ValueError('No selected free-edge bars located on '+leaf)
    for sign in (-1,1):
        half=LineString([(centre,0),(centre,sign*1000)])
        if not any(half.intersection(b).length>.1 for b in stock_shapes):
            extreme=Point(centre,sign*geometry['selected_width']/2)
            if min(line.distance(extreme) for line in hostlines.values())>1.e-5:raise ValueError('A free Whitmore edge lacks its selected face bar')
