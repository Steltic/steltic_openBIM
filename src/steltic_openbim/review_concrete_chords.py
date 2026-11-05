"""CFS4's two source #4 edge chords, with explicit unverified set-out.

Continuous, contact-lapped straight runs follow each slab edge. Orthogonal
ends are shown with their real concrete bond; no welded or bent corner is
silently invented. This design representation is not a bar-bending schedule.
"""
from .review_concrete_collectors import stock_runs,openings_on_line


def apply(b):
    if b.key!='cfs4':return
    rid='diaphragms/diaphragm-floors';selection=b.records[rid]['data']['selection']
    if 'continuous chord bars (2 #4 Gr 60, lap-spliced)' not in selection:
        raise ValueError('Unrecognized source perimeter chord selection')
    pid=b.custom('REBAR-4','round',dict(d=.5),basis='S source #4 nominal diameter; ribs omitted')
    for panel in (p for p in b.panels if p['kind']=='floor'):
        level=panel['level'];top=panel['vertices'][0][2]
        lo=[min(q[i] for q in panel['vertices']) for i in (0,1)]
        hi=[max(q[i] for q in panel['vertices']) for i in (0,1)]
        ends={};rows=[]
        for along in (0,1):
            across=1-along
            for side in (0,1):
                inward=1 if side==0 else -1
                edge=lo[across] if side==0 else hi[across]
                for index,inset in enumerate((1.25,2.)):
                    made=[]
                    for piece,(start,end) in enumerate(stock_runs(lo[along]+3,hi[along]-3,240,20)):
                        station=edge+inward*(inset+(-.25 if piece%2==0 else .25))
                        z=top-.5-along*.5
                        if openings_on_line(b,panel,along,station,start,end,.25):
                            raise ValueError('Perimeter chord requires an explicit route around a floor void')
                        a=[start,station,z] if along==0 else [station,start,z]
                        d=[end,station,z] if along==0 else [station,end,z]
                        mid=f'EDGE-CHORD-L{level}-{along}-{side}-B{index+1}-P{piece+1}'
                        m=b.member(mid,pid,'diaphragm_chord_bar',a,d,level,'S size/count/grade; A fit',
                            host_panel_id=panel['id'],
                            source_context_record_ids=[rid],source_selection=selection,
                            chord_edge=[along,side],source_bar_index=index+1,source_bar_count=2,
                            engineering_status='not_verified',
                            geometry_basis='A 20 ft maximum stock, 20 in contact laps, 3 in end margins; edge line centres1.25/2 in, staggered0.25 in for touching laps; X/Y centres0.5/1 in below topping top. Cover, congestion and development require verification.')
                        m['material_id']='CFS4-REBAR-GR60';made.append(m);rows.append(m['id'])
                        c=b.connection(mid+':BOND','review_collector_bond',[(x+y)/2 for x,y in zip(a,d)],[m],
                            parameters=dict(host_panel_id=panel['id'],slab_top_in=top,topping_in=2.5,
                                reinforcement_label='Source #4 perimeter chord',
                                reinforcement_note='S: two #4 Gr60 continuous lap-spliced bars along this slab edge. A: straight stock pieces, 20 in contact laps, locations and layers. Shown cover and development are unverified; no corner hook, weld or supplier approval is inferred.'),
                            title='SOURCE EDGE CHORD / A BOND AND COVER FIT')
                        for end_name in ('start','end'):
                            b.endpoint_links.append(dict(member_id=mid,end=end_name,connection_id=c['id'],
                                basis='Actual chord end embedded in its source topping; contact laps are separately located. End development and corner force transfer are unverified.'))
                    for left,right in zip(made,made[1:]):
                        b.connection(left['id']+':LAP','review_collector_lap',
                            [(x+y)/2 for x,y in zip(left['axis'][1],right['axis'][0])],[left,right],
                            parameters=dict(host_panel_id=panel['id'],slab_top_in=top,topping_in=2.5,lap_in=20,
                                reinforcement_label='Source #4 edge chord',reinforcement_note='S two #4 Gr60 edge chord bars. A20 in contact lap, stock lengths and set-out. No development or cover approval.'),
                            title='SOURCE EDGE CHORD / A CONTACT LAP')
                    ends[along,side,index]=[made[0],made[-1]]
        for xside in (0,1):
            for yside in (0,1):
                ms=[ends[0,yside,i][xside] for i in (0,1)]+[ends[1,xside,i][yside] for i in (0,1)]
                q=[lo[0] if xside==0 else hi[0],lo[1] if yside==0 else hi[1],top]
                b.connection(f'EDGE-CORNER-L{level}-{xside}-{yside}','review_collector_bond',q,ms,
                    parameters=dict(host_panel_id=panel['id'],slab_top_in=top,topping_in=2.5,context_extent_in=30,
                        reinforcement_label='Orthogonal source edge chords',
                        reinforcement_note='S two #4 Gr60 bars along each edge, continuous through their located straight laps. A orthogonal end set-out in separate layers; each run develops through its actual concrete host. No welded intersection or bent-bar continuation is claimed. Corner anchorage, force transfer, cover and development remain unverified.'),
                    title='EDGE CHORD CORNER / A STRAIGHT-END BOND')
        panel['perimeter_chord_design']=dict(source_context_record_id=rid,bar_ids=rows,
            bars_per_edge=2,diameter_in=.5,grade='Gr60',lap_in=20,
            corner_basis='A separate straight edge runs with actual embedded ends; no welded or bent corner assumed',
            engineering_status='not_verified')
        b.changes.append(dict(kind='source_perimeter_chord_bars',host_panel_id=panel['id'],member_ids=rows,
            basis='S two #4 Gr60 continuous, lap-spliced edge chords. A exact straight pieces, contact laps, end development geometry and shallow-topping layer fit; no capacity or bar-fabrication certification.'))
    b.note('PERIMETER-CHORDS','S: two #4 Gr60 continuous lap-spliced chord bars along each concrete floor edge. A: 20 ft maximum pieces, 20 in contact laps, 3 in end margins and explicit staggered/layered set-out. The tight2.5 in topping and its shown cover require engineering review. Orthogonal end runs have explicit concrete bond; no corner weld, hidden hook or bent continuation is invented. Deck attachments are detailed separately.')
