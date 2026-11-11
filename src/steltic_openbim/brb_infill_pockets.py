"""Only remove the finite mortar swept by named stationary stock at a BRB end."""
import math

from shapely import constrained_delaunay_triangles,set_precision
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union


def subtract_pockets(bands, pockets, length):
    cuts=[]
    for row in pockets:
        end=row['end_index'];depth=row['depth_in']
        if end not in (0,1) or not math.isfinite(depth) or not 0<depth<length:
            raise ValueError('BRB mortar pocket has an invalid finite end depth')
        if not row.get('obstruction_ids'):
            raise ValueError('BRB mortar pocket needs named stationary stock')
        mask=Polygon(row['polygon_yz_in'])
        if not mask.is_valid or mask.is_empty or mask.area<=1e-10:
            raise ValueError('BRB mortar pocket has an invalid local outline')
        low,high=(0.,depth) if end==0 else (length-depth,length)
        cuts.append((low,high,mask))
    stations=sorted({0.,length,*(v for a,b,_ in cuts for v in (a,b))})
    result=[]
    for i,(lo,hi) in enumerate(zip(stations,stations[1:])):
        if hi-lo<1e-8:continue
        at=(lo+hi)/2
        masks=unary_union([mask for a,b,mask in cuts if a<at<b])
        for band in bands:
            raw=Polygon(band['sections'][0][1]);remaining=set_precision(raw.difference(masks),1e-8)
            pieces=list(remaining.geoms) if remaining.geom_type=='MultiPolygon' else [remaining]
            cells=[]
            for piece in pieces:
                if piece.is_empty or piece.area<1e-9:continue
                cells.extend(constrained_delaunay_triangles(piece).geoms if piece.interiors else [piece])
            for j,cell in enumerate(sorted(cells,key=lambda p:(p.bounds,p.wkb))):
                ring=[list(point) for point in orient(cell,sign=1).exterior.coords[:-1]]
                result.append(dict(band,id=f"{band['id']}-{i}-{j}",sections=[[lo,ring],[hi,ring]],
                                   basis=band['basis']+'; located terminal relief for the named full-travel obstruction'))
    return result
