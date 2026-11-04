"""Explicit fictional splice fits at otherwise unconnected bottom-track ends.

The source wall anchorage and collector details remain separate. These local
clips are engineer-entered example proposals, not source strength selections.
"""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,unit,dot
from .review_receiver_geometry import horizontal_frame,extract


def apply(b):
    if not b.key.startswith('cfs'):return
    nodes=defaultdict(list)
    for m in b.members:
        if m['kind']!='bottom_track':continue
        p=b.profiles[m['profile_id']]
        if p['family']!='channel' or p['dimensions']['lip'] or m['local_y'][2]<.999:continue
        for end,q in enumerate(m['axis']):nodes[tuple(round(v,5) for v in q)].append((m,end))
    covered=defaultdict(list)
    for c in b.connections:
        covered[tuple(round(v,5) for v in c['point'])].append(set(c['member_ids']))
    for point,items in sorted(nodes.items()):
        if len(items)!=2:continue
        (first,ei),(second,ej)=sorted(items,key=lambda row:row[0]['id'])
        if first['profile_id']!=second['profile_id']:continue
        dx=unit(sub(first['axis'][1-ei],point));dy=unit(sub(second['axis'][1-ej],point))
        if dot(dx,dy)>-.999 or abs(dx[2])>.001:continue
        ids={first['id'],second['id']}
        if any(ids<=s for s in covered[point]):continue
        physical=[add(m['axis'][end],m['end_offsets'][end]) for m,end in items]
        if math.dist(*physical)>.001:continue
        if min(math.dist(*m['axis']) for m,_ in items)<8:continue
        cid='TRACK-SPLICE:'+first['id']+':'+second['id']
        for m,end,ray in ((first,ei,dx),(second,ej,dy)):
            previous=list(m['end_offsets'][end]);m['end_offsets'][end]=add(previous,mul(ray,.0625))
            b.changes.append(dict(kind='bottom_track_splice_gap',member_id=m['id'],end=end,
                previous_offset=previous,end_offset=list(m['end_offsets'][end]),connection_id=cid,
                basis='A: 1/16 in end cut at each side of a 1/8 in butt gap, retaining the actual track web bearing datum. Two external 54 mil flange straps with three No.12 screws per track on each face; capacity remains unverified.'))
        b.connection(cid,'review_track_splice',point,[first,second],parameters=dict(
            gap_in=.125,strap_thickness_in=.0566,strap_length_in=12,screws_per_end_per_face=3),
            title='BOTTOM TRACK BUTT SPLICE / A')
    if any(c['detail_ref']['id']=='review_track_splice' for c in b.connections):
        b.note('TRACK-SPLICES','A: coincident bottom-track segment ends have a 1/8 in butt gap and two 54 mil flange straps, each with three No.12 screws into each track. This accepted fictional fit is not a verified collector, wall shear-transfer or anchor design; those source details and capacity requirements remain.')


def draw(ctx):
    a,p=ctx.a,ctx.p;first,second=ctx.ms;origin=ctx.c['point']
    far=max(first['axis'],key=lambda q:math.dist(q,origin));axes=horizontal_frame(sub(far,origin))
    first_part=extract(ctx,first,'TRACK1',axes,18)
    extract(ctx,second,'TRACK2',axes,18)
    d=p[first['profile_id']]['dimensions'];t=ctx.params['strap_thickness_in']
    height=d['b']-.5
    if height<.5:raise ValueError('Track flange too short for the proposed splice')
    # local_y is vertical: the channel flanges are the two outside Y faces.
    z0=first_part['member']['axis'][0][2]+.25;zc=z0+height/2
    for side in (-1,1):
        face=side*d['d']/2;label='STRAP'+str(side)
        a.box(label,[-6,face if side>0 else face-t,z0],[12,t,height],
            'A','A 54 mil external flange splice strap')
        for receiver,sign in (('TRACK1',1),('TRACK2',-1)):
            points=[[sign*x,face+side*t,zc] for x in (1,3,5)]
            a.fastener(label+'-'+receiver,points,[0,-side,0],.216,t+d['t'],[label,receiver],
                'A three No.12 screws per end per face; actual track sheet thickness',basis='A',screw=True)
    a.front_axes=(0,2);a.section_axis=0;a.section_at=3
    a.dim([-6,0,z0],[6,0,z0],'A 12 in splice strap',basis='A')
    a.dim([-.0625,0,z0],[.0625,0,z0],'A 1/8 in butt gap',basis='A',offset=-32)
    a.notes.append('A local bottom-track splice only. Two physical tracks and both outside flange straps are shown. The source sill anchors, floor attachments and shear-wall collectors remain separate; no source capacity is claimed for this proposed splice.')
