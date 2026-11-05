"""Located SBMF chord hold-downs; source hardware and explicit adopted fit."""
import copy
from .pilots.model import cross, dot, sub
from .review_receiver_geometry import extract
from .review_sbmf_girts import cross_section
from .review_cfs_source_bindings import attach


def apply(b):
    if b.key not in ('cfs10', 'cfs18'):
        return
    lookup = {m['id']: m for m in b.members}
    shifted = {}
    for c in list(b.connections):
        if c['detail_ref']['id'] != 'review_sbmf_hold_down':
            continue
        chord, rod = [lookup[mid] for mid in c['member_ids'][:2]]
        par = c['parameters']; continuous = par['continuous']
        u = chord['local_y']; offset = [1.5*q for q in u]
        old = copy.deepcopy(rod['axis'])
        for point in rod['axis']:
            for i in range(3):
                point[i] += offset[i]
        shifted[rod['id']] = offset
        par['actual_sbmf_hold_down'] = True
        par['rod_offset_in'] = 1.5
        if continuous:
            # These are cast base anchors, not continuous 24ft tie rods.
            rod['axis'][0][2] = -12
            rod['axis'][1][2] = 2.5
            for end in ('start', 'end'):
                b.endpoint_links.append(dict(member_id=rod['id'], end=end,
                    connection_id=c['id'], basis='The actual short cast anchor terminates in the drawn base plate/nut and bracket take-up; embedment is adopted foundation geometry.'))
            b.endpoint_links.append(dict(member_id=chord['id'], end='start',
                connection_id=c['id'], basis='Actual continuous chord foot is attached by its own source four-bolt bent-plate hold-down.'))
        else:
            b.endpoint_links.append(dict(member_id=chord['id'], end='end',
                connection_id=c['id'], basis='Actual chord head is attached to its own located adopted take-up bracket and source story rod.'))
            if chord['level'] == 1:
                rod['axis'][0][2] = -12
                f = b.connection(rod['id']+'-FOUNDATION', 'review_sbmf_rod_foundation',
                    list(rod['axis'][0]), [rod], parameters=dict(actual_sbmf_hold_down=True),
                    basis='A: adopted embedded end plate and nut; foundation capacity remains delegated')
                f['source_context_records'] = list(c['design_record_ids'])
                b.endpoint_links.append(dict(member_id=rod['id'], end='start', connection_id=f['id'],
                    basis='Actual source-sized story rod reaches its own adopted embedded plate and nut.'))
            if chord['level'] == 2:
                b.endpoint_links.append(dict(member_id=rod['id'], end='end', connection_id=c['id'],
                    basis='Actual top rod projection terminates above this head bracket and take-up nut.'))
        prefix = 'chord-north-wall' if continuous and b.key == 'cfs10' else 'chord-side-wall' if continuous else ('office' if b.key == 'cfs10' else 'mezz')+'-chord-s'+str(chord['level'])
        attach(b, chord, b.record('chords', prefix), 'Exact source chord section and story; physical bracket and rod offset are separate adopted fit inputs.')
        b.changes.append(dict(kind='sbmf_located_hold_down_rod', member_id=rod['id'],
            previous_axis=old, axis=copy.deepcopy(rod['axis']),
            basis='S rod diameter. A 1.5in offset into one chord cavity, avoiding the paired-web gap; 12in foundation depth and take-up geometry unverified. Continuous main-wall source anchor is short, not a full-height rod.'))
    for c in b.connections:
        if c['detail_ref']['id'] != 'review_rod_coupler':
            continue
        offsets = [shifted[mid] for mid in c['member_ids'] if mid in shifted]
        if offsets:
            assert len(offsets) == 2 and offsets[0] == offsets[1]
            c['point'] = [q+v for q,v in zip(c['point'], offsets[0])]
    b.note('SBMF-HOLD-DOWN-FIT', 'S: source continuous-wall 3/8in bent bracket, four 3/4in A325 web bolts, and saved story/anchor rod diameters. A: actual 1.5in rod offset within a channel cavity, bracket outline, bolt set-out, solid web pack, supplier take-up envelope and embedded plate geometry. Main-wall cast anchors terminate at their bases; wing rods retain the located floor couplers. These fit inputs do not establish bracket, foundation or modified chord capacity.')


