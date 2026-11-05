"""Separate the saved floor layers and keep them out of steel bearing strips."""
import copy
from collections import defaultdict
from shapely.geometry import Polygon,box


def bind_bearing_clearances(b):
    """Name actual rods/packs occupying the finish-free bearing strips.

    Packs are added after the floor layers, so resolve this after framing is
    complete. Test the whole declared layer depth, not only its top surface.
    Architectural doors, windows and floor openings are never exempted here.
    """
    if b.key!='cfs6':return
    panels={p['id']:p for p in b.panels}
    actual=[]
    for m in b.members:
        if m['kind'] not in ('hold_down_rod','chord_squash_pack'):continue
        ends=[[v+o for v,o in zip(q,off)] for q,off in zip(m['axis'],m['end_offsets'])]
        if any(abs(ends[1][i]-ends[0][i])>1e-8 for i in (0,1)):continue
        actual.append((m['id'],ends[0][:2],sorted(q[2] for q in ends)))
    for opening in b.openings:
        if opening.get('kind')!='wall_bearing_holdback':continue
        panel=panels[opening['host_id']]
        if panel.get('thickness_direction')!='negative_global_z':raise ValueError('Expected source floor-layer top datum')
        top=opening['z_ft']*12;bottom=top-panel['thickness_in']
        x0,y0=opening['x_ft']*12,opening['y_ft']*12
        x1,y1=x0+opening['width_ft']*12,y0+opening['height_ft']*12
        ids=[mid for mid,(x,y),(lo,hi) in actual if x0<=x<=x1 and y0<=y<=y1 and min(hi,top)>max(lo,bottom)+1e-8]
        if ids:opening.update(penetrating_member_ids=sorted(ids),penetration_basis=
            'This finish-free bearing strip deliberately clears these actual continuous tie rods and scheduled chord squash packs. Each listed member overlaps this floor layer; the strip is material clearance, not an unobstructed architectural opening.')


def rectangles(poly):
    """Rectangular pieces of an orthogonal clipped strip, all inside its host."""
    polygons=[poly] if poly.geom_type=='Polygon' else list(poly.geoms)
    for polygon in polygons:
        if polygon.is_empty:continue
        xs=sorted({q[0] for q in polygon.exterior.coords})
        for left,right in zip(xs,xs[1:]):
            part=polygon.intersection(box(left,polygon.bounds[1],right,polygon.bounds[3]))
            for piece in ([part] if part.geom_type=='Polygon' else getattr(part,'geoms',[])):
                if piece.area<1e-8:continue
                a,c,d,e=piece.bounds
                if abs(piece.area-(d-a)*(e-c))>1e-6:raise ValueError('Holdback needs an orthogonal host')
                yield a,c,d,e


