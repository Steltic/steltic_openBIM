"""Saved SPSW collector selections and applicability of unused splice checks."""


def collectors(b):
    if b.key!='hr9':return
    scopes=[('X-B',0,336,[(0,336),(672,1344),(1680,2016)],12),
            ('X-D',0,1008,[(1008,1344)],12),
            ('Y-3',1,672,[(336,1344)],13),('Y-5',1,1344,[(336,1344)],13),
            ('Y-4',1,1008,[(0,672)],12)]
    for line,along,station,intervals,last in scopes:
        rid='members/collector-'+line
        if b.records[rid]['data']['inputs']['section']!='W24X68':raise ValueError('HR9 source collector selection changed')
        for m in b.members:
            if m['kind'] not in ('beam','girder','moment_beam') or not 1<=m['level']<=last:continue
            if not all(abs(q[1-along]-station)<.001 for q in m['axis']):continue
            lo,hi=sorted(q[along] for q in m['axis'])
            if hi-lo<.01 or not any(lo>=a-.001 and hi<=z+.001 for a,z in intervals):continue
            # The level-12 PXB transfer HBE has its own capacity-limited axial
            # selection; the source explicitly excludes it from W24X68 sizing.
            if line=='X-B' and m['level']==12 and lo>=672 and hi<=1344:continue
            before=m['profile_id']
            if before not in ('W24X55','W24X68','W16X31'):raise ValueError('Unexpected HR9 collector source section '+before)
            m['profile_id']=b.profile('W24X68');m['source_collector_line']=line
            if before!='W24X68':
                m['analysis_profile_id']=before
                m['source_context_records']=list(m['design_record_ids'])
                m['design_record_ids']=[rid]
                b.changes.append(dict(kind='gold_local_member_selection',member_id=m['id'],analysis_profile_id=before,
                    physical_profile_id='W24X68',record_id=rid,basis='S: explicit final collector design selects W24X68 at every level of this named line; saved generic analysis section remains unchanged.'))
            elif rid not in m['design_record_ids']:m['design_record_ids'].append(rid)
            b.used_records.add(rid)


def splice_scope(b):
    if b.key!='hr9':return
    lookup={m['id']:m for m in b.members}
    for pid in ('BOX34X34X2.5','BOX38X38X4','W14X193'):
        rid='connections/conn-lateral_col-'+pid
        actual=[m for m in b.members if m['kind']=='column' and m['profile_id']==pid]
        same=[c for c in b.connections if 'splice' in c['detail_ref']['id'] and len(c['member_ids'])>=2
            and all(lookup[i]['profile_id']==pid for i in c['member_ids'][:2])]
        if not actual or same:raise ValueError('HR9 unused equal-section splice disposition no longer applies')
        reason=('Retained gold equal-section '+pid+' splice check. The accepted physical column pieces run continuously through the same-section story boundary; '
                'their first field splice joins a different upper section and is covered by that transition selection. No equal-section field splice exists in this adopted piece schedule.')
        b.record_dispositions=getattr(b,'record_dispositions',[])+[dict(record_id=rid,status='not_applicable',reason=reason,evidence_member_ids=[m['id'] for m in actual])]
        b.note('UNUSED-SPLICE-'+pid,reason)
    for pid in ('W14X211','W14X283'):
        rid='connections/conn-lateral_col-'+pid
        if 'no field splice' not in b.records[rid]['data'].get('components',''):raise ValueError('HR9 post continuity selection changed')
        posts=[m for m in b.members if m['kind']=='rocking_post' and m['profile_id']==pid]
        if not posts:raise ValueError('Missing HR9 source one-piece posts')
        for m in posts:m['design_record_ids'].append(rid)
        b.used_records.add(rid)
