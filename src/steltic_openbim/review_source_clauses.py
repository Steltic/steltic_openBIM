"""Apply exact base/floor schedule clauses after actual tracks are bound."""
from .bim_record_clauses import clauses


def apply(model,package):
    records={r['id']:r for r in package['design_records']};members={m['id']:m for m in model['members']}
    for c in model['connections']:
        tracks=[members[mid] for mid in c['member_ids'] if members[mid]['kind'] in ('bottom_track','ordinary_track','tier_track') and members[mid]['local_y'][2]>.9]
        if not tracks:continue
        for rid in c['design_record_ids']:
            data=records[rid]['data']
            for field in ('components','selection'):
                options=clauses(data.get(field))
                if not options:continue
                track=min(tracks,key=lambda m:abs(m['axis'][0][2]-c['point'][2]));level=track['level'];label='base' if level==1 else 'floors'
                selection=dict(record_id=rid,field=field,clause=label,text=options[label],level=level,basis='Exact labelled source schedule at the actual bound bottom-track storey')
                c['source_record_selections']=[s for s in c.get('source_record_selections',[]) if s['record_id']!=rid]+[selection]
