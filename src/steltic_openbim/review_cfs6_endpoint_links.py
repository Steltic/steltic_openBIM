"""Identify nearby real attachments serving cut ends after floor/roof fitting."""
import math
from collections import defaultdict
from .review_cfs_occurrences import axis


def apply(b):
    if b.key!='cfs6':return
    links=b.endpoint_links;linked={(r['member_id'],r['end']) for r in links};bound=defaultdict(list)
    for c in b.connections:
        for mid in c['member_ids']:bound[mid].append(c)
    for m in b.members:
        if m['kind']=='joist':
            families={'review_source_floor_block','review_source_floor_rim','review_chord_floor_clip','review_cfs_joist'};limit=8
            basis='This actual cut joist end is served by its own located rim, tight squash-block/track or chord-pack attachment; no remote member substitutes for it.'
        elif m['kind'] in ('ordinary_track','top_track','bottom_track','tier_track'):
            families={'cfs_stud','review_double_top_track','review_track_corner','review_source_floor_block'};limit=24
            basis='The unloaded cut track end projects only to its nearby actual stud, nested-ply stitch or source floor attachment. The link identifies that hardware; it does not invent a joint between adjacent wall lines.'
        else:continue
        options=[c for c in bound[m['id']] if c['detail_ref']['id'] in families]
        if not options:continue
        for end,q in zip(('start','end'),axis(m)):
            if (m['id'],end) in linked:continue
            chosen=min(options,key=lambda c:math.dist(c['point'],q));distance=math.dist(chosen['point'],q)
            if distance>limit:continue
            links.append(dict(member_id=m['id'],end=end,connection_id=chosen['id'],basis=basis+f' Actual distance {distance:.4f} in.'))
            linked.add((m['id'],end))


def bind(model):
    """Use the final receiver bindings made during detail preparation."""
    if model.get('pilot')!='cfs6':return
    from types import SimpleNamespace
    apply(SimpleNamespace(key=model['pilot'],members=model['members'],connections=model['connections'],
                          endpoint_links=model.setdefault('connection_endpoint_links',[])))
