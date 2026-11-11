"""Cut only mortar entered by a stationary pin plate during the selected relative travel."""
from math import dist
from shapely.affinity import affine_transform
from shapely.geometry import Polygon,box
from .pilots.model import cross,sub,unit,dot


def fit_pockets(member,connection,point,fixed,terminal,stroke,bands):
    end=min(range(2),key=lambda i:dist(point,member['axis'][i]))
    gx=unit(sub(member['axis'][1],member['axis'][0]));my=member['local_y'];mz=unit(cross(gx,my))
    away=unit(sub(member['axis'][1-end],member['axis'][end]));hx=unit([away[0],away[1],0.])
    ey=cross([0.,0.,1.],hx);en=unit(cross(away,ey))
    a,b,c,d=dot(ey,my),dot(en,my),dot(ey,mz),dot(en,mz)
    to_member=[a,b,c,d,0.,0.];to_assembly=[a,c,b,d,0.,0.];clearance=.0625;pockets=[]
    for ring in bands.values():
        block=Polygon(ring);local=affine_transform(block,to_assembly)
        for part,y0,y1,foot in fixed:
            zone=local.intersection(box(y0-clearance,-10000,y1+clearance,10000))
            if zone.is_empty or zone.area<=1e-7:continue
            _,z0,_,z1=zone.bounds
            actual=foot.intersection(box(terminal-stroke-clearance,z0-clearance,terminal+24+stroke,z1+clearance))
            if actual.is_empty:continue
            amount=actual.bounds[2]+stroke+clearance-terminal
            if amount<=1e-6:continue
            footprint=box(y0-clearance,actual.bounds[1]-clearance,y1+clearance,actual.bounds[3]+clearance)
            result=block.intersection(affine_transform(footprint,to_member))
            if result.is_empty or result.area<=1e-7:continue
            pockets.append(dict(end_index=end,depth_in=amount,polygon_yz_in=[list(q) for q in list(result.exterior.coords)[:-1]],
                obstruction_ids=[connection+'/'+part],basis='Located stationary bearing steel swept over the selected axial travel plus 1/16-in clearance'))
    others=[p for p in member.get('brb_infill_pockets',[]) if p['end_index']!=end]
    member['brb_infill_pockets']=sorted(others+pockets,key=lambda p:(p['end_index'],p['obstruction_ids'],p['depth_in'],p['polygon_yz_in']))
