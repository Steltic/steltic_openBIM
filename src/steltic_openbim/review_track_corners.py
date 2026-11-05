"""Explicit fictional ordinary-track corner fit and attachment.

One track butts clear of the other. An external formed corner clip joins their
actual flanges. This is an accepted coordination fit, not a checked shear-wall
collector connection or a replacement for floor/foundation anchorage.
"""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import horizontal_frame,extract


def apply(b):
    if not b.key.startswith('cfs'):return
    nodes=defaultdict(list)
    for m in b.members:
        if m['kind'] not in ('ordinary_track','top_track','bottom_track','tier_track'):continue
        p=b.profiles[m['profile_id']]
        if p['family']!='channel' or p['dimensions']['lip']:continue
        if abs(m['axis'][0][2]-m['axis'][1][2])>.001:continue
        for end,q in enumerate(m['axis']):nodes[tuple(round(v,5) for v in q)].append((m,end))
    existing={c['id'] for c in b.connections}
    for point,items in sorted(nodes.items()):
        mezz_corner=b.key=='cfs18' and len(items)==2 and all(m['id'].startswith('MEZZ-') for m,_ in items)
        if len(items)!=2 or not (mezz_corner or any(m['kind']=='ordinary_track' for m,_ in items)):continue
        # At the end of a braced wall, keep its scheduled track untouched and
        # cut back only the complementary ordinary return. Two braced tracks
        # still need their own selected collector connection.
        (first,ei),(second,ej)=sorted(items,key=lambda row:(row[0]['kind']=='ordinary_track',row[0]['id']))
        dx=unit(sub(first['axis'][1-ei],point));dy=unit(sub(second['axis'][1-ej],point))
        if abs(dot(dx,dy))>.001 or dot(first['local_y'],second['local_y'])<.999:continue
        cid='TRACK-CORNER:'+first['id']+':'+second['id']
        if cid in existing:continue
        width=b.profiles[first['profile_id']]['dimensions']['d']
        previous=list(second['end_offsets'][ej]);offset=add(previous,mul(dy,width/2+.125-dot(previous,dy)))
        second['end_offsets'][ej]=offset
        # Preserve the shared workpoint. The endpoint's selected physical
        # offset is carried into the native model and every detail extract.
        b.connection(cid,'review_track_corner',point,[first,second],parameters=dict(
            corner_turn=1 if dot(dy,cross([0,0,1],dx))>0 else -1,
            flange_direction=1 if first['local_y'][2]>0 else -1,
            cutback_in=width/2+.125),title=('MEZZANINE TRACK FIT / A' if mezz_corner else 'ORDINARY TRACK CORNER / A'))
        b.changes.append(dict(kind='ordinary_track_corner_fit',member_id=second['id'],end=ej,
            previous_offset=previous,end_offset=offset,connection_id=cid,
            basis=('A: butt the mezzanine return track 1/8 in clear of the other track and join the actual flanges with an adopted formed clip. This is a local corner fit; source shear-wall collector transfer requires its separate source-bound detail.' if mezz_corner else 'A: butt the ordinary return track 1/8 in clear of the first track, preserving its existing vertical datum; join their actual outer flanges with the shown formed clip. The braced-wall track, source sections and checked collector details are unchanged.')))
    if any(c['detail_ref']['id']=='review_track_corner' for c in b.connections):
        b.note('ORDINARY-TRACK-CORNERS','A: ordinary-track corners use explicit face cutbacks and formed external clips. These local assembly fits retain source track sections; floor transfer, shear-wall collectors and base anchorage remain separate source-bound details. No new capacity verification.')


def draw(ctx):
    a,p=ctx.a,ctx.p;first,second=ctx.ms;origin=ctx.c['point']
    far=max(first['axis'],key=lambda q:math.dist(q,origin));axes=horizontal_frame(sub(far,origin))
    extract(ctx,first,'TRACK1',axes,24);extract(ctx,second,'TRACK2',axes,24)
    d1=p[first['profile_id']]['dimensions'];d2=p[second['profile_id']]['dimensions']
    side=ctx.params['corner_turn'];up=ctx.params['flange_direction'];t=.0566
    height=min(d1['b'],d2['b'])-.5
    if height<.5:raise ValueError('Track flange too short for the proposed corner clip')
    z0=.15 if up>0 else -.15-height;zc=z0+height/2
    x0=-d2['d']/2;face=-side*d1['d']/2;end=ctx.params['cutback_in']+4.25
    # Two connected plate surfaces describe one formed angle. The screw grip
    # includes the actual sheet thickness, not an arbitrary nominal track.
    a.box('CLIP1',[x0-t,face-t if side>0 else face,z0],[6-x0+t,t,height],
          'A','A 54 mil formed corner clip against the first outer flange')
    yy=sorted((face,side*end))
    a.box('CLIP2',[x0-t,yy[0],z0],[t,yy[1]-yy[0],height],
          'A','A return leg against the actual perpendicular track flange')
    a.fastener('SCREWS1',[[xx,face-side*t,zc] for xx in (1,3,5)],
        [0,side,0],.216,t+d1['t'],['TRACK1','CLIP1'],
        'A three No.12 screws into first actual track flange',basis='A',screw=True)
    a.fastener('SCREWS2',[[x0-t,side*(ctx.params['cutback_in']+dd),zc] for dd in (.75,2,3.25)],
        [1,0,0],.216,t+d2['t'],['TRACK2','CLIP2'],
        'A three No.12 screws into second actual track flange',basis='A',screw=True)
    a.weld('BEND',[x0,face,z0],[x0,face,z0+height],['CLIP1','CLIP2'],kind='BEND',basis='A',description='A continuous formed corner, no site weld')
    a.front_axes=(0,1);a.section_axis=2;a.section_at=zc
    a.dim([0,0,0],[0,side*ctx.params['cutback_in'],0],basis='A')
    a.notes.append('A ordinary-track corner assembly only. One physical track is cut clear of the other; the clip reaches both actual outer flanges. This attachment is not a verified collector or foundation connection. Those source selections remain on their own details.')
