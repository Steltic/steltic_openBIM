"""Additional source geometry and connection applicability for the second HR batch."""
import ast,math,re
from collections import defaultdict
from .review_model import add,sub,mul,unit
from .assembly_templates import number,NUMBER

KEYS={'hr14','hr16','hr18','hr20','hr21','hr24','hr25','hr30','hr31','hr35'}
def is_case(b):return b.key in KEYS

def prepare(b):
    if b.key=='hr16':b.note('FINAL-SYSTEM','S: the completed school design is SMF with RBS joints and boxed two-way columns. The original folder/brief title says IMF; the final source design changed the system. Three roof datums remain separate.')
    if b.key=='hr14':b.note('HILLSIDE','S: east basement bases at B1; uphill columns start at Level 1. A: base plate top 12 in below the uphill grade/slab; retaining-wall separation remains a foundation interface. No uphill column is spliced to a nonexistent basement column.')
    if b.key=='hr21':b.note('JOIST-ANSWER','S: 50 ft open-web joists at 5 ft, supplier-designed with Is >= 1500 in4. A: 36 in deep paired-channel trusses and their node/seat geometry are fictional coordination geometry; the source supplier design requirement remains.')

def floor_cells(b,levels):
    c=b.config;nx,ny=c['NX'],c['NY'];sx,sy=c.get('SX',336),c.get('SY',336);out=[]
    for k,z in enumerate(levels[1:],1):
        bays={(i,j) for i in range(nx) for j in range(ny)}
        if b.key=='hr14':bays={tuple(p) for p in c['BAYS_L1' if k==1 else 'BAYS_ALL']}
        if b.key=='hr16':
            regions=[c['CLASS']]+([c['LINK']] if k in (1,2) else []) if k!=3 else [c['GYM']]
            bays=set()
            for region in regions:
                pts={tuple(p) for p in region}
                bays|={(i,j) for i in range(nx) for j in range(ny) if {(i,j),(i+1,j),(i,j+1),(i+1,j+1)}<=pts}
        if b.key=='hr25' and k<c['LID']:bays-={tuple(p) for p in c['ATRIUM']}
        for i,j in sorted(bays):out.append([i*sx,(i+1)*sx,j*sy,(j+1)*sy,z])
    b.note('SOURCE-FLOORS','S: complete occupied cells reconstructed from source floor/wing/atrium declarations, including floors over omitted columns. Missing analysis-viewer cells do not imply floor openings.')
    return out

