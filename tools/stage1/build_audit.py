"""Read-only Stage 1 audit. Does not run cfg.py, a solver, or a design engine.

Inputs: inspect_sources.py snapshot in corpus.json and reviewed building notes.
Outputs: reviewable CSV/JSON coverage and issue registers. Geometry screening is
lexical evidence discovery, not a production connection parser or design check.
"""
import ast
import argparse
import collections
import csv
import hashlib
import json
import pathlib
import re
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work-dir', type=pathlib.Path, default=pathlib.Path(__file__).parent)
parser.add_argument('--review-notes', type=pathlib.Path, default=pathlib.Path(__file__).parent/'review_notes.json')
args=parser.parse_args()
HERE = args.work_dir
OUT = HERE / 'data'
OUT.mkdir(exist_ok=True)
CORPUS = json.loads((HERE / 'corpus.json').read_text(encoding='utf-8'))
REVIEW = json.loads(args.review_notes.read_text(encoding='utf-8'))
AS_OF = '2026-11-02'
REPO_REVISIONS = {
    'HR': 'f880ef4396e620d1a24a355c19e9237b304570d9',
    'CFS': '2e93c55fcf8ced44a3bbb211f61d48a14b300ad3',
    'Hub': '601b7dac4bac459290675a1d3d856a2b7641fc9a',
}
EXTRA_TABLES = ['anchorage','holddowns','collectors','diaphragms','schedules','bases','chords','frames','framing','gravity_framing','headers','joists','wall_lines','studs','materials','segment_framing','braced_wall_layout','braced_bay_layout']
DETAIL_KEYS = ['components','selection','member','section','sheathing','fastening','fastener_schedule','design_note','note','bracing','bracing_assumption','rod_schedule','rows','schedule','elements','by_level','design_by_level','material','spec','grade','walls','braced_bays_ft','line_extent_ft']
LOCATION_KEYS = ['line','direction','story','level','levels','by_joint','joint','at_pos','at_neg','governing_level','governing_story']

def text(value):
    return json.dumps(value, ensure_ascii=False) if not isinstance(value,str) else value

def snippet(value,n=350):
    v=re.sub(r'\s+',' ',text(value)).strip()
    return v if len(v)<=n else v[:n-3]+'...'

def short_id(name,module):
    return ('HR-' if module=='HR' else 'CFS-') + re.search(r'Ex(\d+[a-z]?)',name).group(1)

def field_strings(obj,path=''):
    if isinstance(obj,dict):
        for k,v in obj.items():
            yield from field_strings(v,path+'/'+str(k).replace('~','~0').replace('/','~1'))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):yield from field_strings(v,path+'/'+str(i))
    else:yield path,obj

