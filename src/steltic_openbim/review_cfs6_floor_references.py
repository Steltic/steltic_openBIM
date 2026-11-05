"""Use the located source floor hardware once, instead of repeated generic packs."""
import math
from collections import defaultdict
from .review_cfs_occurrences import axis


def apply(model):
    if model['pilot']!='cfs6':return
    members={m['id']:m for m in model['members']};blocks={};attached=defaultdict(list);outer_tracks={}
    for c in model['connections']:
        if c['detail_ref']['id']=='review_source_floor_block':blocks[c['member_ids'][0]]=c
        if c.get('parameters',{}).get('actual_source_floor') or c.get('parameters',{}).get('actual_chord_floor') or c['detail_ref']['id']=='review_double_top_track':
            for mid in c['member_ids']:attached[mid].append(c)
        if c['detail_ref']['id']=='review_double_top_track' and c.get('parameters',{}).get('purpose')=='stitch':
            inner,outer=c['member_ids'];outer_tracks[inner]=outer
    removed={};links=model.setdefault('connection_endpoint_links',[]);updates={}
    for c in model['connections']:
        if c['detail_ref']['id'] not in ('review_cfs_floor','review_cfs_sill','review_cfs_joist','review_final_cfs_joist'):continue
        primary=members[c['member_ids'][0]];options=attached[primary['id']]
        if not options:continue
        data=c.get('parameters',{}).get('physical_floor_stack',{});ids=data.get('block_to_joist_ids',{})
        children=[blocks[mid] for mid in ids if mid in blocks]
        # The old track marker may lie between the new aligned stud stations.
        # Its generic stack then cannot bind, even though the actual short
        # packs already connect that same track to the real floor receivers.
        # Use those explicit member bindings, never a proximity-only substitute.
        if not children and primary['kind'] in ('ordinary_track','top_track','bottom_track'):
            children=[other for other in options if other['detail_ref']['id'] in
                      ('review_source_floor_block','review_chord_floor_pack')]
            # The inner collector is coupled to its outer ply by real web
            # stitches. Bearing blocks sit on that outer ply. Follow only this
            # explicit physical pair, rather than a nearby unrelated track.
            if not children and primary['id'] in outer_tracks:
                children=[other for other in attached[outer_tracks[primary['id']]]
                          if other['detail_ref']['id'] in ('review_source_floor_block','review_chord_floor_pack')]
        if not children:continue
        # Compression-only chord packs do not select floor anchorage screws.
        # Those requirements belong to the actual bound floor/track hardware.
        # Keep the source record as context on the bearing pack, and transfer
        # the active selection only to a real screwed source-floor assembly.
        bearings=[other for other in children if other['detail_ref']['id']=='review_chord_floor_pack']
        hardware=[other for other in children if other['detail_ref']['id']=='review_source_floor_block']
        for other in options:
            if other['detail_ref']['id']=='review_source_floor_block' and other not in hardware:hardware.append(other)
        if not hardware:continue
        children=hardware
        endpoints=[]
        for end,q in enumerate(axis(primary)):
            target=min(options,key=lambda other:math.dist(other['point'],q))
            if math.dist(target['point'],q)>24.01:break
            endpoints.append((end,target))
        if len(endpoints)!=2:continue
        for child in bearings:
            child['source_context_records']=sorted(set(child.get('source_context_records',[])+c['design_record_ids']))
            child.setdefault('source_record_applicability',[]).extend(dict(record_id=rid,application='context_only',
                basis='This scheduled chord pack is a compression-bearing assembly. The floor anchorage screws are on the separately located floor-member/track assemblies bound to the same wall track.') for rid in c['design_record_ids'])
        for child in children:
            child['design_record_ids']=sorted(set(child['design_record_ids']+c['design_record_ids']))
            for field in ('source_record_selections','source_record_applicability'):
                for item in c.get(field,[]):
                    if item not in child.setdefault(field,[]):child[field].append(item)
            child['source_context_records']=sorted(set(child.get('source_context_records',[])+c.get('source_context_records',[])))
            child.setdefault('replaces_generic_floor_ids',[]).append(c['id'])
        for end,target in endpoints:
            link=dict(member_id=primary['id'],end='start' if end==0 else 'end',connection_id=target['id'],
                basis='This actual floor member/track end is served by the nearby located source floor/collector hardware. The former generic floor marker is removed to avoid duplicate bearing packs and fasteners.')
            updates[primary['id'],link['end']]=link
        removed[c['id']]=[child['id'] for child in children]
    if not removed:return
    links[:]=[r for r in links if (r['member_id'],r['end']) not in updates]+list(updates.values())
    remaining={c['id']:c for c in model['connections'] if c['id'] not in removed}
    for link in links:
        if link['connection_id'] not in removed:continue
        options=[remaining[cid] for cid in removed[link['connection_id']] if link['member_id'] in remaining[cid]['member_ids']]
        if not options:raise ValueError('Removed generic floor marker still has an unbound endpoint link')
        member=members[link['member_id']];q=axis(member)[0 if link['end']=='start' else 1]
        link['connection_id']=min(options,key=lambda c:math.dist(c['point'],q))['id']
    model['connections'][:]=list(remaining.values())
    model['changes'].append(dict(kind='located_source_floor_hardware_replaces_generic_markers',replacements=removed,
        basis='Every source block, rim and track attachment remains separately located. Source record/clause links move to those actual assemblies; generic repeated pack/fastener solids are removed only where the primary member has nearby real end attachments.'))
