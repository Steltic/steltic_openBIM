"""Physical HR review reconstruction from saved axes and completed design records."""
import math,re
from collections import defaultdict
from .review_model import add,sub,mul,unit,cross
from .assembly_templates import number

def shape_in(text,default=None):
    match=re.search(r'(?:W\d+X[\d.]+|HSS[\d.]+X[\d.]+(?:X[\d./]+)?|C\d+X[\d.]+)',str(text),re.I)
    return match[0].upper() if match else default

def build(b):
    from . import review_final_hr as final
    if b.key in final.KEYS:final.prepare(b)
    from .review_next_hr import prepare,physical_extras,connection_extras,is_case
    if is_case(b):prepare(b)
    if b.key=='hr31':
        from .review_next_hr_industrial import gable
        gable(b);return
    p=b.package;c=b.config;levels=c['Z'] if b.key=='hr14' else p['layout_evidence']['levels_in'];level=lambda z:min(range(len(levels)),key=lambda k:abs(levels[k]-z))
    b.levels=[(k,'BASE' if k==0 else ('ROOF' if k==len(levels)-1 else 'L'+str(k))+' TOS',z) for k,z in enumerate(levels)]
    analysis={x['id']:x for x in p['analysis']['elements']};nodes={}
    rawmembers={m['id']:m for m in b.raw['members']};column_ids=set()
    source_profiles={p['id']:p for p in p['physical']['profiles']}
    def member_records(pid,kind,k,point):
        options=[r for r in rawmembers if r.endswith('-'+pid)]
        if not options:return []
        words=('lateral_col','gravity_col') if kind=='column' else (('brace',) if kind=='brace' else (('roof',) if k==len(levels)-1 else ('floor',)))
        frames=c.get('FRAMES',[]);grid=c.get('G',{})
        if kind=='column' and frames and all(isinstance(f,dict) and 'bay' in f for f in frames) and grid.get('xs') and grid.get('ys'):
            in_frame=False
            for frame in frames:
                if k not in frame.get('levels',[]):continue
                direction=frame['dir'];along=grid['xs' if direction=='X' else 'ys'];across=grid['ys' if direction=='X' else 'xs'];i=0 if direction=='X' else 1
                if abs(point[1-i]-across[frame['line']])<.01 and any(abs(point[i]-along[j])<.01 for j in (frame['bay'],frame['bay']+1)):in_frame=True;break
            words=('lateral_col',) if in_frame else ('gravity_col',)
        first=next((r for w in words for r in options if r.startswith(w)),options[0]);return [b.record('members',first)]
    for m in p['physical']['members']:
        pid=m['profile_id'];kind='column' if m['kind'] in ('col','column') else m['kind'];aa,bb=m['axis'];k=level(max(aa[2],bb[2]))
        if pid.startswith(('WEB','CW','RZ-','CB')):
            b.excluded.append(dict(id=m['id'],reason='Analysis idealization replaced by physical plate wall / coupling assembly',profile_id=pid));continue
        if b.key=='hr28' and pid in ('W44X408','W44X230'):
            b.excluded.append(dict(id=m['id'],reason='Equivalent STMF beam replaced by individual truss members',profile_id=pid));continue
        if pid.startswith('BRB'):
            core=float(pid[3:]);body=max(10,math.ceil(math.sqrt(core)*2));b.custom(pid,'rhs',dict(h=body,b=body,t=.375),basis='A: supplier BRB casing envelope; source core area retained',core_area_in2=core)
        elif b.key=='hr16' and re.fullmatch(r'W\d+X\d+B',pid):
            b.profile(pid[:-1]);pid=pid[:-1]
        else:b.profile(pid)
        a=analysis.get(m['id'],{});rec=member_records(m['profile_id'] if b.key=='hr16' and m['profile_id'].endswith('B') else pid,kind,k,aa)
        made=b.member(m['id'],pid,kind,aa,bb,k,records=[r for r in rec if r],local_y=m.get('local_y'),source=m['id'],analysis_ids=m.get('analysis_ids',[]),source_forces=a.get('source_schedule',{}))
        if pid.startswith(('W','S','M','HP')) and 'analysis_local_y' not in m:
            from .physical_frame import width_axis
            physical_y=width_axis([aa,bb],a.get('local_y'),a.get('builder_arguments',[]),source_profiles.get(m['profile_id'],{}).get('properties',{}))
            if physical_y is not None:
                made['analysis_local_y']=m.get('local_y');made['local_y']=physical_y
                made['orientation_basis']='Source element inertia ratio maps the analysis frame to physical flange width; no analysis change'
                if math.dist(physical_y,m['local_y'])>1e-6:
                    b.changes.append(dict(kind='physical_section_axis_conversion',member_id=m['id'],analysis_local_y=m['local_y'],local_y=physical_y,basis=made['orientation_basis']))
        if b.key=='hr16' and m['profile_id'].endswith('B'):made['boxing_thickness_in']=1;made['source_boxed_profile']=m['profile_id']
        if b.key=='hr16' and m['profile_id'].endswith('B'):
            # cfg.py adds the boxed section as (A,Ix,Iy,J); add_column passes
            # (Iy,Ix). Boxing makes the two inertias nearly equal, so ordering
            # by their magnitude cannot recover this known source convention.
            made['analysis_local_y']=list(a['local_y']);made['local_y']=cross(unit(sub(bb,aa)),a['local_y'])
            made['orientation_basis']='S: original boxed-column add_column convention (Iy,Ix); physical flange width follows analysis local z'
            made['boxing_width_in']=b.config['_WG'][pid][1]-2*b.config['_WG'][pid][3]
        if b.key=='hr11' and k==10 and kind in ('beam','girder') and all(abs(q[1]-336)<.01 and 0<=q[0]<=672 for q in (aa,bb)):
            original=made['profile_id'];made['profile_id']=b.profile('W24X62');made['design_record_ids']=[b.record('members','roof-girder-mechanical-W24X62')]
            made['analysis_profile_id']=original
            b.changes.append(dict(kind='gold_local_member_selection',member_id=made['id'],analysis_profile_id=original,physical_profile_id='W24X62',record_id=made['design_record_ids'][0],basis='S: explicit final mechanical-zone hand design supersedes the generic roof analysis section on Grid B / Grids 1-3'))
        if b.key=='hr32':made['phase']='existing A36' if max(aa[2],bb[2])<=468.01 else 'new A992'
        if kind=='column':column_ids.add(made['id'])
    from .review_hr9_selections import collectors
    collectors(b)
    # Floor cells preserve real voids and setbacks; the crane bracket level is not a floor.
    from .review_floor_layout import cells,thickness,interval
    for i,cell in enumerate(cells(b,levels)):
        if len(cell)!=5:continue
        x0,x1,y0,y1,z=cell
        if b.key=='hr33' and abs(z-456)>.1:continue
        if b.key=='hr27' and x0>=360 and x1<=1080 and y0>=360 and y1<=720:continue
        b.panel('FLOOR-'+str(i),'floor',[[x0,y0,z],[x1,y0,z],[x1,y1,z],[x0,y1,z]],thickness(b.key,level(z)),level(z),'A',surface_basis='A: top of steel datum; source floor/deck build-up')
    if b.key=='hr12':
        for k,z in enumerate(levels[1:10],1):b.panel(f'CHAMFER-{k}','floor',[[0,336,z],[336,0,z],[336,336,z]],6.25,k,'S')
    # Add source-designed infill framing that was omitted from the analysis model.
    if b.key!='hr33':
        existing={tuple(sorted(tuple(round(t,3) for t in q) for q in m['axis'])) for m in b.members}
        deck=b.cfg.get('deck_span','Y' if b.key=='hr28' else 'X');span_axis=0 if deck=='Y' else 1
        spacing=b.cfg.get('infill_spacing',{'hr11':112,'hr13':100,'hr28':90,'hr32':100}.get(b.key,120))
        for panel in list(b.panels):
            if panel['kind']!='floor':continue
            pts=panel['vertices'];z=pts[0][2];k=panel['level'];xs=[v[0] for v in pts];ys=[v[1] for v in pts];lo=[min(xs),min(ys)];hi=[max(xs),max(ys)];other=1-span_axis
            if isinstance(deck,dict):span_axis=0 if deck.get(str(k),deck.get(k,'X'))=='Y' else 1;other=1-span_axis
            records=[r for r in rawmembers if 'infill' in r]
            candidates=[r for r in records if ('roof' in r)==(k==len(levels)-1)] or records
            if b.key=='hr9':want='infill-roof-' if k==13 else ('infill-L12-' if k==12 else 'infill-floor-');candidates=[r for r in records if r.startswith(want)]
            if b.key=='hr13':want='mezzanine' if k==2 else ('office-roof' if k==6 else 'office');candidates=[r for r in records if want in r]
            if b.key=='hr11':
                exposed=k==10 or k==7 and not any(p['level']==8 and min(q[0] for q in p['vertices'])<sum((lo[0],hi[0]))/2<max(q[0] for q in p['vertices']) and min(q[1] for q in p['vertices'])<sum((lo[1],hi[1]))/2<max(q[1] for q in p['vertices']) for p in b.panels)
                if exposed:
                    mechanical=k==10 and hi[0]<=672 and hi[1]<=672
                    candidates=[r for r in records if r=='infill-roof-W16X26'] if not mechanical else [r for r in records if 'infill-roof' in r and 'mechanical' in r]
            if b.key=='hr16':
                library=k==1 and 1008<=lo[0] and hi[0]<=1344 and 336<=lo[1] and hi[1]<=1008
                link_roof=k==2 and lo[0]>=1008
                if library:candidates=['infill-library-W18X46']
                elif link_roof:candidates=[r for r in records if r.startswith('infill-link-roof-')] or ['snowdrift-link-roof-W16X26']
            if b.key=='hr32':candidates=[r for r in records if ('existing' in r if k<=3 else f'L{k}-' in r)]
            if b.key=='hr16' and k==3:candidates=['floor-W16X36'];span_axis=0;other=1
            if b.key=='hr20' and k in (1,2):candidates=[r for r in records if f'level{k+1}-' in r]
            if b.key=='hr35':candidates=[r for r in records if 'W12X16' in r]
            if b.key=='hr8' and k==5 and lo[1]>=720:candidates=[r for r in records if 'terrace' in r]
            if b.key=='hr10' and k==3:
                upper={tuple(q) for q in c['PRESENT']['4']}
                ix=c['XS'].index(lo[0]);iy=c['YS'].index(lo[1])
                if not {(ix,iy),(ix+1,iy),(ix,iy+1),(ix+1,iy+1)}<=upper:
                    candidates=[r for r in records if r.startswith('infill-terrace-')]
            if b.key in final.KEYS:candidates=final.infill(b,k,lo,hi,records,candidates)
            record=candidates[0] if candidates else None;pid=shape_in(record,'W18X35');b.profile(pid)
            step=spacing.get(str(k),spacing.get(k,100)) if isinstance(spacing,dict) else spacing
            if b.key in ('hr11','hr16'):step=112
            if b.key=='hr13' and k==4:step=75
            station=lo[other]+(step/2 if b.key=='hr28' else step)
            while station<hi[other]-.1:
                ends=interval(pts,station,other,span_axis)
                if not ends or ends[1]-ends[0]<.1:station+=step;continue
                aa=[0,0,z];bb=aa.copy();aa[other]=bb[other]=station;aa[span_axis],bb[span_axis]=ends
                if b.key=='hr16' and k==2 and lo[0]>=1008 and abs(station-1120)<.01:
                    record='snowdrift-link-roof-W16X26';pid=b.profile('W16X26')
                if b.key=='hr21':
                    from .review_cfs import simple_truss
                    simple_truss(b,'ROOF-JOIST-'+panel['id']+'-'+str(station),span_axis,station,*ends,z-36,33,k,'2X600S162-97','2X362S162-68',60,flat=True)
                    station+=step;continue
                if b.key=='hr13' and k==4:
                    from .review_cfs import simple_truss
                    simple_truss(b,'WORKSHOP-JOIST-'+panel['id']+'-'+str(station),span_axis,station,*ends,z-18,16,k,'2X250S162-68','2X250S137-54',30,flat=True)
                    station+=step;continue
                ident=tuple(sorted((tuple(aa),tuple(bb))))
                if ident not in existing:
                    m=b.member('INF-'+panel['id']+'-'+str(round(station,3)),pid,'infill',aa,bb,k,'A',records=[b.record('members',record)] if record else [],setout_basis='Source spacing, adopted datum/end fitting');existing.add(ident)
                station+=step
    if b.key in ('hr8','hr14'):ebf(b)
    if b.key=='hr9':plate_walls(b,levels);rocking_posts(b,levels)
    if b.key=='hr27':core_walls(b,levels)
    if b.key=='hr28':stmf(b,levels)
    if b.key=='hr33':crane(b)
    if b.key=='hr32':retrofit(b)
    if b.key=='hr13':b.note('WORKSHOP-JOISTS','S: workshop roof open-web joists at 75 in centres; source delegated supplier design requirements remain in the source records. A: the displayed 18 in nominal envelope, paired-channel chords/webs, panel nodes and bearing seats are fictional supplier coordination geometry, not a selected or verified SJI product.')
    if is_case(b):physical_extras(b,levels)
    if b.key in final.KEYS:final.physical_extras(b,levels)
    connect_primary(b,levels)
    from .review_hr_complements import apply
    apply(b,levels)
    if is_case(b):connection_extras(b,levels)
    if b.key in final.KEYS:final.connections(b,levels)
    # Keep the drawing datum and every secondary cutback explicit.
    b.note('DATUM','A: source floor nodes are adopted as top-of-steel datums; physical beam axes are lowered by half their actual section depth. Added infills follow source spacing. Local end cutbacks use the connected support face; schedules report workline lengths.')
    for m in b.members:
        if m['kind'] in ('beam','infill','moment_beam','girder'):
            depth=b.depth(m['profile_id']);m['end_offsets']=[[0,0,-depth/2],[0,0,-depth/2]]
    # Grid coordinates come from source column workpoints, not truss panel points.
    for i,axis in enumerate(('x','y')):
        values=sorted({round(p[i],4) for m in b.members if m['kind']=='column' for p in m['axis']})
        b.grids[axis]=[(str(j+1) if i==0 else chr(65+j),x) for j,x in enumerate(values)]

