"""Physical set-out of the second wall batch, independent of fitted analysis lines."""
import re
from .review_model import MIL
KEYS={'cfs2','cfs4','cfs6','cfs9','cfs12'}

def prepare(b):
    if b.key=='cfs2':
        for line in b.cfg['lines_y']:
            n=line.get('bays_per_seg',1)
            if n>1:line['segments']={k:[[line['bay_w'],h] for w,h in rows for j in range(n)] for k,rows in line['segments'].items()}
    b.note('PHYSICAL-HEIGHTS','A: floor finish levels retain the source story heights. Wall tops are reduced by the scheduled floor build-up; where the analysis used full story heights for its wall panels this is an explicit physical fit, not a revised design calculation. Clear rod spaces, short blocking and local plate fits are A.')

def depth(b,k):
    roof=k==len(b.cfg['heights_ft'])
    if b.key=='cfs2':return 12*b.config['ROOF_DEPTH_FT' if roof else 'FLOOR_DEPTH_FT']
    if b.key=='cfs12':return 14.4
    if b.key=='cfs4':return 12.75 if roof else 16
    if b.key=='cfs9':return 8.72 if roof else 12.22
    return 10.75 if roof else 12.25

def locations(b,d,line,k,ranges):
    from .review_cfs import spaced_segments
    name=line['name'];widths=[s[0] for s in line['segments'][str(k)]];n=len(widths)
    if b.key=='cfs2' and d=='Y':
        # Source specifies two continuous multi-bay walls with shared
        # interior posts. Keep each group contiguous and centre it in its wing.
        half=n//2;result=[]
        for lo,hi,ws in ((0,31,widths[:half]),(37,68,widths[half:])):
            x=(lo+hi-sum(ws))/2
            for width in ws:result.append((x,x+width));x+=width
        return result
    if b.key=='cfs6' and name in ('Y0','YLE'):ranges=[(0,152)]
    if b.key=='cfs6' and name in ('YLC1','YLC2'):ranges=[(0,90)]
    if b.key=='cfs6' and name.startswith('P'):ranges=[(90,152)]
    if b.key=='cfs9':
        if d=='X' and name in ('XP3','XP4','XN'):ranges=[(0,62),(148,210)]
        if name=='XCY':ranges=[(62,148)]
        if name in ('YW62','YE148'):ranges=[(0,130)]
    if b.key=='cfs12' and name[1:] in ('45','105'):ranges=[(0,150)]
    if len(ranges)==1:return spaced_segments(*ranges[0],widths)
    # Equal wing runs have equal source bay counts; no panel crosses the courtyard.
    if len(ranges)==2 and n%2==0:return spaced_segments(*ranges[0],widths[:n//2])+spaced_segments(*ranges[1],widths[n//2:])
    raise ValueError('Unresolved physical wall runs '+b.key+' '+name)

def stud(b,d,name,k,props,ordinary):
    from .review_cfs import story_value
    if b.key=='cfs2':
        rid='stud-ext-long' if name in ('XS','XN') else 'stud-corridor' if name in ('XCS','XCN') else 'stud-end-walls' if name in ('YW','YE') else 'stud-demising'
        row=story_value(next(r for r in b.raw['studs'] if r['id']==rid),k)
        row['section']=('600S162-33' if name in ('XS','XN') else '600S162-'+('43' if k<=3 else '33') if name in ('XCS','XCN') else ('2X' if k<=3 else '')+'600S200-43');row['spacing_in']=16;return row
    if b.key=='cfs4':return dict(ordinary,section='600S162-54' if name in ('XS','XN') else '600S162-68' if k<=2 else '600S200-54',spacing_in=12)
    row=story_value(ordinary,k);mil=round(props.get('t_stud_in',.054)*1000)
    if b.key in ('cfs9','cfs12'):row['section']='600S162-'+str(mil)
    row['spacing_in']=12 if b.key=='cfs12' else 16
    return row

def bearing_lines(b):
    if b.key=='cfs2':return [(1,x*12) for x in range(0,205,17)]
    if b.key=='cfs6':return [(1,x*12) for x in (0,14,28,34,48,62)]+[(0,y*12) for y in (90,104,118,124,138,152)]
    if b.key=='cfs9':return [(1,x*12) for x in (0,15,30,45,53.5,62,77,92,105,118,133,148,156.5,165,180,195,210)]
    if b.key=='cfs12':return [(1,x*12) for x in (0,15,30,45,60,66,72,75,90,105,120,135,150)]
    return []

def floors(b,outline,levels):
    from .review_cfs import frange,intersections,simple_truss,section
    rows={r['id']:r for r in b.raw['framing']}
    def joist(mid,pid,axis,station,lo,hi,z,k,rid,spacing):
        d=b.depth(b.profile(pid));aa=[lo,station,z-d/2] if axis==0 else [station,lo,z-d/2];dd=[hi,station,z-d/2] if axis==0 else [station,hi,z-d/2]
        refs=[b.record('framing',rid)]
        checked=b.records.get('gravity_framing/'+rid)
        if checked and section(checked['data'].get('section'),'')==pid and abs(hi-lo-12*checked['data'].get('span_ft',-1))<.01:
            refs.append(checked['id'])
        m=b.member(mid,pid,'joist',aa,dd,k,'A',records=refs);b.ends(m,'review_cfs_joist',refs,parameters={'spacing':spacing,'floor_depth':depth(b,k),'concrete_slab':b.key in ('cfs2','cfs4')})
    for k,z in enumerate(levels[1:],1):
        roof=k==len(levels)-1;finish=(.6 if roof else 3.5) if b.key=='cfs2' else (.75 if roof else 4) if b.key=='cfs4' else 2.4 if b.key=='cfs12' else .72 if roof else 2.22
        b.panel(f'FLOOR-{k}','roof' if roof else 'floor',[[x*12,y*12,z] for x,y in outline],finish,k,'A')
        if b.key=='cfs2':
            for y in frange(0,816+.1,24):
                if 372<y<444:continue
                for j,x in enumerate(range(0,204,17)):
                    simple_truss(b,f'OW-{k}-{y}-{j}',0,y,x*12,(x+17)*12,z-finish-10.75,9.5,k,'250S162-68','250S137-43',24,flat=True)
            stations=list(frange(0,2448+.1,24))
            for _,position in bearing_lines(b):
                if any(abs(position-x)<.001 for x in stations):continue
                stations.append(position)
                b.changes.append(dict(kind='adopted_corridor_wall_joist',level=k,station_in=position,member_id=f'COR-{k}-{position}',
                    basis='A: additional corridor joist on the existing bearing-wall line where it misses the regular 24-in grid. Match the selected 1200S162-68 corridor section and 6-ft span, retaining the source grid. Added wall-load transfer and squash/blocking capacity remain separately required.'))
            for x in sorted(stations):joist(f'COR-{k}-{x}','1200S162-68',1,x,372,444,z-finish,k,'joist-corridor',24)
            continue
        if b.key=='cfs6':
            regions=[(0,62,0,90,0,[0,14,28,34,48,62]),(0,180,90,152,1,[90,104,118,124,138,152])]
            for ri,(x0,x1,y0,y1,axis,supports) in enumerate(regions):
                if roof and ri==1:
                    for x in frange(0,2160+.1,24):simple_truss(b,f'BAR-ROOF-{x}',1,x,1080,1824,z,124,k,'2X600S162-68','2X600S162-54',96)
                    continue
                for station in frange((y0 if axis==0 else x0)*12,(y1 if axis==0 else x1)*12+.1,16):
                    for j,(lo,hi) in enumerate(zip(supports,supports[1:])):
                        rid='joist-corridor' if hi-lo==6 else 'joist-amenity-roof' if roof else 'joist-unit';pid=section(rows[rid]['section']);joist(f'J-{k}-{ri}-{station}-{j}',pid,axis,station,lo*12,hi*12,z-finish,k,rid,16)
            continue
        rid='joist-roof' if roof and 'joist-roof' in rows else 'joist-floor';pid=section(rows[rid]['section']);spacing=24 if roof and b.key=='cfs12' else 12 if b.key in ('cfs4','cfs12') else 16
        support_positions=[p for axis,p in bearing_lines(b) if axis==1] or [i*336 for i in range(6)]
        stations=list(frange(0,max(y for x,y in outline)*12+.1,spacing))
        if b.key=='cfs12':
            from .review_supplements import wall_axis_framing_stations
            stations=wall_axis_framing_stations(b,stations,0,k,f'J-{k}-'+'{station}-','source-family joist')
        for station in stations:
            for run,(lo,hi) in enumerate(intersections(outline,0,station/12)):
                supports=sorted({lo*12,hi*12}|{p for p in support_positions if lo*12<p<hi*12})
                for j,(a,d) in enumerate(zip(supports,supports[1:])):joist(f'J-{k}-{station}-{run}-{j}',pid,0,station,a,d,z-finish,k,rid,spacing)
    b.note('FLOOR-SUPPLEMENTS','S: scheduled joist/truss section families and spacings. A: extra bearing lines needed to realise the scheduled spans, local datum fitting, floor finish geometry and any source-unspecified roof member selection. L-plan units span exterior-to-mid-unit-to-corridor walls; bar-roof truss internals remain A supplier coordination geometry. No joist is extended unsupported through a courtyard.')

def connections(b):
    from .assembly_templates import NUMBER,number
    lookup={m['id']:m for m in b.members}
    def attach(c,table,name,first=False):
        rid=b.record(table,name)
        if rid and rid not in c['design_record_ids']:
            c['design_record_ids'].insert(0,rid) if first else c['design_record_ids'].append(rid);b.used_records.add(rid)
    for c in b.connections:
        m=lookup[c['member_ids'][0]];family=c['detail_ref']['id'];par=c.setdefault('parameters',{});k=m['level'];line=m['id'].split('-L')[0];direction='X' if line.startswith('X') else 'Y'
        if b.key=='cfs2':
            if family=='review_cfs_strap':
                dims=b.profiles[m['profile_id']]['dimensions'];mil=min(MIL,key=lambda n:abs(MIL[n]-dims['thickness']));attach(c,'connections',f'conn-strap-end-{dims["width"]:g}x{mil}',True)
            if family in ('review_cfs_floor','review_cfs_joist'):attach(c,'connections','conn-rim-squash-block')
            if family=='review_roof_seat' and k==6:attach(c,'connections','conn-uplift-roof-truss')
        if family in ('review_cfs_floor','review_cfs_sill','review_cfs_joist') and b.key in ('cfs4','cfs9'):
            use=line
            if b.key=='cfs4':use={'XN':'XS','XCN':'XCS','Y140':'Y0','Y56':'Y28','Y84':'Y28','Y112':'Y28'}.get(line,line)
            attach(c,'connections','conn-floor-transfer-'+direction+'-'+use,True);attach(c,'connections','conn-deck-to-wall')
        if family=='review_cfs_hold_down' and b.key in ('cfs4','cfs9'):
            if k>1:attach(c,'connections','conn-rod-'+('end' if line in ('Y0','Y140') else 'typ')+'-s'+str(k) if b.key=='cfs4' else 'conn-rod-'+direction+'-s'+str(k))
            raw=next((r for r in b.raw['holddowns'] if r['id']=='hd-'+direction+'-'+line),{})
            match=re.search(r'bearing plates ([\d/, .-]+) in\.',raw.get('selection',''))
            if match:
                sizes=re.findall(NUMBER,match[1]);par['bearing_thickness']=number(sizes[k-1]) if k<=len(sizes) else .5
        if b.key=='cfs6' and family=='review_cfs_joist' and k==5:attach(c,'connections','conn-amenity-uplift')
        if b.key=='cfs10' and family=='review_roof_seat':attach(c,'connections','conn-roof-truss-uplift')
