"""Strong-axis source roof distribution channels nested beneath actual caps."""
import math
from collections import defaultdict
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract,horizontal_frame,point
from .pilots.model import add,sub,mul,unit

RID='framing/truss-bearing-distribution'


def apply(b):
    if b.key!='cfs6':return
    roof=max(k for k,_,_ in b.levels);tracks=defaultdict(list);studs=defaultdict(list)
    # The bar's delegated trusses bear on the actual south/north wall caps.
    # In-line leg joists retain their separate direct bearing arrangements.
    for m in b.members:
        if m['level']!=roof:continue
        if m['kind'] in ('top_track','ordinary_track','tier_track') and m['local_y'][2]<-.99:
            a,d=axis(m)
            if abs(a[1]-d[1])<.001 and a[1] in (1080,1824):tracks[a[1]].append(m)
        if m['kind'] in ('stud','chord','opening_jamb'):
            a,d=axis(m)
            if a[1] in (1080,1824) and m['local_y'][0]>.99 and d[2]-a[2]>9 and d[2]>560:studs[a[1]].append(m)
    cuts={};new=[];pid=b.profile('600S162-54')
    for station,values in studs.items():
        highest={}
        for m in values:
            x=m['axis'][0][0]
            if x not in highest or axis(m)[1][2]>axis(highest[x])[1][2]:highest[x]=m
        ordered=sorted(highest.values(),key=lambda m:m['axis'][0][0])
        for left,right in zip(ordered,ordered[1:]):
            lo,hi=left['axis'][0][0],right['axis'][0][0]
            if not 6<=hi-lo<=24.01:continue
            options=[t for t in tracks[station] if min(q[0] for q in axis(t))+.01<=lo and hi<=max(q[0] for q in axis(t))-.01]
            if not options:continue
            track=min(options,key=lambda t:axis(t)[0][2]);tt=b.profiles[track['profile_id']]['dimensions']['t']
            top=axis(track)[0][2]-tt/2;bottom=top-6
            if any(bottom-.125-min(q[2] for q in axis(m))<4 for m in (left,right)):continue
            label=f'ROOF-DISTRIBUTE-{left["id"]}-{right["id"]}'
            beam=b.member(label,pid,'load_distribution',[lo,station,bottom+3],[hi,station,bottom+3],roof,'S',local_y=[0,1,0],records=[RID],
                source_span_in=16,adopted_span_in=hi-lo,engineering_status='source_span_retained' if hi-lo<=16.01 else 'longer_fit_span_unverified',
                physical_fit_basis='S single600S162-54, six-inch depth vertical, source16in distribution span. A finite cap-nested end cuts and lowered actual stud heads. Any longer span at a chord/jamb transition is explicitly unverified; the source16in capacity is not assigned to that longer span.')
            if hi-lo>16.01:beam['basis']='A'
            for end,stud in enumerate((left,right)):
                from .pilots.geometry import strips
                sign=1 if end==0 else -1
                webs=[poly for poly in strips(b.profiles[stud['profile_id']],b.profiles)
                    if max(q[0] for q in poly)-min(q[0] for q in poly)<.3 and max(q[1] for q in poly)-min(q[1] for q in poly)>2]
                web=max(webs,key=lambda poly:sign*(max if sign>0 else min)(q[0] for q in poly));face=(max if sign>0 else min)(q[0] for q in web)
                thickness=max(q[0] for q in web)-min(q[0] for q in web)
                beam['end_offsets'][end][0]=face+sign*.125
                if stud['kind']=='stud':
                    old=stud['end_offsets'][1][2];target=min(bottom-.125,axis(stud)[1][2]);stud['end_offsets'][1][2]=target-stud['axis'][1][2]
                    previous=cuts.get(stud['id'],{}).get('previous_end_offset_z',old)
                    cuts[stud['id']]=dict(previous_end_offset_z=previous,end_offset_z=stud['end_offsets'][1][2],target_z=target)
                q=[stud['axis'][0][0],station,bottom]
                cid=label+'-CLIP'+str(end)
                b.connection(cid,'review_roof_distribution',q,[beam,stud,track],[RID,'connections/conn-header-jamb'],
                    parameters=dict(actual_roof_distribution=True,purpose='end',end=end,receiver_web_face=face,receiver_web_thickness=thickness))
                b.endpoint_links.append(dict(member_id=beam['id'],end='start' if end==0 else 'end',connection_id=cid,basis='Actual distribution-channel end clips through its web into the shortened actual stud, matching the source web-supported load path.'))
                if stud['kind']=='stud':b.endpoint_links.append(dict(member_id=stud['id'],end='end',connection_id=cid,basis='Roof stud head now meets the source distribution channel through its actual web clip; the old cap-only end connection is replaced.'))
            mid=(lo+hi)/2
            b.connection(label+'-CAP','review_roof_distribution',[mid,station,top],[beam,track],[RID],
                parameters=dict(actual_roof_distribution=True,purpose='cap'))
            new.append(label)
    removed=set()
    for c in b.connections:
        if c['detail_ref']['id']!='cfs_stud' or c['member_ids'][0] not in cuts:continue
        row=cuts[c['member_ids'][0]]
        if c['point'][2]>row['target_z']:removed.add(c['id'])
    b.connections[:]=[c for c in b.connections if c['id'] not in removed]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['connection_id'] not in removed]
    b.changes.append(dict(kind='source_cfs6_roof_distribution',member_ids=new,stud_head_fits=cuts,replaced_connection_ids=sorted(removed),
        basis='S600S162-54 distribution channel, strong-axis6in depth beneath the real roof cap, source16in checked span; source54mil web clips and sixNo12 into each receiving stud. A header-side sixNo12, clip proportions, lowered stud heads,1/8in cuts and twoNo10 cap stitches. Longer transition spans (up to24in) carry an explicit A/unverified status; source16in capacity is not assigned to them. Source truss/header/stud capacities not rerun.'))
    b.note('ROOF-DISTRIBUTION','S: single600S162-54 roof load-distribution channels keep six-inch vertical depth under the actual caps; the checked source span is16in. Web-supported ends use54mil clips and sixNo12 into the receiving stud. A: local head cuts, header-side screws, clip proportions and cap stitches. Longer actual chord/jamb transition spans (up to24in) are explicitly A and unverified, with no16in capacity assigned. Continuous chord/jamb heads are retained. Delegated truss geometry and capacities remain unverified; the channel is not rotated onto its weak axis.')