def family(row,table):
    typ=str(row.get('type') or row.get('joint') or '')
    ident=str(row.get('id',''))
    head=(typ+' '+ident).lower()
    head+=' '+re.sub(r'[_-]+',' ',head)
    if row.get('waived'):return 'Excluded by source'
    if re.match(r'no (?:column |beam )?splice|gravity column, no splice',typ.lower()):return 'No-splice design note'
    if table!='connections':
        return {'anchorage':'Anchorage','holddowns':'Hold-down / rod','collectors':'Collector / splice','diaphragms':'Diaphragm transfer','schedules':'Secondary framing schedule','bases':'Base / hold-down','chords':'Built-up chord','frames':'Frame assembly','framing':'Framing / bearing detail','gravity_framing':'Gravity framing detail','headers':'Header / jamb','joists':'Joist / bearing','wall_lines':'Wall assembly','studs':'Stud / chord / bridging','materials':'Material specification','segment_framing':'Wall segment framing','braced_wall_layout':'Braced wall layout','braced_bay_layout':'Braced bay layout'}[table]
    tests=[
        ('Movement / separation joint',r'seismic joint|seismic-joint|movement joint'),
        ('Equipment / attachment',r'tuned mass|tmd.support|vessel leg|stair.stringer'),
        ('Crane / runway / bracket',r'crane|runway|tie.back|monorail'),
        ('Base / anchor / foundation',r'column base|base plate|base.anchor|post base|vbe base|conn.base|wall.to.mat|foundation|embedded.*base'),
        ('Bearing / cap / squash',r'^column top: cap plate'),
        ('Splice',r'splice'),
        ('RBS moment connection',r'reduced beam|rbs|conn-rbs'),
        ('End plate',r'end.plate'),
        ('Portal knee / ridge / valley',r'^(?:knee|ridge|apex|valley)\b|portal.*(?:knee|ridge|apex|valley)|conn[-_ ](?:knee|ridge|apex|valley)\b'),
        ('Hold-down / rod',r'hold.down|rod.*bracket|chord rods|conn.rod'),
        ('Truss joint',r'stmf|truss.*column|trusses.*segment|trusses.*vertical'),
        ('Wall / embed / tie',r'web plate.to|web.to|coupling beam.to.wall|tie bar.to.wall|wall.*stud|core.wall|ivbe'),
        ('Joint reinforcement',r'panel.zone|strong.column|scwb|hinge zone|continuity plate|local yielding|crippling|buckling|column web|doublers|stiffener'),
        ('BRB end / gusset',r'brb.to|brb.*gusset|brbf.*brace'),
        ('Knife / pin / clevis',r'knife|pin.hinge|clevis'),
        ('Shear plate / angle',r'single.plate|two.plate|double.plate|shear tab|simple shear|clip.angle|shear connection'),
        ('Brace / gusset / strap',r'brace|gusset|strap.end|conn-strap'),
        ('Floor / diaphragm transfer',r'floor.to.wall|wall.to.floor|floor.transfer|deck.to.wall|diaphragm|roof.step|split.line|roof.*walls|roof.*end wall|collector|drag|panel tracks'),
        ('Uplift / clip',r'uplift|clip'),
        ('Header / girder / post',r'header|girder.to.post|edge beam.to.post|beam.post|stud.*post'),
        ('Bearing / cap / squash',r'bearing|cap plate|column top|squash'),
        ('Built-up / stud / track',r'built.up|stud.to.track|interconnection'),
        ('Member restraint / bracing',r'bottom.flange.struts|special bracing|torsion.brac'),
        ('Braced-bay beam joint',r'scbf corner columns'),
        ('Welded moment joint',r'fully restrained|moment|cjp'),
        ('Ledger / walkway / attachment',r'ledger|walkway|attachment|terrace|guard'),
        ('Beam / column joint',r'beam.to.column|beam.end|girder.to.column|beam.to.girder'),
    ]
    for f,regex in tests:
        if re.search(regex,head):return f
    return 'Special connection - review'

def describe(row):
    return ' | '.join(k+': '+snippet(row[k],1800) for k in DETAIL_KEYS if row.get(k) not in (None,'',[],{}))

def detected_dimensions(row):
    raw=text(row)
    checks={
        'fasteners':r'\bbolt|\bscrew|\banchor rod|\bpin\b',
        'spacing':r'\bpitch\b|\bgauge\b|\bgage\b|\bspacing\b|\bspaced\b|\bo\.c\.|screw_spacing_in|anchor_spacing_in',
        'edge distance':r'\bedge (?:distance|>=|≥)|\bend distance|\bedge/end|\bend/edge|\b(?:vertical|horizontal) edge|\be\s*=|\bedge\s*\d',
        'weld':r'\bweld|\bfillet|\bcjp\b|\bpjp\b',
        'plate datum':r'top.of.steel|top of (?:the )?(?:beam|girder)|(?:centred|centered|centering|centring).*web|below.*(?:top flange|top of)|plate.*(?:top|bottom).*elevation',
        'hole':r'\bhole|\bslot',
    }
    return {k:bool(re.search(v,raw,re.I)) for k,v in checks.items()}

def json_ref(b,table,index=None):
    p='design/'+('calc_package.json' if b['module']=='HR' else 'calc_package_cfs.json')
    return p+'#/'+table+(('/'+str(index)) if index is not None else '')