def physical_extras(b,levels):
    if b.key=='hr25':
        spans=[m for m in b.members if m['profile_id']=='W36X925']
        assert len(spans)==2
        first,second=sorted(spans,key=lambda m:min(q[1] for q in m['axis']))
        first['axis']=[min(first['axis'],key=lambda q:q[1]),max(second['axis'],key=lambda q:q[1])]
        first['analysis_ids']=first.get('analysis_ids',[])+second.get('analysis_ids',[])
        b.members.remove(second);b.changes.append(dict(kind='merge_analysis_segments',member=first['id'],merged=second['id'],basis='S continuous atrium lid girder; central column is a bearing load, not a girder splice'))
    if b.key=='hr14':
        # 132 in is an uphill footing datum, never an extra floor. B1 auxiliary
        # gravity framing was designed by hand and is absent from the viewer.
        for i in range(3,6):
            for j in range(2,5):
                b.member(f'B1-G-{i}-{j}','W21X44','girder',[i*312,j*312,0],[(i+1)*312,j*312,0],0,'S',records=[b.record('members','basement-girder-W21X44')])
        for i,j in b.config['BAYS_L1']:
            b.panel(f'B1-FLOOR-{i}-{j}','floor',[[i*312,j*312,0],[(i+1)*312,j*312,0],[(i+1)*312,(j+1)*312,0],[i*312,(j+1)*312,0]],6.25,0,'S')
            for off in (104,208):b.member(f'B1-INF-{i}-{j}-{off}','W16X26','infill',[i*312+off,j*312,0],[i*312+off,(j+1)*312,0],0,'S',records=[b.record('members','basement-infill-W16X26')])
    # The W-shaped transfer truss has physical members already in the replay.
    if b.key=='hr30':
        for beam in list(b.members):
            if beam['kind'] not in ('beam','girder','moment_beam'):continue
            a,d=beam['axis']
            if abs(a[0]-d[0])>.1:continue
            sign=1 if a[0]<540 else -1;depth=b.depth(beam['profile_id'])
            for j,y in enumerate(range(round(min(a[1],d[1]))+120,round(max(a[1],d[1])),120)):
                point=[a[0],y,a[2]-2];end=[a[0]+sign*120,y,a[2]-2]
                st=b.member(beam['id']+'-ST'+str(j),'HSS4X4X1/4','lateral_strut',point,end,beam['level'],'S')
                kick=b.member(beam['id']+'-KICK'+str(j),'HSS3X3X1/4','flange_brace',[a[0],y,a[2]-depth], [a[0]+sign*(depth-2),y,a[2]-2],beam['level'],'S')
                b.ends(st,'review_angle_clip',[b.record('connections','conn-strut-bracing-Y')],parameters={'count':2,'diameter':.75})
                b.ends(kick,'review_angle_clip',[b.record('connections','conn-strut-bracing-Y')],parameters={'count':2,'diameter':.75})
    if b.key=='hr20':
        for m in b.members:
            if m['profile_id']=='W14X665':
                m['kind']='transfer_vertical' if abs(m['axis'][1][2]-m['axis'][0][2])>1 and math.dist(m['axis'][0][:2],m['axis'][1][:2])<1 else 'transfer_chord' if abs(m['axis'][1][2]-m['axis'][0][2])<1 else 'transfer_diagonal'
        nodes=defaultdict(list)
        for m in b.members:
            if m['kind'].startswith('transfer_'):
                for point in m['axis']:nodes[tuple(point)].append(m)
        from .review_hr import nearest
        for i,(point,ms) in enumerate(nodes.items()):
            col=nearest(b,point,('column',));refs=[b.record('connections','conn-floor-W14X665'),b.record('connections','conn-brace-W14X665')]
            if col:refs.append(b.record('connections','conn-truss-support-C2-C5'))
            b.connection('TRANSFER-NODE-'+str(i),'review_transfer_truss',point,ms+([col] if col else []),refs,parameters={'support':bool(col),'joint':'support' if col else 'panel'})
        b.note('TRANSFER-RELEASE','S: Level-2 bottom chord is separated from slab by slip sheet and has no studs; adjacent C2-C3/C4-C5 beams have horizontal long slots at truss ends. Only Level 3 transfers the discontinuous Grid C frame shear. The drawing does not introduce a rigid diaphragm attachment at the lower nodes.')
    if b.key in ('hr16','hr25'):
        raw={r['id'] for r in b.raw['connections']}
        for col in b.members:
            if col['kind']!='column':continue
            if b.key=='hr16':continue  # exact source boxed-column orientation is already retained
            if b.key=='hr25' and not (col['axis'][0][0]==1008 and col['axis'][0][1] in (0,1440)):continue
            prefix='conn-two-way-'+('4A4E-' if b.key=='hr25' else '')+col['profile_id']+'-strong-'
            for beam in b.members:
                if beam['kind'] in ('beam','moment_beam','girder') and prefix+beam['profile_id'] in raw and any(math.dist(q[:2],col['axis'][0][:2])<.1 and min(v[2] for v in col['axis'])<=q[2]<=max(v[2] for v in col['axis']) for q in beam['axis']):
                    v=unit(sub(*reversed(beam['axis'])));col['local_y']=[-v[1],v[0],0];break
        for m in list(b.members):
            t=m.get('boxing_thickness_in')
            if b.key=='hr25' and m['kind']=='column' and m['axis'][0][0]==1008 and m['axis'][0][1] in (0,1440) and m['level']>=7:t=1
            if not t:continue
            m['boxing_thickness_in']=t;d=b.profiles[m['profile_id']]['dimensions'];ly=m['local_y'];normal=[-ly[1],ly[0],0]
            pid=b.custom('BOX-SIDE-'+m['profile_id']+'-'+str(t),'flat',dict(width=d['d'],thickness=t),basis='S: source full-height side plate; A edge fit')
            plates=[]
            for side in (-1,1):
                offset=mul(ly,side*(d['bf']+t)/2);axis=[add(q,offset) for q in m['axis']]
                if b.key=='hr25':axis[0][2]=max(axis[0][2],levels[6]+48)
                plates.append(b.member(m['id']+'-BOX'+str(side),pid,'column_box_plate',*axis,m['level'],'A',local_y=normal))
            refs=[b.record('connections','conn-two-way-joint-'+m['profile_id']),b.record('connections','conn-boxed-col-4A4E-'+m['profile_id']),b.record('members','lateral_col-'+m.get('source_boxed_profile',''))]
            b.connection(m['id']+'-BOX','review_column_box',m['axis'][0],[m]+plates,refs,parameters={'boxing_t':t})
    if b.key=='hr35':
        from .review_next_hr_industrial import equipment
        equipment(b,levels)
    if b.key in ('hr18','hr21','hr30'):
        groups=defaultdict(list)
        for m in b.members:
            if m['kind']=='brace':groups[tuple(round((a+d)/2,4) for a,d in zip(*m['axis']))].append(m)
        for i,(point,ms) in enumerate(groups.items()):
            if len(ms)<2:continue
            refs=[b.record('connections','conn-brace-'+m['profile_id']) for m in ms]
            if b.key=='hr30':
                direction='X' if abs(ms[0]['axis'][1][0]-ms[0]['axis'][0][0])>.1 else 'Y';refs.insert(0,b.record('connections','conn-brace-crossing-'+direction+'-'+ms[0]['profile_id']))
            if b.key=='hr21':refs.insert(0,b.record('connections','conn-brace-HSS7X7X1/2-crossing'))
            b.connection('X-CROSS-'+str(i),'review_brace_crossing',point,ms,refs,parameters={'joint':'crossing'})

