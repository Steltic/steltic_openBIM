"""Located flange struts and explicit delegated truss receiving extensions."""
from .review_cfs import simple_truss
from .review_receiver_geometry import extract
from .review_cfs_occurrences import axis
from .pilots.geometry import strips

AXES=([1,0,0],[0,1,0],[0,0,1])


def prepare(b):
    if b.key not in ('cfs10','cfs18'):return
    lookup={m['id']:m for m in b.members};office=b.key=='cfs10';length=1200 if office else 2400
    trusses={}
    for c in b.connections:
        if c['detail_ref']['id']!='review_sbmf_strut':continue
        m,beam=[lookup[mid] for mid in c['member_ids']]
        # The original label contains --1 for the negative hand.
        hand=-1 if m['id'].endswith('--1') else 1
        cx=beam['axis'][0][0];face=b.profiles[beam['profile_id']]['components'][1]['offset'][0]
        single=b.profiles[b.profiles[beam['profile_id']]['components'][1]['profile_id']];bd=single['dimensions'];t=bd['t']
        face-=t/2
        into=hand if 0<cx<length or (cx==0 and hand==1) or (cx==length and hand==-1) else -hand
        # Start inside the real flange; place both source screws within its
        # width. At a perimeter, the outside-channel strut points inward.
        start=cx+hand*(face+.25 if into==hand else face+bd['b']-.25)
        end=start+into*24;rx=end-into
        y=m['axis'][0][1];z=beam['axis'][0][2]-b.depth(beam['profile_id'])/2-b.depth(m['profile_id'])/2
        m['axis']=[[start,y,z],[end,y,z]];m['local_y']=[0,into,0];m['end_offsets']=[[0,0,0],[0,0,0]]
        if not office:m.update(basis='A',material_id='assumed_test_steel')
        c['point']=list(m['axis'][0]);c.setdefault('parameters',{}).update(actual_sbmf_restraint=True,into=into,receiver_x_in=rx,source_strut=office)
        trusses[round(rx,7)]=f'ROOF-RESTRAINT-{rx:.7f}'
        b.changes.append(dict(kind='sbmf_strut_receiver_setout',member_id=m['id'],truss_x_in=rx,
            basis='S CFS10 24in strut and section; A exact flange stations, perimeter inward orientation and added delegated receiving truss. CFS18 local strut size/length is A. Supplier restraint capacity remains a requirement.'))
    for x,label in sorted(trusses.items()):
        if not 0<x<length:raise ValueError('Restraint receiver outside the roof footprint')
        simple_truss(b,label,1,x,0,600,302 if office else 300,0 if office else 12.5,3,'2X600S162-68','2X362S162-54',60,heel=36 if office else 24)
    b.note('SBMF-RESTRAINT-LAYOUT','S: CFS10 24in 362S162-54 struts, two No.12 flange screws and one1/2in vertically slotted truss-web bolt. A: exact strut placement under the real bottom flanges, inward perimeter struts, extra delegated trusses at the required receiving stations, 54mil vertical extensions and their cap attachments. The existing4ft truss grid remains; added trusses reduce local spacing. CFS18 retains its1.39kip restraint requirement, with A local strut sizes. The added supplier receiving system and its stiffness have not been designed or certified.')


def apply(b):
    if b.key not in ('cfs10','cfs18'):return
    lookup={m['id']:m for m in b.members};chords=[m for m in b.members if m['kind']=='truss_chord' and m['id'].startswith('ROOF-RESTRAINT-') and abs(m['axis'][0][2]-m['axis'][1][2])<1e-7]
    for c in list(b.connections):
        if not c.get('parameters',{}).get('actual_sbmf_restraint'):continue
        m,beam=[lookup[mid] for mid in c['member_ids']];x=c['parameters']['receiver_x_in'];y=m['axis'][0][1];z=m['axis'][0][2]
        chord=min((v for v in chords if abs(v['axis'][0][0]-x)<1e-6 and min(q[1] for q in v['axis'])+.75<=y+1.75<=max(q[1] for q in v['axis'])-.75),key=lambda v:v['axis'][0][2])
        top=axis(chord)[0][2]-b.depth(chord['profile_id'])/2-.125
        vertical=b.member(m['id']+'-VERTICAL','362S162-54','truss_restraint_vertical',[x,y+.0566,z-2],[x,y+.0566,top],3,'A',local_y=[0,1,0],records=[b.record('schedules','sched-purlin')])
        c['member_ids']=[m['id'],beam['id'],vertical['id']]
        b.connection(vertical['id']+'-CAP','review_sbmf_restraint_cap',[x,y,top],[vertical,chord],
            [b.record('schedules','sched-purlin')],parameters=dict(actual_sbmf_restraint=True),basis='A')
        for mid,end,cid in ((m['id'],'start',c['id']),(m['id'],'end',c['id']),(vertical['id'],'start',c['id']),(vertical['id'],'end',vertical['id']+'-CAP')):
            b.endpoint_links.append(dict(member_id=mid,end=end,connection_id=cid,basis='Located flange restraint and explicit supplier receiving vertical; actual components and attachments shown.'))


