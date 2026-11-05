"""Use the located source floor hardware once, instead of repeated generic packs."""
import math
from collections import defaultdict
from .review_cfs_occurrences import axis


def apply(model):
    if model['pilot']!='cfs6':return
    members={m['id']:m for m in model['members']};blocks={};attached=defaultdict(list)
    for c in model['connections']:
        if c['detail_ref']['id']=='review_source_floor_block':blocks[c['member_ids'][0]]=c
        if c.get('parameters',{}).get('actual_source_floor') or c['detail_ref']['id']=='review_double_top_track':
            for mid in c['member_ids']:attached[mid].append(c)
    removed={};links=model.setdefault('connection_endpoint_links',[]);updates={}
    for c in model['connections']:
        if c['detail_ref']['id'] not in ('review_cfs_floor','review_cfs_sill','review_cfs_joist','review_final_cfs_joist'):continue
        data=c.get('parameters',{}).get('physical_floor_stack',{});ids=data.get('block_to_joist_ids',{})
        children=[blocks[mid] for mid in ids if mid in blocks]
        if not children:continue
        primary=members[c['member_ids'][0]];options=attached[primary['id']]
        if not options:continue
        endpoints=[]
        for end,q in enumerate(axis(primary)):
            target=min(options,key=lambda other:math.dist(other['point'],q))
            if math.dist(target['point'],q)>24.01:break
            endpoints.append((end,target))
        if len(endpoints)!=2:continue
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
