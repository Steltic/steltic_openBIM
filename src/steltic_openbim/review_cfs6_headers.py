"""Apply the saved six-foot L1 exterior header selection to matching openings."""
from .review_cfs_source_bindings import attach


def apply(b):
    if b.key!='cfs6':return
    rid='framing/header-ext-L1';source=b.records[rid]['data']
    if source['section']!='2 x 800S162-54':raise ValueError('CFS6 header source changed')
    lookup={m['id']:m for m in b.members};changed=[]
    for opening in b.openings:
        if opening['level']!=1 or opening['kind']!='window' or abs(opening['width_ft']-6)>.001:continue
        if opening['plane']!='xz' or abs(opening['y_ft']-152)>.001:continue
        m=lookup['OPEN-'+opening['id']+'-H'];old=m['profile_id'];m['profile_id']=b.profile('2X800S162-54')
        reason='S typical six-foot L1 exterior window header, two 800S162-54 plies. A existing located opening, jamb/support fit and applicability to the fictional wall loads; source six-foot prototype does not certify all adopted openings.'
        attach(b,m,rid,reason)
        for c in b.connections:
            if c['member_ids'][0]==m['id']:
                attach(b,c,rid,reason)
                c.setdefault('parameters',{})['source_header_clip_t']=.0566
        changed.append(dict(member_id=m['id'],previous_profile_id=old,profile_id=m['profile_id'],source_record_id=rid))
    if not changed:raise ValueError('CFS6 has no matching six-foot L1 exterior window')
    b.changes.append(dict(kind='source_cfs6_six_foot_headers',members=changed))
    b.note('L1-WINDOW-HEADERS','S: the located six-foot L1 north exterior windows use the saved two-ply 800S162-54 header and 54 mil clips. A: their actual support geometry and load applicability; the other adopted opening spans retain their explicitly unverified fictional selection. The source prototype is not a capacity approval for every opening.')
