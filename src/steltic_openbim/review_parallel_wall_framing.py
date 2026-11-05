"""Physical joist pairs selected beneath parallel wall lines in saved examples.

Source sections and transverse set-out are retained; longitudinal endpoints
come from the adjacent real floor span. Block packs and force-transfer details
remain separately required, so this step does not bind the complete wall check.
"""
import copy,re


SCOPES={
    'cfs1':('framing/walls-on-joists-N-S',{'W','E','P32','P64','P96','P128'}),
    'cfs6':('framing/walls-on-joists',{'XSB','XLP1','XLP2','X90','XN','Y0','YLE','P30','P60','P90','P120','P150','P180'}),
    'cfs11':('framing/walls-on-joists-XB70-XB96',{'XB70','XB96'}),
    'cfs14':('framing/walls-on-joists-Y',{'WS','WN','C1S','C1N','C2S','C2N','ES','EN'}),
}


def apply(b):
    if b.key not in SCOPES:return
    rid,lines=SCOPES[b.key];source=b.records[rid]['data'];text=source['section']
    hit=re.search(r'a pair of (\d{3,4}S\d{3}-\d+) joists, flanges pointing inward, webs 1 in. outside each wall face',text)
    if not hit:raise ValueError('Parallel-wall source joist-pair selection changed')
    pid=b.profile(hit[1]);dim=b.profiles[pid]['dimensions'];offset=4-dim['t']/2
    roof=max(w['level'] for w in b.walls);existing=[m for m in b.members if m['kind']=='joist'];added=set()
    for wall in b.walls:
        k=wall['level'];line=wall['line']
        if line not in lines or k>=roof:continue
        along=0 if wall['direction']=='X' else 1;normal=1-along
        for position in sorted({r['position_in'] for r in wall['runs']}):
            tracks=[m for m in b.members if m['kind'] in ('top_track','ordinary_track') and m['level']==k
                and m['local_y'][2]<-.99 and all(abs(q[normal]-position)<.001 for q in m['axis'])]
            candidates=[m for m in existing if m['level']==k and abs(m['axis'][1][normal]-m['axis'][0][normal])<.001
                and abs(m['axis'][0][normal]-position)<=16.001]
            spans={}
            for m in candidates:
                lo,hi=sorted(q[along] for q in m['axis'])
                if not any(min(hi,max(q[along] for q in t['axis']))-max(lo,min(q[along] for q in t['axis']))>1 for t in tracks):continue
                span=(lo,hi,m['axis'][0][2]);old=spans.get(span)
                if old is None or abs(m['axis'][0][normal]-position)<abs(old['axis'][0][normal]-position):spans[span]=m
            for (lo,hi,z),reference in sorted(spans.items()):
                key=(k,along,position,lo,hi,z)
                if key in added:continue
                # A shorter corridor joist and a selected deeper wall-line
                # pair share the actual top-of-steel floor surface, not their
                # centreline. Keep the depth difference explicit in the fit.
                z+=(b.depth(reference['profile_id'])-b.depth(pid))/2
                added.add(key)
                for sign in (-1,1):
                    aa=[0.,0.,z];bb=aa.copy();aa[along]=lo;bb[along]=hi;aa[normal]=bb[normal]=position+sign*offset
                    y=[0.,0.,0.];y[normal]=-sign
                    label=f'PAIR-J-{line}-L{k}-{lo:g}-{hi:g}-{sign}'
                    m=b.member(label,pid,'joist',aa,bb,k,'S',local_y=y,source_context_records=[rid],
                        parallel_wall_line=line,parallel_wall_axis_in=position,
                        physical_fit_basis='S: two inward-facing source joists, outer web faces 1 in beyond the 6 in wall. A: span endpoints from the adjacent physical floor joist; no new capacity check.')
                    b.ends(m,'review_cfs_joist',[],parameters=dict(spacing=16,source_wall_pair=True))
                    b.changes.append(dict(kind='source_parallel_wall_joist_pair',member_id=m['id'],source_record_id=rid,
                        reference_span_member_id=reference['id'],axis=copy.deepcopy(m['axis']),basis=m['physical_fit_basis']))
    b.note('SOURCE-PARALLEL-WALL-JOISTS','S: actual paired joists beneath the explicitly named parallel wall lines, flanges inward and outer web faces 8 in apart. A: longitudinal support spans follow adjacent floor framing. Source squash blocks, interruptions at chord packs, subfloor holdbacks and diaphragm attachments are separate physical requirements; a pair alone does not satisfy the full source wall/floor check.')
