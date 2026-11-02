"""T-plan: source-positioned strap walls plus gravity framing and roof interfaces."""
import re
from fractions import Fraction
from .model import Model,add,sub,mul,unit,cross,box,cylinder,points

MIL={43:.0451,54:.0566,68:.0713,97:.1017,118:.1242,137:.1445}
LEVELS=[0,120,236.004,352.008,468.012]
NATURAL={'SS':0,'HS':84,'HN':130,'HW':0,'SW':47,'SE':93,'HE':140}


def frac(s): return sum(float(Fraction(x)) for x in s.replace('-',' ').split())


def build(source,catalog):
    m=Model(source,catalog,'cfs8_t_plan_housing')
    layouts={r['data']['line']:r for r in source['design_records'] if r['table']=='braced_bay_layout'}
    evidence={(r['line'],r['story']):r for r in source['layout_evidence']['wall_lines']}
    toptracks={}; chord_stations={}
    def pos(direction,station,along,z): return [along,station,z] if direction=='X' else [station,along,z]
    def scheduled(mid,a,b,profile,kind,refs,connrefs=None,level=1,**kw):
        bm=m.member(mid,a,b,profile,kind,refs,level,**kw)
        m.ends(bm,connrefs or refs,template='cfs_'+kind)
        return bm
    # Braced wall geometry comes directly from the corrected native exporter.
    for src in source['physical']['panels']:
        _,_,direction,line,_,story,_,bay=src['id'].split(':'); story=int(story); bay=int(bay)
        verts=src['vertices']; p0,p1,p2,p3=verts; along=unit(sub(p1,p0)); normal=cross(along,[0,0,1])
        wall_ref=f'wall_lines/wall-{direction}-{line}-s{story}'; data=m.record(wall_ref)
        match=re.search(r': ([\d.]+) in\. x (\d+) mil',data['selection']); assert match,data['selection']
        width,mil=float(match[1]),int(match[2]); strap=m.flat(width,MIL[mil])
        conn=f'connections/conn-strap-end-{width:g}x{mil}'
        chord_ref=f'studs/chord-{direction}-{line}'; chordrow=next(r for r in m.record(chord_ref)['rows'] if r['story']==story)
        match=re.fullmatch(r'(\d+) x (\d{3,4}S\d{3}-\d+) back-to-back',chordrow['section']); assert match
        n,section=int(match[1]),match[2]; m.profile(section)
        bracket=f'connections/conn-rod-bracket-{direction}-{line}'; spec=m.record(bracket)['selection']
        gap=4.75 if '4-3/4' in spec else (4.25 if '4-1/4' in spec else 4)
        chordprofile=m.builtup(f'{line}-S{story}-CHORD',section,n,gap=gap if n==2 else 0,
            pair_spacing=2*m.profiles[section]['dimensions']['b']+gap if n==4 else None)
        m.panel(f'BAY-{direction}-{line}-{story}-{bay}',verts,6,'envelope','strap_wall_zone',[wall_ref,layouts[line]['id']],story,
            display='outline only; no solid wall or structural sheathing',assembly='Studs, chord packs and four strap diagonals',scope='assembly')
        for end,(bottom,top) in enumerate([(p0,p3),(p1,p2)]):
            mid=f'CHORD-{line}-{story}-{bay}-{end}'
            chord_stations.setdefault((line,story),[]).append(bottom[0 if direction=='X' else 1])
            bm=scheduled(mid,bottom,top,chordprofile,'chord',[chord_ref],
                [bracket,f'holddowns/hd-{direction}-{line}'],story,local_y=along)
            hd=m.record(f'holddowns/hd-{direction}-{line}'); rodrow=next(r for r in hd['rows'] if r['story']==story)
            diameter=frac(rodrow['rod'].split(' in.')[0]); rid=m.custom_profile(f'ROD-{diameter:g}','round',{'d':diameter},
                basis='Solid rod outer diameter from hold-down source')
            # Rod through the explicit pack opening, not through solid stud webs.
            rodtop=pos(direction,bottom[1 if direction=='X' else 0],bottom[0 if direction=='X' else 1],LEVELS[story])
            rod=scheduled('ROD-'+mid,bottom,rodtop,rid,'hold_down_rod',[f'holddowns/hd-{direction}-{line}'],[bracket],story,material='rod')
            thickness=1 if gap==4.75 else (.875 if gap==4.25 else .625)
            origin=add(top,add(mul(along,-gap/2-.25),mul(normal,-2.75)))
            connection=next(c for c in m.ph['connections'] if c['joint_id']==mid+':end')
            connection['parts']=[box('rod-bearing-plate',origin,[gap+.5,5.5,thickness],along,normal)]
            connection['geometry_scope']='Source plate thickness/width and nut clearance; side-plate height and screw pattern remain unresolved'
            if story<4:
                rows=m.record('framing/chord-squash-floor')['rows']; row=next(r for r in rows if r['member']==f'chord-{direction}-{line}' and r['level']==story)
                nm=re.fullmatch(r'(\d+) x (\d{3,4}S\d{3}-\d+)',row['blocks']); bn,bs=int(nm[1]),nm[2]
                bprof=m.builtup(f'BLOCK-{line}-{story}',bs,bn,gap=gap if bn==2 else 0,pair_spacing=(2*catalog[bs]['dimensions']['b']+gap) if bn==4 else None)
                scheduled('BLOCK-'+mid,top,add(top,[0,0,row['block_length_in']]),bprof,'squash_block',['framing/chord-squash-floor'],
                    [f'connections/conn-floor-{direction}-{line}'],story,local_y=along)
        for face in [-1,1]:
            for diagonal,(a,b) in enumerate([(p0,p2),(p1,p3)]):
                offset=mul(normal,face*(3+MIL[mil]*(diagonal+.5)))
                a,b=add(a,offset),add(b,offset); d=unit(sub(b,a)); w=unit(cross(normal,d))
                scheduled(f'STRAP-{line}-{story}-{bay}-{face}-{diagonal}',a,b,strap,'strap',[wall_ref],[conn],story,local_y=w)
        # Sill anchor occurrences: source count and size; equal layout is a named
        # proposal since end distances are not given in the calculation record.
        if story==1:
            anchor_ref=f'anchorage/anch-{direction}-{line}'; ad=m.record(anchor_ref)['selection']
            count=4 if '4 x 3/4' in ad else 6; dia=.75 if count==4 else (.875 if '7/8' in ad else 1)
            refs=[anchor_ref]; parts=[]
            for k in range(count):
                p=add(p0,mul(sub(p1,p0),(k+.5)/count))
                parts.append(cylinder(f'anchor-{k}',add(p,[0,0,-7]),[0,0,1],dia/2,8,material='anchor',kind='anchor'))
                parts.append(box(f'washer-{k}',add(p,add(mul(along,-1.5),mul(normal,-1.5))),[3,3,.25],along,normal))
            jid=f'CHORD-{line}-{story}-{bay}-0:start'
            m.ph['connections'].append(dict(id='SILL-'+jid,joint_id=jid,scope='designed',design_record_ids=m.refs(refs),parts=parts,detail_ref={'id':'sill_anchor_group','revision':'1'},
                representation='Source count/diameter/embedment; equal-spacing proposal',geometry_scope='placement proposal'))
    # Wall stud set-out: source party-wall spacing and real exterior boundaries.
    wall_specs=[('HN','X',130,0,140,'stud-ext-roof-bearing'),('HS','X',84,0,140,'stud-ext-roof-bearing'),
        ('SS','X',0,47,93,'stud-ext-end-walls'),('HW','Y',0,84,130,'stud-ext-end-walls'),('HE','Y',140,84,130,'stud-ext-end-walls'),
        ('SW','Y',47,0,84,'stud-ext-walkway-SW'),('SE','Y',93,0,84,'stud-ext-roof-bearing')]
    wall_specs += [(f'PH{i}','Y',i*14,84,130,'stud-typ-bearing') for i in range(1,10)]
    wall_specs += [(f'PS{i}','X',i*14,47,93,'stud-typ-bearing') for i in range(1,6)]
    for line,direction,station,a,b,family in wall_specs:
        station*=12; a*=12; b*=12; along=[1,0,0] if direction=='X' else [0,1,0]
        for story in range(1,5):
            z=LEVELS[story-1]; clear=evidence[('HN',story)]['segments_in'][0][1]; top=z+clear
            rec=f'studs/{family}'; row=next(r for r in m.record(rec)['rows'] if r['story']==story); section=row['section']; mil=int(section.split('-')[-1])
            chord_locs=chord_stations.get((line,story),[])
            for idx,s in enumerate(points(a,b,16)):
                if any(abs(s-q)<8 for q in chord_locs): continue  # avoid ordinary studs through chord packs
                scheduled(f'STUD-{line}-{story}-{idx}',pos(direction,station,s,z),pos(direction,station,s,top),section,'stud',[rec],
                    ['connections/conn-stud-to-track'],story,local_y=along,material='cfs33' if mil<=43 else 'cfs50')
            track=f'600T125-{mil}'
            for kind,zz,sgn in [('bottom_track',z,1),('top_track',top,-1)]:
                if kind=='top_track' and line in layouts: continue  # double drag tracks below replace this track
                # Track web lies in wall width horizontally, flanges point into studs.
                width=[0,0,sgn]; p0=pos(direction,station,a,zz); p1=pos(direction,station,b,zz)
                spans=[(a,b,track)]
                if kind=='bottom_track' and line in layouts:
                    bays=[p['vertices'] for p in source['physical']['panels'] if f':{line}:story:{story}:' in p['id']]
                    ranges=[(v[0][0 if direction=='X' else 1],v[1][0 if direction=='X' else 1]) for v in bays]
                    boundaries=sorted({a,b}|{q for rg in ranges for q in rg if a<q<b}); spans=[]
                    for lo,hi in zip(boundaries,boundaries[1:]):
                        in_bay=any(lo>=l and hi<=h for l,h in ranges)
                        gauge=97 if story==1 else int(re.search(r'to the (\d+) mil track',m.record(f'wall_lines/wall-{direction}-{line}-s{story}')['connection'])[1])
                        spans.append((lo,hi,f'600T125-{gauge}' if in_bay else track))
                for segment,(lo,hi,shape) in enumerate(spans):
                    tr=scheduled(f'TRACK-{line}-{story}-{kind}-{segment}',pos(direction,station,lo,zz),pos(direction,station,hi,zz),shape,kind,[rec],['connections/conn-stud-to-track'],story,local_y=width,
                        profile_origin='web-centre at horizontal bearing plane')
                if kind=='top_track': toptracks[line,story]=tr
            # Horizontal all-steel bridging through punchouts, source 48-in rows.
            for height in [48,96]:
                if height>=clear: continue
                scheduled(f'BRIDGE-{line}-{story}-{height}',pos(direction,station,a,z+height),pos(direction,station,b,z+height),
                    '150U050-54','stud_bridging',[rec],[rec],story)
                for idx,s in enumerate(points(a,b,96)):
                    target=s+48 if s+48<=b else s-48
                    pa=pos(direction,station,s,z+height); pb=pos(direction,station,target,z+height-48)
                    scheduled(f'BRIDGE-ANCHOR-{line}-{story}-{height}-{idx}',pa,pb,m.flat(1.5,.0566),'bridging_anchor',[rec],level=story,
                        local_y=unit(cross(([0,1,0] if direction=='X' else [1,0,0]),unit(sub(pb,pa)))))
    # Continuous double-track collectors are distinct source assemblies. They
    # replace the light top track where the source specifies a stronger drag line.
    for line,layout in layouts.items():
        direction=layout['data']['direction']; a,b=[float(v)*12 for v in layout['data']['line_extent_ft'].split('-')]
        station=NATURAL[line]*12; rec=f'collectors/collector-{line}-line'; data=m.record(rec)
        track=re.search(r'600T200-\d+',data['selection'])[0]
        for story in range(1,5):
            z=LEVELS[story-1]+evidence[line,story]['segments_in'][0][1]
            for ply in range(2):
                bm=scheduled(f'DRAG-{line}-{story}-{ply}',pos(direction,station,a,z+ply*MIL[int(track.split('-')[-1])]),
                    pos(direction,station,b,z+ply*MIL[int(track.split('-')[-1])]),track,'collector',[rec],
                    [f'connections/conn-floor-{direction}-{line}'],story,local_y=[0,0,-1])
                if ply==0: toptracks[line,story]=bm
    # Floor joists: 14-ft party-wall spans, 16-in transverse stations, 2.5-in
    # end bearing about wall centrelines. All lounge joists have the same section.
    for level in range(1,4):
        walltop=LEVELS[level-1]+evidence['HN',level]['segments_in'][0][1]; center=walltop+6
        perimeter=[('SS','X',0,564,1116,[0,1,0]),('SE','Y',1116,0,1008,[-1,0,0]),
            ('HS','X',1008,1116,1680,[0,1,0]),('HE','Y',1680,1008,1560,[-1,0,0]),('HN','X',1560,0,1680,[0,-1,0]),
            ('HW','Y',0,1008,1560,[1,0,0]),('HS','X',1008,0,564,[0,1,0]),('SW','Y',564,0,1008,[1,0,0])]
        for edge,(line,direction,station,a,b,opening) in enumerate(perimeter):
            # Interrupt the rim at each physical squash pack. The proposal uses
            # the pack footprint; its final fit allowance is an open review item.
            packs=[]
            for bm in m.members.values():
                if bm['kind']!='squash_block' or bm['level']!=level or not bm['id'].startswith('BLOCK-CHORD-'+line+'-'): continue
                s=bm['axis'][0][0 if direction=='X' else 1]
                if not a<=s<=b: continue
                from .geometry import strips
                bounds=[pt[0] for poly in strips(m.profiles[bm['profile_id']],m.profiles) for pt in poly]
                packs.append((max(a,s+min(bounds)),min(b,s+max(bounds))))
            cursor=a; segments=[]
            for lo,hi in sorted(packs):
                if lo>cursor: segments.append((cursor,lo))
                cursor=max(cursor,hi)
            if cursor<b: segments.append((cursor,b))
            rimdepth=catalog['1200T200-54']['dimensions']['d']
            for idx,(lo,hi) in enumerate(segments):
                scheduled(f'RIM-{level}-{edge}-{idx}',pos(direction,station,lo,walltop+rimdepth/2),pos(direction,station,hi,walltop+rimdepth/2),
                    '1200T200-54','rim_track',['studs/stud-typ-bearing','framing/chord-squash-floor'],['framing/chord-squash-floor','connections/diaphragm-across-walls'],level,local_y=opening)
        for wing,spans,stations in [('head',list(range(0,1681,168)),points(1008,1560,16)),('stem',list(range(0,1009,168)),points(564,1116,16))]:
            for bay,(a,b) in enumerate(zip(spans,spans[1:])):
                for idx,s in enumerate(stations):
                    pa,pb=([a+.5,s,center],[b-.5,s,center]) if wing=='head' else ([s,a+.5,center],[s,b-.5,center])
                    bm=scheduled(f'JOIST-{wing}-{level}-{bay}-{idx}',pa,pb,'1200S200-68','joist',
                        ['framing/joist-typ','framing/joist-lounge','gravity_framing/joist-typ','gravity_framing/joist-lounge'],['connections/conn-joist-bearing'],level)
                    for end,p in enumerate([pa,pb]):
                        scheduled(f'STIFF-{bm["id"]}-{end}',add(p,[0,0,-5.5]),add(p,[0,0,5.5]),'362S162-43','bearing_stiffener',
                            ['connections/conn-joist-bearing'],level=level,material='cfs33')
                if wing=='head': verts=[[a+3,1011,walltop+12],[b-3,1011,walltop+12],[b-3,1557,walltop+12],[a+3,1557,walltop+12]]
                else: verts=[[567,a+3,walltop+12],[1113,a+3,walltop+12],[1113,b-3,walltop+12],[567,b-3,walltop+12]]
                refs=[r['id'] for r in source['design_records'] if r['table']=='diaphragms' and r['data']['level']==level and (r['data']['segment'].startswith(wing) or (r['data']['segment'].startswith('center') and (wing=='stem' or (b>564 and a<1116))))]
                m.panel(f'FLOOR-{wing}-{level}-{bay}',verts,.71875,'wsp','floor',refs+['connections/diaphragm-across-walls'],level,
                    cutback='3 in from wall centre, sheathing excluded at bearing lines; architectural openings unresolved')
        for idx,y in enumerate(points(0,1008,16)):
            scheduled(f'WALK-{level}-{idx}',[492,y,walltop+4],[561,y,walltop+4],'800S200-54','walkway_joist',
                ['framing/joist-walkway','gravity_framing/joist-walkway'],['connections/conn-walkway-hanger'],level)
        scheduled(f'WALK-LEDGER-{level}',[561,0,walltop+6],[561,1008,walltop+6],'1200T200-54','ledger',
            ['connections/conn-walkway-hanger'],level=level)
        # Full-depth blocking plus twin straps in the T-junction collector zones.
        for line,direction,station,a,b in [('HS','X',1008,564,1116),('SW','Y',564,1008,1560),('SE','Y',1116,1008,1560)]:
            ref=f'collectors/collector-{line}-'+('junction' if line=='HS' else 'head')
            for ply in range(2):
                offset=(ply-.5)*8
                scheduled(f'T-DRAG-{line}-{level}-{ply}',pos(direction,station+offset,a,walltop+12),pos(direction,station+offset,b,walltop+12),
                    m.flat(8,.1017),'junction_collector',[ref],level=level)
            for idx,s in enumerate(points(a,b,16)[:-1]):
                scheduled(f'T-BLOCK-{line}-{level}-{idx}',pos(direction,station,s,walltop+6),pos(direction,station,min(s+16,b),walltop+6),
                    '1200S250-97','collector_blocking',[ref],level=level)
    # Joined roof envelope: five planar polygons, valley lines stop at ridge.
    z=LEVELS[4]; ridge=z+69
    roof_polys=[[(0,107),(140,107),(140,130),(0,130)],[(0,84),(47,84),(70,107),(0,107)],
        [(93,84),(140,84),(140,107),(70,107)],[(47,0),(70,0),(70,107),(47,84)],[(70,0),(93,0),(93,84),(70,107)]]
    roofrefs=[r['id'] for r in source['design_records'] if r['table']=='diaphragms' and r['data']['level']==4]
    for i,poly in enumerate(roof_polys):
        vertices=[]
        for x,y in poly:
            rise=(23-abs(y-107)) if i<3 else (23-abs(x-70))
            vertices.append([x*12,y*12,z+3*rise])
        m.panel(f'ROOF-{i}',vertices,.71875,'wsp','roof',roofrefs,4,scope='delegated',basis='3:12 slope governs per completed criteria_deviations; valley intersections derived geometrically')
    for wing,stations in [('head',points(0,1680,16)),('stem',points(0,1008,16))]:
        for i,s in enumerate(stations):
            if wing=='head' and 564<s<1116: continue  # supplier valley/girder-truss zone
            v=[[s,1008,z],[s,1560,z],[s,1284,ridge]] if wing=='head' else [[564,s,z],[1116,s,z],[840,s,ridge]]
            m.panel(f'TRUSS-{wing}-{i}',v,1.625,'envelope','truss_envelope',['connections/conn-uplift-truss-clip'],4,
                scope='delegated',display='outline only; no designed internal chords/webs represented')
            for side,p in enumerate(v[:2]):
                line=('HS' if side==0 else 'HN') if wing=='head' else ('SW' if side==0 else 'SE')
                track=toptracks[line,4]; jid=f'TRUSS-HEEL-{wing}-{i}-{side}'; m.joint(jid,p,[],[track['id']])
                m.connect(jid,['connections/conn-uplift-truss-clip'],template='cfs_delegated_truss_heel_clip')
    mats={r['id']:r for r in m.ph['materials']}
    for r,mids in zip([r for r in source['design_records'] if r['table']=='materials'],[['cfs50','cfs33'],['cfs50'],['screw'],['rod'],['plate'],['anchor'],['boltA325']]):
        for mid in mids:
            mats[mid].setdefault('source_specifications',[]).append(r['data']['spec'])
            mats[mid].setdefault('design_record_ids',[]).extend(m.refs([r['id']]))
    m.interface('CFS8-ROOF','Roof-truss supplier','Truss internals, valley/girder-truss load paths and supplier bracing; source completed design fixes 3:12 and 16 in centres',roofrefs)
    m.interface('CFS8-FOUNDATION','Foundation engineer','Continuous rod anchorage, couplers and foundation concrete/reinforcement',
        [r for r in m.records if r.startswith('anchorage/') or r.startswith('holddowns/')])
    m.interface('CFS8-WALKWAY','Walkway/architectural designer','Outer edge beam, posts, guard and foundation support: included as mass only in cfg; no member schedule supplied')
    m.item('CFS8-OPENINGS','Locate doors, windows, stairs and service openings before cutting studs or diaphragms','missing',
        'Brief gives braced-bay locations and party-wall spacing; no architectural opening set-out exists. Gross wall zones are not declared opening-free.')
    m.item('CFS8-CHORDS','Reconcile spaced chord packs with the physical rod-bracket clearances','source_conflict',
        'Bracket records require 4–4.75 in nut/wrench clearance. Chord records call the packs back-to-back. The display uses the stated clearance; spacers/interconnection and out-of-plane design must be confirmed.')
    m.item('CFS8-FLOOR','Resolve exact platform bearing, rim interruptions and floor datum tolerances','proposal',
        'cfg uses nominal 12.75 in floor depth and rounded clear heights; squash records use 12.11 in blocks, while replay catalogue track outside depth is 12.1981 in including fitting clearance. Rim pieces are interrupted at pack footprints.',
        proposed='Joists bear on clear wall tops; floor WSP sits above 12 in joists. Do not issue cut lengths until the complete stack is reconciled.')
    m.item('CFS8-ROOF-INTERFACE','Supply valley/girder-truss arrangement and roof support reactions','delegated',
        'Whole roof envelope and ordinary truss stations shown; no invented webs or crossing solid trusses at the T-junction.')
    m.item('CFS8-WALKWAY-EDGE','Provide the walkway outer edge beam, posts, guard and foundations','missing',
        'cfg includes their 20 plf mass, but the completed package only sizes 6 ft simple-span joists and the wall ledger/hangers. Outer support is shown as an unresolved interface.')
    m.item('CFS8-STUD-SETOUT','Review party-wall starting grid, chord replacements and framing intersections','proposal',
        '14 ft party-wall spacing is stated; the recipe starts at wing ends. Ordinary studs within 8 in of chord centres are replaced by the chord pack, pending panel detailing.')
    m.item('CFS8-DETAILS','Complete gusset outlines, side-plate extents, sill anchor set-out and bridging anchors','missing',
        'All 27 designed connection families are placed/referenced. Exact screw-group locations and plate boundaries omitted from sources remain coordination items; counts and specifications are retained.')
    return m.finish({
        'primary_members':{'complete':True,'basis':'88 physical braced bays at true plan coordinates, 176 story chord packs, 352 strap diagonals and 176 rod segments; all story section/rod schedules applied.'},
        'secondary_members':{'complete':False,'basis':'Party/exterior studs and tracks, floor/walkway joists, bearing stiffeners, interrupted rim tracks, collectors, bridging/anchors and roof envelopes populated; exact rim/platform fitting, walkway outer supports and supplier roof internals pending.'},
        'connections':{'complete':False,'basis':'All 27 connection families assigned; source missing plate/pattern coordinates and pack-spacing conflict remain explicit.'},
        'openings':{'complete':False,'basis':'Architectural opening locations absent; no false opening-free declaration.'}})
