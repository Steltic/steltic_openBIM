"""Final source-bound HR drawing cases; no analysis or capacity redesign."""
import math,re
from .assembly_templates import NUMBER,number
KEYS={'hr1','hr2','hr3','hr4','hr5','hr6','hr7a','hr15','hr17','hr19','hr23','hr26','hr29','hr34a','hr34b'}

def prepare(b):
    if b.key=='hr19':b.custom('PG84X1108','i',{k:b.config['PG'][k] for k in ('d','bf','tw','tf')},basis='S: source welded plate girder, 84 in depth, 30 x 4 in flanges, 1-1/8 in web')

def floor_cells(b,levels):
    c=b.config;g=c.get('G',c.get('GEO',c.get('LAYOUT',{})));xs=c.get('XS',g.get('xs'));ys=c.get('YS',g.get('ys'));present=c.get('PRESENT',g.get('present'))
    if not xs:xs=[i*c.get('SX',336) for i in range(c['NX']+1)]
    if not ys:ys=[i*c.get('SY',336) for i in range(c['NY']+1)]
    result=[]
    for k,z in enumerate(levels[1:],1):
        points={tuple(p) for p in present.get(str(k),[])} if present else None
        for i in range(len(xs)-1):
            for j in range(len(ys)-1):
                if points is not None and b.key!='hr19' and not {(i,j),(i+1,j),(i,j+1),(i+1,j+1)}<=points:continue
                result.append([xs[i],xs[i+1],ys[j],ys[j+1],z])
    b.note('SOURCE-FLOORS','S: occupied floor cells follow the source grid/presence declarations; omitted transfer columns are not slab openings. A: the floor workline is top of steel, and supplementary stair/service openings are explicitly framed.')
    return result

def infill(b,k,lo,hi,records,candidates):
    want=None
    if b.key=='hr4' and k<=2 and lo[0]>=370 and hi[0]<=1850 and lo[1]>=330 and hi[1]<=990:want='infill-stack-'
    if b.key=='hr15' and ((k==7 and (hi[0]>1800 or hi[1]>1440)) or (k==14 and (lo[0]<360 or lo[1]<360))):want='infill-terrace-'
    if b.key=='hr17' and k==9:want='infill-level9-'
    if b.key.startswith('hr34') and k==2:want='infill-L2ext-' if b.key=='hr34b' and lo[0]>=1080 else 'infill-L2-'
    if want:return [r for r in records if r.startswith(want)] or candidates
    # Typical floors must not inherit a terrace / library / podium size just because it is first.
    regular=[r for r in candidates if not any(s in r for s in ('stack','terrace','L2','L9','drift'))]
    return regular or candidates

def beam_record(b,m,raw,default,levels):
    pid=m['profile_id'];k=m['level'];roof=k==len(levels)-1
    if b.key=='hr7a' and m['kind']!='infill':
        a,d=m['axis'];along=0 if abs(d[0]-a[0])>abs(d[1]-a[1]) else 1;normal=1-along;step=b.config['SY' if normal==1 else 'SX'];span=b.config['SX' if along==0 else 'SY'];mid=(a[along]+d[along])/2/span
        moment=any(f[0]=='XY'[along] and abs(a[normal]-f[1]*step)<.1 and f[2]<mid<f[3]+1 for f in b.config['FRAMES'])
        if not moment:return next((r for r in raw if r.startswith('conn-simple-') and r.endswith('-'+pid)),default)
    options=[r for r in raw if r.endswith('-'+pid) and ('infill' in r)==(m['kind']=='infill') and not any(t in r for t in ('col-','col_','base-','brace','joint','simple-'))]
    if m['kind']=='infill':
        expected=[r.replace('members/','conn-') for r in m['design_record_ids']]
        exact=next((r for r in expected if r in raw),None)
        if exact:return exact
    exact=f'conn-floor-{pid}-level-{k}'
    if exact in raw:return exact
    return next((r for r in options if ('roof' in r)==roof),default)

