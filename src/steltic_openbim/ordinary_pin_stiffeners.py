"""Cut the two selected face bars along each unrestrained primary-gusset edge."""
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def free_chains(shape,support):
    ring=list(orient(shape,sign=1).exterior.coords)
    edges=[]
    for a,b in zip(ring,ring[1:]):
        edge=LineString([a,b])
        length=edge.length
        if length<1e-6:continue
        count=max(1,math.ceil(length/2))
        cuts={i*length/count for i in range(count+1)}
        for line in support:
            for pt in line.coords:
                q=Point(pt)
                if edge.distance(q)<1e-6:cuts.add(edge.project(q))
        ordered=sorted(cuts)
        for u,w in zip(ordered,ordered[1:]):
            if w-u<1e-6:continue
            mid=edge.interpolate((u+w)/2)
            edges.append((edge.interpolate(u).coords[0],edge.interpolate(w).coords[0],
                          any(mid.distance(s)<1e-6 for s in support)))
    first=next((i for i,e in enumerate(edges) if e[2]),None)
    if first is None:raise ValueError('The primary gusset does not meet a finite selected support edge')
    chains=[]
    chain=[]
    for index in range(1,len(edges)+1):
        a,b,restrained=edges[(first+index)%len(edges)]
        if restrained:
            if chain:chains.append(chain)
            chain=[]
        else:
            if not chain:chain=[a]
            chain.append(b)
    return chains


def cut_strips(shape,support,keepout,width,limits,cheek_fillet):
    rows=[]
    allowed=limits.buffer(1e-7)
    def thickness_to_each_side(q,normal):
        reach=LineString([q,q-normal*width]).intersection(allowed).length/np.linalg.norm(normal)
        clear=max(0.,(Point(q).distance(keepout)-cheek_fillet-.125)/np.linalg.norm(normal))
        inside=min(clear,max(width/2,width-reach))
        return min(width,inside),max(0.,width-inside)
    for chain in free_chains(shape,support):
        pts=np.asarray(chain)
        steps=np.diff(pts,axis=0)
        normals=steps[:,[1,0]]*[-1.,1.]/np.linalg.norm(steps,axis=1)[:,None]
        left=[]
        right=[]
        for i,q in enumerate(pts):
            before=normals[max(i-1,0)]
            after=normals[min(i,len(normals)-1)]
            mitre=(before+after)/max(.01,1.+before@after)
            mitre/=max(1.,np.linalg.norm(mitre)/2.5)
            # At the cheek the cheek/primary seam is already occupied. Carry the
            # six-inch bar farther outboard through the pin zone, then back onto
            # the primary on the unoccupied rear edges.
            if np.linalg.norm(mitre)<1e-6:mitre=after
            inset,outset=thickness_to_each_side(q,mitre)
            left.append(q+mitre*inset)
            right.append(q-mitre*outset)
        pieces=[]
        for i in range(len(pts)-1):
            poly=Polygon([left[i],left[i+1],right[i+1],right[i]])
            if not poly.is_valid:poly=poly.buffer(0)
            pieces.append(poly)
            normal=normals[i]
            si,so=thickness_to_each_side(pts[i],normal)
            ei,eo=thickness_to_each_side(pts[i+1],normal)
            pieces.append(Polygon([pts[i]+si*normal,pts[i+1]+ei*normal,
                                   pts[i+1]-eo*normal,pts[i]-so*normal]))
        stock=unary_union(pieces).intersection(limits)
        # The pin nose is a shared free boundary with the cheek. Cutting the
        # cheek steel out of this strip keeps the two solids disjoint.
        stock=stock.difference(keepout)
        if rows:stock=stock.difference(unary_union(rows))
        geoms=stock.geoms if hasattr(stock,'geoms') else [stock]
        rows.extend(orient(poly,sign=1) for poly in geoms if poly.geom_type=='Polygon' and poly.area>.01)
    # The intersection of tangential cheek and stock boundaries can leave
    # consecutive vertices coincident at the mesh contract's precision.
    # Clean the planar cut before triangulating either face or its edge walls.
    from shapely import set_precision
    cleaned=[]
    for poly in rows:
        stock=set_precision(poly,grid_size=1.e-6)
        pieces=stock.geoms if hasattr(stock,'geoms') else [stock]
        cleaned.extend(orient(piece,sign=1) for piece in pieces if piece.area>.01)
    return cleaned


def add_face_stock(assembly,shape,cheek,welds,source,at,limits,axis):
    from .pilots.model import dot
    normal=(-axis[2],0.,axis[0])
    support=[LineString([(dot(p,axis),dot(p,normal)) for p in (w['a'],w['b'])]) for w in welds]
    width=source['width'];thickness=source['thickness'];t=source['primary_thickness']
    if min(width,thickness,t)<=0 or source['faces']!=2:raise ValueError('Invalid selected gusset face bars')
    bound=10000.
    xz=[-bound,-bound,bound,bound]
    for index,side,edge in limits:
        xz[index if side>0 else index+2]=edge
    allowed=Polygon([(x*axis[0]+z*axis[2],x*normal[0]+z*normal[2]) for x,z in list(box(*xz).exterior.coords)[:-1]])
    strips=cut_strips(shape,support,cheek,width,allowed,source['cheek_fillet'])
    if not strips:raise ValueError('No selected free-edge face bar could be located')
    for i,stock in enumerate(strips,1):
        # Actual fillet trajectories follow the part of the bar boundary on
        # primary steel. Both face bars are formed from the same plan cut.
        border=stock.boundary.intersection(shape.buffer(1e-7)).difference(cheek.buffer(.0625))
        pieces=border.geoms if hasattr(border,'geoms') else [border]
        legs=[(p,q) for line in pieces if line.geom_type=='LineString' for p,q in zip(line.coords,list(line.coords)[1:]) if math.dist(p,q)>.02]
        if not legs:raise ValueError('A free-edge bar has no located weld to the primary plate')
        for j,side in enumerate((-1,1),1):
            face=side*t/2
            y=face-thickness if side<0 else face
            key=f'GUSSET-EDGE-{i}-{j}'
            description=f'Selected free-edge stiffener PL {thickness:g} x {width:g}, fitted on the gusset face'
            if stock.interiors:
                from shapely import constrained_delaunay_triangles
                faces=[]
                for tri in constrained_delaunay_triangles(stock).geoms:
                    coords=list(orient(tri,sign=1).exterior.coords)[:-1]
                    faces.extend([[at(*p,y) for p in coords],[at(*p,y+thickness) for p in reversed(coords)]])
                for loop in [stock.exterior,*stock.interiors]:
                    for a,b in zip(loop.coords,list(loop.coords)[1:]):
                        faces.append([at(*a,y),at(*a,y+thickness),at(*b,y+thickness),at(*b,y)])
                part=assembly.part(key,description,faces,'S','plate',thickness=thickness)
            else:
                part=assembly.polygon(key,[at(s,d,y) for s,d in list(stock.exterior.coords)[:-1]],thickness,
                                      basis='S stock; A fitted perimeter',description=description)
            part['parameters']=dict(free_edge_bar=True,source_primary_gusset='GUSSET')
            if source.get('material'):part['selected_material']=source['material']
            for index,(a,b) in enumerate(legs,1):
                assembly.weld(f'W-{key}-{index}',at(*a,face),at(*b,face),['GUSSET',key],.3125,basis='A',
                    description='Fitted face bar to primary gusset')
                assembly.welds[-1]['attachment_role']='free_edge_bar_fillet'
    return max(stock.bounds[2] for stock in strips)
