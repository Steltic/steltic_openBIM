"""Located roof-header joints for the two fictional SBMF review cases.

The source header selections are retained. The overlapping moment-beam webs
need explicit reliefs for the shear tabs; these are A, with no transfer of the
uncut source beam capacity to the revised local fit.
"""
import math
from .pilots.model import add,sub,mul,unit
from .pilots.geometry import strips
from .review_receiver_geometry import extract

AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key not in ('cfs10','cfs18'):return
    members={m['id']:m for m in b.members};cap_by_header={}
    b.endpoint_links=getattr(b,'endpoint_links',[])
    for m in list(b.members):
        if not m['id'].startswith('HEADER-'):continue
        section=b.profiles[m['profile_id']]['components'][0]['profile_id']
        track=b.profile(section.replace('S','T',1));td=b.profiles[track]['dimensions'];d=b.depth(m['profile_id'])
        ends=[list(q) for q in m['axis']]
        for q in ends:q[2]+=d/2+td['t']/2
        cap=b.member(m['id']+'-CAP',track,'header_cap',*ends,m['level'],'S',
                     local_y=[0,0,-1],records=m['design_record_ids'])
        cap_by_header[m['id']]=cap
    for c in list(b.connections):
        if c['detail_ref']['id']!='review_sbmf_header':continue
        m,column=[members[mid] for mid in c['member_ids']];end=min(range(2),key=lambda i:math.dist(m['axis'][i],c['point']))
        sg=1 if end==0 else -1;frame=members[column['id'].rsplit('-C',1)[0]+'-BEAM'];cap=cap_by_header[m['id']]
        # The moment-beam channels straddle the same HSS faces used by the
        # header. Clear their flanges and expose the column through a named
        # web relief; do not silently draw the shear tab through solid steel.
        polys=strips(b.profiles[frame['profile_id']],b.profiles)
        outside=max(sg*q[0] for poly in polys for q in poly)
        face=b.depth(column['profile_id'])/2;cut=outside+.25
        m['end_offsets'][end][0]=sg*cut;cap['end_offsets'][end][0]=sg*cut
        # Put the six-inch-high tab below the SBMF top flange and keep both
        # bolts in the actual header web. Header worklines remain unchanged.
        z=min(m['axis'][end][2],frame['axis'][0][2]+b.depth(frame['profile_id'])/2-.25-3)
        frame_start=add(frame['axis'][0],frame['end_offsets'][0]);station=c['point'][1]-frame_start[1]
        slot=dict(start_in=station-.375,end_in=station+.375,section_axis=1,
                  centre_in=frame['axis'][0][2]-z,width_in=6.125,basis='A',
                  description='A opposed SBMF-web reliefs for the roof-header tabs. Revised beam/connection capacity unverified.')
        if slot not in frame.setdefault('slots',[]):frame['slots'].append(slot)
        c['member_ids']=[m['id'],column['id'],frame['id'],cap['id']]
        c.setdefault('parameters',{}).update(actual_sbmf_header=True,end=end,into=sg,
            tab_z_relative=z-c['point'][2],column_face_in=face,tab_projection_in=cut-face+2,
            source_tab=b.key=='cfs10')
        b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],
            basis='Actual roof-header cut clears the SBMF flange; the named tab reaches the HSS through an explicit A web relief.'))
        b.endpoint_links.append(dict(member_id=cap['id'],end='start' if end==0 else 'end',connection_id=c['id'],
            basis='Cap ends with the actual header; its distributed screws are shown separately.'))
        b.changes.append(dict(kind='sbmf_header_physical_fit',connection_id=c['id'],member_id=m['id'],
            receiving_column_id=column['id'],moment_beam_id=frame['id'],cap_id=cap['id'],
            cut_offset_in=sg*cut,tab_z_in=z,web_relief=slot,
            basis='S header/column/cap sections. S CFS10 tab thickness, bolts and welds; A CFS18 tab and all exact fit dimensions. The source uncut SBMF beam capacity is not assigned to the relieved section; revised local verification remains required.'))
    for hid,cap in cap_by_header.items():
        m=members[hid];a,d=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])];count=max(1,math.ceil((d[0]-a[0]-2)/12))
        for i in range(count+1):
            x=a[0]+1+(d[0]-a[0]-2)*i/count
            b.connection(cap['id']+'-SCREWS'+str(i),'review_sbmf_cap',[x,a[1],cap['axis'][0][2]],
                [cap,m],m['design_record_ids'],parameters=dict(actual_sbmf_header=True),basis='A')
    # A supplier truss heels retain their roof top-chord elevations. Lift the
    # bottom-chord workline enough to clear the actual source cap webs.
    delta=3+(.1242 if b.key=='cfs10' else .1017);base=302 if b.key=='cfs10' else 300
    for m in b.members:
        if not m['id'].startswith('ROOF-') or 'truss' not in m['kind']:continue
        for q in m['axis']:
            if abs(q[2]-base)<1e-6:q[2]+=delta
    for c in b.connections:
        if c['id'].startswith('ROOF-') and abs(c['point'][2]-base)<1e-6:c['point'][2]+=delta
    b.note('SBMF-HEADER-FIT','S: source paired headers and cap-track sections. A: cap orientation/attachment, bottom truss chord raised to the real cap underside bearing datum while roof top chords stay fixed, finite header cuts, tab projection and bolt stations. CFS10 retains the specified3/8in tab, two5/8in bolts and paired1/4in x6in welds; the same sizes in CFS18 are an A proposal because no source header joint is supplied. The tab conflicts with the source SBMF web: explicit3/4in-long x6-1/8in-high opposed web reliefs are shown, with no source capacity assigned to the modified beam. These local modifications require engineering verification; the original uncut design checks remain unchanged as evidence.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params
    if ctx.family=='review_sbmf_cap':
        cap,m=ctx.ms;extract(ctx,cap,'CAP',AXES,10);extract(ctx,m,'HEADER',AXES,10)
        td=p[cap['profile_id']]['dimensions'];profile=p[m['profile_id']];t=p[profile['components'][0]['profile_id']]['dimensions']['t']
        # One screw in the middle of each actual top flange; cap web is wider
        # than the paired header and is never substituted with a narrow strip.
        ys=[]
        for poly in strips(profile,p):
            if max(q[1] for q in poly)-min(q[1] for q in poly)<.2 and min(q[1] for q in poly)>0:
                lo,hi=min(q[0] for q in poly),max(q[0] for q in poly)
                if hi-lo>1:ys.append((lo+hi)/2)
        a.fastener('SCREWS',[[0,y,td['t']/2] for y in ys],[0,0,-1],.216,td['t']+t,
            ['CAP','HEADER'],'A one No.12 screw per actual top flange at maximum12in stations',basis='A',screw=True)
        a.section_axis=0;a.section_at=0
        a.notes.append('Full source cap-track web and legs, in their accepted horizontal cap orientation. The wider cap overhang and its two-flange screw attachment are A fit decisions, not a verified source local bending check.')
        return
    header,column,frame,cap=ctx.ms;sg=par['into'];face=par['column_face_in'];z=par['tab_z_relative'];length=par['tab_projection_in'];basis='S' if par['source_tab'] else 'A'
    for m,label in ((header,'HEADER'),(column,'COLUMN'),(frame,'SBMF'),(cap,'CAP')):extract(ctx,m,label,AXES,24)
    a.box('TAB',[sg*face if sg>0 else -face-length,-.1875,z-3],[length,.375,6],basis,
          ('S' if par['source_tab'] else 'A')+'3/8in tab; A actual projection and six-inch vertical fit')
    tw=p[p[header['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];x=sg*(face+length-1)
    a.fastener('B',[[x,-.1875-tw,z+v] for v in (-1.5,1.5)],[0,1,0],.625,.375+2*tw,
        ['HEADER','TAB'],basis+' two5/8in A325-N through both header webs; A3in vertical pitch',basis=basis)
    for i,y in enumerate((-.1875,.1875)):
        a.weld('W'+str(i),[sg*face,y,z-3],[sg*face,y,z+3],['COLUMN','TAB'],.25,basis=basis,
            description=basis+'1/4in x6in fillet at the actual HSS face')
    a.dim([x,0,z-1.5],[x,0,z+1.5],'A3in bolt pitch',basis='A');a.section_axis=2;a.section_at=z+1.5
    a.notes.append('The actual header, cap, HSS and adjacent moment beam are shown. The shear tab passes through a named A SBMF-web relief; header and cap cuts clear the moment-beam flanges. This local relief changes the source beam and requires a revised capacity check; the source uncut beam result is not approval of this fit.')
