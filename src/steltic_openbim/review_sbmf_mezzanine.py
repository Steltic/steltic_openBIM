"""CFS18 source chord tracks and slab anchors at actual ten-foot panels."""
import math
from .review_cfs_source_bindings import attach
from .pilots.model import add


def prepare(b):
    if b.key!='cfs18':return
    # The west/south corner generated two perpendicular studs on one axis.
    # Keep the south-wall stud in its continuous track; the west return starts
    # on the next16in station, beyond its actual corner cutback.
    duplicates={m['id'] for m in b.members if m['id'].startswith('MEZZ-W') and m['kind']=='stud'
        and m['axis'][0][1]==24}
    b.members[:]=[m for m in b.members if m['id'] not in duplicates]
    b.connections[:]=[c for c in b.connections if not set(c['member_ids']) & duplicates]
    lookup={m['id']:m for m in b.members}
    for m in b.members:
        if not m['id'].startswith('MEZZ-') or m['kind'] not in ('stud','chord'):continue
        label=m['id'].split('-ST-')[0] if m['kind']=='stud' else m['id'].split('-CH-')[0]
        top=lookup[label+'TT'];bt=next(v for v in b.members if v['id'].startswith(label+'BT'))
        bottom=min(q[2] for q in bt['axis']);head=top['axis'][0][2]
        # Source floor-to-floor datums stay in the level register. The actual
        # second-story bottom track bears on WSP, not on the gypsum topping.
        if abs(m['axis'][0][2]-bottom)<.2:m['end_offsets'][0][2]=b.profiles[bt['profile_id']]['dimensions']['t']-(m['axis'][0][2]-bottom)
        if abs(m['axis'][1][2]-head)<.2:m['end_offsets'][1][2]=-b.profiles[top['profile_id']]['dimensions']['t']+(head-m['axis'][1][2])
    b.note('MEZZ-STRUCTURAL-DATUM','S: story1 600T300-97 chord tracks, story2 600T200-54, and23/32in WSP-only floor-transfer gap. A: extend the source deep track through the intervening field runs, place the upper structural wall atWSP top118.5in with gypsum cut back beneath it, and align accepted10ft panel starts to the16in grid so the source transfer bolts clear joists. Story levels remain120/240in. Chord worklines are a full120in apart; the earlier3in chord insets are removed. At the SW corner keep one south-wall stud, removing the overlapping perpendicular duplicate; the west return begins at the next16in station. Exact local end cuts/track fit and changed field tracks require verification.')


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members};walls={w['id']:w for w in b.walls}
    for chord in [m for m in b.members if m['id'].startswith('MEZZ-') and m['kind']=='chord']:
        label=chord['id'].split('-CH-')[0];axis=0 if walls[label]['direction']=='X' else 1;normal=1-axis
        bottom=next(m for m in b.members if m['id'].startswith(label+'BT') and min(q[axis] for q in m['axis'])<=chord['axis'][0][axis]<=max(q[axis] for q in m['axis']))
        top=lookup[label+'TT'];count=24 if chord['level']==1 else 12
        for end,track in ((0,bottom),(1,top)):
            c=b.connection(chord['id']+'-TRACK'+str(end),'review_sbmf_chord_track',chord['axis'][end],
                [chord,track],['framing/mezz-chord-track'],parameters=dict(end=end,screws=count),basis='S')
            b.endpoint_links.append(dict(member_id=chord['id'],end='start' if end==0 else 'end',connection_id=c['id'],
                basis='Source story-specific chord and deep/shallow track joined by the actual24/12 No.12 screws and fit packers.'))
        if chord['level']!=1:continue
        into=1 if chord['id'].endswith('-0') else -1;u=chord['local_y']
        c=b.connection(chord['id']+'-SHEAR-ANCHORS','review_sbmf_track_anchor',chord['axis'][0],
            [bottom],['bases/mezz-shear-anchors'],parameters=dict(diameter=.75,embedment=8,stations=[into*d for d in (4,8,12,16)],along=axis),basis='S')
    for track in [m for m in b.members if m['id'].startswith('MEZZ-') and m['kind']=='bottom_track' and m['level']==1]:
        along=0 if abs(track['axis'][1][0]-track['axis'][0][0])>1 else 1;normal=1-along
        label=track['id'].split('BT')[0];wall=walls[label];lo,hi=sorted(add(q,o)[along] for q,o in zip(track['axis'],track['end_offsets']))
        fixed=[c['point'][along]+s for c in b.connections if c['detail_ref']['id']=='review_sbmf_track_anchor' and c['member_ids']==[track['id']] for s in c['parameters']['stations']]
        # Supplement the specified four-anchor chord groups with the source
        # maximum32in field pattern. Do not place anchors in the access door.
        targets=sorted(set([lo+2,*fixed,hi-2]));new=[]
        for a,d in zip(targets,targets[1:]):
            n=math.ceil((d-a)/32)
            new.extend(a+(d-a)*j/n for j in range(1,n))
        new.extend(v for v in (lo+2,hi-2) if all(abs(v-f)>.01 for f in fixed))
        for i,x in enumerate(sorted(new)):
            point=list(track['axis'][0]);point[along]=x
            b.connection(track['id']+'-FIELD-ANCHOR'+str(i),'review_sbmf_track_anchor',point,[track],
                ['bases/mezz-shear-anchors'],parameters=dict(diameter=.75,embedment=8,stations=[0],along=along),basis='S')
        attach(b,track,'bases/mezz-shear-anchors','Actual source600T300-97 bottom track with four3/4in anchors within16in of each chord and maximum32in field pitch; adopted8in embedment is unverified.')
    # Remove generic sill fasteners at the same source-anchored base tracks.
    b.connections[:]=[c for c in b.connections if not(c['detail_ref']['id']=='review_cfs_sill' and c['member_ids'][0].startswith('MEZZ-') and lookup[c['member_ids'][0]]['level']==1)]
    b.note('MEZZ-CHORD-TRACK-ANCHORS','S: each story1 chord end has24 No.12 screws to600T300-97, each story2 end has12 to600T200-54. Source slab tracks have four3/4in F1554 anchors within16in of each chord and maximum32in between. A: distinct screw patterns and packs fitted to actual catalog clearances (0.03125in story1;0.04245in story2), finite group positions, field spacing at corners/door cuts and8in anchor embedment. Source bolts/floor transfer, nested collectors and diaphragm attachments remain separate details.')
