"""Source-specific geometry for the last three fictional CFS review buildings."""
import re,math
from .review_model import MIL

KEYS={'cfs1','cfs5','cfs15'}

def prepare(b):
    if b.key=='cfs5':
        for line in b.cfg['lines_y']:
            n=line['bays_per_seg']
            line['segments']={k:[[line['bay_w'],h] for w,h in segs for _ in range(n)] for k,segs in line['segments'].items()}
    b.note('PHYSICAL-FLOORS','S: source floor finishes, joist sizes, bearing spans and stepped footprints. A: local datum fit uses the deepest floor member to set the wall top; shorter corridor joists have explicitly detailed bearing packers. No analysis is rerun.')

def depth(b,k):
    return (8.75 if k==4 else 12.25) if b.key=='cfs1' else 12 if b.key=='cfs5' else (12.75 if k==6 else 14.25)

def locations(b,d,line,k,ranges):
    from .review_cfs import spaced_segments
    name=line['name'];widths=[s[0] for s in line['segments'][str(k)]]
    if b.key=='cfs5' and d=='Y':
        if name in ('YW','YE'):return [(15+10*j,25+10*j) for j in range(3)]
        return [(1.5,13.5),(13.5,25.5),(34.5,46.5),(46.5,58.5)]
    if b.key=='cfs15' and d=='X':return spaced_segments(0 if name.endswith('W') else 140,140 if name.endswith('W') else 240,widths)
    if d=='Y' and not (b.key=='cfs15' and name=='STEP'):
        half=len(widths)//2;corr=(28,34) if b.key=='cfs1' else (27,33)
        return spaced_segments(0,corr[0],widths[:half])+spaced_segments(corr[1],b.cfg['plan_ft'][1],widths[half:])
    return spaced_segments(ranges[0][0],ranges[-1][1],widths)

def stud(b,d,name,k,props,ordinary):
    if b.key=='cfs1':
        prefix='stud-ext-' if name in ('S','N') else 'stud-corridor-' if name in ('CS','CN') else 'stud-endwall-' if name in ('W','E') else 'stud-party-'
        for r in b.raw['studs']:
            if not r['id'].startswith(prefix):continue
            nums=list(map(int,re.findall(r'L(\d+)',r['id'])))
            if nums and min(nums)<=k<=max(nums):return r
    if b.key=='cfs5':
        pid=('600S162-54' if k<=4 else '600S162-43') if name in ('XS','XN') else ('600S200-54' if k<=2 else '600S200-43' if k<=4 else '600S162-33') if name in ('XCS','XCN') else ('600S162-54' if k<=2 else '600S162-43' if k<=4 else '600S162-33')
        return dict(ordinary,section=pid,spacing_in=16)
    if b.key=='cfs15':
        prefix='stud-step-' if name=='STEP' else 'stud-party-terrace-' if name=='P126' else 'stud-end-W' if name=='W0' else 'stud-end-E' if name=='E240' else 'stud-party-W-' if name.startswith('P') and b.config['Y_POS'][name]<140 else 'stud-party-E-' if name.startswith('P') else 'stud-corr-W' if name in ('CSW','CNW') else 'stud-corr-E' if name in ('CSE','CNE') else 'stud-ext-W' if name.endswith('W') else 'stud-ext-E-'
        row=tier(b,prefix,k)
        if row:
            pid=row['section'];mil=max(int(pid.split('-')[-1]),round(props.get('t_stud_in',.033)*1000));return dict(row,section=pid.rsplit('-',1)[0]+'-'+str(mil))
    return dict(ordinary,section='600S162-'+str(round(props.get('t_stud_in',.054)*1000)),spacing_in=16)

def tier(b,prefix,k):
    for r in b.raw['studs']:
        if not r['id'].startswith(prefix):continue
        nums=list(map(int,re.findall(r'L(\d+)',r['id'])))
        if not nums or min(nums)<=k<=max(nums):return r