def physical_extras(b,levels):
    from .review_hr import nearest
    if b.key=='hr3':
        b.note('STEEL-GRADE-LIMIT','The steel review begins at the grade slab. Column sections and splice stations above grade follow the HR design.')
    if b.key=='hr19':
        pieces=[m for m in b.members if m['profile_id']=='PG84X1108'];first=min(pieces,key=lambda m:min(q[0] for q in m['axis']))
        first['axis']=[min((q for m in pieces for q in m['axis']),key=lambda q:q[0]),max((q for m in pieces for q in m['axis']),key=lambda q:q[0])]
        first['analysis_ids']=[v for m in pieces for v in m.get('analysis_ids',[])];b.members[:]=[m for m in b.members if m not in pieces or m is first]
        b.note('TRANSFER','S: continuous PG84X1108 simple-span transfer girder; columns A2/A3 bear on its top flange. End seats slide, while the separate top collar carries axial force. Brief Level 2 is model L1. Supplier bearing certification and foundation design remain delegated.')
    if b.key=='hr26':
        z=levels[-1];rid=b.record('connections','tmd-support-path')
        b.endpoint_links=getattr(b,'endpoint_links',[]);legs={}
        for j,x in enumerate((480,600)):
            m=b.member('TMD-SUPPORT-'+str(j),'W24X68','girder',[x,360,z+24],[x,720,z+24],18,'A',records=[rid,b.record('members','tmd-support-W24X68')],setout_basis='S 30 ft span and 10 ft spacing; A top-of-support datum')
            for y in (420,660):
                leg=b.member(f'TMD-LEG-{j}-{y}','HSS4X4X1/4','equipment_leg',[x,y,z+24.75],[x,y,z+48],18,'A',
                    setout_basis='A: accepted fictional supplier support leg; damper supplier design remains delegated')
                foot=b.connection(f'TMD-FOOT-{j}-{y}','review_equipment_foot',[x,y,z+24],[leg,m],[rid],parameters={'joint':'tmd_supplier_base'})
                legs[j,y]=leg;b.endpoint_links.append(dict(member_id=leg['id'],end='start',connection_id=foot['id'],basis='Actual supplier leg bottom welded to its own located base plate'))
        for y in (420,660):
            rail=b.member('TMD-BASE-RAIL-'+str(y),'HSS6X4X1/4','equipment_base_rail',[480,y,z+51.5],[600,y,z+51.5],18,'A',records=[rid],setout_basis='A: explicit supplier base-frame rail on the four leg cap plates; no new capacity approval')
            for j,x in enumerate((480,600)):
                head=b.connection(f'TMD-HEAD-{j}-{y}','review_equipment_head',[x,y,z+48],[legs[j,y],rail],parameters={'rail_side':1 if j==0 else -1},basis='A: supplier cap plate and base-frame attachment; supplier verification remains required')
                b.endpoint_links.extend([dict(member_id=legs[j,y]['id'],end='end',connection_id=head['id'],basis='Actual supplier leg head welded to its own cap plate'),dict(member_id=rail['id'],end='start' if j==0 else 'end',connection_id=head['id'],basis='Actual supplier base-frame rail bears and bolts to this same cap plate')])
        b.changes.append(dict(kind='accepted_supplier_support_geometry',basis='A: four HSS4X4X1/4 supplier legs give the previously shown damper feet an explicit physical receiver. These legs and attachments have no new capacity approval.'))
        b.panel('TMD-ENVELOPE','equipment',[[468,408,z+24],[612,408,z+24],[612,672,z+24],[468,672,z+24]],48,18,'A',scope='A supplier mass/base-frame envelope; S 87 kip damper')
        b.note('DAMPER','S: 87 kip TMD; two W24X68 beams, 30 ft span and 10 ft apart, at third points of the core X roof struts. A: beams placed above the roof struts, 12 x 22 x 4 ft supplier envelope, base plate and bolt fit. Supplier dynamics, travel and anchorage design are not inferred.')

