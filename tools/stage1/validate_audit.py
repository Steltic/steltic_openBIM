"""Independently reconcile Stage 1 deliverables against the supplied files.

This verifies inventory, provenance and evidence references, not engineering
adequacy or numerical connection geometry. It never executes source job code.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(r'C:\Users\mikea\drawings'))
parser.add_argument('--work-dir', type=Path, default=Path(__file__).parent)
parser.add_argument('--review-notes', type=Path, default=Path(__file__).parent/'review_notes.json')
parser.add_argument('--repo-root', type=Path, help='Optional parent of inspection clones steltic, steltic_cfs, steltic_hub')
args = parser.parse_args()
data = args.work_dir/'data'
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
coverage = read(data/'coverage_matrix.json')
register = read(data/'missing_data_register.json')
records = read(data/'record_index.json')
families = read(data/'family_coverage.json')
summary = read(data/'audit_summary.json')
checks = read(data/'source_checks.json')
reviews = read(args.review_notes)
manifest = read(args.work_dir/'source_manifest_before.json')
errors = []
def check(condition, message):
    if not condition: errors.append(message)
def sha(value):
    return hashlib.sha256(value).hexdigest()
def pointer(obj, path):
    if not path: return obj
    for token in path.lstrip('/').split('/'):
        token = token.replace('~1','/').replace('~0','~')
        obj = obj[int(token)] if isinstance(obj,list) else obj[token]
    return obj

byid = {r['building']:r for r in coverage}
bykey = {r['key']:r for r in records}
packages = {}
viewers = {}
source_connection_count = 0
source_aux_count = 0
modules = collections.Counter(r['module'] for r in coverage)
check(len(coverage)==61 and len(byid)==61 and modules=={'HR':36,'CFS':25}, 'Expected 61 distinct buildings (36 HR, 25 CFS)')
check(len(register)==len({g['id'] for g in register}), 'Duplicate register IDs')
check(len(records)==len(bykey), 'Duplicate record keys')
check(set(reviews)==set(byid), 'Reviewed notes must cover exactly the building inventory')
for bid, c in byid.items():
    folder=args.root/c['source_folder']
    package=folder/'design'/c['source_package']
    p=read(package)
    packages[bid]=p
    source_connection_count+=len(p['connections'])
    check(sha(package.read_bytes())==c['package_sha256'], bid+' package fingerprint')
    local=[r for r in records if r['building']==bid]
    source_aux_count+=len([r for r in local if r['table']!='connections'])
    indexed_connections=[r for r in local if r['table']=='connections']
    check(len(indexed_connections)==len(p['connections'])==c['connection_records'],bid+' connection count')
    check(len(local)-len(indexed_connections)==c['additional_records'],bid+' supporting record count')
    check({r['source'] for r in indexed_connections}=={'design/'+c['source_package']+'#/connections/'+str(i) for i in range(len(p['connections']))},bid+' connection index completeness')
    for table in {r['table'] for r in local if r['table']!='connections'}:
        check(len([r for r in local if r['table']==table])==len(p[table]),bid+' auxiliary index completeness: '+table)
    cfg=(folder/'cfg.py').read_text(encoding='utf-8-sig')
    for issue in reviews[bid]['issues']:
        for ref in issue['evidence']:
            if ref.startswith('cfg:'):
                check(bool(re.search(ref[4:],cfg,re.I)),bid+' reviewed cfg pattern: '+ref)
    check(set(c['follow_up_ids'])=={g['id'] for g in register if g['building']==bid},bid+' follow-up links')
for r in records:
    try:
        row=pointer(packages[r['building']],r['source'].split('#',1)[1])
        expected=sha(json.dumps(row,sort_keys=True,ensure_ascii=False).encode())
        check(expected==r['record_hash_sha256'],r['key']+' record fingerprint')
        if row.get('id'): check(str(row['id'])==r['record_id'],r['key']+' source ID')
        if row.get('waived'): check(r['scope']=='Excluded by source',r['key']+' waived scope')
    except (KeyError,IndexError,TypeError,ValueError) as e:
        errors.append(r['key']+' source pointer '+str(e))
for g in register:
    for key in g['affected_records']:
        check(key in bykey,g['id']+' unknown affected record '+key)
        if key in bykey: check(bykey[key]['building']==g['building'],g['id']+' cross-building affected record')
    if g['building']=='ALL': continue
    folder=args.root/byid[g['building']]['source_folder']
    for ref in g['source'].split('; '):
        name, sep, fragment=ref.partition('#')
        match=re.fullmatch(r'(.*):L(\d+)',name)
        if match:
            name=match[1]
            lines=(folder/name).read_text(encoding='utf-8-sig').splitlines()
            check(0<int(match[2])<=len(lines),g['id']+' line reference '+ref)
        file=folder/name
        check(file.is_file(),g['id']+' missing evidence file '+ref)
        if sep and file.is_file():
            try:
                if name.endswith('.json'): pointer(read(file),fragment)
                elif name=='viewer_3d.html':
                    if g['building'] not in viewers:
                        text=file.read_text(encoding='utf-8-sig')
                        marker=re.search(r'\b(?:const|let|var)\s+DATA\s*=\s*',text)
                        viewers[g['building']]=json.JSONDecoder().raw_decode(text,marker.end())[0]
                    pointer(viewers[g['building']],fragment.removeprefix('DATA'))
            except (KeyError,IndexError,TypeError,ValueError) as e:
                errors.append(g['id']+' invalid evidence '+ref+': '+str(e))

category_counts=dict(collections.Counter(g['category'] for g in register))
check(category_counts==summary['register_categories'],'Register category totals')
check(source_connection_count==summary['connection_records']==2078,'Source connection total')
check(source_aux_count==summary['additional_detail_schedule_records']==2785,'Supporting record total')
check(len(records)==4863,'Full record index total')
fc=collections.Counter((r['module'],r['table'],r['family']) for r in records)
check(fc=={(r['module'],r['table'],r['family']):r['records'] for r in families},'Family count reconciliation')
check(all(c['file_hash_checks'] and all(c['file_hash_checks']) for c in checks),'Recorded source package/configuration hashes')
check(all(c['model_stats']['tag_check']=='MATCH' for c in checks if c['building'].startswith('HR-')),'HR model/viewer/schedule tag reconciliation')
for name, rows in [('coverage_matrix',coverage),('missing_data_register',register),('record_index',records),('family_coverage',families)]:
    with (data/(name+'.csv')).open(encoding='utf-8-sig',newline='') as stream:
        csvrows=list(csv.DictReader(stream))
    check(len(csvrows)==len(rows),name+' CSV/JSON row count')
    key=next(iter(rows[0]))
    check([r[key] for r in csvrows]==[str(r[key]) for r in rows],name+' CSV/JSON row order')

before={(r['module'],r['building'],r['file']):r for r in manifest}
after={}
for module, base in [('HR',args.root/'jobs'),('CFS',args.root/'gold_cfs_jobs_2026-10-31/jobs_cfs')]:
    for job in base.iterdir():
        if not job.is_dir(): continue
        for file in job.rglob('*'):
            if not file.is_file(): continue
            relative=file.relative_to(job).as_posix()
            if relative.startswith(('rag/','figs/')): continue
            blob=file.read_bytes()
            after[(module,job.name,relative)]={'module':module,'building':job.name,'file':relative,'bytes':len(blob),'sha256':sha(blob)}
check(before==after,'Source files changed since the initial snapshot')
check(read(data/'source_manifest.json')==manifest,'Published manifest differs from the initial snapshot')
repo_checks={}
if args.repo_root:
    for module, name in [('HR','steltic'),('CFS','steltic_cfs'),('Hub','steltic_hub')]:
        repo=args.repo_root/name
        head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
        check(not status,module+' inspection checkout has modifications')
        check(head==summary['repository_inspection_revisions'][module],module+' inspection revision changed')
        repo_checks[module]={'head':head,'working_tree_clean':not status}
result={
    'audit_date':summary['audit_date'],'status':'PASS' if not errors else 'FAIL',
    'buildings':len(coverage),'module_buildings':dict(modules),
    'connection_records_verified':source_connection_count,'supporting_records_verified':source_aux_count,
    'record_fingerprints_verified':len(records),'register_items':len(register),
    'register_category_counts':category_counts,'source_files_compared':len(after),
    'source_bytes_compared':sum(r['bytes'] for r in after.values()),'source_files_unchanged':before==after,
    'hr_analysis_elements_reconciled':sum(c['model_stats']['model_elements'] for c in checks if c['building'].startswith('HR-')),
    'inspection_repositories':repo_checks,
    'limits':'Inventory, source fingerprints and evidence references only. No structural or drawing geometry validation; job code and design engines were not run.',
    'errors':errors,
}
(data/'audit_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
raise SystemExit(bool(errors))
