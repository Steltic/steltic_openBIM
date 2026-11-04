"""Full-width wall anchorage, bound to the actual source wall receiver."""


def prepare(builder):
    members={m['id']:m for m in builder.members}
    for c in builder.connections:
        if c['detail_ref']['id']!='review_plate_base':continue
        wall=members[c['member_ids'][0]]
        profile=builder.profiles[wall['profile_id']]
        if profile['family']!='flat':raise ValueError('Plate wall base needs the actual flat wall profile')
        refs=[r for r in wall.get('design_record_ids',[]) if r.startswith('connections/conn-brace-')]
        if not refs:raise ValueError('Plate wall base needs its source boundary fishplate selection')
        c['design_record_ids']=list(dict.fromkeys(c['design_record_ids']+refs))
        # The saved fictional wall proposal already calls for a nominal 2 in
        # boundary gap. Record its actual bottom cut; analysis worklines remain.
        end=min(range(2),key=lambda i:wall['axis'][i][2])
        previous=list(wall['end_offsets'][end]);offset=list(previous);offset[2]=2
        wall['end_offsets'][end]=offset
        c.setdefault('parameters',{})['plate_base_fit']=dict(bottom_gap_in=2,embed_depth_in=12,
            fishplate_height_in=4,stud_length_in=5,stud_rows=2,stud_pitch_in=6,
            basis='S: full-width 1 x 12 in embed plate, 3/8 x 4 in fishplate and two rows of headed studs at 6 in pitch. A: 2 in wall-bottom clearance, fishplate datum, 5 in stud length and 3 in stud edge margins. Foundation and local-fit capacity remain unverified.')
        for panel in builder.panels:
            if panel['id']!=wall['id']+'-PL':continue
            bottom=min(q[2] for q in panel['vertices'])
            for q in panel['vertices']:
                if abs(q[2]-bottom)<1e-6:q[2]+=2
        builder.changes.append(dict(kind='plate_wall_base_clearance',member_id=wall['id'],connection_id=c['id'],
            previous_end_offset=previous,end_offset=offset,basis=c['parameters']['plate_base_fit']['basis']))


def plate(ctx):
    a,p=ctx.a,ctx.p;wall=ctx.ms[0];profile=p[wall['profile_id']]
    if profile['family']!='flat':raise ValueError('Plate wall base requires a flat source profile')
    width=profile['dimensions']['width'];thickness=profile['dimensions']['thickness']
    fit=ctx.params.get('plate_base_fit')
    if not fit:raise ValueError('Plate wall base needs a recorded actual-wall fit')
    gap=fit['bottom_gap_in'];half=width/2;fish_y=-thickness/2-.375
    a.member('WALL',wall['profile_id'],[0,0,gap],[0,0,12],y=[1,0,0],source_member_index=0,
        description='Actual full-width source steel plate wall; A recorded bottom clearance')
    embed_pid=f'SOURCE-WALL-BASE-EMBED-{width:g}'
    p[embed_pid]=dict(id=embed_pid,family='flat',dimensions=dict(width=width,thickness=1))
    a.member('EMBED',embed_pid,[0,0,-12],[0,0,0],y=[1,0,0],representation_role='assembly_component',
        description='S: full-width 1 x 12 in A572 Grade 50 embedded plate')
    a.box('FISH',[-half,fish_y,0],[width,.375,4],'S size; A datum','Source 3/8 x 4 in boundary fishplate along the full panel')
    a.box('CONC',[-half-6,-18,-20],[width+12,36,20],'A','Mat context; foundation reinforcement and anchorage verification delegated',kind='concrete')
    # The source check is more specific than its component summary: two rows
    # at 6 in, not an interchangeable single row at 3 in. Preserve both.
    per_row=round(width/6)
    if per_row<1 or abs(per_row*6-width)>.001:raise ValueError('Full-width stud run needs an explicit end-spacing proposal')
    xs=[-half+3+6*i for i in range(per_row)]
    points=[[x,-.5,z] for z in (-9,-3) for x in xs];count=len(points)
    a.fastener('STUDS',points,[0,-1,0],.875,fit['stud_length_in'],['EMBED','CONC'],
        f'S: {count} headed studs, 7/8 in diameter, two rows at 6 in pitch (4 per foot); A: 5 in length and 3 in edge margins',
        basis='S diameter, two rows and 6 in pitch; A length and edge margins')
    for i,(x,y,z) in enumerate(points):
        a.weld('WS'+str(i),[x-.4375,y,z],[x+.4375,y,z],['EMBED','STUDS'],kind='STUD_WELD',
            description='Source welded headed stud; symbolic weld line at actual embed-plate face')
    for i,y in enumerate((fish_y,fish_y+.375)):
        a.weld('WF'+str(i),[-half,y,0],[half,y,0],['FISH','EMBED'],.25,
            description='Source two 1/4 in fishplate shop fillets; A top-face attachment datum')
    for i,z in enumerate((gap,4)):
        a.weld('WW'+str(i),[-half,-thickness/2,z],[half,-thickness/2,z],['WALL','FISH'],.1875,
            description='Source 3/16 in field fillets along both lap edges')
    a.section_axis=0;a.section_at=xs[len(xs)//2]
    a.dim([-half,0,-12],[half,0,-12],'Full source panel / embedded plate width',offset=-34)
    a.dim([0,0,-12],[0,0,0],'12 in source embedded plate depth',view='section',offset=34)
    a.dim([0,0,0],[0,0,gap],'A wall bottom clearance',view='section',basis='A',offset=-34)
    a.notes.extend([fit['basis'],
        'The 36 in typical strip is replaced by the entire physical panel width. Stud quantity covers that full width; no hidden multiplier is required.',
        'Source foundation breakout, pullout and mat reinforcement remain the foundation engineer responsibility. Stud length and row datum are accepted fictional fit proposals, not a verified anchorage design.'])
