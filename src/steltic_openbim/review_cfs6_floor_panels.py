"""Separate the saved floor layers and keep them out of steel bearing strips."""
import copy
from collections import defaultdict


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
            # six-inch wall face. A: use the same eight-inch holdback on all
            # walls so no finish crosses a bearing strip; edge support and
            # cross-wall shear transfer are separately located components.
            lo=[start,station-4] if along==0 else [station-4,start]
            size=[end-start,8] if along==0 else [8,end-start]
            for host,z in ((panel,top-1.5),(finish,top)):
                oid=f'{host["id"]}-WALL-HOLDBACK-{index}'
                opening=dict(id=oid,kind='wall_bearing_holdback',plane='xy',x_ft=lo[0]/12,y_ft=lo[1]/12,
                    z_ft=z/12,width_ft=size[0]/12,height_ft=size[1]/12,level=k,basis='A',confirmed=True,
                    host_id=host['id'],query_id='CFS6-FLOOR-HOLDBACKS',source_wall_ids=[t['id'] for t in tracks],
                    source_requirement='framing/rim-ext-stacked; framing/squash-mid-leg; framing/walls-on-joists; framing/chord-squash-floor')
                b.openings.append(opening);host.setdefault('openings',[]).append(oid)
        b.changes.append(dict(kind='source_cfs6_floor_layers_and_holdbacks',previous_panel=before,
            subfloor_panel_id=panel['id'],finish_panel_id=finish['id'],wall_strips=len(groups),
            basis='S 23/32 in WSP plus1.5 in gypsum and no finish beneath bearing/shear walls. A exact8 in strip width/extent and unchanged finished-floor datum. Steel packing, blocks, rims and diaphragm transfers are separately represented.'))
    b.note('FLOOR-HOLDBACKS','S: separate23/32 in WSP and1.5 in gypsum layers, held back beneath every bearing/shear wall. A:8 in wide strips follow actual upper-wall lines. This preserves the accepted finished-floor elevations; any steel bearing packs needed between the framing and the upper tracks remain explicit A components. The source15/32 in diaphragm strength values are retained without reducing the physical23/32 in subfloor.')
