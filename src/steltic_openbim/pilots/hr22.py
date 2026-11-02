"""Hospital pilot: physical columns, RBS beams, gravity/infill and design details."""
from .model import Model,add,sub,mul,unit,cross,dot,box,cylinder,points

LEVELS=[0,192,360,528,696,864,1032]


def build(source,catalog):
    m=Model(source,catalog,'hr22_hospital')
    cols={}; beams={}; col_source={}
    for candidate in source['physical']['members']:
        if candidate['kind']=='col': col_source.setdefault(tuple(candidate['axis'][0][:2]),[]).append(candidate)
    def column_at(x,y,z):
        return next(c for c in cols[x,y] if c['axis'][0][2]-1e-5<=z<=c['axis'][1][2]+1e-5)
    for (x,y),rows in sorted(col_source.items()):
        rows.sort(key=lambda r:r['axis'][0][2]); i,j=int(x/360),int(y/360)
        lateral=rows[0]['profile_id'].startswith('W36')
        # The completed cfg puts corner columns in the Y frames. All remaining
        # perimeter frame columns are oriented into their moment-frame plane.
        width=[1,0,0] if i in (0,6) else [0,-1,0]
        if not lateral: width=[0,-1,0]
        intervals=[(0,408),(408,744),(744,1032)]
        cols[x,y]=[]
        for k,(lo,hi) in enumerate(intervals):
            profile=rows[2*k]['profile_id']; kind='lateral_col' if lateral else 'gravity_col'
            refs=[f'members/{kind}-{profile}']
            c=m.member(f'COL-{i+1}-{chr(65+j)}-{k+1}',[x,y,lo],[x,y,hi],profile,'column',refs,level=2*k+1,
                local_y=width,material='steel',offsets=[[0,0,-96 if lateral and k==0 else (3.625 if k==0 else 0)],[0,0,0]],analysis_segments=[])
            for r in rows:
                a,b=[v[2] for v in r['axis']]; low=max(lo,a); high=min(hi,b)
                if high>low: c['analysis_segments'].append({'analysis_id':r['analysis_ids'][0],'start':(low-a)/(b-a),'end':(high-a)/(b-a)})
            cols[x,y].append(c)
        c=cols[x,y][0]; dims=m.profiles[c['profile_id']]['dimensions']
        base_ref=f'connections/conn-base-{kind}-{c["profile_id"]}'
        jid='BASE-'+c['id']; m.joint(jid,[x,y,0],[(c['id'],'start')])
        if lateral:
            side=47 if c['profile_id']=='W36X395' else 46; thick=3.25 if side==47 else 2
            parts=[box('end-plate',[x-side/2,y-side/2,-96-thick],[side,side,thick])]
            depth=cross([0,0,1],width)
            for sign in [-1,1]:
                o=add([x,y,-96],add(mul(width,-dims['bf']/2 if sign<0 else dims['bf']/2-.75),mul(depth,-17)))
                parts.append(box(f'box-side-{sign}',o,[.75,34,96],width,depth))
        else:
            parts=[box('base-plate',[x-11.5,y-11.5,2],[23,23,1.625]),
                box('lug-x',[x-8,y-.5,-3],[16,1,5]),box('lug-y',[x-.5,y-8,-3],[1,16,5])]
        m.connect(jid,[base_ref],parts,'hr_column_base')
        for k in [1,2]:
            below,above=cols[x,y][k-1:k+1]; z=above['axis'][0][2]
            jid=f'SPLICE-{i+1}-{chr(65+j)}-{k}'
            m.joint(jid,[x,y,z],[(below['id'],'end'),(above['id'],'start')])
            m.connect(jid,[f'connections/conn-{kind}-{c["profile_id"]}' for c in [below,above]],template='hr_column_splice_48in_above_floor')
        c=cols[x,y][-1]; jid='TOP-'+c['id']; m.joint(jid,c['axis'][1],[(c['id'],'end')])
        m.ph['joint_dispositions'].append({'joint_id':jid,'reason':'Column terminates at roof; beam joints attach to this continuous column. Roof cap definition retained in joint design.'})

    rbs=source['design_context']['capacity_design']['RBS']
    for candidate in source['physical']['members']:
        if candidate['kind']!='beam': continue
        a,b=candidate['axis']; z=a[2]; level=LEVELS.index(z); direction=unit(sub(b,a)); width=unit(cross([0,0,1],direction))
        sec=candidate['profile_id']; role='roof' if level==6 else 'floor'; moment=sec in rbs
        penthouse=level==6 and a[1]==b[1] and a[1] in (360,720) and a[0]>=720 and b[0]<=1440
        refs=[f'members/{role}-{sec}']
        if penthouse: sec='W27X84'; refs=['members/roof-penthouse-girder-W27X84']
        m.profile(sec); d=m.profiles[sec]['dimensions']['d']
        offsets=[]; supports=[]
        for p,sign in [(a,1),(b,-1)]:
            col=column_at(*p); supports.append(col)
            cd=m.profiles[col['profile_id']]['dimensions']; depth=cross([0,0,1],col['local_y'])
            face=cd['d']/2 if abs(dot(direction,depth))>.9 else cd['tw']/2
            offsets.append(add(mul(direction,sign*(face+(0 if moment else 1.25))),[0,0,-d/2]))
        bm=m.member('B-'+candidate['id'].split(':')[-1],a,b,sec,'moment_beam' if moment else 'girder',refs,level=level,
            local_y=width,material='steel',offsets=offsets,analysis_ids=candidate['analysis_ids'],rbs=rbs.get(sec))
        beams[tuple(a),tuple(b)]=bm
        for idx,(point,col) in enumerate(zip([a,b],supports)):
            end='start' if idx==0 else 'end'; jid=f'{bm["id"]}:{end}'; m.joint(jid,point,[(bm['id'],end)],[col['id']])
            face=add(point,add(offsets[idx],[0,0,d/2])); inward=mul(direction,1 if idx==0 else -1)
            refs=[f'connections/conn-{role}-{candidate["profile_id"]}']; parts=[]
            if moment:
                # Full RBS parameters belong to the beam solid; the reference
                # below contains the CJP and erection-tab specification.
                kind='end' if (col['axis'][0][0]/360,col['axis'][0][1]/360) in [(0,0),(0,4),(6,0),(6,4),(1,0),(5,0),(1,4),(5,4)] else 'int'
                joint_ref=f'connections/conn-joint-L{level}-{kind}-{col["profile_id"]}'
                if joint_ref not in m.records: raise ValueError(joint_ref)
                refs.append(joint_ref)
                # One panel-zone assembly per column/level, shared by two beams.
                if idx==0 or kind=='end':
                    jd=m.record(joint_ref); text=jd.get('components','')
                    rows=source['design_context']['capacity_design']['continuity_plates']['by_joint']
                    row=next(r for r in rows if r['joint'].startswith(f'L{level} '+('frame-end' if kind=='end' else 'interior')))
                    t=row['continuity_plates_in']; cd=m.profiles[col['profile_id']]['dimensions']; cy=col['local_y']; cz=cross([0,0,1],cy)
                    for zz in [z-m.profiles[sec]['dimensions']['tf'],z-d]:
                        for side,offset in [('left',-cd['bf']/2),('right',cd['tw']/2)]:
                            o=add([point[0],point[1],zz],add(mul(cy,offset),mul(cz,-(cd['d']/2-cd['tf']))))
                            parts.append(box(f'continuity-{zz}-{side}',o,[(cd['bf']-cd['tw'])/2,cd['d']-2*cd['tf'],t],cy,cz))
                    pz=next(r for r in source['design_context']['capacity_design']['panel_zone']['by_joint'] if r['joint'].startswith(f'L{level} '+('frame-end' if kind=='end' else 'interior')))
                    if pz['doubler_in']:
                        o=add([point[0],point[1],z-d],add(mul(cy,cd['tw']/2),mul(cz,-(cd['d']/2-cd['tf']))))
                        parts.append(box('doubler',o,[pz['doubler_in'],cd['d']-2*cd['tf'],d],cy,cz))
            else:
                center=add(face,[0,0,-d/2]); outward=unit(cross([0,0,1],inward))
                origin=add(center,add(mul(inward,-1.25),add(mul(outward,m.profiles[sec]['dimensions']['tw']/2),[0,0,-8.625])))
                parts.append(box('shear-plate',origin,[4.75,.5,17.25],inward,outward))
                for n in range(6):
                    o=add(origin,add(mul(inward,3),[0,0,1.125+3*n]))
                    parts.append(cylinder(f'bolt-{n+1}',add(o,mul(outward,-1)),outward,.875/2,2.5,material='boltA490'))
                # Existing collectors are selected X girders, not extra beams.
                if a[1]==b[1] and a[1] in (360,1080) and (a[0]==0 or b[0]==2160):
                    refs.extend([f'connections/conn-collector-X-{role}','connections/conn-collector-columns-J10'])
                    bm['design_record_ids']=m.refs(bm['design_record_ids']+[f'members/collector-X-{role}-{candidate["profile_id"]}'])
            m.connect(jid,refs,parts,'hr_rbs_joint' if moment else 'hr_simple_shear_plate')
    # Infill runs Y at 10 ft; two per 30-ft bay. At the penthouse, the completed
    # local gravity design supersedes the typical roof beam selection.
    for level,z in enumerate(LEVELS[1:],1):
        for i in range(6):
            for off in [120,240]:
                x=i*360+off
                for j in range(4):
                    a=[x,j*360,z]; b=[x,(j+1)*360,z]
                    pent=level==6 and 720<x<1440 and j==1; sec='W18X40' if pent else 'W30X99'
                    ref='members/roof-penthouse-infill-W18X40' if pent else f'members/infill-{"roof" if level==6 else "floor"}-W30X99'
                    m.profile(sec); d=m.profiles[sec]['dimensions']['d']
                    supports=[beams[((i*360,p[1],z),((i+1)*360,p[1],z))] for p in [a,b]]
                    offsets=[[0,m.profiles[supports[0]['profile_id']]['dimensions']['tw']/2+1.5,-d/2], [0,-m.profiles[supports[1]['profile_id']]['dimensions']['tw']/2-1.5,-d/2]]
                    bm=m.member(f'INF-L{level}-{i}-{off}-{j}',a,b,sec,'infill',[ref],level,material='steel',offsets=offsets,
                        cope={'ends':['start','end'],'depth_in':1.75,'length_in':6,'basis':'connections/conn-infill-W30X99; applicability to penthouse requires confirmation' if pent else 'connections/conn-infill-W30X99'})
                    for idx,p in enumerate([a,b]):
                        jid=bm['id']+(':start' if idx==0 else ':end'); m.joint(jid,p,[(bm['id'],'start' if idx==0 else 'end')],[supports[idx]['id']])
                        m.connect(jid,['connections/conn-infill-W30X99'],template='hr_infill_shear_plate_cope')
        m.panel(f'SLAB-L{level}',[[0,0,z+3],[2160,0,z+3],[2160,1440,z+3],[0,1440,z+3]],3.25,'concrete','floor',level=level,basis='cfg floor system; openings awaiting architecture')
        m.panel(f'DECK-L{level}',[[0,0,z],[2160,0,z],[2160,1440,z],[0,1440,z]],3,'deck','deck_envelope',level=level,scope='delegated')
    # Counts/spacing of studs are included as source-backed repeated assemblies,
    # without fabricating individual deck-rib-dependent stud positions.
    for bm in list(m.members.values()):
        if bm['kind'] not in ('girder','infill','moment_beam'): continue
        sec=bm['profile_id']; level=bm['level']
        if bm['kind']=='moment_beam': count=None; specification='3/4 in studs @12 in, strictly outside RBS protected zones'
        else:
            count=({'W33X130':38,'W30X99':36} if level<6 else {'W24X62':44,'W30X99':58}).get(sec)
            specification='3/4 in headed studs; rib-dependent positions by deck/fabricator' if count else 'Local non-composite penthouse member'
        bm['stud_assembly']={'count':count,'diameter_in':.75,'specification':specification,'source':'design_context/composite_design'}
        if bm['kind']=='moment_beam':
            rec=bm['design_record_ids'][0]; spacing=m.record(rec)['smf_beam']['brace_spacing_in']; a,b=bm['axis']; direction=unit(sub(b,a))
            for s in points(spacing,360-spacing,spacing):
                point=add(add(a,mul(direction,s)),[0,0,-m.profiles[sec]['dimensions']['d']])
                jid=f'BRACE-REQUIRED-{bm["id"]}-{s:g}'
                m.joint(jid,point,[],[bm['id']])
                m.connect(jid,[rec],template='hr_required_bottom_flange_brace',representation='Required attachment at source brace spacing; kicker section and attachment geometry unresolved')
    for label,party in source['design_context']['capacity_design']['delegated_design'].items(): m.interface('HR-'+label,party,label)
    m.item('HR-OPENINGS','Stair, lift and shaft openings need architectural dimensions and locations','missing',
        'cfg irregularity_statements.H3 confirms openings exist; no set-out in the completed job. Gross slab planes are explicitly uncut.')
    m.item('HR-SETOUT','Review top-of-steel datums, shear-plate vertical alignment and column bases','proposal',
        'Analysis elevations are workpoints; the detail source does not give all vertical set-out.',proposed='Level Z is top of steel; shear bolt groups centred on beam web; fixed bases embedded 96 in; gravity steel starts above 2 in grout and 1-5/8 in plate.')
    m.item('HR-PENTHOUSE','Confirm local penthouse girder/infill placements and their connection applicability','proposal',
        'Source gives Grids 3-5/B-C and local W27X84/W18X40 designs but no occurrence plan or matching connection record.',
        proposed='Four W27X84 X girders at B/C and four W18X40 Y infills within the zone; typical shear details are review references only.')
    m.item('HR-BASE-STUDS','Embedded-base stud layout contains conflicting count/spacing wording','source_conflict',
        'W36X395 base describes 48 studs, two rows of 24 at 6 in, in a 12 in zone. Retain the record; do not invent a resolved stud pattern.')
    m.item('HR-DETAILS','Resolve beam kickers, RBS erection tabs, splice plate extents and deck attachments','missing',
        'Design specifications and connection occurrences are retained. Geometry absent from source is not manufactured; these details remain visible in the connection schedule.')
    m.item('HR-SEPARATION','Locate the existing hospital interface and verify its 14 in seismic joint','missing',
        'Source specifies 14 in clearance but not which building face; existing-wing displacement confirmation is required.')
    return m.finish({
        'primary_members':{'complete':True,'basis':'35 columns split at the two physical splice elevations, 348 analysed beams; all 558 analysis elements mapped by full or fractional intervals.'},
        'secondary_members':{'complete':False,'basis':'288 infill beams and deck/slab envelopes placed; stud counts retained; precise kicker and deck attachment set-out pending.'},
        'connections':{'complete':False,'basis':'All source connection families assigned to physical occurrences; missing shop/placement dimensions listed for coordination.'},
        'openings':{'complete':False,'basis':'Known stair/lift/shaft openings lack architectural set-out.'}})