def ordinary_sections(b):
    for m in b.members:
        if m['kind']!='stud' or not m['id'].startswith('ORD-'):continue
        axis=int(m['id'].split('-')[1]);point=m['axis'][0];pos=point[1-axis]/12;k=m['level'];rid=None;pid=None
        if b.key=='cfs1':
            prefix='stud-midunit-' if axis==0 and pos in (14,48) else 'stud-ext-' if axis==0 and pos in (0,62) else 'stud-corridor-' if axis==0 else 'stud-endwall-' if pos in (0,160) else 'stud-party-'
            row=tier(b,prefix,k);pid=row['section'];rid=row['id']
        elif b.key=='cfs5':
            if axis==0 and pos in (13.5,46.5):pid='600S200-68' if k<=2 else '600S162-54' if k<=4 else '600S162-33';rid='stud-int-bearing'
            else:
                name='XS' if axis==0 and pos in (0,60) else 'XCS' if axis==0 else 'YW';row=stud(b,'X' if axis==0 else 'Y',name,k,{},{});pid=row['section'];rid='stud-ext-long' if name=='XS' else 'stud-corridor' if name=='XCS' else 'stud-end-walls'
        else:
            prefix='stud-step-' if axis==1 and pos==140 else 'stud-party-terrace-' if axis==1 and pos==126 else 'stud-end-W' if axis==1 and pos==0 else 'stud-end-E' if axis==1 and pos==240 else 'stud-party-W-' if axis==1 and pos<140 else 'stud-party-E-' if axis==1 else ('stud-corr-' if pos in (27,33) else 'stud-ext-')+('W' if point[0]<1680 else 'E')
            row=tier(b,prefix,k)
            if row:pid=row['section'];rid=row['id']
        if pid:
            m['profile_id']=b.profile(pid);rr=b.record('studs',rid)
            if rr:m['design_record_ids'].append(rr);b.used_records.add(rr)
    b.note('ORDINARY-SECTIONS','S: source bearing, corridor, exterior and party-wall stud tiers also apply to the complementary wall runs. A: local non-braced set-out and end fitting remain authored; no generic lighter stud replaces the scheduled bearing-wall section.')

def bearing_lines(b):
    if b.key=='cfs1':return [(0,y*12) for y in (0,14,28,34,48,62)]
    if b.key=='cfs5':return [(0,y*12) for y in (0,13.5,27,33,46.5,60)]
    return [(1,x*12) for x in b.config['Y_POS'].values()]+[(0,324),(0,396)]

