"""CFS18 nonbearing field-stud heads with actual track and vertical travel."""
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members};connections={c['id']:c for c in b.connections};count=0
    for stud in list(b.members):
        if not stud['id'].startswith('SIDE-') or '-ST-' not in stud['id'] or stud['kind']!='stud':continue
        label=stud['id'].split('-ST-')[0];upper=stud['id'].endswith('-1')
        track=lookup[label+'TT' if upper else label+'-TIER-1']
        td=b.profiles[track['profile_id']]['dimensions'];underside=axis(track)[0][2]-td['t']/2
        # No roof/tier gravity bearing: retain an explicit5/8in initial head
        # gap. A centred one-inch vertical slot travel leaves1/8in reserve.
        stud['end_offsets'][1][2]=underside-.625-stud['axis'][1][2]
        stud.update(head_clearance_in=.625,head_vertical_travel_in=1.,physical_fit_basis='S nonbearing stud slides in top track; A5/8in initial gap and1in centred guide travel')
        c=connections[stud['id']+':1']
        c.update(point=axis(stud)[1],member_ids=[stud['id'],track['id']],detail_ref={'id':'review_sbmf_stud_head'},design_record_ids=['framing/sidewall-studs'],basis='A',parameters=dict(actual_sbmf_wall=True,head_gap_in=.625,slot_length_in=1.25,travel_in=1.,tier='upper' if upper else 'lower'))
        b.endpoint_links.append(dict(member_id=stud['id'],end='end',connection_id=c['id'],basis='Source nonbearing field stud has a physical clearance below its actual head track and independent vertically slotted guides on both flanges.'))
        count+=1
    b.changes.append(dict(kind='cfs18_nonbearing_field_stud_heads',count=count,basis='S sliding head requirement; A5/8in gap, two No12 shouldered guides,1.25in slots and1in total travel. Guide product and local connection capacity require verification.'))
    b.note('SBMF-FIELD-STUD-HEAD','S: field studs are nonbearing and slip in their top tracks; source sections and tier heights remain. A: each field-stud tier has5/8in initial head clearance, one No12 shouldered guide per flange through a1.25in vertical slot in the actual track leg,1in total centred travel, and washers bridging the slot without clamping it. Chord-pack collector joints stay fixed. Guide hardware/product, movement demand and local capacity are unverified adopted test details.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;stud,track=ctx.ms
    extract(ctx,stud,'STUD',AXES,16);extract(ctx,track,'TRACK',AXES,9)
    sd=p[stud['profile_id']]['dimensions'];td=p[track['profile_id']]['dimensions'];origin=ctx.c['point']
    web=axis(track)[0][2]-origin[2];centre=web-1.1;outer=td['d']/2;inside=outer-td['t'];flange=sd['d']/2
    gap=inside-flange
    if gap<-.00001:raise ValueError('Sliding stud does not fit inside its actual track')
    for side in (-1,1):
        a.fastener('GUIDE'+str(side),[[sd['b']/2,side*outer,centre]],[0,-side,0],.216,td['t']+gap+sd['t'],['STUD','TRACK'],
            'A No12 shouldered guide, washer bridges vertical track slot without clamping; proprietary hardware and capacity unverified',basis='A',screw=True)
        a.fasteners[-1].update(slot=dict(direction=[0,0,1],length_in=par['slot_length_in'],width_in=.28125,travel_in=par['travel_in'],host_part_id='TRACK',basis='A'),
            shoulder_length_in=td['t']+gap,installation='A shoulder bears at stud flange; track slides below washer, no rigid screw clamping of track slot')
    a.interfaces.append(dict(id='SLIP',kind='vertical_slotted_connection',connects=['STUD','TRACK'],travel_in=par['travel_in'],initial_head_clearance_in=par['head_gap_in'],basis='A',description='S nonbearing head; A guide hardware, centred travel and initial clearance'))
    a.dim([0,0,0],[0,0,par['head_gap_in']],'A initial head clearance',basis='A')
    a.section_axis=0;a.section_at=sd['b']/2
    a.notes.append('S nonbearing field-stud slip requirement. Actual source stud/track sections and tracks at their real tier/header datums. A5/8in head gap,1in total centred travel and shouldered guides. Ordinary tightly clamped screws cannot provide this slip action; verify selected guide hardware, slot washer, movement demand and local capacity. Chord-pack force-transfer screws are separate fixed connections.')