def nearest(b,point,kinds,exclude=()):
    best=None;dist=1e30
    for m in b.members:
        if m['id'] in exclude or m['kind'] not in kinds:continue
        aa,bb=m['axis'];v=sub(bb,aa);t=max(0,min(1,sum(x*y for x,y in zip(sub(point,aa),v))/sum(x*x for x in v)))
        d=math.dist(point,add(aa,mul(v,t)))
        if d<dist:dist=d;best=m
    return best if dist<30 else None


def brace_record(b,m,raw):
    """Match source applicability, including same-size frame/story variants."""
    pid=m['profile_id'];k=m['level'];aa,dd=m['axis'];along=0 if abs(dd[0]-aa[0])>abs(dd[1]-aa[1]) else 1;normal=1-along
    frame=None
    for f in b.config.get('FRAMES',[]):
        if not isinstance(f,dict):continue
        step=b.config.get('SY' if normal==1 else 'SX',336);span=b.config.get('SX' if along==0 else 'SY',336)
        if f['dir']=='XY'[along] and abs(aa[normal]-f['line']*step)<.1 and f['bay']*span-.1<=sum(q[along] for q in m['axis'])/2<=(f['bay']+1)*span+.1 and k in f['levels']:
            frame=f['name'].split()[0];break
    lower=min(m['axis'],key=lambda q:q[2]);col=nearest(b,lower,('column',));cp=col['profile_id'] if col else ''
    candidates=[r for r in raw if r.startswith('conn-brace-') and (raw[r].get('section')==pid or r=='conn-brace-'+pid or r.startswith('conn-brace-'+pid+'-'))]
    def score(r):
        row=raw[r];txt=row.get('type','');context=row.get('design_basis','').split('(the other')[0].split('(the brace size')[0]
        value=0
        if frame:
            names=re.findall(r'\b[XY]\d+\b',txt)
            if names:value+=100 if frame in names else -1000
        hit=re.search(r'stor(?:y|ies)\s+([\d, -]+(?:to \d+)?)',txt,re.I)
        if hit:
            nums=[int(n) for n in re.findall(r'\d+',hit[1])]
            if ('-' in hit[1] or 'to' in hit[1]) and len(nums)==2:nums=list(range(nums[0],nums[1]+1))
            story=([1,3,5,6].index(k)+1 if k in (1,3,5,6) else k) if b.key=='hr13' and pid=='HSS6X6X3/8' else ([2,4].index(k)+1 if k in (2,4) else k) if b.key=='hr13' else k
            value+=50 if story in nums else -500
        if cp and cp in txt:value+=30
        elif cp and cp in context:value+=10
        if b.key=='hr13':
            height=abs(dd[2]-aa[2])/12
            value+=50 if re.search(r'\b'+str(round(height))+r' ft',txt) else 0
            value+=20 if ('office' in txt)==(pid=='HSS6X6X3/8') else -100
            diagonal=math.dist(aa[:2],dd[:2])>200
            if pid=='HSS7X7X1/2':value+=100 if ('diagonal' in txt)==diagonal else -200
        return value
    return max(candidates,key=score) if candidates else None,frame

