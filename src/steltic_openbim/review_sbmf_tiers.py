"""CFS18 double tier tracks and actual column/chord restraint angles."""
import math
from .review_receiver_geometry import extract
from .review_sbmf_girts import cross_section

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs18':return
    lookup={m['id']:m for m in b.members};removed=set()
    for lower in [m for m in b.members if m['id'].startswith('SIDE-') and m['id'].endswith('-TIER-1')]:
        label=lower['id'].removesuffix('-TIER-1');upper=lookup[label+'-TIER1'];t=b.profiles[lower['profile_id']]['dimensions']['t']
        for track,sg in ((lower,-1),(upper,1)):
            for q in track['axis']:q[2]=144+sg*t/2
            track['end_offsets']=[[0,0,0],[0,0,0]]
        for end in (0,1):
            into=1 if end==0 else -1;chord=lookup[label+'-CH-0-'+str(end)]
            x,y=chord['axis'][0][:2]
            column=min((v for v in b.members if v['kind']=='column' and abs(v['axis'][0][1]-y)<.01),key=lambda v:abs(v['axis'][0][0]-x))
            polys=cross_section(chord,b.profiles,AXES)
            outer=max(into*q[0] for poly in polys for q in poly)
            for track in (lower,upper):track['end_offsets'][end][0]=into*(outer+.125)
            c=next(c for c in b.connections if c['id']==lower['id']+':'+str(end))
            c.update(point=[x,y,144],member_ids=[lower['id'],upper['id'],chord['id'],column['id']],detail_ref={'id':'review_sbmf_tier'})
            c.setdefault('parameters',{}).update(actual_sbmf_wall=True,into=into,end=end)
            removed.add(upper['id']+':'+str(end))
            for track in (lower,upper):b.endpoint_links.append(dict(member_id=track['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual paired tier-track end clip to the continuous chord; source HSS restraint angles are shown at the same joint.'))
        lo=lower['axis'][0][0]+lower['end_offsets'][0][0]+1
        hi=lower['axis'][1][0]+lower['end_offsets'][1][0]-1;n=math.ceil((hi-lo)/12)
        for i in range(n+1):
            x=lo+(hi-lo)*i/n
            b.connection(label+'-TIER-SEAM-'+str(i),'review_sbmf_tier_seam',[x,lower['axis'][0][1],144],[lower,upper],
                [b.record('framing','sidewall-tier-track')],parameters=dict(actual_sbmf_wall=True),basis='S')
    b.connections[:]=[c for c in b.connections if c['id'] not in removed]
    b.note('SBMF-TIER-FIT','S: source11.25ft braced-bay chord worklines, two800T200-68 tier tracks with their webs back to back, No.12 seam screws at maximum12in, and paired L3x3x3/8 x6in column restraint angles with two1/4in x6in welds each. A: exact track end cuts and welded chord-web clips, two No.12 end-clip screws, one1/2in vertically slotted retention bolt per angle,1in travel and local fit. The source angle1.5in reaction lever arm is retained. Upper and lower strap collectors leave the central tier slot clear. Source capacity checks remain evidence, not verification of the adopted attachment details.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;lower,upper=ctx.ms[:2]
    extract(ctx,lower,'LOWER',AXES,22);extract(ctx,upper,'UPPER',AXES,22)
    t=p[lower['profile_id']]['dimensions']['t']
    if ctx.family=='review_sbmf_tier_seam':
        a.fastener('SEAM',[[0,0,t]],[0,0,-1],.216,2*t,['LOWER','UPPER'],'S No.12 at maximum12in through the two actual touching track webs',screw=True)
        a.section_axis=0;a.section_at=0
        return
    chord,column=ctx.ms[2:];extract(ctx,chord,'CHORD',AXES,24);extract(ctx,column,'COLUMN',AXES,24)
    into=par['into'];origin=ctx.c['point'];polys=cross_section(chord,p,AXES)
    # Chord-web end clip stays inside the wall cavity, clear of the outer
    # strap collectors and the independent column restraint angles.
    webs=[]
    for poly in polys:
        lo,hi=min(q[0] for q in poly),max(q[0] for q in poly)
        if .001<hi-lo<.5 and max(q[1] for q in poly)-min(q[1] for q in poly)>4:webs.append((into*(hi if into>0 else lo),hi if into>0 else lo))
    _,face=max(webs);cut=lower['end_offsets'][par['end']][0];ct=.125;z=-t
    a.polygon('WEB-CLIP',[[face,y,zz] for y,zz in ((-3,z-ct-4),(3,z-ct-4),(3,z-ct),(-3,z-ct))],ct,normal=[into,0,0],basis='A',description='A1/8in chord-web clip,4in high')
    a.polygon('TRACK-CLIP',[[x,y,z] for x,y in ((face+into*ct,-3),(cut+into*5,-3),(cut+into*5,3),(face+into*ct,3))],ct,normal=[0,0,-1],basis='A',description='A continuous1/8in clip under actual paired track webs')
    for i,y in enumerate((-3,3)):
        a.weld('CW'+str(i),[face,y,z-ct-4],[face,y,z-ct],['WEB-CLIP','CHORD'],.0625,basis='A',description='A1/16in x4in chord-web clip weld')
    a.fastener('TRACK-SCREWS',[[cut+into*1.5,y,t] for y in (-1.5,1.5)],[0,0,-1],.216,2*t+ct,
        ['LOWER','UPPER','TRACK-CLIP'],'A two No.12 screws through both track webs into end clip',basis='A',screw=True)
    a.interfaces.append(dict(id='CLIP-FOLD',kind='continuous_folded_clip',connects=['WEB-CLIP','TRACK-CLIP'],basis='A',description='Continuous bent chord-web end clip'))
    cd=p[column['profile_id']]['dimensions']['h'];cx=column['axis'][0][0]-origin[0]+into*cd/2
    cp=p[chord['profile_id']];pd=p[cp['components'][0]['profile_id']]['dimensions'];half=pd['d']/2;pt=pd['t'];angle=.375
    for side in (-1,1):
        inner=side*(half-pt);heel=inner
        col_label='ANGLE-COLUMN'+str(side);arm_label='ANGLE-CHORD'+str(side)
        a.polygon(col_label,[[cx,yy,z] for yy,z in ((heel-side*3,-3),(heel,-3),(heel,3),(heel-side*3,3))],angle,normal=[into,0,0],basis='S',description='S L3x3x3/8 x6in column leg')
        a.polygon(arm_label,[[xx,heel,z] for xx,z in ((cx+into*angle,-3),(cx+into*3,-3),(cx+into*3,3),(cx+into*angle,3))],angle,normal=[0,-side,0],basis='S',description='S3in outstanding angle leg against inner chord flange')
        for j,yy in enumerate((heel-side*3,heel)):
            a.weld('AW'+str(side)+str(j),[cx,yy,-3],[cx,yy,3],['COLUMN',col_label],.25,description='S1/4in x6in weld at each vertical column-leg edge')
        a.fastener('KEEPER'+str(side),[[cx+into*1.5,heel-side*angle,0]],[0,side,0],.5,angle+pt,
            [arm_label,'CHORD'],'A1/2in retention bolt; vertical slot and washer bridging;1.5in source reaction lever arm',basis='A')
        a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=1.5,width_in=.5625,travel_in=1.,basis='A')
        a.interfaces.append(dict(id='ANGLE-FOLD'+str(side),kind='continuous_rolled_angle',connects=[col_label,arm_label],basis='S',description='Source L3x3x3/8; root radius omitted'))
        a.interfaces.append(dict(id='ANGLE-SLIP'+str(side),kind='vertical_slotted_connection',connects=[arm_label,'CHORD'],travel_in=1.,basis='A',description='Out-of-plane restraint with vertical travel; adopted keeper-bolt fit'))
    a.section_axis=2;a.section_at=0
    a.notes.append('The source angle legs meet the actual HSS and continuous chord flanges. The tier tracks are two separate continuous pieces with touching webs; their cuts clear the chord. A internal chord-web clips carry the track ends. Slot and clip fit, receiving-member local behavior and bolt/weld capacities require engineering review.')
