"""Source mezzanine layout and explicitly adopted physical fitting inputs.

The saved gold design remains immutable. These are opt-in fictional case inputs;
an original capacity is never claimed for an added or altered local interface.
"""
import math
from collections import defaultdict
from .pilots.model import add,sub,mul,unit,cross
from .review_cfs_occurrences import axis
from .drawing_workflow import fingerprint

TOP=144.;DECK=1.125;STEEL=TOP-DECK
PT=.1017;JT=.0713;TT=.0566


def joint(b,cid,purpose,q,members,records=(),**parameters):
    c=b.connection(cid,'review_mezzanine29',q,members,records,
                   parameters=dict(purpose=purpose,actual_mezzanine29=True,**parameters))
    return c


def link(b,m,c,end):
    b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],
        basis='Actual finite mezzanine member participates in this located attachment; source selection and adopted fit are separately retained.'))


def build(b):
    b.endpoint_links=[]
    b.levels=[(0,'EXISTING SLAB',0),(1,'MEZZANINE FFL',TOP)]
    b.grids={'x':[(str(i+1),x) for i,x in enumerate(range(0,721,144))],
             'y':[('A',0),('B',192),('C',384)]}
    b.material_selections=[dict(id='MEZZ29-WSP',basis='S',specification='1-1/8in PS1/PS2 Exposure1 T&G 48oc wood structural panel; source unblocked diaphragm'),
                           dict(id='MEZZ29-A36',basis='S',specification='ASTM A36 plate and angles; Fy36ksi Fu58ksi')]
    # Physical boxed posts occupy the source gravity grid. Shared braced-bay
    # corners are one real post, with every applicable line requirement retained.
    walls=[('XS',0,0,0,144),('XS',0,0,576,720),('XM',0,192,0,144),('XM',0,192,576,720),
           ('XN',0,384,0,144),('XN',0,384,576,720),('Y0',1,0,192,384),('Y60',1,720,0,192)]
    roles=defaultdict(list)
    for line,along,pos,lo,hi in walls:
        for v in (lo,hi):roles[(v,pos) if along==0 else (pos,v)].append(line)
    postpid=b.pack(b.profile('600S250-97'),2,'box',label='MEZZ29-POST-BOX')
    posts={};caps={}
    for x in range(0,721,144):
        for y in (0,192,384):
            lines=roles[x,y];refs=['gravity_framing/post-typ','connections/conn-post-base']
            refs += [b.record('studs','chord-'+('Y' if q.startswith('Y') else 'X')+'-'+q) for q in lines]
            refs += [b.record('holddowns','hd-'+('Y' if q.startswith('Y') else 'X')+'-'+q) for q in lines]
            m=b.member(f'MZ-POST-{x}-{y}',postpid,'chord' if lines else 'column',[x,y,0],[x,y,TOP],1,'A',records=refs,local_y=[0,1,0])
            m['end_offsets']=[[0,0,.375],[0,0,-DECK-.25]]
            m['physical_fit_basis']='S2x600S25097 toe-to-toe box on source12x16ft grid. A flange faces normalX; base plate3/8in and top1/4in bearing cap below source1-1/8in deck.'
            m['braced_lines']=lines;posts[x,y]=m
            c=joint(b,m['id']+'-BASE','base',[x,y,0],[m],refs,lines=lines);link(b,m,c,0)
            capid=b.custom('MEZZ29-POST-CAP','flat',dict(width=8,thickness=.25),basis='A8x8x1/4in post bearing cap')
            cap=b.member(m['id']+'-CAP',capid,'bearing_plate',[x,y-4,STEEL-.125],[x,y+4,STEEL-.125],1,'A',local_y=[1,0,0]);caps[x,y]=cap
            c=joint(b,m['id']+'-CAP-JOINT','post_cap',[x,y,STEEL],[m,cap],['gravity_framing/post-typ'],lines=lines);link(b,m,c,1)
            link(b,cap,c,0);link(b,cap,c,1)
            joint(b,m['id']+'-SEAMS','box_seams',[x,y,72],[m],['gravity_framing/post-typ'],post=True)
    beams={}
    for y in (0,192,384):
        pid=b.pack(b.profile('1400S300-118' if y==192 else '1200S300-97'),2,'box',label='MEZZ29-BEAM-'+str(y==192))
        depth=14 if y==192 else 12
        line={0:'XS',192:'XM',384:'XN'}[y]
        for x in range(0,720,144):
            refs=['gravity_framing/beam-typ','diaphragms/diaphragm-platform','collectors/coll-X-'+line]
            m=b.member(f'MZ-BEAM-{x}-{y}',pid,'girder',[x,y,STEEL-depth/2],[x+144,y,STEEL-depth/2],1,'A',records=refs)
            m['end_offsets']=[[4.5,0,0],[-4.5,0,0]];beams[x,y]=m
            for end,xx in enumerate((x,x+144)):
                c=joint(b,m['id']+'-END'+str(end),'beam_end',[xx,y,STEEL-depth/2],[m,posts[xx,y]],['connections/conn-beam-post',*refs],end=end)
                link(b,m,c,end)
            joint(b,m['id']+'-SEAMS','box_seams',[x+72,y,STEEL-depth/2],[m],['gravity_framing/beam-typ'],post=False)
    joists={}
    for x in range(0,721,16):
        for y in (0,192):
            ly=[1 if x<720 else -1,0,0]
            m=b.member(f'MZ-JOIST-{x}-{y}','1200S250-68','joist',[x,y,STEEL-6],[x,y+192,STEEL-6],1,'A',records=['gravity_framing/joist-typ'],local_y=ly)
            # Beam box envelopes are6+t wide, while a post is5+t wide. Source
            # on-grid joists land on a real post face through an explicit clip.
            hosts=[];faces=[]
            for yy in (y,y+192):
                host=posts.get((x,yy)) or beams[min(x//144,4)*144,yy]
                half=(5+PT)/2 if host['kind'] in ('column','chord') else (6+b.profiles[b.profiles[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t'])/2
                hosts.append(host);faces.append(half)
            m['end_offsets']=[[0,faces[0]+.125,0],[0,-faces[1]-.125,0]]
            joists[x,y]=m
            for end,yy in enumerate((y,y+192)):
                refs=['connections/conn-joist-clip','gravity_framing/joist-typ']
                if x in (0,720):refs.append('collectors/coll-Y-'+('Y0' if x==0 else 'Y60'))
                c=joint(b,m['id']+'-END'+str(end),'joist_end',[x,yy,STEEL-6],[m,hosts[end]],refs,end=end,receiver_face=faces[end],hand=ly[0])
                link(b,m,c,end)
    # Restore exact source Y collector halves. The opposite half is braced;
    # the old centred16ft wall put both chord posts off the gravity grid.
    for wi,(line,along,pos,lo,hi) in enumerate(walls):
        direction='X' if along==0 else 'Y';rid='wall_lines/wall-'+direction+'-'+line+'-s1'
        ztop=STEEL-(14 if line=='XM' else 12)
        wall=dict(id=line+'-L1',line=line,direction=direction,level=1,base_z_in=0,top_z_in=ztop,
                  runs=[dict(start_in=lo,end_in=hi,position_in=pos)],source_record=rid,
                  basis='S source grid and bay sizes; Y braced half opposite the explicitly located unbraced collector half; A finite track/post fitting.')
        previous=next((w for w in b.walls if w['id']==wall['id']),None)
        if previous:previous['runs']+=wall['runs']
        else:b.walls.append(wall)
        walltag=f'{line}-L1-B{len(previous["runs"]) if previous else 1}'
        def pt(u,z):return [u,pos,z] if along==0 else [pos,u,z]
        ends=[posts[tuple(pt(v,0)[:2])] for v in (lo,hi)]
        clearance=3.125 if along==0 else (5+PT)/2+.125
        tracks={}
        for label,z,sg in (('BT',TT/2,1),('TT',ztop-TT/2,-1)):
            tr=b.member(f'{walltag}-{label}','600T150-54','bottom_track' if label=='BT' else 'top_track',pt(lo+clearance,z),pt(hi-clearance,z),1,'A',records=[rid,'studs/stud-typ-bearing'],local_y=[0,0,sg])
            tracks[label]=tr
        stations=list(range(int(lo)+(12 if line=='XM' else 24),int(hi),12 if line=='XM' else 24))
        studs=[]
        for u in stations:
            st=b.member(f'{walltag}-ST-{u}','600S162-54','stud',pt(u,TT+.03125),pt(u,ztop-TT-.03125),1,'A',records=[rid,'studs/stud-typ-bearing'],local_y=[1,0,0] if along==0 else [0,1,0]);studs.append(st)
            for end,label in enumerate(('BT','TT')):
                c=joint(b,st['id']+'-'+label,'stud_track',pt(u,TT+.03125 if end==0 else ztop-TT-.03125),[st,tracks[label]],[rid],along=along,end=end)
                link(b,st,c,end)
        for label,tr in tracks.items():
            for end,post in enumerate(ends):
                c=joint(b,tr['id']+'-POST'+str(end),'track_post',axis(tr)[end],[tr,post],[rid],along=along,end=end,top=label=='TT');link(b,tr,c,end)
        for u in range(int(lo)+12,int(hi),24):
            joint(b,f'{walltag}-ANCH-{u}','track_anchor',pt(u,0),[tracks['BT']],['anchorage/anch-'+direction+'-'+line],along=along)
            host=beams[lo,pos] if along==0 else joists[pos,lo]
            joint(b,f'{walltag}-TRANSFER-{u}','track_transfer',pt(u,ztop),[tracks['TT'],host],['connections/conn-top-track-collector'],along=along)
        # Two source No12 collector end groups into track/post clips; explicit
        # local geometry is supplied in the assembly, not a remote record tag.
        for end,post in enumerate(ends):
            if along==1 and (lo if end==0 else hi)!=192:continue
            host=(beams[(lo if end==0 else hi-144),pos] if along==0 else joists[pos,0 if pos==0 else 192])
            joint(b,f'{walltag}-COLLECTOR{end}','collector',pt(lo if end==0 else hi,ztop),[tracks['TT'],host,post],['collectors/coll-'+direction+'-'+line],along=along,end=end)
        wall_bracing(b,walltag,along,pos,lo,hi,ztop,ends,rid)
        wall_bridging(b,walltag,along,pos,lo,hi,studs,ends,rid)
    deck(b,beams,joists,caps)
    from .review_cfs29_stairs import build as stair_guard
    stair_guard(b,posts,beams,joists)
    # The legacy solution retains the same gravity selections in both tables.
    # Bind both exact records to their real members; never alias unequal data.
    for collection in (b.members,b.connections):
        for entity in collection:
            for rid in list(entity['design_record_ids']):
                if not rid.startswith('gravity_framing/'):continue
                twin=rid.replace('gravity_framing/','framing/',1)
                if twin in b.records:
                    if b.records[twin]['data']!=b.records[rid]['data']:raise ValueError('Different source framing records: '+twin)
                    if twin not in entity['design_record_ids']:entity['design_record_ids'].append(twin)
                    b.used_records.add(twin)
    b.note('SOURCE-FRAMING','S:60x32ft free-standing mezzanine,12ft floor,12x16ft gravity grid,2x600S25097 boxed posts,2x1400S300118 interior/2x1200S30097 edge box beams,1200S25068 joists at16in,1-1/8in unblocked T&G WSP. Beam seams continuous; post seams1.5in at12in plus8in end welds. A:exact post roll, beam4.5in setbacks, finite joist clips, top caps and flush steel elevation142.875in. Original strength checks do not approve adopted fit, concurrent corner loads or added local steel.')
    b.note('HOST','S:no ties to the host;4in clear separation,6in existing slab,4in anchor embedment and6in minimum clearance from sawcuts. Landlord engineer retains slab/punching/anchor and host displacement verification. A:drawn slab envelope and unknown joint/host positions are coordination assumptions; source reactions and clearance requirements remain attached.')
    b.note('BRACED-CORNERS','S:distinct X/Y hold-down requirements retained on each shared post. A:one larger12x12 four-anchor base at shared Y corners and one saddle with the governing source screw count. Consolidation is an adopted physical proposal, not approval of the separate or combined source demands; all individual device counts and conditions remain in the source schedule.')
    b.physical_interfaces=[dict(id='MEZZ29-EXISTING-SLAB',kind='existing_structure',scope='existing',member_ids=[m['id'] for m in posts.values()],
        status='delegated',responsible_party='Landlord structural engineer',requirements={k:b.raw[k] for k in ('slab_handoff','separation')},
        representation='S existing 6in slab, separation and anchor requirements; A local slab and adopted saddle envelopes. Slab capacity, actual joints and simultaneous X/Y device demand require the landlord engineer.',detail_ref=dict(id='gold/cfs29/existing-slab',revision=fingerprint(b.raw['slab_handoff'])),
        basis='S source scope and requirements; A physical envelope'),
        dict(id='MEZZ29-CLOSURE',kind='source_weld_requirements',scope='delegated',member_ids=[m['id'] for m in [*posts.values(),*beams.values()]],
        responsible_party='Steel fabricator / project engineer',representation='Source seam lengths and stations modeled with explicit weld-metal envelopes. Exact qualified flare V-groove preparation and welding procedure remain source requirements.',detail_ref=dict(id='gold/cfs29/box-member-closure',revision=fingerprint(b.raw['box_member_closure'])),
        requirements=b.raw['box_member_closure'],basis='S filled-flush flare V-groove seams; A sharp-corner drawing envelope'),
        dict(id='MEZZ29-ACCESS-INFILL',kind='delegated_component',scope='delegated',member_ids=[m['id'] for m in b.members if m['kind'] in ('guard_post','guard_rail','stair_stringer','stair_tread')],
        responsible_party='Access system supplier / project engineer',representation='Guard posts, rails, stringers and tread design envelopes are modeled. Proprietary infill, stair side protection, handrail products, openings and access compliance require supplier coordination; no fabricated product or capacity is implied.',detail_ref=dict(id='accepted/cfs29/access-infill',revision='1'))]


def wall_bracing(b,walltag,along,pos,lo,hi,ztop,posts,rid):
    def pt(u,z,n=0):return [u,pos+n,z] if along==0 else [pos+n,u,z]
    n=[0,1,0] if along==0 else [1,0,0]
    pid=b.custom('MEZZ29-STRAP','flat',dict(width=2.5,thickness=.0451),basis='S A1003 ST50H43mil, no Grade33 substitution')
    for face in (-1,1):
        for flip in (0,1):
            # Two crossing planes keep both source straps continuous. Exact
            # termination and packing are A; no welded intersection is invented.
            z0,z1=(.375+12,ztop-12) if flip==0 else (ztop-12,.375+12)
            offset=face*(3.2+flip*(.0451+.0625)+.0451/2)
            m=b.member(f'{walltag}-STRAP-{face}-{flip}',pid,'strap',pt(lo,z0,offset),pt(hi,z1,offset),1,'A',records=[rid,'connections/conn-strap-end'],local_y=unit(cross(n,unit(sub(pt(hi,z1),pt(lo,z0))))))
            direction=unit(sub(*m['axis'][::-1]));m['end_offsets']=[mul(direction,-3.3),mul(direction,3.3)]
            for end,host in enumerate(posts):
                q=axis(m)[end]
                c=joint(b,m['id']+'-END'+str(end),'strap_end',q,[m,host],[rid,'connections/conn-strap-end'],along=along,face=face,end=end,layer=flip)
                link(b,m,c,end)
            m['physical_fit_basis']='S continuous2.5x43mil source strap,10 staggeredNo10 per end. A ends12in inside physical wall height, crossing planes and finite end extension/packing; no source capacity reassigned.'


def wall_bridging(b,walltag,along,pos,lo,hi,studs,posts,rid):
    def pt(u,z,n=0):return [u,pos+n,z] if along==0 else [pos+n,u,z]
    pid=b.custom('MEZZ29-BRIDGING-STRAP','flat',dict(width=1.5,thickness=TT),basis='S strap bridging at48in / A1.5x54mil selection')
    for z in (48,96):
        for face in (-1,1):
            m=b.member(f'{walltag}-BRIDGE-{z}-{face}',pid,'stud_bridging',pt(lo,z,face*(3+TT/2)),pt(hi,z,face*(3+TT/2)),1,'A',records=['studs/stud-typ-bearing'],local_y=[0,0,1])
            for st in studs:
                c=joint(b,m['id']+'-'+st['id'],'bridge_stud',pt(st['axis'][0][along],z,face*3),[m,st],['studs/stud-typ-bearing'],along=along,face=face)
            for end,post in enumerate(posts):
                c=joint(b,m['id']+'-END'+str(end),'bridge_post',axis(m)[end],[m,post],['studs/stud-typ-bearing'],along=along,face=face,end=end);link(b,m,c,end)
        # Source calls for blocking as well as straps. One actual channel in
        # each clear stud interval, with end tabs to the named adjacent studs.
        hosts=[posts[0],*studs,posts[1]]
        for j,(left,right) in enumerate(zip(hosts,hosts[1:])):
            a=left['axis'][0][along];d=right['axis'][0][along]
            la=(3 if along==0 else (5+PT)/2) if left in posts else TT/2
            rd=(3 if along==0 else (5+PT)/2) if right in posts else TT/2
            m=b.member(f'{walltag}-BLOCK-{z}-{j}','600S162-54','stud_blocking',pt(a+la+.125,z),pt(d-rd-.125,z),1,'A',records=['studs/stud-typ-bearing'],local_y=[0,0,1])
            for end,host in enumerate((left,right)):
                c=joint(b,m['id']+'-END'+str(end),'blocking_end',axis(m)[end],[m,host],['studs/stud-typ-bearing'],along=along,end=end);link(b,m,c,end)


def deck(b,beams,joists,caps):
    panel=b.panel('MEZZ29-FLOOR','floor',[[0,0,TOP],[720,0,TOP],[720,384,TOP],[0,384,TOP]],DECK,1,'S',records=['diaphragms/diaphragm-platform'],
        material_id='MEZZ29-WSP',thickness_direction='negative_global_z',physical_constituent_member_ids=[])
    # The flange is on one side of the joist web. Locate BOTH sheet edges
    # within it, rather than losing one sheet's screws at a workline seam.
    limits=[0]+[v+1.25 for v in range(16,720,48)]+[720]
    for ix,(x,xend) in enumerate(zip(limits,limits[1:])):
        width=xend-x
        pid=b.custom('MEZZ29-WSP-'+str(width),'flat',dict(width=width,thickness=DECK),basis='S1-1/8in panel / A cut4x8ft sheet set-out on actual flange')
        for iy,y in enumerate(range(0,384,96)):
            m=b.member(f'MZ-DECK-{ix}-{iy}',pid,'floor_sheet',[(x+xend)/2,y,TOP-DECK/2],[(x+xend)/2,y+96,TOP-DECK/2],1,'A',records=['diaphragms/diaphragm-platform'],local_y=[1,0,0])
            m.update(material_id='MEZZ29-WSP',material_category='wood');panel['physical_constituent_member_ids'].append(m['id'])
            m['sheet_x_limits']=[x,xend]
            for xx in range(0,721,16):
                host=joists[xx,(y//192)*192];hand=host['local_y'][0]
                flange=sorted((xx+hand*.25,xx+hand*2.25))
                edge=next((v for v in (x,xend) if flange[0]<=v<=flange[1]),None)
                xp=edge+(.5 if edge==x else -.5) if edge is not None else xx+hand*.75
                if not x+.25<=xp<=xend-.25:continue
                spacing=6 if edge is not None or xx in (0,720) else 12
                ys=[y+3+i*spacing for i in range(math.ceil(90/spacing)) if y+3+i*spacing<y+93]
                ys=[v for v in ys if min(q[1] for q in axis(host))+.5<v<max(q[1] for q in axis(host))-.5]
                if ys:
                    joint(b,m['id']+'-J'+str(xx),'deck_screws',[xp,(ys[0]+ys[-1])/2,TOP],[m,host],['diaphragms/diaphragm-platform'],points=[[xp,v,TOP] for v in ys],spacing=spacing)
            # On supported transverse boundaries use the source6in line. A
            # shared top cap carries the few screws over each real post gap.
            for yy in (y,y+96):
                if yy not in (0,192,384):continue
                py=yy+(1.5 if yy==y else -1.5)
                groups=defaultdict(list)
                for xx in range(math.ceil(x+.5),math.floor(xend-.5)+1,6):
                    nearest=min(range(0,721,144),key=lambda q:abs(q-xx))
                    if abs(xx-nearest)<=4:host=caps[nearest,yy];cap=True
                    elif abs(xx-nearest)<4.5:continue
                    else:host=beams[min(int(xx//144),4)*144,yy];cap=False
                    groups[host['id'],cap].append([xx,py,TOP])
                lookup={v['id']:v for v in [*caps.values(),*beams.values()]}
                for (hid,cap),qs in groups.items():
                    joint(b,m['id']+'-B'+str(yy)+'-'+hid,'deck_screws',qs[len(qs)//2],[m,lookup[hid]],['diaphragms/diaphragm-platform'],points=qs,spacing=6,cap=cap)
    for sheet in [m for m in b.members if m['kind']=='floor_sheet']:
        groups=[c for c in b.connections if c['parameters']['purpose']=='deck_screws' and sheet['id'] in c['member_ids']]
        if not groups:raise ValueError('Floor sheet has no actual support screws: '+sheet['id'])
        for end in (0,1):
            c=min(groups,key=lambda c:math.dist(c['point'],axis(sheet)[end]))
            b.endpoint_links.append(dict(member_id=sheet['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Actual screw group on this finite sheet; the transverse cut edge is supported on the source beam or meets the unblocked T&G seam, without an invented end fastener.'))
    b.note('DECK','S1-1/8in T&G48oc WSP,No10at6in supported edges/boundaries and12in field,unblocked. A4x8ft sheets cut to17.25in first/30.75in last strips and48in intermediate strips; seams on actual joist flanges with a separate screw row on each sheet. Source joists retain16in spacing. Unsupported transverse edges retain T&G contact without invented blocking. Drawn screws and top caps do not certify a panel product or local support capacity.')