def connection_extras(b,levels):
    from .review_hr import nearest
    lookup={m['id']:m for m in b.members};raw={r['id']:r for r in b.raw['connections']}
    def attach(c,rid,first=False):
        rid=b.record('connections',rid)
        if rid and rid not in c['design_record_ids']:
            c['design_record_ids'].insert(0,rid) if first else c['design_record_ids'].append(rid)
            b.used_records.add(rid)
    for con in b.connections:
        m=lookup[con['member_ids'][0]];p=con.setdefault('parameters',{});fam=con['detail_ref']['id'];k=m['level'];point=con['point'];pid=m['profile_id'];a,d=m['axis'];along=0 if abs(d[0]-a[0])>abs(d[1]-a[1]) else 1;direction='XY'[along]
        if b.key=='hr16' and m.get('source_boxed_profile') and fam in ('review_base','review_splice','review_column_continuity'):
            rid='conn-'+('base-' if fam=='review_base' else '')+'lateral_col-'+m['source_boxed_profile']
            if rid in raw:con['design_record_ids']=[b.record('connections',rid)];b.used_records.add(b.record('connections',rid))
            p['boxing_t']=1
        if b.key=='hr25' and fam=='review_base' and point[0]==1008 and point[1] in (0,1440):
            con['design_record_ids']=[b.record('connections','conn-base-4A4E-W14X455')];b.used_records.update(con['design_record_ids'])
        if b.key=='hr16' and fam=='review_base' and pid=='W14X176' and point[0] in (336,672) and point[1] in (0,672):
            con['design_record_ids']=[b.record('connections','conn-base-pinned-W14X176')];b.used_records.update(con['design_record_ids'])
        if fam in ('review_beam','review_pin_beam'):
            support=next((lookup[i] for i in con['member_ids'][1:] if lookup[i]['kind']=='column'),None)
            if support and support.get('boxing_thickness_in'):p['boxing_t']=support['boxing_thickness_in']
            if support and support.get('boxing_thickness_in') and b.key in ('hr16','hr25'):
                weak=abs(sum(q*v for q,v in zip(unit(sub(d,a)),support['local_y'])))>.7;side='weak' if weak else 'strong';cp=support['profile_id'];prefix='conn-two-way-'+('4A4E-' if b.key=='hr25' else '')
                attach(con,prefix+cp+'-'+side+'-'+pid,True);attach(con,'conn-two-way-joint-'+('4A4E-' if b.key=='hr25' else '')+cp)
            if b.key=='hr16':
                if support:attach(con,'conn-column-webs-collector-lines')
                if support and support.get('source_boxed_profile'):attach(con,'conn-two-way-joint-'+support['profile_id'])
                if k==1 and pid=='W18X46' and m['kind']=='infill' and 1008<=point[0]<=1344 and 336<=point[1]<=1008:attach(con,'conn-infill-library-W18X46',True)
                if k in (1,2) and point[1] in (336,672) and 672<=point[0]<=1344:attach(con,'collector-irregularity-lines')
            if b.key in ('hr18','hr21','hr30'):
                braces=[mm for mm in b.members if mm['kind']=='brace' and mm['level']==k and abs(mm['axis'][0][1-along]-a[1-along])<.1 and min(q[along] for q in mm['axis'])<=sum(q[along] for q in m['axis'])/2<=max(q[along] for q in mm['axis'])]
                if braces and m['kind']!='infill':
                    attach(con,'conn-bracedbay-beam-'+direction+'-'+braces[0]['profile_id'],True)
                    attach(con,'conn-roof-'+pid+'-braced-bay',True)
                    if b.key=='hr30':p['paired_shear_plates']=True
                elif m['kind']!='infill':
                    suffix=direction+'-'+('roof' if k==len(levels)-1 else 'floor')+'-'+pid
                    attach(con,'conn-collector-beam-'+suffix,True);attach(con,'conn-collector-'+suffix,True)
            if b.key=='hr20':
                if k%2==0 and support:
                    rid='conn-'+('roof' if k==12 else 'floor')+'-'+pid+('' if k==12 else '-level-'+str(k+1))
                    if rid in raw and 'pin' in str(raw[rid]).lower():con['detail_ref']['id']='review_pin_beam';con['design_record_ids']=[b.record('connections',rid)];p['joint']='pin_release'
                if point[1]==720 and point[2]==216 and point[0] in (720,1080) and pid!='W14X665':
                    con['detail_ref']['id']='review_transfer_slip';p['joint']='horizontal_slip';p['travel_in']=2;attach(con,'conn-diaphragm-level3-transfer')
                elif 'two-plate' in str([raw.get(r.split('/')[-1],{}) for r in con['design_record_ids']]):p['paired_shear_plates']=True
            if b.key=='hr25' and pid=='W36X925':p['joint']='atrium_lid_end'
            if b.key=='hr30' and pid=='W21X68':p['paired_shear_plates']=True
            if b.key=='hr30' and m['kind']=='infill':attach(con,'conn-strut-bracing-X')
            if b.key=='hr14' and k==0 and m['kind']=='infill':attach(con,'conn-basement-infill-W16X26',True)
            if b.key=='hr14' and k==0 and pid=='W21X44':attach(con,'conn-basement-girder-W21X44',True)
            if b.key=='hr21':attach(con,'conn-collector-'+direction)
            if b.key=='hr24' and direction=='Y' and point[0] in (0,1080,2160) and m['kind']!='infill':attach(con,'conn-collector-Y-lines',True)
            if b.key=='hr24' and pid=='W24X103' and point[:2] in ([0,0],[2160,1080]) and k%2==1:
                attach(con,'conn-scbf-corner-1A7D-odd')
                if k==9:p['boxing_t']=1.5;p['boxing_length_in']=30
            if b.key=='hr25':
                if k<7 and (point[0] in (672,1344) and 360<=point[1]<=1080 or point[1] in (360,1080) and 672<=point[0]<=1344):attach(con,'conn-atrium-edge-collector',True)
                if pid in ('W18X35','W24X55'):
                    if k<7 and point[1] in (360,1080):attach(con,'conn-atrium-collector-continuation-'+pid)
                    attach(con,'conn-infill-'+pid if m['kind']=='infill' else 'conn-column-webs-chord-lines')
        if fam=='review_brace':
            if b.key=='hr24':
                if p.get('joint')=='apex':attach(con,'conn-scbf-midspan-gusset',True)
                elif point[:2] in ([0,0],[b.config['NX']*b.config['SX'],b.config['NY']*b.config['SY']]):
                    lev=min(range(len(levels)),key=lambda j:abs(levels[j]-point[2]));attach(con,'conn-scbf-corner-1A7D-'+('L'+str(lev) if lev%2==0 else 'odd'),True)
            if b.key in ('hr18','hr30','hr35') and p.get('joint')=='base':
                for rid in ('conn-gusset-base-'+direction+'-'+pid,'conn-brace-base-'+direction,'conn-brace-base-'+direction+'-'+pid):attach(con,rid,True)
            if b.key=='hr21' and direction=='X':attach(con,'conn-brace-HSS7X7X1/2-x-frames',True)
            if b.key=='hr30' and p.get('joint')!='base':p['beam_only_gusset']=True
            if b.key=='hr35' and direction=='Y' and point[1]==0:
                attach(con,'conn-brace-base-Y-web-'+pid if p.get('joint')=='base' else 'conn-brace-web-'+pid,True);p['weak_axis_gusset']=True
    if b.key=='hr16':
        for y in (672,1008):
            col=nearest(b,[1680,y,288],('column',));low=nearest(b,[1680,y,288],('beam','girder','moment_beam'));high=nearest(b,[1680,y,312],('beam','girder','moment_beam','infill'))
            if col and low and high:b.connection('ROOF-STEP-'+str(y),'review_roof_step',[1680,y,288],[col,low,high],[b.record('connections','conn-step-link-gym-roofs')],parameters={'joint':'roof_step'})
    if b.key=='hr25':
        column=next(m for m in b.members if m['kind']=='column' and m['level']==8 and m['axis'][0][:2]==[1008,720])
        point=min(column['axis'],key=lambda p:p[2]);beam=next(m for m in b.members if m['profile_id']=='W36X925')
        b.connections[:]=[c for c in b.connections if not (c['member_ids'][0]==column['id'] and c['detail_ref']['id'] in ('review_column_continuity','review_splice') and c['point'][2]<point[2]+49)]
        b.connection('ATRIUM-COLUMN-BEARING','review_transfer_bearing',point,[column,beam],[b.record('members','floor-W36X925'),b.record('members','lateral_col-W14X99')],parameters={'joint':'column_on_lid'})
    if b.key=='hr20':
        for k,z in enumerate(levels[1:],1):
            for direction in ('X','Y'):
                beam=next(m for m in b.members if m['level']==k and m['kind'] in ('beam','girder') and ('X' if abs(m['axis'][1][0]-m['axis'][0][0])>1 else 'Y')==direction)
                b.connection(f'DIAPHRAGM-{k}-{direction}','review_diaphragm',beam['axis'][0],[beam],[b.record('connections','conn-diaphragm-level3-transfer' if k==2 else 'conn-diaphragm-floors'),b.record('connections','conn-diaphragm-frame-studs')],parameters={'transfer':k==2,'direction':direction,'joint':'transfer' if k==2 else 'typical'})
        b.note('FLOOR-LEVEL-NAMES','Source model k=1 is architectural Level 2 (+18 ft), k=2 is Level 3 (+36 ft). Only k=2 has the transfer reinforcement; Level 2 remains isolated at the truss bottom chord. The diaphragm details show the scheduled braced-line attachment zones; non-braced gravity beams do not inherit their stud counts.')
    # Column-top closure/seat is not a fabricated field splice.
    if b.key in ('hr21','hr35'):
        for m in list(b.members):
            if m['kind']!='column':continue
            point=max(m['axis'],key=lambda p:p[2])
            if any(mm['kind']=='column' and mm['id']!=m['id'] and math.dist(min(mm['axis'],key=lambda p:p[2]),point)<.1 for mm in b.members):continue
            ids=[r for r in raw if r.endswith('-'+m.get('source_boxed_profile',m['profile_id'])) and 'base' not in r and ('col-' in r or 'col_' in r)]
            if not ids:continue
            b.connection(m['id']+'-CAP','review_column_cap',point,[m],[b.record('connections',r) for r in ids],parameters={'joint':'cap','stiffened':b.key=='hr35' and point[:2] not in ([0,0],[720,0],[0,480],[720,480])})
    # Stud layout and camber are source design outputs, kept independent of strength checks.
    if b.key=='hr30':
        for m in list(b.members):
            if m['kind'] not in ('beam','girder','infill','moment_beam'):continue
            pid=m['profile_id'];roof=m['level']==len(levels)-1
            m['camber_in']=.75 if pid=='W21X55' or roof and pid=='W21X44' else 0
            if roof or pid not in ('W21X55','W24X62','W21X68'):continue
            count={'W21X55':80,'W24X62':49,'W21X68':53}[pid]
            b.connection(m['id']+'-COMPOSITE','review_composite_studs',[(a+d)/2 for a,d in zip(*m['axis'])],[m],[b.record('composite_design','studs')],parameters={'count':count,'diameter':.75,'length_in':math.dist(*m['axis']),'joint':pid,'camber_in':m['camber_in']})
        b.note('CAMBER','S: W21X55 floor beams 3/4 in; W21X44 roof beams 3/4 in; W24X62 and W21X68 zero. Source composite_design overrides the generic analysis camber screen. Source headed studs: 80/49/53 by section with end/middle zoning. A stud height and local deck fit remain labelled.')
    for panel in b.panels:
        k=panel['level'];verts=panel['vertices'];is_roof=k==len(levels)-1 and b.key!='hr35' or b.key=='hr21'
        if b.key=='hr16':
            is_roof=k in (3,4) or k==2 and all(1008<=q[0]<=1680 for q in verts)
        if panel['kind']=='floor' and is_roof:panel['kind']='roof'