def connect_primary(b,levels):
    from .review_next_hr import is_case as is_next_case
    from . import review_final_hr as final
    existing={mid for c in b.connections if c['detail_ref']['id'] not in ('review_retrofit_beam','review_retrofit_column','review_ebf_link') for mid in c['member_ids']};raw={r['id']:r for r in b.raw['connections']}
    columns=[m for m in b.members if m['kind']=='column']
    for m in list(b.members):
        pid=m['profile_id'];k=m['level'];kind=m['kind'];members=[]
        record_pid=m.get('source_boxed_profile',pid)
        if m['id'] in existing and kind!='column' and not ((is_next_case(b) or b.key in final.KEYS) and kind in ('brace','beam','girder','moment_beam','infill')):continue
        if kind=='column':
            low=min(m['axis'],key=lambda p:p[2]);bases=[r for r in raw if 'base-' in r and r.endswith('-'+record_pid)]
            brace_column=any(mm['kind']=='brace' and any(math.dist(q[:2],low[:2])<.1 for q in mm['axis']) for mm in b.members)
            founded=low[2]<.1 or b.key=='hr14' and not any(mm['id']!=m['id'] and max(q[2] for q in mm['axis'])<=low[2]+.1 and math.dist(max(mm['axis'],key=lambda q:q[2]),low)<.1 for mm in columns)
            if founded:
                preferred='lateral_col' if brace_column or m['id'] in existing and b.key!='hr35' or b.key=='hr33' or pid.startswith('BOX') else 'gravity_col'
                rid=next((r for r in bases if preferred in r),bases[0] if bases else None)
                refs=[b.record('connections',rid)] if rid else []
                extra=b.record('connections','conn-column-base-segment-'+pid)
                if extra:refs.append(extra)
                b.connection(m['id']+':base','review_base',low,[m],refs,parameters={'existing_grillage':b.key=='hr32'})
                continuous=[r for r in raw if r.endswith('-'+record_pid) and 'base-' not in r and re.search(r'\bno (?:field |column )?splice\b',str(raw[r].get('components','')),re.I)]
                for r in continuous:
                    ref=b.record('connections',r)
                    if ref not in m['design_record_ids']:m['design_record_ids'].append(ref);b.used_records.add(ref)
                if continuous:m['continuity_basis']='Source one-piece shaft; no field joint at the analysis subdivision'
            else:
                # Material/profile changes and source two-storey splice stations only.
                below=nearest(b,low,('column',),(m['id'],));rid=next((r for r in raw if r.startswith('conn-') and '-col-' in r and r.endswith(record_pid)),None)
                choices=[r for r in raw if ('gravity_col-' in r or 'lateral_col-' in r) and 'base-' not in r and r.endswith('-'+record_pid)]
                transitions=[r for r in raw if r.startswith('conn-') and '-over-' in r and pid+'-over-'+(below['profile_id'] if below else '?') in r and r.endswith('-L'+str(k-1))]
                pair=record_pid+' over '+(below.get('source_boxed_profile',below['profile_id']) if below else '?')
                pair_records=[r for r in raw if ('col-' in r or 'col_' in r) and pair+':' in str(raw[r].get('components',''))]
                preferred=next((r for r in choices if 'lateral_col' in r),None) if m['id'] in existing or brace_column or pid.startswith('BOX') else None
                if b.key=='hr32' and k==4:preferred=next((r for r in choices if 'lateral_col' in r),preferred)
                rid=transitions[0] if transitions else preferred if preferred in pair_records else pair_records[0] if pair_records else (preferred or choices[0]) if choices else rid;txt=str(raw.get(rid,{}))
                changes_profile=below and below.get('source_boxed_profile',below['profile_id'])!=record_pid
                no_splice=any(w in txt.lower() for w in (('no column splice','no field splice','one-piece','single-story','single length','no splice') if b.key in ('hr14','hr16','hr18','hr20','hr21','hr24','hr25','hr30','hr35') else ('no column splice','no field splice')))
                school_splice=b.key=='hr16' and 'classroom only' in txt.lower() and abs(low[2]-288)<.1 and low[0]<=1008 and low[1]<=672
                if b.key=='hr16' and 'classroom only' in txt.lower():no_splice=not school_splice
                if rid and no_splice:
                    ref=b.record('connections',rid)
                    if ref not in m['design_record_ids']:m['design_record_ids'].append(ref);b.used_records.add(ref)
                initial_ocbf_splice=b.key=='hr18' and k==2 and pid=='W14X145'
                workshop_splice=b.key=='hr13' and abs(low[2]-240)<.1 and low[0]>=1500
                if rid and not no_splice and (changes_profile or k%2==1 or 'gravity' in txt.lower() or b.key=='hr32' and k==4 or school_splice or initial_ocbf_splice or workshop_splice):
                    role='lateral_col' if 'lateral_col' in rid else 'gravity_col' if 'gravity_col' in rid else None
                    # Equal shaft names/roles do not make different reinforcement
                    # selections interchangeable (e.g. W14X193 versus its boxed B
                    # variant). Only identical selections can share this binding.
                    # Envelope records can append a second pair after '; also'.
                    # Their identical first selection still applies to this pair.
                    primary_selection=lambda r:str(raw[r].get('components','')).split('; also ',1)[0]
                    equivalent=[r for r in pair_records if primary_selection(r)==primary_selection(rid)]
                    refs=[b.record('connections',r) for r in dict.fromkeys([rid]+equivalent)]
                    pp=add(low,[0,0,48]);b.connection(m['id']+':splice','review_splice',pp,[m]+([below] if below else []),refs,parameters={'splice_offset_in':48})
            # Column participation at beam joints is linked below; a continuous
            # upper column also receives an explicit continuity reference.
            if not any(m['id'] in c['member_ids'] for c in b.connections):b.connection(m['id']+':continuity','review_column_continuity',low,[m]+([nearest(b,low,('column',),(m['id'],))] if nearest(b,low,('column',),(m['id'],)) else []),parameters={'continuous':True})
            continue
        if kind=='brace':
            rid,frame=brace_record(b,m,raw)
            for side,point in enumerate(m['axis']):
                col=nearest(b,point,('column',),(m['id'],));beam=nearest(b,point,('beam','moment_beam','girder'),(m['id'],));others=[m]+([col] if col else [])+([beam] if beam else [])
                joint='base' if point[2]<.1 or b.key=='hr14' and col and point[2]<=min(q[2] for q in col['axis'])+.1 and not any(mm['kind']=='column' and max(q[2] for q in mm['axis'])<point[2]+.1 and math.dist(max(mm['axis'],key=lambda q:q[2]),point)<.1 for mm in b.members) else 'corner' if col else 'link_end' if b.key in ('hr8','hr14') else 'apex'
                refs=[b.record('connections',rid)] if rid else []
                if b.key=='hr10':
                    extra=b.record('connections','conn-brace-base-'+pid) if joint=='base' else b.record('connections','conn-brace-apex-'+beam['profile_id']) if joint=='apex' and beam else None
                    if extra:refs.insert(0,extra)
                con=b.connection(m['id']+':'+str(side),'review_brb' if pid.startswith('BRB') else 'review_brace',point,others,refs,parameters={'brace_angle':round(math.degrees(math.atan2(abs(m['axis'][1][2]-m['axis'][0][2]),math.dist(m['axis'][0][:2],m['axis'][1][:2]))),3),'joint':joint,'story':k,'upper_end':point[2]==max(q[2] for q in m['axis'])})
                con['source_frame']=frame
            continue
        if kind not in ('beam','girder','infill','moment_beam','joist'):continue
        options=[r for r in raw if r.endswith('-'+pid) and not any(s in r for s in ('base-','col-','brace-','joint-'))]
        rid=next((r for r in options if ('infill' in r)==(kind=='infill') and ('roof' in r)==(k==len(levels)-1)),options[0] if options else None)
        if not rid and kind=='infill':rid=next((r for r in raw if 'infill' in r),None)
        if b.key in final.KEYS:rid=final.beam_record(b,m,raw,rid,levels)
        text=str(raw.get(rid,{}));moment=any(w in text.lower() for w in ('rbs','fully restrained','flanges cjp'))
        if b.key=='hr32' and k<=3:moment=any(all(abs(p[axis]-value)<.1 for p in m['axis']) for axis,value in ((0,0),(0,1440),(1,0),(1,1080)))
        if moment:m['kind']='moment_beam'
        for side,point in enumerate(m['axis']):
            support=nearest(b,point,('column',),(m['id'],)) or nearest(b,point,('beam','girder','moment_beam','truss_chord'),(m['id'],))
            family='review_pin_beam' if 'pin ' in text.lower() and 'clevis' in text.lower() else 'review_beam'
            if family=='review_pin_beam' and (not support or support['kind']!='column'):
                m.setdefault('continuous_analysis_segment_ends',[]).append(side)
                continue
            if b.key=='hr32' and k<=3 and moment:family='review_existing_joint'
            axial=float(m.get('source_forces',{}).get('collector_axial_kip') or 0)
            refs=[b.record('connections',rid)] if rid else []
            if b.key=='hr10' and abs(axial)>10:
                direction='X' if abs(m['axis'][1][0]-m['axis'][0][0])>1 else 'Y'
                extra=b.record('connections','conn-collector-'+direction+'-'+pid)
                if extra:refs.insert(0,extra)
            if moment and support and support['kind']=='column':
                along=0 if abs(m['axis'][1][0]-m['axis'][0][0])>abs(m['axis'][1][1]-m['axis'][0][1]) else 1;direction='XY'[along]
                opposite=any(mm['id']!=m['id'] and mm['kind'] in ('beam','moment_beam','girder') and mm['level']==k and any(math.dist(q,point)<.1 for q in mm['axis']) and abs(mm['axis'][1][1-along]-mm['axis'][0][1-along])<.1 and (sum(q[along] for q in mm['axis'])/2-point[along])*(sum(q[along] for q in m['axis'])/2-point[along])<0 for mm in b.members)
                joint_type='int' if opposite else 'end'
                for joint in raw:
                    match=re.match(r'conn-joint-'+direction+r'-L(\d+)-(\d+)-'+joint_type+'-'+re.escape(support['profile_id'])+'$',joint)
                    if match and int(match[1])<=k<=int(match[2]):refs.append(b.record('connections',joint));break
                if b.key=='hr10':
                    matches=[r for r in raw if r.startswith('conn-SMF-joint-'+support['profile_id'])]
                    preferred=next((r for r in matches if r.endswith('-'+pid)),None) or next((r for r in matches if r.endswith('-roof') and k==len(levels)-1),None) or next((r for r in matches if r.endswith(support['profile_id'])),None)
                    if preferred:refs.append(b.record('connections',preferred))
                match=re.search(r'RBS a = (\d+(?:[ -]\d+/\d+|/\d+|\.\d+)?) in, b = (\d+(?:[ -]\d+/\d+|/\d+|\.\d+)?) in, c = (\d+(?:[ -]\d+/\d+|/\d+|\.\d+)?)',text)
                if match:m['rbs']=dict(zip(('a_in','b_in','c_in'),map(number,match.groups())))
            b.connection(m['id']+':'+str(side),family,point,[m]+([support] if support else []),refs,parameters={'moment':moment,'collector':abs(axial)>10 or bool(m.get('source_collector_line')),'existing':b.key=='hr32' and k<=3})