def apply(b):
    if b.key!='cfs6':return
    floors=[p for p in b.panels if p['kind']=='floor'];source_openings={o['id']:o for o in b.openings}
    b.material_selections=getattr(b,'material_selections',[])
    b.material_selections.extend([
        dict(id='CFS6-FLOOR-WSP',basis='S',specification='23/32 in wood structural subfloor; source diaphragm uses the conservative 15/32 in table values'),
        dict(id='CFS6-FLOOR-GYPSUM',basis='S',specification='1.5 in gypsum underlayment; excluded from the steel-to-steel wall bearing strips')])
    for panel in floors:
        k=panel['level'];top=panel['vertices'][0][2];before=copy.deepcopy(panel)
        panel.update(thickness_in=23/32,vertices=[[q[0],q[1],top-1.5] for q in panel['vertices']],
            material_id='CFS6-FLOOR-WSP',basis='S layer thickness; A accepted footprint and holdback set-out',
            thickness_direction='negative_global_z',floor_stack_id='CFS6-FLOOR-'+str(k))
        finish=b.panel('FINISH-'+str(k),'floor_finish',copy.deepcopy(before['vertices']),1.5,k,'S',
            material_id='CFS6-FLOOR-GYPSUM',thickness_direction='negative_global_z',
            floor_stack_id=panel['floor_stack_id'],openings=[])
        for oid in list(panel.get('openings',[])):
            lower=source_openings[oid];lower.update(host_id=panel['id'],z_ft=(top-1.5)/12)
            upper=copy.deepcopy(lower);upper.update(id=oid+'-FINISH',host_id=finish['id'],z_ft=top/12,parent_opening_id=oid)
            b.openings.append(upper);finish['openings'].append(upper['id'])
        groups=defaultdict(list)
        for track in b.members:
            if track['level']!=k+1 or track['kind'] not in ('bottom_track','ordinary_track','tier_track') or track['local_y'][2]<.99:continue
            along=max(range(2),key=lambda i:abs(track['axis'][1][i]-track['axis'][0][i]));normal=1-along
            groups[along,round(track['axis'][0][normal],6)].append(track)
        if not groups:raise ValueError('Floor has no actual upper-wall bearing strips')
        for index,((along,station),tracks) in enumerate(sorted(groups.items())):
            start=min(q[along] for t in tracks for q in t['axis']);end=max(q[along] for t in tracks for q in t['axis'])
            # S: paired parallel-wall joist webs lie one inch beyond each
            # six-inch wall face. A6.625in holdback clears the nested tracks,
            # leaving actual inward joist flanges beneath the panel edge.
            # An8in holdback would wrongly cut the panel back beyond that ledge.
            half=3.3125
            lo=[start,station-half] if along==0 else [station-half,start]
            size=[end-start,2*half] if along==0 else [2*half,end-start]
            clipped=Polygon([q[:2] for q in panel['vertices']]).intersection(box(*lo,lo[0]+size[0],lo[1]+size[1]))
            for host,z in ((panel,top-1.5),(finish,top)):
                for part,(x0,y0,x1,y1) in enumerate(rectangles(clipped)):
                    oid=f'{host["id"]}-WALL-HOLDBACK-{index}-{part}'
                    opening=dict(id=oid,kind='wall_bearing_holdback',plane='xy',x_ft=x0/12,y_ft=y0/12,
                        z_ft=z/12,width_ft=(x1-x0)/12,height_ft=(y1-y0)/12,level=k,basis='A',confirmed=True,
                        host_id=host['id'],query_id='CFS6-FLOOR-HOLDBACKS',source_wall_ids=[t['id'] for t in tracks],
                        source_requirement='framing/rim-ext-stacked; framing/squash-mid-leg; framing/walls-on-joists; framing/chord-squash-floor')
                    rods=[]
                    for member in b.members:
                        if member['kind']!='hold_down_rod':continue
                        aa,dd=[[v+off for v,off in zip(q,o)] for q,o in zip(member['axis'],member['end_offsets'])]
                        if not min(aa[2],dd[2])<=z<=max(aa[2],dd[2]) or abs(dd[2]-aa[2])<1e-8:continue
                        ratio=(z-aa[2])/(dd[2]-aa[2]);xy=[aa[i]+ratio*(dd[i]-aa[i]) for i in (0,1)]
                        if x0<=xy[0]<=x1 and y0<=xy[1]<=y1:rods.append(member['id'])
                    if rods:opening.update(penetrating_member_ids=sorted(rods),
                        penetration_basis='The floor-layer bearing cutback deliberately passes these actual continuous wall tie rods. It is a material clearance, not an unobstructed architectural opening.')
                    b.openings.append(opening);host.setdefault('openings',[]).append(oid)
        b.changes.append(dict(kind='source_cfs6_floor_layers_and_holdbacks',previous_panel=before,
            subfloor_panel_id=panel['id'],finish_panel_id=finish['id'],wall_strips=len(groups),
            basis='S 23/32 in WSP plus1.5 in gypsum and no finish beneath bearing/shear walls. A exact6.625 in strip width/extent, clipped to the actual L-plan host, and unchanged finished-floor datum. Steel packing, blocks, rims and diaphragm transfers are separately represented.'))
    b.note('FLOOR-HOLDBACKS','S: separate23/32 in WSP and1.5 in gypsum layers, held back beneath every bearing/shear wall. A:6.625 in wide strips follow actual upper-wall lines and retain a panel bearing ledge on inward-facing joist flanges. Each strip is clipped to its real L-plan host. This preserves the accepted finished-floor elevations; any steel bearing packs needed between the framing and the upper tracks remain explicit A components. The source15/32 in diaphragm strength values are retained without reducing the nominal23/32 in subfloor.')
