"""Apply exact base/floor schedule clauses after actual tracks are bound."""
from .bim_record_clauses import clauses


def apply(model,package):
    records={r['id']:r for r in package['design_records']};members={m['id']:m for m in model['members']}
    for c in model['connections']:
        tracks=[members[mid] for mid in c['member_ids'] if members[mid]['kind'] in ('bottom_track','ordinary_track','tier_track') and members[mid]['local_y'][2]>.9]
        if not tracks:continue
        track=min(tracks,key=lambda m:abs(m['axis'][0][2]-c['point'][2]));level=track['level']
        for rid in list(c['design_record_ids']):
            data=records[rid]['data']
            # Some schedules have a separate, expressly story-1 foundation
            # record. Retain it as context above the podium, rather than making
            # upper-floor sheet connections incorrectly select cast-in anchors.
            # Unlabelled and mixed base/floor schedules remain untouched.
            explicit_base=(records[rid].get('table')=='anchorage' and data.get('story')==1
                           and 'base story' in data.get('basis','').lower()
                           and not any(clauses(data.get(field)) for field in ('components','selection')))
            if c['detail_ref']['id']=='review_cfs_sill' and level>1 and explicit_base:
                c['design_record_ids'].remove(rid)
                c['source_context_records']=sorted(set(c.get('source_context_records',[])+[rid]))
                c.setdefault('source_record_applicability',[]).append(dict(record_id=rid,
                    actual_level=level,source_story=1,application='context_only',
                    basis='The immutable anchorage record explicitly selects the base story. This occurrence is an upper-floor bottom track; its floor-transfer selection governs.'))
                continue
            for field in ('components','selection'):
                options=clauses(data.get(field))
                if not options:continue
                label='base' if level==1 else 'floors'
                selection=dict(record_id=rid,field=field,clause=label,text=options[label],level=level,basis='Exact labelled source schedule at the actual bound bottom-track storey')
                c['source_record_selections']=[s for s in c.get('source_record_selections',[]) if s['record_id']!=rid]+[selection]