def ebf(b):
    length=b.config.get('E_LINK',36)
    for m in b.members:
        if m['kind']!='beam' or abs(math.dist(*m['axis'])-length)>.1:continue
        pid=m['profile_id'];rid=b.record('members','floor-'+pid) or b.record('members','roof-'+pid)
        b.connection('LINK-'+m['id'],'review_ebf_link',[(a+d)/2 for a,d in zip(*m['axis'])],[m],[rid] if rid else [],parameters={'link_length':length})
        m['protected_zone']=f'Entire {length:g} in shear link; no attachment inside except specified stiffeners'

def plate_walls(b,levels):
    for name,(direction,line,bay,first,last,count) in b.config['PIERS'].items():
        along=0 if direction=='X' else 1;normal=1-along;station=line*336;start=bay*336;length=count*336
        for k in range(first,last+1):
            section=b.config['WEBS'][str(k)];t=b.config['TGROSS'][section];pid=b.custom('PHYSICAL-'+section+'-'+str(length),'flat',dict(width=length,thickness=t),basis='S: physical SPSW plate, not a tension-field strip')
            aa=[0,0,levels[k-1]];bb=[0,0,levels[k]];aa[normal]=bb[normal]=station;aa[along]=bb[along]=start+length/2
            out=[0,0,0];out[along]=1
            m=b.member(f'SPSW-{name}-{k}',pid,'plate_wall',aa,bb,k,records=[b.record('connections','conn-brace-'+section)],local_y=out,perforations={'diameter_in':6,'diagonal_pitch_in':10.75} if section.endswith('P') else None)
            verts=[]
            for u,z in ((start,levels[k-1]),(start+length,levels[k-1]),(start+length,levels[k]),(start,levels[k])):
                q=[0,0,z];q[normal]=station;q[along]=u;verts.append(q)
            b.panel(m['id']+'-PL','steel_plate_wall',verts,t,k,'S',perforated=section.endswith('P'))
            support=nearest(b,aa,('column','beam'));b.connection(m['id']+':edge','review_plate_wall',aa,[m]+([support] if support else []),[b.record('connections','conn-brace-'+section)],parameters={'thickness':t,'perforated':section.endswith('P')})
            if k==1:b.connection(m['id']+':base','review_plate_base',aa,[m],[b.record('connections','conn-web-base')])
        b.views.append(dict(title='SPSW '+name,direction=direction,station_in=station,range_in=[start,start+length],detail='Plate boundaries / fishplates / intermediate VBE'))
    b.note('SPSW','Source tension-field WEB analysis strips are excluded. Gross 3/16 in physical panels and their source perforation pattern are retained. A: 2 in nominal boundary fit and corner clearances; actual wall openings and boundary members remain in their source bays.')

