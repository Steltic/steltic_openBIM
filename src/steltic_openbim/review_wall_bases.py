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
    from .pilots.model import dot,sub
    a,p=ctx.a,ctx.p;wall=ctx.ms[0];profile=p[wall['profile_id']]
    a.title='SPSW HALF-PANELS / CONTINUOUS EMBEDDED BASE'
    if profile['family']!='flat':raise ValueError('Plate wall base requires a flat source profile')
    width=profile['dimensions']['width'];thickness=profile['dimensions']['thickness']
    fit=ctx.params.get('plate_base_fit')
    if not fit:raise ValueError('Plate wall base needs a recorded actual-wall fit')
    gap=fit['bottom_gap_in'];half=width/2;fish_y=-thickness/2-.375
    embed_width=fit.get('embed_width_in',width);embed_offset=fit.get('embed_offset_in',0)
    embed_half=embed_width/2
    fields=[]
    for i,field in enumerate(ctx.ms):
        fw=p[field['profile_id']]['dimensions']['width'];shift=dot(sub(field['axis'][0],ctx.c['point']),wall['local_y'])
        name='WALL' if len(ctx.ms)==1 else 'WALL'+str(i+1)
        fields.append((name,shift-fw/2,shift+fw/2))
        a.member(name,field['profile_id'],[shift,0,gap],[shift,0,12],y=[1,0,0],basis=field['basis'],source_member_index=i,
            description='Actual source half-panel; A recorded bottom clearance')
    embed_pid=f'SOURCE-WALL-BASE-EMBED-{embed_width:g}'
    p[embed_pid]=dict(id=embed_pid,family='flat',dimensions=dict(width=embed_width,thickness=1))
    a.member('EMBED',embed_pid,[embed_offset,0,-12],[embed_offset,0,0],y=[1,0,0],representation_role='assembly_component',
        description='S: full-width 1 x 12 in A572 Grade 50 embedded plate')
    a.box('CONC',[embed_offset-embed_half-6,-18,-20],[embed_width+12,36,20],'A','Mat context; foundation reinforcement and anchorage verification delegated',kind='concrete')
    # The source check is more specific than its component summary: two rows
    # at 6 in, not an interchangeable single row at 3 in. Preserve both.
    per_row=round(embed_width/6)
    if per_row<1 or abs(per_row*6-embed_width)>.001:raise ValueError('Full-width stud run needs an explicit end-spacing proposal')
    xs=[embed_offset-embed_half+3+6*i for i in range(per_row)]
    points=[[x,-.5,z] for z in (-9,-3) for x in xs];count=len(points)
    a.fastener('STUDS',points,[0,-1,0],.875,fit['stud_length_in'],['EMBED','CONC'],
        f'S: {count} headed studs, 7/8 in diameter, two rows at 6 in pitch (4 per foot); A: 5 in length and 3 in edge margins',
        basis='S diameter, two rows and 6 in pitch; A length and edge margins')
    for i,(x,y,z) in enumerate(points):
        a.weld('WS'+str(i),[x-.4375,y,z],[x+.4375,y,z],['EMBED','STUDS'],kind='STUD_WELD',
            description='Source welded headed stud; symbolic weld line at actual embed-plate face')
    for j,(name,left,right) in enumerate(fields):
        fish='FISH' if len(fields)==1 else 'FISH'+str(j+1)
        a.box(fish,[left,fish_y,0],[right-left,.375,4],'S size; A datum','Source 3/8 x 4 in boundary fishplate along this half-panel')
        for i,y in enumerate((fish_y,fish_y+.375)):
            a.weld('WF'+str(j)+'-'+str(i),[left,y,0],[right,y,0],[fish,'EMBED'],.25,
                description='Source two 1/4 in fishplate shop fillets; A top-face attachment datum')
        for i,z in enumerate((gap,4)):
            a.weld('WW'+str(j)+'-'+str(i),[left,-thickness/2,z],[right,-thickness/2,z],[name,fish],.1875,
                description='Source 3/16 in field fillets along both lap edges')
        if abs(embed_width-(right-left))>.001:a.dim([left,0,gap],[right,0,gap],'A clear field plate width',basis='A',offset=36)
    a.section_axis=0;a.section_at=xs[len(xs)//2]
    a.dim([embed_offset-embed_half,0,-12],[embed_offset+embed_half,0,-12],'Source gross bay / embedded plate width',offset=-34)
    a.dim([0,0,-12],[0,0,0],'12 in source embedded plate depth',view='section',offset=34)
    a.dim([0,0,0],[0,0,gap],'A wall bottom clearance',view='section',basis='A',offset=-34)
    a.notes.extend([fit['basis'],
        'One continuous embedded plate runs across the original gross bay beneath both half-panels. Stud quantity covers that full width once; no duplicate anchorage or hidden multiplier is required.',
        'Source foundation breakout, pullout and mat reinforcement remain the foundation engineer responsibility. Stud length and row datum are accepted fictional fit proposals, not a verified anchorage design.'])