def draw(ctx):
    a=ctx.a;par=ctx.params;beam=ctx.ms[0];axes=horizontal_frame([1,0,0]);bp=extract(ctx,beam,'HEADER',axes,20)
    ht=ctx.p[beam['profile_id']]['dimensions']['t']
    if par['purpose']=='cap':
        track=ctx.ms[1];tp=extract(ctx,track,'CAP',axes,20);tt=ctx.p[track['profile_id']]['dimensions']['t']
        top=tp['member']['axis'][0][2]+tt/2
        x=min(3,min(abs(q[0]) for q in bp['member']['axis'])-.75)
        if x<.5:raise ValueError('Distribution cap has no room for two actual stitches')
        a.fastener('CAP-S',[[-x,.75,top],[x,.75,top]],[0,0,-1],.19,tt+ht,['CAP','HEADER'],
            'A twoNo10 cap-to-distribution flange stitches; strong-axis header retains its separate source web end clips',basis='A',screw=True)
        a.section_axis=0;a.section_at=x;return
    stud,track=ctx.ms[1:];sp=extract(ctx,stud,'STUD',axes,14);extract(ctx,track,'CAP',axes,20)
    st=par['receiver_web_thickness'];sign=1 if par['end']==0 else -1;t=.0566
    face=par['receiver_web_face'];clipx=min(face,face+sign*t);clipy=-ht/2-t
    # Both formed legs stay outside the header web and clear its flanges.
    xlo,xhi=sorted((face,face+sign*2.75));zlo=-3.5;zhi=3
    a.box('HEADER-LEG',[xlo,clipy,zlo],[xhi-xlo,t,zhi-zlo],'S54mil; A local fit','Source54mil clip, A continuous leg outside the header web')
    a.box('STUD-LEG',[clipx,-2.5,zlo],[t,2.5+clipy,zhi-zlo],'S54mil; A local fit','Source54mil return on the actual stud web')
    a.fastener('HEADER-S',[[face+sign*x,clipy,z] for x in (.875,1.875) for z in (.75,1.5,2.25)],[0,1,0],.216,t+ht,
        ['HEADER-LEG','HEADER'],'A sixNo12 to the header web; source specifically selects sixNo12 into the stud',basis='A',screw=True)
    a.fastener('STUD-S',[[face+sign*t,y,z] for y in (-.75,-1.75) for z in (-.875,-1.75,-2.625)],[-sign,0,0],.216,t+st,
        ['STUD-LEG','STUD'],'S sixNo12 screws through the clip into the actual receiving stud; A gauge and pitch',screw=True)
    a.weld('BEND',[face,clipy,zlo],[face,clipy,zhi],['HEADER-LEG','STUD-LEG'],kind='BEND',basis='A',description='Continuous formed54mil clip; no site weld')
    a.section_axis=2;a.section_at=1.5;a.front_axes=(0,2)
    a.notes.append('Six-inch channel depth remains vertical. Source end reaction passes through the header web and clip into the real stud web, rather than through flange bearing. A clip proportions, head set-out and header-web attachment remain unverified local fit.')