def connections(b,levels):
    from .review_hr import nearest
    raw={r['id']:r for r in b.raw['connections']};lookup={m['id']:m for m in b.members}
    def attach(c,short,first=False):
        rid=b.record('connections',short)
        if rid and rid not in c['design_record_ids']:
            c['design_record_ids'].insert(0,rid) if first else c['design_record_ids'].append(rid);b.used_records.add(rid)
    for c in b.connections:
        m=lookup[c['member_ids'][0]];pid=m['profile_id'];k=m['level'];p=c.setdefault('parameters',{});fam=c['detail_ref']['id'];point=c['point'];a,d=m['axis'];along=0 if abs(d[0]-a[0])>abs(d[1]-a[1]) else 1;direction='XY'[along]
        if fam in ('review_brace','review_brb'):
            if b.key=='hr4':
                group='F3_F4' if along==0 else 'F1_F2';rid=f'conn-brace-{pid}-{group}-s{k}'
                if rid in raw:c['design_record_ids']=[b.record('connections',rid)];b.used_records.update(c['design_record_ids'])
            if p.get('joint')=='base':attach(c,'conn-brace-base-'+pid,True)
            if p.get('joint')=='apex':
                beam=next((lookup[i] for i in c['member_ids'][1:] if lookup[i]['kind'] in ('beam','girder','moment_beam')),None)
                if beam:attach(c,'conn-brace-apex-'+beam['profile_id'],True)
        if fam=='review_beam':
            support=next((lookup[i] for i in c['member_ids'][1:] if lookup[i]['kind']=='column'),None)
            if support and p.get('moment'):
                opposite=any(mm['id']!=m['id'] and mm['kind']=='moment_beam' and mm['level']==k and any(math.dist(q,point)<.1 for q in mm['axis']) and abs(mm['axis'][1][1-along]-mm['axis'][0][1-along])<.1 and (sum(q[along] for q in mm['axis'])/2-point[along])*(sum(q[along] for q in m['axis'])/2-point[along])<0 for mm in b.members)
                typ='int' if opposite else 'end';cp=support['profile_id']
                for short in (f'conn-joint-L{k}-{typ}-{cp}',f'conn-joint-L{k}-{typ}-{cp}-{direction}'):attach(c,short)
                prefix='conn-SMF-joint-'+cp
                top=max(q[2] for q in support['axis'])
                at_top=abs(point[2]-top)<.1 and not any(mm['kind']=='column' and mm['id']!=support['id'] and min(q[2] for q in mm['axis'])>=top-.1 and math.dist(mm['axis'][0][:2],point[:2])<.1 for mm in b.members)
                best=prefix+'-roof' if at_top and prefix+'-roof' in raw else prefix+'-'+pid if prefix+'-'+pid in raw else prefix
                attach(c,best)
                if b.key=='hr15':attach(c,f'conn-collector-setback-L{k}-{direction}-{pid}')
            if p.get('collector') and not p.get('moment'):
                for short in (f'conn-collector-{direction}-'+('roof' if k==len(levels)-1 else 'floor'),f'conn-collector-{direction}-{pid}',f'conn-collector-setback-L{k}-{direction}-{pid}','conn-column-webs-collector-lines'):attach(c,short,True)
            if b.key=='hr3' and m['kind']!='infill':
                braces=[mm for mm in b.members if mm['kind']=='brace' and mm['level']==k and abs(mm['axis'][0][1-along]-a[1-along])<.1 and min(q[along] for q in mm['axis'])<=sum(q[along] for q in m['axis'])/2<=max(q[along] for q in mm['axis'])]
                if braces:attach(c,'conn-bracedbay-beam-'+direction+'-'+braces[0]['profile_id'],True);attach(c,'collector-irregularity-lines');attach(c,'conn-column-webs-collector-lines');p['collector']=True
            if b.key=='hr19' and pid=='PG84X1108':
                c['detail_ref']['id']='review_pg_seat';attach(c,'conn-A1-A4-level2-hinge-zone')
                generic=b.record('connections','conn-collector-X-floor')
                if generic in c['design_record_ids']:
                    c['design_record_ids'].remove(generic);c.setdefault('source_context_records',[]).append(generic)
                    b.changes.append(dict(kind='specific_transfer_bearing_selection',connection_id=c['id'],context_record=generic,basis='Source PG sliding seat and separate axial collar govern this transfer-girder end; the ordinary beam single-plate collector detail remains on its actual W-beam occurrences'))
        if fam=='review_splice' and len(c['member_ids'])>1:
            below=lookup[c['member_ids'][1]];pair=pid+' over '+below['profile_id'];matches=[r for r,row in raw.items() if pair+':' in row.get('components','')]
            if matches:
                for short in matches:attach(c,short)
                txt=raw[matches[0]].get('components','');hit=re.search(r'story '+str(k)+r': '+NUMBER+r' in above the floor',txt) or re.search(NUMBER+r' in above the floor',txt)
                if hit:offset=number(hit[1]);c['point'][2]=min(q[2] for q in m['axis'])+offset;p['splice_offset_in']=offset
        if fam in ('review_column_continuity','review_base'):
            short='conn-lateral_col-'+pid
            if short in raw and any(t in str(raw[short]).lower() for t in ('no field splice','no column splice','one piece')):attach(c,short)
            if b.key=='hr19' and pid=='W36X925':attach(c,'conn-transfer-support-col-W36X925')
    if b.key=='hr17':
        for k,z in enumerate(levels[1:],1):
            for direction in ('X','Y'):
                beam=next(m for m in b.members if m['level']==k and m['kind'] in ('beam','girder') and ('X' if abs(m['axis'][1][0]-m['axis'][0][0])>1 else 'Y')==direction)
                b.connection(f'DIAPHRAGM-{k}-{direction}','review_diaphragm',beam['axis'][0],[beam],[b.record('connections','conn-diaphragm-floors'),b.record('connections','conn-diaphragm-frame-studs')],parameters={'transfer':False,'direction':direction})
    if b.key=='hr19':
        pg=next(m for m in b.members if m['profile_id']=='PG84X1108')
        for i,point in enumerate(pg['axis']):
            col=nearest(b,point,('column',))
            b.connection('PG-COLLAR-'+str(i),'review_pg_collar',point,[pg,col],[b.record('connections','conn-A1-A4-level2-hinge-zone')])
        for x in (360,720):
            col=next(m for m in b.members if m['kind']=='column' and m['level']==2 and m['axis'][0][:2]==[x,0])
            b.connections[:]=[c for c in b.connections if not(c['member_ids'][0]==col['id'] and c['detail_ref']['id'] in ('review_splice','review_column_continuity'))]
            b.connection('PG-PICKUP-'+str(x),'review_pg_pickup',[x,0,levels[1]],[col,pg],[b.record('connections','conn-transfer-pickups-A2-A3')])
    if b.key.startswith('hr34'):
        side=1080 if b.key=='hr34a' else 0
        for k in range(2,min(10,len(levels)-1)+1):
            beam=next(m for m in b.members if m['kind'] in ('beam','girder') and m['level']==k and all(abs(q[0]-side)<.1 for q in m['axis']))
            b.connection('TOWER-INTERFACE-'+str(k),'review_tower_podium' if k==2 else 'review_tower_joint',[side,600,levels[k]],[beam],[b.record('connections','L2-inter-tower-transfer' if k==2 else 'seismic-joint-TowerA-TowerB')],parameters={'joint':'podium' if k==2 else 'separation','clear_gap_in':19,'column_spacing_in':39})
        b.note('TOWER-JOINT','S: 19 in clear seismic joint, columns 39 in apart, from L3 to Tower B roof. No member crosses it. S: L2 podium slab/tie is continuous with #4 at 12 in each way and 3/4 in collector studs at 12 in. Each tower model uses its own local X origin; the interface details show the adjacent tower as labelled context. Hardware remains supplier-designed.')
    for panel in b.panels:
        if panel['kind']=='floor' and panel['level']==len(levels)-1:panel['kind']='roof'