def draw(ctx):
    a,p=ctx.a,ctx.p
    if ctx.family=='review_sbmf_restraint_cap':
        vertical,chord=ctx.ms;extract(ctx,vertical,'VERTICAL',AXES,36);extract(ctx,chord,'CHORD',AXES,16)
        a.box('CAP',[-3,-.25,0],[6,3,.125],'A','A1/8in cap shoe on actual supplier vertical')
        # The extension's web is parallel to Y; cap welds follow its three
        # real top edges, not a generic rectangular tube.
        vd=p[vertical['profile_id']]['dimensions'];half=vd['d']/2;t=vd['t'];yy=.0566
        a.weld('WEB-WELD',[-half,yy-t/2,0],[half,yy-t/2,0],['VERTICAL','CAP'],.0625,basis='A',description='A1/16in shop weld at actual vertical web')
        for side in (-1,1):
            a.weld('FLANGE-WELD'+str(side),[side*(half-t/2),yy,0],[side*(half-t/2),yy+vd['b'],0],['VERTICAL','CAP'],.0625,basis='A')
        flanges=[]
        for poly in strips(p[chord['profile_id']],p):
            lo,hi=min(q[1] for q in poly),max(q[1] for q in poly)
            if lo>0 and hi-lo<.2 and max(q[0] for q in poly)-min(q[0] for q in poly)>1:
                flanges.append(((min(q[0] for q in poly)+max(q[0] for q in poly))/2,hi-lo))
        for i,(x,tt) in enumerate(flanges):
            a.fastener('B'+str(i),[[x,1.75,0]],[0,0,1],.375,.125+tt,['CAP','CHORD'],'A3/8in through-bolt in actual bottom-chord flange',basis='A')
        a.section_axis=1;a.section_at=1.75
        a.notes.append('A delegated receiving extension and cap shoe are real model components. Source truss-side strength and stiffness are requirements; this drawing does not certify the extension, cap, welds, bolts or truss permanent bracing.')
        return
    m,beam,vertical=ctx.ms;par=ctx.params;into=par['into'];source='S' if par['source_strut'] else 'A'
    extract(ctx,m,'STRUT',AXES,30);extract(ctx,beam,'BEAM',AXES,20);extract(ctx,vertical,'VERTICAL',AXES,45)
    st=p[m['profile_id']]['dimensions']['t'];d=p[m['profile_id']]['dimensions']['d'];bt=p[p[beam['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
    a.fastener('SCREWS',[[into*x,into*.8,d/2-st] for x in (1,2.5)],[0,0,1],.216,st+bt,
        ['STRUT','BEAM'],source+' two No.12 screws through actual strut top flange into SBMF bottom flange',basis=source,screw=True)
    vx=vertical['axis'][0][0]-ctx.c['point'][0]
    a.fastener('SLIDE',[[vx,-st/2,0]],[0,1,0],.5,2*st,['STRUT','VERTICAL'],source+' one1/2in bolt into real54mil receiving vertical; A2in vertical slot',basis=source)
    a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=2,travel_in=1.5,basis='A')
    a.interfaces.append(dict(id='SLIDE-MOVEMENT',kind='vertical_slotted_connection',connects=['STRUT','VERTICAL'],travel_in=1.5,basis='A',description='Lateral restraint with vertical travel; no gravity load transfer into the SBMF beam'))
    a.dim([0,0,-d/2],[into*24,0,-d/2],source+'24in strut',basis=source)
    a.section_axis=0;a.section_at=vx
    a.notes.append('Actual24in strut beneath the real SBMF bottom flange. Both source screws contact the flange, and the slotted end bolt reaches the modeled supplier vertical. Its separate cap detail locates the attachment to an actual truss bottom chord. A supplier extension, added truss placement and travel require verification; no generic or disconnected receiving member is substituted.')
