"""Full 23-frame warehouse with scheduled secondary steel and end walls."""
import math
from .model import Model,add,sub,mul,unit,cross,box,cylinder,points


def roof(x): return 240+min(x,720-x)*.2


def build(source,catalog):
    m=Model(source,catalog,'cfs16_portal_warehouse')
    main=m.builtup('PORTAL-4x1400S300-118','1400S300-118',4,gap=.375,pair_spacing=6.375)
    posts=m.builtup('POST-2x800S250-97','800S250-97',2)
    by_frame={}
    for c in source['physical']['members']:
        fi=int(c['id'].split(':')[2]); a,b=c['axis']; iscol=c['kind']=='column'
        bm=m.member(c['id'],a,b,main,'column' if iscol else 'rafter',[f'members/frame-{"col" if iscol else "raf"}'],
            analysis_ids=c['analysis_ids'],local_y=[0,1,0],offsets=[[0,0,2.25 if iscol else 0],[0,0,0]], frame=fi)
        by_frame.setdefault(fi,[]).append(bm)
    for fi,rows in by_frame.items():
        grouped={}
        for bm in rows:
            for i,end in enumerate(['start','end']): grouped.setdefault(tuple(bm['axis'][i]),[]).append((bm['id'],end))
        for point,ends in grouped.items():
            x,y,z=point; jid=f'FRAME-{fi}-{x:g}-{z:g}'; m.joint(jid,point,ends)
            if z==0:
                m.connect(jid,['anchorage/base-anchor'],[box('base-plate',[x-7,y-8,1.5],[14,16,.75])], 'cfs_portal_pinned_base')
                continue
            knee=x in (0,720); refs=['connections/conn-knee' if knee else 'connections/conn-apex']; nrows=4 if knee else 3; parts=[]
            # Two independent web-pair bolt groups on each leg. Bolt layout is
            # dimensioned by the source; plate outer polygon remains a review
            # envelope until the bracket outline/cutbacks are supplied.
            for mid,end in ends:
                bm=m.members[mid]; sign=1 if end=='start' else -1; d=mul(unit(sub(bm['axis'][1],bm['axis'][0])),sign)
                across=unit(cross([0,1,0],d))
                for pair,off in enumerate([-3.1875,3.1875]):
                    o=add(list(point),add([0,off+.1875,0],add(mul(d,0),mul(across,-6))))
                    parts.append(box(f'plate-envelope-{mid}-{pair}',o,[12,(nrows-1)*3+4,.375],across,d))
                    for row in range(nrows):
                        for col in range(3):
                            p=add(list(point),add([0,off-.5,0],add(mul(d,2+3*row),mul(across,-4+4*col))))
                            parts.append(cylinder(f'bolt-{mid}-{pair}-{row}-{col}',p,[0,1,0],.375,1,material='boltA325'))
            m.connect(jid,refs,parts,'cfs_knee_3x4' if knee else 'cfs_apex_3x3',geometry_scope='bolt pattern and plate group envelope; outer gusset cut shape unresolved')
    def add_secondary(mid,a,b,section,kind,rid,**kw):
        bm=m.member(mid,a,b,section,kind,[rid],**kw)
        m.ends(bm,[rid],template='cfs_scheduled_'+kind)
        return bm
    # Each purlin/girt is a span piece with the source 24-in extension on each
    # side of an interior support. This is a real overlap, not an analysis mesh.
    for bay in range(22):
        ya=bay*150; yb=ya+150; lo=ya-(24 if bay else 0); hi=yb+(24 if bay<21 else 0)
        for xi in range(13):
            x=60*xi; slope=.2 if x<=360 else -.2
            normal=unit([-slope,0,1]); width=unit([-1,0,-slope]); shift=mul(normal,11)
            a=add([x,lo,roof(x)],shift); b=add([x,hi,roof(x)],shift)
            sec='800Z250-68' if bay in (0,21) else '800Z250-54'
            bm=add_secondary(f'PURLIN-{xi}-{bay+1}',a,b,sec,'purlin','schedules/sched-purlin',material='cfs55',local_y=width,
                lap_extensions_in=[24 if bay else 0,24 if bay<21 else 0],support_y_in=[ya,yb])
            if bay in (0,21) and x in (120,240,300,420,480,600):
                # Nested reinforcement from every post-top-kicker design row.
                add_secondary(f'NEST-{xi}-{bay+1}',add(a,mul(normal,.1)),add(b,mul(normal,.1)),sec,'purlin_nested','schedules/sched-endwall',material='cfs55',local_y=width,
                    nesting='0.1 in viewing separation proposed; actual nesting clearance needs manufacturer geometry')
        for side,x in enumerate([0,720]):
            sign=-1 if side==0 else 1
            for z in [72,144,216]:
                add_secondary(f'GIRT-{side}-{z}-{bay+1}',[x+sign*11,lo,z],[x+sign*11,hi,z],'800Z250-54','girt','schedules/sched-girt',material='cfs55',local_y=[0,0,sign])
            add_secondary(f'EAVE-{side}-{bay+1}',[x+sign*11,ya,240],[x+sign*11,yb,240],'800S250-68','eave_strut','schedules/sched-strap',local_y=[0,0,sign])
    # Exact source end-wall posts and door jamb coordinates (ft -> inches).
    stations=[0,120,240,276,444,480,600,720]
    for end,y in enumerate([0,3300]):
        for label,x in zip('ABCDEF',[120,240,276,444,480,600]):
            bm=add_secondary(f'END-{end}-{label}',[x,y,0],[x,y,roof(x)-7],posts,'endwall_post','schedules/sched-endwall',local_y=[1,0,0])
            bm['detail']='Pinned base / vertically slotted top clip; source endwall schedule rows'
        for z in [72,144,216,288]:
            for k,(a,b) in enumerate(zip(stations,stations[1:])):
                if z<192 and a==276: continue  # the 14 x 16 ft door stays open
                if roof(a)<z or roof(b)<z: continue
                sec='800Z250-54' if k in (0,6) else '800Z250-97'
                add_secondary(f'EGIRT-{end}-{z}-{k}',[a,y+(-11 if end==0 else 11),z],[b,y+(-11 if end==0 else 11),z],sec,'endwall_girt','schedules/sched-endwall',material='cfs55',local_y=[0,0,1])
        add_secondary(f'HEADER-{end}',[276,y,195],[444,y,195],'HSS6X4X3/16','door_header','schedules/sched-endwall',local_y=[0,1,0],material='tube')
        panel=m.panel(f'ENDWALL-{end}',[[0,y,0],[720,y,0],[720,y,240],[360,y,312],[0,y,240]],.018,'deck','cladding_envelope',
            ['schedules/sched-endwall'],scope='delegated',display='outline only; no manufacturer panel profile implied')
        m.ph['openings'].append(dict(id=f'DOOR-{end}',host_id=panel['id'],vertices=[[276,y,0],[444,y,0],[444,y,192],[276,y,192]],kind='overhead_door',design_record_ids=m.refs(['schedules/sched-endwall'])))
    # Brace diagonals. Crossing tension straps occupy distinct planes.
    def xbrace(prefix,corners,profile,offset):
        for n,(i,j) in enumerate([(0,2),(1,3)]):
            shift=mul(offset,n+.5)
            add_secondary(f'{prefix}-{n}',add(corners[i],shift),add(corners[j],shift),profile,'strap','schedules/sched-strap',material='cfs_strap')
    for bay in [0,21]:
        ya=bay*150; yb=ya+150
        for x,sign in [(0,-1),(720,1)]:
            xbrace(f'SIDE-X-{bay}-{x}',[[x,ya,0],[x,yb,0],[x,yb,240],[x,ya,240]],m.flat(6,.1242),[sign*.25,0,0])
        for x in range(0,720,120):
            xbrace(f'ROOF-X-{bay}-{x}',[[x,ya,roof(x)+7],[x+120,ya,roof(x+120)+7],[x+120,yb,roof(x+120)+7],[x,yb,roof(x)+7]],m.flat(3.5,.1017),[0,0,.25])
    for end,y in enumerate([0,3300]):
        for a,b in [(0,240),(480,720)]:
            xbrace(f'END-X-{end}-{a}',[[a,y,0],[b,y,0],[b,y,roof(b)],[a,y,roof(a)]],m.flat(3,.0713),[0,(-.25 if end==0 else .25),0])
    # Scheduled 30-in flange kickers at known girt and alternate purlin lines.
    # Connection offsets/handedness are explicit review proposals, never inferred
    # from the 2-D analysis section's weak-axis inertia.
    for fi in range(1,24):
        y=(fi-1)*150
        for x in [0,720]:
            for z in [72,144,216]:
                for pair in [-1,1]:
                    dx=-14 if x==0 else 14; dy=pair*math.sqrt(30**2-dx**2)
                    add_secondary(f'KICK-C-{fi}-{x}-{z}-{pair}',[x-dx/2,y+pair*3.1875,z],[x+dx/2,y+pair*3.1875+dy,z],
                        'L2x2x1/8','flange_kicker','schedules/sched-strap',material='angle')
        for x in [120,240,480,600]:
            normal=unit([-.2 if x<360 else .2,0,1])
            for pair in [-1,1]:
                a=add([x,y+pair*3.1875,roof(x)],mul(normal,-7)); b=add(a,add(mul(normal,14),[0,pair*math.sqrt(30**2-14**2),0]))
                add_secondary(f'KICK-R-{fi}-{x}-{pair}',a,b,'L2x2x1/8','flange_kicker','schedules/sched-strap',material='angle')
    mats={r['id']:r for r in m.ph['materials']}
    for r,mid in zip([r for r in source['design_records'] if r['table']=='materials'],['cfs50','cfs55','cfs_strap','plate','boltA325','screw','anchor','weld','deck']):
        mats[mid].update(specification=r['data']['spec'],design_record_ids=m.refs([r['id']]))
    m.interface('CFS16-FOUNDATION','Foundation engineer','Anchor reinforcement, concrete failure modes and footing geometry; source anchorage handoff', ['anchorage/base-anchor'])
    m.interface('CFS16-CLADDING','Panel and door supplier','26 ga panel profile, guide attachments, personnel doors and weathering details', ['schedules/sched-purlin','schedules/sched-endwall'])
    m.item('CFS16-DOORS','Locate personnel doors and coordinate side-wall framing interruptions','missing',
        'Original brief specifies personnel doors but provides no count, size or locations. Both dimensioned overhead doors are modelled.')
    m.item('CFS16-FRAME-SETOUT','Confirm clear-span datum, built-up pair layout and member cutbacks','proposal',
        'Brief says 60 ft clear; analysis axes are 60 ft apart. Group geometry follows explicit 3/8 in gusset gaps.',
        proposed='Retain analysis worklines for review; 6.375 in pair centres, 3/8 in web gaps; final cutbacks/mitres remain unissued.')
    m.item('CFS16-BRACKETS','Supply knee/apex gusset outer polygons and base-gusset bolt coordinates','missing',
        'Designed bolt counts, pitches, edge distances, plate thicknesses and materials are retained and knee/apex bolt groups displayed. Rectangles bound groups; they are not approved gusset cut shapes.')
    m.item('CFS16-SECONDARY-SETOUT','Confirm secondary offsets, nested Z fit and flange-brace endpoints','proposal',
        'Source gives sections, spacing, laps and flange-brace lengths, but not every attachment workpoint.',
        proposed='Purlins/girts outside the frame flanges, source 24 in lap extensions; 30 in kickers at source stations. Additional knee/apex and post-top braces require coordinated attachment points.')
    m.item('CFS16-END-BRACING','Confirm end-wall strap bays and corner girt zoning','proposal',
        'Source specifies two braced bays per end wall; review places them outside the door in the 0–20 ft and 40–60 ft side zones.')
    return m.finish({
        'primary_members':{'complete':True,'basis':'All 23 portals, 92 primary members and 414 analysis segments; 12 scheduled end-wall posts and two HSS headers.'},
        'secondary_members':{'complete':False,'basis':'All purlin/girt spans, laps, eave struts, three bracing planes and regular flange kickers modelled; knee/apex/post-top attachment set-out pending.'},
        'connections':{'complete':False,'basis':'Source connection and schedule records linked to occurrences; plate outlines and remaining brace attachment positions unresolved.'},
        'openings':{'complete':False,'basis':'Two 14 x 16 ft overhead doors placed from end-wall design. Personnel doors need architectural set-out.'}})