def floors(b,outline,levels):
    from .review_cfs import frange,simple_truss,section
    ordinary_sections(b)
    rows={r['id']:r for r in b.raw['framing']}
    def joist(label,rid,axis,station,lo,hi,z,k,finish):
        pid=b.profile(section(rows[rid]['section']));d=b.depth(pid)
        def pt(u):return [u,station,z-finish-d/2] if axis==0 else [station,u,z-finish-d/2]
        m=b.member(label,pid,'joist',pt(lo),pt(hi),k,'A',records=[b.record('framing',rid)])
        b.ends(m,'review_final_cfs_joist',[b.record('framing',rid)],parameters={'spacing':16,'floor_depth':depth(b,k),'bearing_packer_in':round(depth(b,k)-finish-d,4)})
    for k,z in enumerate(levels[1:],1):
        roof=k==len(levels)-1
        if b.key in ('cfs1','cfs5'):
            finish=.75 if roof else 2.25 if b.key=='cfs1' else 2
            b.panel(f'FLOOR-{k}','roof' if roof else 'floor',[[x*12,y*12,z] for x,y in outline],finish,k,'A')
            supports=[pos for axis,pos in bearing_lines(b)]
            for x in frange(0,b.cfg['plan_ft'][0]*12+.1,16):
                for j,(lo,hi) in enumerate(zip(supports,supports[1:])):
                    rid='joist-roof' if roof else 'joist-corridor' if hi-lo==72 else 'joist-unit' if b.key=='cfs1' else 'joist-typ'
                    joist(f'J-{k}-{x}-{j}',rid,1,x,lo,hi,z,k,finish)
            continue
        xmax=1680 if k>=4 else 2880;finish=.75 if roof else 2.25
        b.panel(f'FLOOR-{k}','roof' if roof else 'floor',[[0,0,z],[xmax,0,z],[xmax,720,z],[0,720,z]],finish,k,'A')
        supports=sorted(pos for axis,pos in bearing_lines(b) if axis==1 and pos<=xmax+.01)
        for y in frange(0,720.1,16):
            if 324<y<396:continue
            for j,(lo,hi) in enumerate(zip(supports,supports[1:])):
                rid='joist-terrace' if roof and hi>1440 else 'joist-roof-west' if roof else 'joist-guestroom'
                joist(f'J-{k}-{y}-{j}',rid,0,y,lo,hi,z,k,finish)
        for x in frange(0,xmax+.1,16):joist(f'COR-{k}-{x}','joist-corridor',1,x,324,396,z,k,finish)
        if k==4:
            # Source lower east roof: 60 ft gable, 24 in truss spacing. A internal panels/sections.
            # The old base was a chord centroid at the wall bearing surface,
            # burying half the chord in the track. Explicit A bearing clearance
            # keeps the delegated truss outside the actual track section.
            chord_shift=3.125;roof_shift=chord_shift+(3+.375)*math.sqrt(1+.25**2)
            for x in frange(1680,2880.1,24):simple_truss(b,f'EAST-ROOF-{x}',1,x,0,720,z-depth(b,k)+chord_shift,90,k,'2X600S162-68','2X600S162-54',96,heel=12)
            for tag,ys,zs in [('S',(0,360),(z+12,z+102)),('N',(360,720),(z+102,z+12))]:
                b.panel('EAST-ROOF-'+tag,'roof',[[1680,ys[0],zs[0]-depth(b,k)+roof_shift],[2880,ys[0],zs[0]-depth(b,k)+roof_shift],[2880,ys[1],zs[1]-depth(b,k)+roof_shift],[1680,ys[1],zs[1]-depth(b,k)+roof_shift]],.75,k,'A')
            # Drag trusses on exact source party-wall axes (not rounded to regular roof stations).
            for name,x in b.config['Y_POS'].items():
                if 140<x<240 and abs(x*12/24-round(x*12/24))>.01:simple_truss(b,f'EAST-DRAG-{name}',1,x*12,0,720,z-depth(b,k)+chord_shift,90,k,'2X600S162-68','2X600S162-54',96,heel=12)
            b.changes.append(dict(kind='cfs15_east_roof_bearing_datum',chord_centroid_shift_in=chord_shift,roof_panel_shift_in=roof_shift,
                basis='A: lower chord underside 1/8 in above wall reference, with fitted bearing pack to actual track web; roof sheathing underside follows the real inclined upper flange. Source truss spacing and declared slope retained. Delegated geometry and local bearing capacity remain unverified.'))
    if b.key=='cfs15':
        z=levels[-1];b.panel('TERRACE-PAVERS','finish',[[1440,0,z+6],[1680,0,z+6],[1680,720,z+6],[1440,720,z+6]],2,6,'A',scope='S terrace x=120-140 ft; A paver/pedestal height')
        b.note('STEPPED-ROOF','S: east wing stops at L4; west wing continues to L6. West terrace is x=120-140 ft. S: east gable trusses at 24 in centres; A: 3:12 roof slope, 12 in heel and displayed truss internals/sections. Source shear-transfer, vertical-slip and supplier requirements remain in the details. The lower east roof does not become a level floor.')
    parapets(b,levels)

def parapets(b,levels):
    from .review_cfs import frange
    if b.key=='cfs1':return
    z=levels[-1];width=180*12 if b.key=='cfs5' else 140*12;rid=b.record('connections','conn-terrace-path')
    for axis,pos,lo,hi in [(0,0,0,width),(0,720,0,width),(1,0,0,720)]+([(1,width,0,720)] if b.key=='cfs5' else []):
        def pt(u,h):return [u,pos,h] if axis==0 else [pos,u,h]
        for u in frange(lo,hi+.1,16):
            m=b.member(f'PAR-{axis}-{pos}-{u}','600S162-43','parapet_stud',pt(u,z-12),pt(u,z+36 if b.key=='cfs5' else z+42),len(levels)-1,'A',records=[b.record('studs','stud-parapet')]);b.ends(m,'review_final_guard',[rid],parameters={'continuous_parapet':True,'height_in':36 if b.key=='cfs5' else 42})
        m=b.member(f'PAR-CAP-{axis}-{pos}','600T125-43','parapet_cap',pt(lo,z+36 if b.key=='cfs5' else z+42),pt(hi,z+36 if b.key=='cfs5' else z+42),len(levels)-1,'A');b.ends(m,'cfs_stud')
    if b.key=='cfs15':
        for axis,pos,lo,hi in [(0,0,1440,1680),(0,720,1440,1680),(1,1680,0,720)]:
            def pt(u,h):return [u,pos,h] if axis==0 else [pos,u,h]
            for u in frange(lo,hi+.1,48):
                m=b.member(f'GUARD-{axis}-{pos}-{u}','2X600S162-54','guard_post',pt(u,z-12),pt(u,z+48),6,'A',records=[rid]);b.connection(m['id'],'review_final_guard',pt(u,z),[m],[rid],parameters={'screws':6,'screw_size':12,'height_in':48})
            m=b.member(f'GUARD-TOP-{axis}-{pos}','600T150-54','guard_rail',pt(lo,z+48),pt(hi,z+48),6,'A');b.ends(m,'review_guard_connection',[rid],parameters={'rail':True})