def core_walls(b,levels):
    c=b.config
    for name,(direction,station,start,end,group) in c['LEGS'].items():
        along=0 if direction=='X' else 1;normal=1-along;length=end-start
        for k in range(1,len(levels)):
            gi=next(i for i,(lo,hi) in enumerate(c['PLATE_GROUPS']) if lo<=k<=hi);t=c['PLATE'][group][gi]
            plate=b.custom(f'CORE-FACE-{length:g}-{t:g}','flat',dict(width=length,thickness=t),basis='S')
            pid=b.custom(f'CORE-{name}-{t:g}','built_up',{},components=[dict(profile_id=plate,offset=[0,s*(18-t)/2],rotation_deg=0) for s in (-1,1)],basis='S: two physical faceplates, concrete between')
            aa=[0,0,levels[k-1]];bb=[0,0,levels[k]];aa[normal]=bb[normal]=station;aa[along]=bb[along]=(start+end)/2;ly=[0,0,0];ly[along]=1
            m=b.member(f'CORE-{name}-{k}',pid,'composite_wall',aa,bb,k,local_y=ly)
            verts=[]
            for u,z in ((start,levels[k-1]),(end,levels[k-1]),(end,levels[k]),(start,levels[k])):
                q=[0,0,z];q[normal]=station;q[along]=u;verts.append(q)
            b.panel(m['id']+'-CONCRETE','composite_core',verts,18-2*t,k,'S')
            b.connection(m['id']+':ties','review_core_wall',aa,[m],[b.record('connections','conn-tie-bar-to-plate'),b.record('connections','conn-diaphragm-to-core-walls')],parameters={'plate_thickness':t,'overall_thickness':18})
            if k==1:b.connection(m['id']+':BASE','review_core_base',aa,[m],[b.record('connections','conn-base-wall-'+name[:2])],parameters={'plate_thickness':t,'overall_thickness':18})
        b.views.append(dict(title='Composite core '+name,direction=direction,station_in=station,range_in=[start,end]))
    for name,(direction,station,start,end) in c['CBS'].items():
        for k in range(1,len(levels)):
            group='Y' if name in ('2','4') else name;gi=next(i for i,(lo,hi) in enumerate(c['CB_GROUPS']) if lo<=k<=hi);tf,tw=c['CB_T'][group][gi]
            pid=b.custom(f'COUPLING-{tf:g}-{tw:g}','i',dict(d=24,bf=18,tf=tf,tw=tw),basis='S: built-up coupling beam plates')
            a=[start,station,levels[k]-12] if direction=='X' else [station,start,levels[k]-12];d=[end,station,levels[k]-12] if direction=='X' else [station,end,levels[k]-12]
            lo,hi=c['CB_GROUPS'][gi];suffix='L1-20' if group=='B' else f'L{lo}-{hi}';rid=b.record('connections',f'conn-coupling-{group}-{suffix}')
            m=b.member(f'COUPLING-{name}-{k}',pid,'coupling_beam',a,d,k,records=[rid] if rid else []);b.ends(m,'review_coupling',[rid] if rid else [],parameters={'wall_thickness':18,'flange_thickness':tf,'web_thickness':tw})
    b.note('CORE','The saved wide-column and rigid-zone analysis members are excluded. Physical paired wall faceplates, concrete thickness, source plate groups and 9 ft coupling openings are reconstructed. A: tie locations and weld fit are dimensioned in the assembled details; they retain source verification requirements.')