def foundation(a, rod_label, centre, dia, base_z):
    x,y = centre
    a.box('ANCHOR-PL', [x-2,y-2,base_z+1], [4,4,.5], 'A', 'A embedded 4x4x1/2in plate; source rod diameter')
    a.cylinder('ANCHOR-NUT', [x,y,base_z+.25], [0,0,1], dia*1.8, .75, 'A', 'A embedded heavy-nut envelope')
    a.interfaces.append(dict(id='ANCHOR-BEARING', kind='thread_bearing',
        connects=[rod_label,'ANCHOR-PL','ANCHOR-NUT'], basis='A',
        description='Actual rod, threaded nut and embedded bearing plate; no welded rod. Foundation resistance is delegated.'))


def draw(ctx):
    a,p,par = ctx.a,ctx.p,ctx.params
    if ctx.family == 'review_sbmf_rod_foundation':
        rod = ctx.ms[0]; axes=([1,0,0],[0,1,0],[0,0,1])
        extract(ctx, rod, 'ROD', axes, 20)
        dia=p[rod['profile_id']]['dimensions']['d']
        foundation(a, 'ROD', [0,0], dia, 0)
        a.box('CONC', [-12,-12,0], [24,24,12], 'A', 'A foundation context, not a foundation design', kind='concrete')
        a.section_axis=2; a.section_at=1.25
        return
    chord,rod = ctx.ms[:2]; u=chord['local_y']; axes=(u,cross([0,0,1],u),[0,0,1])
    extract(ctx, chord, 'CHORD', axes, 24)
    extract(ctx, rod, 'ROD', axes, 24)
    polys=cross_section(chord,p,axes); webs=[]
    for poly in polys:
        lo,hi=min(q[0] for q in poly),max(q[0] for q in poly)
        if .001<hi-lo<.5 and max(q[1] for q in poly)-min(q[1] for q in poly)>4:
            webs.append((lo,hi))
    assert len(webs)==2
    webs.sort(); left,right=webs[0][0],webs[-1][1]; gap=(webs[0][1],webs[-1][0])
    dia=par['rod_diameter']; t=.375; base=par['continuous']; seat=.125 if base else -.5
    low,high=(seat,seat+10) if base else (seat-10,seat)
    # Wide enough for source 1-1/4in office rod washers, inside 6in chord depth.
    a.box('BRACKET', [right,-2.75,low], [t,5.5,high-low], 'S' if base else 'A',
        'S 3/8in bent-plate bracket / A width and height' if base else 'A 3/8in take-up bracket; supplier verification required')
    a.box('SEAT', [right+t,-2.75,seat], [3.25-right-t,5.5,t], 'A', 'A continuous folded seat around actual offset rod')
    a.box('WEB-PACK', [gap[0],-2.75,low], [gap[1]-gap[0],5.5,high-low], 'A', 'A solid pack between the two actual chord webs')
    bolt_z=(seat+3,seat+8) if base else (seat-8,seat-3)
    a.fastener('BOLTS', [[right+t,y,z] for y in (-2,2) for z in bolt_z], [-1,0,0],
        .75,t+right-left,['BRACKET','CHORD','WEB-PACK'],
        ('S four 3/4in A325 through both actual chord webs; A pitch and gauge' if base else 'A four 3/4in through-web bracket bolts; capacity unverified'), basis='S' if base else 'A')
    centre=[dot(sub(rod['axis'][0],ctx.c['point']),v) for v in axes]
    a.cylinder('TAKE-UP',[centre[0],centre[1],seat+t],[0,0,1],dia*1.8,dia,'A','A supplier take-up/nut envelope above actual bearing seat')
    a.interfaces.append(dict(id='ROD-BEARING',kind='thread_bearing',connects=['ROD','TAKE-UP','SEAT'],basis='A',description='Threaded rod nut bears on the seat; no rod weld'))
    a.interfaces.append(dict(id='BRACKET-FOLD',kind='continuous_folded_clip',connects=['BRACKET','SEAT'],basis='A',description='One continuous bent plate; bend radius omitted'))
    if base:
        foundation(a,'ROD',centre[:2],dia,rod['axis'][0][2]-ctx.c['point'][2])
        a.box('CONC',[-12,-12,-12],[24,24,12],'A','A cast-anchor foundation context, unverified',kind='concrete')
    a.dim([0,0,seat],[centre[0],0,seat],'A 1-1/2in rod offset',basis='A')
    a.section_axis=2; a.section_at=bolt_z[0]
    a.notes.append('The rod is inside one open channel cavity, clear of the paired chord webs. Bolts pass through both actual webs, a solid pack and the bracket backplate. Source hardware sizes are retained; adopted pitch, gauge, bracket fit, local chord behavior, take-up and foundation capacities remain unverified.')