def connections(b):
    from .review_cfs import section
    lookup={m['id']:m for m in b.members}
    def attach(c,name,table='connections',first=False):
        rid=b.record(table,name)
        if rid and rid not in c['design_record_ids']:
            c['design_record_ids'].insert(0,rid) if first else c['design_record_ids'].append(rid);b.used_records.add(rid)
    for c in b.connections:
        m=lookup[c['member_ids'][0]];family=c['detail_ref']['id'];k=m['level'];par=c.setdefault('parameters',{})
        if family=='review_final_cfs_joist':
            attach(c,'diaphragm-across-walls','framing');attach(c,'conn-joist-bearing')
            if b.key=='cfs5' and k==6:attach(c,'conn-uplift-roof-joist');par.update(screws=2,screw_size=10)
        if b.key=='cfs1' and family=='review_final_cfs_joist' and k==4:attach(c,'conn-roof-uplift');par.update(screws=2,screw_size=10)
        if b.key=='cfs5' and family=='review_cfs_strap':
            dims=b.profiles[m['profile_id']]['dimensions'];mil=min(MIL,key=lambda n:abs(MIL[n]-dims['thickness']));attach(c,f'conn-strap-end-{dims["width"]:g}x{mil}',first=True)
        if family=='test_wall_opening' and m['kind']=='opening_header':
            rid='header-ext-L1' if b.key=='cfs1' else 'header-window-east-L4-drift' if k==4 and m['axis'][0][0]>=1680 and m['axis'][0][0]<1903.2 else 'header-window-east-L4' if k==4 and m['axis'][0][0]>=1680 else 'header-window-typ'
            row=next((r for r in b.raw['framing'] if r['id']==rid),None)
            if row:m['profile_id']=b.profile(section(row['section']));attach(c,rid,'framing');par.update(source_header_screws=6 if b.key=='cfs1' else 16,source_header_screw_size=12,source_header_clip_t=MIL[54]);c['detail_ref']['id']='review_final_header'
        if b.key!='cfs15':continue
        if family=='review_final_cfs_joist' and k==6:attach(c,'conn-roof-joist-uplift-west');par.update(screws=2,screw_size=10)
        if family=='review_roof_seat' and m['id'].startswith('EAST-'):
            attach(c,'conn-truss-uplift-east');attach(c,'conn-roof-to-long-walls-east');par.update(screws=5,screw_size=12)
        if family=='review_cfs_floor' and k==4:
            line=m['id'].split('-L')[0]
            if line=='STEP':attach(c,'conn-drag-truss-step')
            elif line in ('CSE','CNE'):attach(c,'conn-roof-to-corridor-walls-east');par['vertical_slip']=True
            elif line.startswith('P') and c['point'][0]>1680:attach(c,'conn-drag-truss-east-party-walls')
            elif line=='E240':attach(c,'conn-gable-end-E240')
            if line in ('STEP','CSE','CNE','E240') or line.startswith('P') and c['point'][0]>1680:c['detail_ref']['id']='review_final_roof_transfer';par['step_line']=line=='STEP'
    b.note('SOURCE-ANCILLARIES','S: story-specific chord packs and rods, source header/roof uplift fasteners, diaphragm crossing and roof transfer requirements. A: ordinary wall fit, extra floor bearing set-out and drawn procurement extents. Roof supplier certification and the original capacity requirements remain outstanding design responsibilities.')