def rocking_posts(b,levels):
    mids=[row[:2] for row in b.config['MIDS'].values()]
    for m in list(b.members):
        if m['kind']!='column' or not any(math.dist(m['axis'][0][:2],q)<.1 for q in mids):continue
        m['kind']='rocking_post'
        for end,point in enumerate(m['axis']):
            beam=nearest(b,point,('beam',));rid=b.record('connections','conn-IVBE-post-'+m['profile_id'])
            if point[2]<.1:b.connection(m['id']+':BASE','review_base',point,[m],[b.record('connections','conn-base-lateral_col-'+m['profile_id'])]);continue
            b.connection(m['id']+':ROCKER'+str(end),'review_rocker',point,[m]+([beam] if beam else []),[rid],parameters={'inverted':end==1})

def stmf(b,levels):
    for k,z in enumerate(levels[1:],1):
        for direction,stations,bays in [('X',(0,1440),3),('Y',(0,2160),2)]:
            for station in stations:
                for bay in range(bays):
                    label=f'STMF-{direction}-{station}-{bay}-{k}';along=0 if direction=='X' else 1;normal=1-along
                    def at(u,zz):return [bay*720+u,station,zz] if along==0 else [station,bay*720+u,zz]
                    outside='W8X48' if direction=='X' else 'W10X100';special='W8X21' if direction=='X' else ('W10X30' if k==8 else 'W8X48')
                    stations_u=[0,45,135,225,270,315,405,450,495,585,675,720]
                    nodes=defaultdict(list);endshape=b.profile(outside);specialshape=b.profile(special)
                    # Chord webs horizontal: flange width, not section depth, sets the 72 in truss depth.
                    for a,d in zip(stations_u,stations_u[1:]):
                        pid=specialshape if 270<=a and d<=450 else endshape;half=b.profiles[pid]['dimensions']['bf']/2
                        for edge,zz in [('TOP',z-half),('BOT',z-72+half)]:
                            m=b.member(f'{label}-{edge}-{a}',pid,'truss_chord',at(a,zz),at(d,zz),k,'S',local_y=[0,0,1]);nodes[a,edge].append(m);nodes[d,edge].append(m)
                    diagonal='HSS5X5X3/8' if direction=='X' else 'HSS8X8X5/8';vertical='HSS5X5X3/8' if direction=='X' else ('HSS6X6X1/2' if k<=2 else 'HSS6X6X3/8')
                    for j,u in enumerate((45,135,225,315,405,495,585,675)):
                        m=b.member(f'{label}-V-{u}',vertical,'truss_web',at(u,z-66),at(u,z-6),k,'A',local_y=[0,1,0] if direction=='X' else [1,0,0]);nodes[u,'TOP'].append(m);nodes[u,'BOT'].append(m)
                    panels=[0,45,135,225,315,405,495,585,675,720]
                    for j,(a,d) in enumerate(zip(panels,panels[1:])):
                        pairs=[('BOT','TOP'),('TOP','BOT')] if a==315 else [('BOT','TOP') if j%2==0 else ('TOP','BOT')]
                        for first,last in pairs:
                            if a==315:
                                dims=(1.75,.75) if direction=='X' and k<=2 else ((1.5,.625) if k<=2 else (1.25,.625));pid=b.custom(f'PL{dims[0]}X{dims[1]}','flat',dict(width=dims[0],thickness=dims[1]),basis='S: source special-segment flat bars')
                            else:pid=b.profile(diagonal)
                            m=b.member(f'{label}-D-{a}-{first}',pid,'truss_web',at(a,z-(6 if first=='TOP' else 66)),at(d,z-(6 if last=='TOP' else 66)),k,'A',local_y=[0,1,0] if direction=='X' else [1,0,0],protected_zone=a==315)
                            nodes[a,first].append(m);nodes[d,last].append(m)
                    for (u,edge),ms in nodes.items():
                        point=at(u,z-(6 if edge=='TOP' else 66));support=nearest(b,point,('column',)) if u in (0,720) else None
                        rid=b.record('connections',f'conn-{"roof" if k==8 else "floor"}-STMF-truss-{direction}') if support else b.record('connections','conn-stmf-web-'+direction)
                        b.connection(f'{label}-NODE-{u}-{edge}','review_stmf_end' if support else 'review_stmf_node',point,ms+([support] if support else []),[rid] if rid else [],parameters={'direction':direction,'special':315<=u<=405,'chord_web_horizontal':True})
    b.note('STMF','W44 equivalent analysis beams are removed. Source 72 in overall trusses, horizontal chord webs, 90 in special segments and designated chord/web sections are modelled explicitly. A: panel-node eccentricities and local chord transitions are fitted; no infill framing is added inside the special segment.')