def cfg_ref(b,pattern):
    for i,line in enumerate(b['cfg'].splitlines(),1):
        if re.search(pattern,line,re.I):return 'cfg.py:L'+str(i)
    return 'cfg.py:L1'

def model_stats(b):
    job=pathlib.Path(b['folder']); nodes={}; elements={}; transforms={}; issues=[]
    f=job/'model_opensees.py'
    if f.exists():
        for n in ast.walk(ast.parse(f.read_text(encoding='utf-8-sig'))):
            if not (isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='ops'):continue
            if n.func.attr not in ('node','element','geomTransf'):continue
            try:a=[ast.literal_eval(x) for x in n.args]
            except (ValueError,TypeError):issues.append('Nonliteral '+n.func.attr);continue
            if n.func.attr=='node':nodes[str(a[0])]=a[1:]
            elif n.func.attr=='element':elements[str(a[1])]=a
            else:transforms[str(a[1])]=a
        vtags={str(e['tag']) for e in b['viewer']['elements']}
        with (job/'design/member_schedule.csv').open(encoding='utf-8-sig',newline='') as stream:
            stags={r['ele_tag'] for r in csv.DictReader(stream)}
        if vtags!=stags or vtags!=set(elements):issues.append('Model/viewer/schedule tag difference')
    return {'literal_nodes':len(nodes) if f.exists() else None,'model_elements':len(elements) if f.exists() else None,'transforms':len(transforms) if f.exists() else None,'tag_check':'MATCH' if f.exists() and not issues else ('NOT APPLICABLE' if not f.exists() else '; '.join(issues))}

records=[]; gaps=[]; coverage=[]; facts=[]

def gap(b,code,category,requirement,available,remaining,action,owner,blocks,refs,excerpt='',affected=None):
    bid=b if isinstance(b,str) else short_id(b['building'],b['module'])
    gaps.append({'id':bid+'-'+code,'building':bid,'module':b['module'] if isinstance(b,dict) else 'All',
        'category':category,'requirement':requirement,'available':available,'remaining':remaining,'action':action,
        'suggested_resolver':owner,'needed_for':blocks,'source':refs,'evidence':snippet(excerpt,1000),
        'affected_records':affected or [],'review_status':'Open','resolution':''})

gap('ALL','01','Extract existing','Versioned drawing data',
    'Source calculation packages and model/schedule files exist for every job.',
    'No common, complete drawing-geometry contract is published by these packages.',
    'Define an openBIM-owned schema with units, physical identities, source pointers and explicit unknowns. Populate it from existing outputs.',
    'openBIM developer','All outputs','HR steel_engine/design_pipeline.py; CFS steel_engine/cfs_pipeline.py; all package roots',
    'HR: calc_package.json, member_schedule.csv, connection_demands.csv and model files. CFS: calc_package_cfs.json, cfg.py and schematic viewer data.')
gap('ALL','02','Verify source','Producer engine revision',
    'Inputs have file hashes; all recorded consistency package hashes match. Current repository revisions are recorded separately.',
    'The exact producer Git commit is not established by the inspected output metadata. Current repository HEAD is not proof of producer version.',
    'Retain immutable input hashes. Record a producer commit if known before executing a configuration in an engine environment.',
    'Project maintainer','Reproducible extraction','design/consistency_result.json; design/pipeline_results.json where present',
    'The source_checks.json and source_manifest.json audit files retain the recorded check metadata and immutable input hashes.')
gap('ALL','03','Drawing decision','Sheet and detail conventions',
    'The brief specifies dimensioned design drawings first and gives an ANSI B connection-detail example.',
    'Project sheet sizes, scales, dimension precision, grid labels, title block and detail numbering are not a shared output contract.',
    'Set an openBIM drawing standard once. Preserve source engineering dimensions and record any presentation rounding.',
    'Drawing lead','DXF / PDF','ideas.txt',
    'Brief: an ANSI B connection-detail prototype; user scope: dimensioned design drawings and IFC export first.')

