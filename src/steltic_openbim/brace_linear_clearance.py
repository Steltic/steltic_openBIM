"""Locate a selected linear gusset fold clearance from its actual support runs."""
from shapely.geometry import LineString,Polygon

from .pilots.model import add,mul,cross,dot


def restraint_station(welds,axis):
    edges=[w for w in welds if 'GUSSET' in w['connects'] and
           any(r in ('COLUMN','BEAM','BASE','COLLAR','SEAT') for r in w['connects'])]
    if not edges:raise ValueError('Selected linear brace-end clearance has no located restrained edge')
    return max(dot(p,axis) for e in edges for p in (e['a'],e['b'])),[e['id'] for e in edges]


def dimension(assembly,axis,ratio,fold,cap,edge_ids):
    plate=next(part for part in assembly.parts if part['id']=='GUSSET')
    normal=cross([0,1,0],axis)
    ring=Polygon([(dot(p,axis),dot(p,normal)) for p in plate['polygon']])
    bounds=ring.bounds
    intervals=[]
    for s in (fold,cap):
        line=ring.intersection(LineString([(s,bounds[1]-1),(s,bounds[3]+1)]))
        if line.is_empty:raise ValueError('Linear brace-end clearance is outside the physical gusset')
        intervals.append((line.bounds[1],line.bounds[3]))
    low=max(r[0] for r in intervals);high=min(r[1] for r in intervals)
    d=(low+high)/2
    a,b=[add(mul(axis,s),mul(normal,d)) for s in (fold,cap)]
    assembly.dim(a,b,f'Brace-end clearance (minimum {ratio:g}t)',basis='S')
    assembly.dimensions[-1]['witness_origins']=[add(mul(axis,s),mul(normal,min(max(d,lo),hi)))
        for s,(lo,hi) in zip((fold,cap),intervals)]
    plate.setdefault('parameters',{})['linear_clearance']=dict(depths=ratio,thickness_in=plate['thickness'],
        axis=axis,restraint_welds=edge_ids,restraint_station_in=fold,cap_station_in=cap)