def crane(b):
    column='W24X117';run=b.profile('W24X84');bracket=b.profile('W16X57');cap=b.custom('C15X33.9','channel',dict(d=15,b=3.4,t=.4,lip=0),basis='A: prismatic cap-channel envelope; source C15x33.9 designation')
    rail_top=336;rail_depth=5.1875;run_top=rail_top-rail_depth-.4;run_axis=run_top-b.depth(run)/2;bracket_axis=run_top-b.depth(run)-.125-b.depth(bracket)/2
    for side,y in enumerate((0,840)):
        direction=1 if side==0 else -1;ry=y+direction*30
        for i,x in enumerate(range(0,3001,300)):
            m=b.member(f'BRACKET-{side}-{i}',bracket,'crane_bracket',[x,y+direction*12.5,bracket_axis],[x,ry+direction*4,bracket_axis],1,'A')
            support=nearest(b,[x,y,bracket_axis],('column',));b.connection(m['id'],'review_crane_bracket',[x,y,bracket_axis],[m,support],[b.record('connections','conn-crane-bracket-W16X57')])
            for end in (-1,1):
                if 0<=i+(end==1)<11:
                    b.connection(m['id']+'-SEAT'+str(end),'review_crane_seat',[x,ry,run_axis],[m],[b.record('connections','conn-runway-girder-to-bracket')],parameters={'runway_profile':run})
        for i,x in enumerate(range(0,3000,300)):
            m=b.member(f'RUNWAY-{side}-{i}',run,'runway_beam',[x+.25,ry,run_axis],[x+299.75,ry,run_axis],1,'A',records=[b.record('members','runway-girder-W24X84-C15X33.9')]);b.ends(m,'review_crane_seat',[b.record('connections','conn-runway-girder-to-bracket')],parameters={'runway_profile':run})
            mc=b.member(f'RUNWAY-CAP-{side}-{i}',cap,'runway_cap',[x+.25,ry,run_top+.2],[x+299.75,ry,run_top+.2],1,'A',local_y=[0,0,-1]);b.ends(mc,'review_crane_tie',[b.record('connections','conn-runway-tie-back')],parameters={'runway_profile':run})
            rail=b.custom('A-85LB-RAIL','i',dict(d=5.1875,bf=5.1875,tf=.625,tw=.5),basis='A: 85 lb rail envelope, exact supplier section is delegated')
            mr=b.member(f'RAIL-{side}-{i}',rail,'crane_rail',[x,ry,336-2.59375],[x+300,ry,336-2.59375],1,'A');b.ends(mr,'review_rail_clip',parameters={'runway_profile':run})
    for x in (0,3000):
        for y in (168,336,504,672):
            m=b.member(f'ENDPOST-{x}-{y}','W12X40','endwall_post',[x,y,0],[x,y,456],1,'A');b.ends(m,'review_sliding_post',[b.record('connections','conn-endwall-wind-column-W12X40')])
    # Explicit open-web roof joists between each transverse rafter, 5 ft o.c.
    from .review_cfs import simple_truss
    for x in range(0,3000,300):
        for y in range(60,840,60):
            simple_truss(b,f'ROOF-JOIST-{x}-{y}',0,y,x,x+300,432,22,1,'2X250S162-68','2X250S137-54',30,flat=True)
    # Source RBS flange restraint and eave restraints, separate from gravity joists.
    for j,x in enumerate(range(0,3000,300)):
        for station in (49.5,840-49.5):
            brace=b.member(f'RBS-BRACE-{j}-{station}','HSS6X6X3/8','flange_bracing_beam',[x,station,420],[x+300,station,420],1,'A',records=[b.record('connections','conn-rafter-bracing')]);b.ends(brace,'review_angle_clip',[b.record('connections','conn-rafter-bracing')],parameters={'count':2,'diameter':.75})
            for end,xx in enumerate((x,x+300)):
                inward=1 if end==0 else -1
                m=b.member(f'RBS-KICKER-{j}-{station}-{end}','HSS4X4X1/4','flange_kicker',[xx,station,456-24],[xx+inward*24,station,408],1,'A');b.ends(m,'review_angle_clip',[b.record('connections','conn-rafter-bracing')],parameters={'count':2,'diameter':.75})
    b.note('CRANE','A: runway brackets and rails are set out 30 in inside the column worklines, with rail top at source 28 ft. Source W24x84/C15x33.9 runway members, bearing gaps, seat bolts and flexible tie-backs are retained. Rail shape and 24 in roof-joist internal geometry are fictional supplier assumptions; fatigue requirements remain in source records.')

def retrofit(b):
    for m in list(b.members):
        if m.get('phase')=='existing A36' and m['kind']=='column' and m['profile_id']=='W14X90':
            b.connection('RETROFIT-'+m['id'],'review_retrofit_column',m['axis'][0],[m],parameters={'plate_thickness':.75,'plate_width':12})
        if m['kind'] in ('beam','infill') and m['level']<=3:
            b.connection('RETROFIT-'+m['id'],'review_retrofit_beam',[(a+d)/2 for a,d in zip(*m['axis'])],[m],parameters={'plate_thickness':.5,'plate_width':6,'length_fraction':.6})
    b.note('RETROFIT','Fictional answers to R1-R7: adopt 1/2 x 6 in bottom cover plates over the middle 60% of existing beams, 3/4 x 12 in column flange cover plates, and illustrated connection/grillage reinforcement. These A details demonstrate the workflow; the source material survey, weldability, ASCE 41 and foundation verification requirements remain unresolved engineering verification, not invented evidence.')
