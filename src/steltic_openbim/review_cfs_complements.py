"""Carry ancillary source load paths into explicit drawing occurrences."""
import math

def apply(b):
    lookup={m['id']:m for m in b.members};top=max(m['level'] for m in b.members)
    def append(c,short):
        rid=b.record('connections',short)
        if rid and rid not in c['design_record_ids']:c['design_record_ids'].append(rid);b.used_records.add(rid)
    for c in b.connections:
        family=c['detail_ref']['id'];m=lookup[c['member_ids'][0]];k=m['level']
        if family in ('review_cfs_floor','review_cfs_sill','review_cfs_joist'):
            for name in ('conn-track-bearing-slab','conn-joist-bearing','conn-uplift-floor-straps','diaphragm-across-walls'):append(c,name)
            if b.key=='cfs13':
                line=m['id'].split('-L')[0];append(c,'anch-typeII-'+line)
            if b.key=='cfs14':
                line=m['id'].split('-L')[0]
                append(c,'conn-strap-track-X-'+line)
                if line=='M' and k==2:append(c,'conn-split-line-M-L1')
            if b.key=='cfs29':append(c,'conn-top-track-collector')
            if m['id'].startswith('WALKJOIST'):append(c,'conn-walkway-ledger')
        if family=='review_roof_seat':
            append(c,'conn-uplift-roof-truss' if b.key=='cfs3' else 'conn-truss-uplift')
            if b.key=='hr33':append(c,'conn-joist-seat-uplift')
        if family=='review_cfs_joist' and k==top:append(c,'conn-uplift-roof-joist')
        if family=='review_cfs_strap' and b.key=='cfs29':append(c,'conn-strap-end')
        if family=='test_wall_opening':append(c,'conn-header-jamb')
    # Pack stitching and uplift across a floor are discrete details, not just notes.
    for m in list(b.members):
        if m['kind']=='chord' and b.profiles[m['profile_id']]['family']=='built_up':
            rid=b.record('connections','conn-chord-pack')
            if rid:b.connection(m['id']+'-PACK','review_pack_stitch',m['axis'][0],[m],[rid])
        if m['kind']=='stud' and m['id'].startswith('ORD'):
            rid=b.record('connections','conn-uplift-foundation' if m['level']==1 else 'conn-uplift-floor-straps')
            if rid:b.connection(m['id']+'-UPLIFT','review_floor_strap',m['axis'][0],[m],[rid],parameters={'foundation':m['level']==1})
    if b.key=='cfs14':
        # The two lower post segments are one source HSS through the walkout floor.
        posts=[m for m in b.members if m['kind']=='chord' and m['profile_id'].startswith('HSS')]
        removed=set()
        for low in posts:
            if low['level']!=1:continue
            high=next((m for m in posts if m['level']==2 and math.dist(m['axis'][0][:2],low['axis'][0][:2])<.1),None)
            if not high:continue
            point=low['axis'][1].copy();low['axis'][1]=high['axis'][1];removed.add(high['id'])
            for c in b.connections:
                if high['id'] in c['member_ids']:c['member_ids']=[low['id'] if i==high['id'] else i for i in c['member_ids']]
            b.connections[:]=[c for c in b.connections if not (c['detail_ref']['id']=='review_cfs_post' and low['id'] in c['member_ids'] and abs(c['point'][2]-point[2])<1)]
            line=low['id'].split('-L')[0];b.connection(low['id']+'-COLLECTOR','review_post_collector',point,[low],[b.record('connections','conn-post-collector-L1'),b.record('connections','conn-split-line-M-L1')],parameters={'screws':14 if line=='S' else 4})
        b.members[:]=[m for m in b.members if m['id'] not in removed]
    if b.key=='cfs11':
        for m in list(b.members):
            if m['kind']=='hold_down_rod' and m['level']==2 and m['id'].startswith(('P80-','P93-')):
                b.connection(m['id']+'-TRANSFER','review_rod_transfer',m['axis'][0],[m],[b.record('connections','conn-rod-girder')])
        from .review_hr import nearest
        for c in list(b.connections):
            if c['detail_ref']['id']!='review_roof_seat':continue
            host=nearest(b,c['point'],('walkway_edge_beam',))
            if host and host['profile_id']=='W8X18':
                c['detail_ref']['id']='review_roof_edge';c['member_ids'].append(host['id']);append(c,'conn-truss-edge-beam')
            append(c,'conn-roof-sheathing-uplift');append(c,'conn-roof-to-walls')
    if b.key=='cfs13':
        for c in b.connections:
            if c['detail_ref']['id'] in ('review_cfs_floor','review_cfs_sill') and c['member_ids'][0].startswith('S130-L4'):append(c,'conn-roof-step-S130')
            if c['detail_ref']['id']=='review_cfs_joist' and lookup[c['member_ids'][0]]['level']==3 and c['point'][0]>=1560:append(c,'conn-lowroof-uplift');c.setdefault('parameters',{}).update(clip=True,screws=2,screw_size=10)
    if b.key=='cfs14':
        for m in b.members:
            if m['kind']=='chord' and m['profile_id'].startswith('HSS') and m['id'].startswith(('C1S','C2S')):
                b.connection(m['id']+'-EDGE','review_post_edge',m['axis'][0],[m],[b.record('connections','conn-edge-stud-post')])