for b in CORPUS:
    p=b['package'];bid=short_id(b['building'],b['module']);review=REVIEW[bid]
    job=pathlib.Path(b['folder']);pack=job/'design'/('calc_package.json' if b['module']=='HR' else 'calc_package_cfs.json')
    cr=json.loads((job/'design/consistency_result.json').read_text(encoding='utf-8-sig'))
    hash_checks=[]
    for k,f,alg in [('calc_package_sha256',pack,'sha256'),('package_sha1',pack,'sha1'),('cfg_sha256',job/'cfg.py','sha256')]:
        if cr.get(k):hash_checks.append(cr[k]==hashlib.new(alg,f.read_bytes()).hexdigest())
    stats=model_stats(b)
    tables=['connections']+(EXTRA_TABLES if b['module']=='CFS' else [])
    local=[]
    for table in tables:
        for i,row in enumerate(p.get(table,[])):
            if not isinstance(row,dict):continue
            rid=str(row.get('id') or '@'+table+'['+str(i)+']')
            fam=family(row,table); mention=detected_dimensions(row)
            srcid=bid+':'+table+':'+rid
            loc={k:row[k] for k in LOCATION_KEYS if row.get(k) not in (None,'',[],{})}
            numeric_paths=[k for k,v in field_strings(row) if isinstance(v,(int,float)) and not isinstance(v,bool) and re.search(r'(?:spacing|edge|pitch|gauge|gage|thick|diam|coord|bolt.*(?:row|count)|n_bolt)',k,re.I)]
            rr={'key':srcid,'building':bid,'module':b['module'],'table':table,'record_id':rid,'id_origin':'source' if row.get('id') else 'audit locator (source has no id)',
                'family':fam,'source':json_ref(b,table,i),'description':row.get('type') or row.get('joint') or row.get('member') or row.get('schedule') or table,
                'scope':'Excluded by source' if row.get('waived') else ('No splice; retain joint notes' if fam=='No-splice design note' else 'In source design'),
                'geometry_evidence':describe(row),'location_evidence':snippet(loc,1000) if loc else '',
                'numeric_geometry_fields':numeric_paths,'mentions':mention,
                'normalization':'Preserve exclusion' if row.get('waived') else ('Retain no-splice boundary and related joint references' if fam=='No-splice design note' else ('Mixed numeric rows and prose' if numeric_paths else 'Prose / schedule extraction')),
                'record_hash_sha256':hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
            records.append(rr);local.append(rr)
    conns=[r for r in local if r['table']=='connections'];active=[r for r in conns if r['scope']!='Excluded by source']
    aux=[r for r in local if r['table']!='connections']
    source_tables=', '.join(k+': '+str(len(p.get(k,[]))) for k in EXTRA_TABLES if p.get(k))
    gap(b,'01','Extract existing','Connection and attachment specifications',
        f'{len(conns)} connection records; {len(aux)} additional schedule/detail records indexed. Geometry appears in prose'+(' and numeric schedule rows.' if any(r['numeric_geometry_fields'] for r in local) else '.'),
        'Dimensions, grades, fastener groups and welds are not yet normalized into drawing primitives. Text availability does not establish a complete drawing.',
        'Extract every active record with its source pointer; join referenced schedules; retain explicit exclusions. Validate units and dimension chains before deciding which values need supplementing.',
        'openBIM developer','Connection DXF / PDF and IFC references',json_ref(b,'connections'),source_tables or active[0]['geometry_evidence'],
        [r['key'] for r in local if r['scope']!='Excluded by source'])
    gap(b,'02','Resolve mapping','Connection records to physical occurrences',
        ('Model element tags, member schedule and connection-demand rows exist; records identify roles/sections and sometimes grids or stories.' if b['module']=='HR' else 'Line/story/joint/zone references appear in parts of the package; viewer tags identify a schematic or replicated model.'),
        'A complete explicit physical-member-end to connection-record/detail crosswalk is not established. Shared section names are insufficient to distinguish every joint.',
        'Build and review a crosswalk with member ID, end, support face, grid/line, level, handedness and connection record. List unmatched or ambiguous occurrences.',
        'openBIM developer + drawing lead','Located details and schedules',json_ref(b,'connections')+'; '+('design/connection_demands.csv' if b['module']=='HR' else 'viewer_3d.html#DATA; '+json_ref(b,'wall_lines' if p.get('wall_lines') else 'members')),
        'Records may describe an entire class, line or story; an analysis work point does not itself locate a physical plate.',[r['key'] for r in active])
    # These are explicitly lexical screens, not claims that geometry is absent from the whole package.
    shear=[r for r in active if r['family']=='Shear plate / angle' and not r['mentions']['plate datum']]
    if shear:
        gap(b,'03','Verify geometry','Shear-plate vertical placement',
            'Plate / bolt / weld descriptions exist in the selected shear-connection records.',
            f'No top-of-steel / beam datum or web-centering clause was identified in {len(shear)} record(s). This is a record-level text screen, not a package-wide absence claim.',
            'Resolve any referenced placement detail. Where none exists, agree the plate vertical datum and member-end setback in an openBIM supplement, then validate bolt edge distances.',
            'Drawing lead','Dimensioned connection elevations', '; '.join(r['source'] for r in shear[:8]),shear[0]['geometry_evidence'],[r['key'] for r in shear])
    fast=[r for r in active if b['module']=='CFS' and r['mentions']['fasteners'] and (not r['mentions']['spacing'] or not r['mentions']['edge distance'])]
    if fast:
        gap(b,'04','Verify geometry','Fastener pattern and edge geometry',
            'Selected records describe bolts, screws or pins. Some have quantities, diameters and partial layouts.',
            f'{len(fast)} connection record(s) lack a detected spacing or edge-distance clause. A count alone does not define an exact pattern.',
            'Review linked schedules and standard details. Supplement only unresolved rows, columns, pitch/gauge, hole/slot orientation, edge distances and clip/plate outline.',
            'Drawing lead','Dimensioned connection details','; '.join(r['source'] for r in fast[:8]),fast[0]['geometry_evidence'],[r['key'] for r in fast])
    # Reviewed, building-specific geometry and scope findings.
    for idx,g in enumerate(review.get('issues',[]),10):
        refs=[];excerpts=[]
        for spec in g['evidence']:
            if spec.startswith('cfg:'):
                pattern=spec[4:];refs.append(cfg_ref(b,pattern))
                hit=next((line.strip() for line in b['cfg'].splitlines() if re.search(pattern,line,re.I)),'')
                excerpts.append(hit)
            elif spec.startswith('json:'):
                key=spec[5:];val=p
                try:
                    for t in key.split('/'):val=val[int(t)] if isinstance(val,list) else val[t]
                except (KeyError,IndexError,ValueError,TypeError):
                    raise ValueError(f'Invalid reviewed evidence {bid}: {spec}')
                refs.append(json_ref(b,key));excerpts.append(snippet(val,500))
            elif spec=='viewer':
                refs.append('viewer_3d.html#DATA/meta/caveat');excerpts.append(b['viewer']['meta'].get('caveat',''))
            else:raise ValueError(spec)
        affected=[r['key'] for r in local if any(ref==r['source'] or ref.startswith(r['source']+'/') for ref in refs)]
        gap(b,str(idx),g['category'],g['requirement'],g['available'],g['remaining'],g['action'],g['owner'],g['blocks'],'; '.join(refs),' | '.join(excerpts),affected)
    special_secs=sorted({e['sec'] for e in b['viewer']['elements'] if not re.match(r'^(?:W\d|HSS\d|L\d|C\d|H\d)',e['sec'])})
    if b['module']=='HR':
        brbs=[s for s in special_secs if s.startswith('BRB')]
        if brbs:
            gap(b,'05','Supplier / delegated','BRB physical casing and end interface',
                'BRB core designations, demands and connection descriptions are present: '+', '.join(brbs[:8])+'.',
                'A core-area designation is not a casing profile. A complete supplier envelope and end-interface geometry is not established by the generic analysis designation.',
                'Extract supplied end-detail information first. Obtain or confirm casing envelope, work-point offsets and end interface; otherwise use a clearly identified design envelope and delegated detail reference.',
                'BRB supplier + engineer','Physical IFC geometry and connection interface',json_ref(b,'members')+'; '+json_ref(b,'connections'),', '.join(brbs))
        nonbrb=[s for s in special_secs if not s.startswith('BRB')]
        if nonbrb:
            gap(b,'06','Extract existing','Custom profiles and analysis idealizations',
                'Non-catalogue designations occur: '+', '.join(nonbrb[:10])+'.',
                'These labels need explicit physical-section definitions or an analysis-only classification. They cannot be exported as arbitrary W sections.',
                'Resolve geometry from configuration registrations and member/detail records; preserve built-up construction. Exclude rigid links and replace wall idealizations with physical wall geometry.',
                'openBIM developer','IFC and physical framing views',cfg_ref(b,r'BOX|PG84|CW\d|WEB|ROD|CB18|RZ-')+'; '+json_ref(b,'members'),', '.join(nonbrb))
    else:
        gap(b,'07','Extract existing','Attachment schedules outside connections[]',
            source_tables,
            'A reader restricted to connections[] would omit these schedule/detail records; counts overlap functional systems and are not physical connection quantities.',
            'Ingest and cross-reference anchorage, hold-down, collector, diaphragm, frame and secondary-framing records. Resolve overlaps by physical occurrence and source role.',
            'openBIM developer','Complete CFS drawing set','; '.join(json_ref(b,k) for k in EXTRA_TABLES if p.get(k)),source_tables,[r['key'] for r in aux])
    local_gaps=[g for g in gaps if g['building']==bid]
    summary={'building':bid,'module':b['module'],'source_building':b['building'],'system':review['system'],'geometry_case':review['geometry'],
        'geometry_readiness':review['geometry_status'],'profile_readiness':review['profiles'],
        'connection_readiness':'Prose extraction + mapping review','location_readiness':'Physical occurrence crosswalk required',
        'secondary_and_interfaces':review['secondary'],'source_provenance':'Recorded PASS; package hash matches' if all(hash_checks) else 'Hash mismatch',
        'connection_records':len(conns),'nonwaived_connection_records':len(active),
        'waived_connection_records':len(conns)-len(active),'no_splice_note_records':sum(r['family']=='No-splice design note' for r in conns),'additional_records':len(aux),
        'member_design_records':len(p.get('members',[])),'viewer_elements':len(b['viewer']['elements']),
        'model_elements':stats['model_elements'],'model_tag_check':stats['tag_check'],'categories':dict(collections.Counter(g['category'] for g in local_gaps)),
        'follow_up_ids':[g['id'] for g in local_gaps],'next_action':review['next_action'],'source_folder':job.relative_to(pathlib.Path(b.get('root',r'C:\Users\mikea\drawings'))).as_posix(),
        'source_package':pack.name,'package_sha256':hashlib.sha256(pack.read_bytes()).hexdigest(),'shared_items':['ALL-01','ALL-02','ALL-03']}
    coverage.append(summary)
    facts.append({'building':bid,'source_consistency':cr,'file_hash_checks':hash_checks,'model_stats':stats,'sections':sorted({e['sec'] for e in b['viewer']['elements']}),'top_level_record_counts':{k:len(v) for k,v in p.items() if isinstance(v,list)}})

family_counts=[]
for (module,table,fam),count in sorted(collections.Counter((r['module'],r['table'],r['family']) for r in records).items()):
    buildings=sorted({r['building'] for r in records if (r['module'],r['table'],r['family'])==(module,table,fam)})
    family_counts.append({'module':module,'table':table,'family':fam,'records':count,'building_count':len(buildings),'buildings':buildings})

assert len(coverage)==61
assert sum(x['connection_records'] for x in coverage)==2078
assert len({r['key'] for r in records})==len(records)
assert len({g['id'] for g in gaps})==len(gaps)
assert all(all(f['file_hash_checks']) for f in facts)
assert all(f['model_stats']['tag_check']=='MATCH' for f in facts if f['building'].startswith('HR-'))
assert set(REVIEW)=={c['building'] for c in coverage}
for g in gaps:
    assert set(g['affected_records']) <= {r['key'] for r in records}

summary={'audit_date':AS_OF,'scope':'Dimensioned engineering design drawings and IFC export; fabrication and IFC import deferred.',
    'buildings':len(coverage),'module_buildings':dict(collections.Counter(c['module'] for c in coverage)),
    'connection_records':sum(c['connection_records'] for c in coverage),'additional_detail_schedule_records':sum(c['additional_records'] for c in coverage),
    'waived_connection_records':sum(c['waived_connection_records'] for c in coverage),
    'no_splice_note_records':sum(c['no_splice_note_records'] for c in coverage),
    'register_items':len(gaps),'register_categories':dict(collections.Counter(g['category'] for g in gaps)),
    'source_files':len(json.loads((HERE/'source_manifest_before.json').read_text(encoding='utf-8'))),
    'repository_inspection_revisions':REPO_REVISIONS,'producer_revision_established':False,
    'definitions':{
        'Extract existing':'Information is present but requires normalization or physical interpretation. Not a request for new engineering data.',
        'Resolve mapping':'Source records need a reviewed association to physical elements, joints, stories or zones.',
        'Verify geometry':'A required detail parameter was not established by the stated inspection. Check linked sources before treating it as absent.',
        'Supplement required':'Reviewed evidence identifies additional drawing data or a placement decision that must be supplied.',
        'Supplier / delegated':'Source scope depends on external engineering or supplier data. Retain its boundary or supply that package.',
        'Scope decision':'Choose which explicitly excluded/context parts are represented and at what level.',
        'Verify source':'Provenance or source applicability needs confirmation.',
        'Drawing decision':'Presentation or drawing conventions need a documented choice.'},
    'limitations':[
        'This audit assesses source data availability, not structural adequacy or construction readiness.',
        'No cfg.py, solver, design engine or generated Python model was executed.',
        'All 61 packages were inventoried; every connections[] row and selected CFS drawing-related tables were indexed. This is not exhaustive numerical reconstruction.',
        'Script geometry was inspected as syntax and literal calls. No-splice notes retain their other joint references and must not be discarded as whole-record exclusions.',
        'Geometry word screens show only whether language was found in a record. They are not numerical parsing or proof of sufficiency.',
        'Referenced schedules and prose can contain additional values. Verify-geometry items are not confirmed package-wide absences.',
        'Register affected-record lists and evidence locators define scope. Blank affected-record lists mean a building-level requirement.',
        'Existing consistency PASS results are reported, not recomputed, and do not test drawing geometry.',
        'Current repository inspection revisions are not claimed to be the revisions that produced the supplied packages.',
        'Counts are source records, including typical groups and exclusions; additional schedule records can describe the same physical system.'
    ]}

def dump(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def csv_out(name,rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
        for r in rows:
            out={k:('; '.join(map(str,v)) if isinstance(v,list) else (json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else v)) for k,v in r.items()}
            # Keep source text literal when opened in a spreadsheet.
            out={k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in out.items()}
            writer.writerow(out)

for name,rows in [('coverage_matrix',coverage),('missing_data_register',gaps),('record_index',records),('family_coverage',family_counts)]:
    dump(name+'.json',rows);csv_out(name+'.csv',rows)
dump('audit_summary.json',summary);dump('source_checks.json',facts)
(OUT/'source_manifest.json').write_bytes((HERE/'source_manifest_before.json').read_bytes())
dump('workbook_data.json',{'summary':summary,'coverage':coverage,'gaps':gaps,'records':records,'families':family_counts})
print(json.dumps({k:summary[k] for k in ['buildings','connection_records','additional_detail_schedule_records','register_items','register_categories']},indent=2))
unknown=[r for r in records if r['family']=='Special connection - review']
print('UNCLASSIFIED',[(r['building'],r['record_id'],r['description']) for r in unknown])
