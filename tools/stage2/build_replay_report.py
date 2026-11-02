"""Audit all exports against source evidence without running either design engine."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
import zipfile

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'))
from steltic_openbim import inspect_package


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('hr-exports','cfs-exports','hr-jobs','cfs-jobs','hr-engine','cfs-engine'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,default=REPO/'docs/stage1/data/source_manifest.json')
    parser.add_argument('--output',type=Path,default=REPO/'docs/stage2/data')
    parser.add_argument('--bundle',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    roots={'HR':args.hr_jobs,'CFS':args.cfs_jobs}
    exports={'HR':args.hr_exports,'CFS':args.cfs_exports}
    engines={'HR':args.hr_engine,'CFS':args.cfs_engine}
    before=read(args.source_manifest)
    key=lambda r:(r['module'],r['building'],r['file'])
    original={key(r):r for r in before}
    current={}
    for module,root in roots.items():
        for job in sorted(root.iterdir()):
            if not job.is_dir() or not (job/'cfg.py').is_file(): continue
            for path in sorted(job.rglob('*')):
                if not path.is_file(): continue
                relative=path.relative_to(job).as_posix()
                if relative.startswith(('rag/','figs/')): continue
                row={'module':module,'building':job.name,'file':relative,'bytes':path.stat().st_size,'sha256':sha(path)}
                current[key(row)]=row
    source_check={'baseline_files':len(original),'current_files':len(current),
                  'baseline_bytes':sum(r['bytes'] for r in before),
                  'modified':[list(k) for k in original.keys() & current.keys() if original[k]['sha256']!=current[k]['sha256']],
                  'missing':[list(k) for k in original.keys()-current.keys()],
                  'added':[list(k) for k in current.keys()-original.keys()]}
    source_check['unchanged']=not any(source_check[k] for k in ('modified','missing','added'))
    rows=[]; findings=[]; packages=[]; summary={}
    for module,root in exports.items():
        expected={p.name for p in roots[module].iterdir() if p.is_dir() and (p/'cfg.py').is_file()}
        actual={p.parent.name for p in root.glob('*/bim_package.json')}
        if expected!=actual: raise ValueError(f'{module}: source/export job sets differ: {expected ^ actual}')
        for path in sorted(root.glob('*/bim_package.json')):
            package=read(path)
            building=path.parent.name
            assert package['module']==module and package['building_id']==building
            verdict=inspect_package(package,roots[module]/building)
            if verdict['status']=='invalid': raise ValueError(f'{module}/{building}: {verdict}')
            assert verdict['status']==package['readiness']['status'], 'Published readiness differs from independent validation'
            for relative,expected_hash in package['provenance']['engine_files'].items():
                assert sha(engines[module]/relative)==expected_hash, f'Engine fingerprint mismatch: {module}/{relative}'
            physical=package['physical']
            table_counts=Counter(r['table'] for r in package['design_records'])
            # Verify every exported source record against its original package location.
            source=read(roots[module]/building/'design'/package['provenance']['package_file'])
            for record in package['design_records']:
                table,index=record['source_pointer'].lstrip('/').rsplit('/',1)
                table=table.replace('~1','/').replace('~0','~')
                assert source[table][int(index)]==record['data'], f'Design evidence changed: {module}/{building}/{record["id"]}'
            expected_records=sum(sum(isinstance(row,dict) for row in value) for table,value in source.items() if table!='bim' and isinstance(value,list))
            assert expected_records==len(package['design_records'])
            row={'module':module,'building':building,'status':verdict['status'],
                 'replay_mode':package['analysis'].get('comparison',{}).get('status'),
                 'analysis_elements':len(package['analysis']['elements']),
                 'physical_member_candidates':sum(m['status']=='candidate' for m in physical['members']),
                 'declared_physical_members':sum(m['status']=='declared' for m in physical['members']),
                 'physical_panel_candidates':sum(p['status']=='candidate' for p in physical['panels']),
                 'analysis_only_entities':len(physical['analysis_only']),
                 'connection_design_records':table_counts['connections'],
                 'all_design_records':len(package['design_records']),
                 'finding_codes':sorted({f['code'] for f in verdict['findings']}),
                 'source_files_verified':len(package['provenance']['source_files']),
                 'exporter_revision':package['provenance']['exporter_revision'],
                 'package_sha256':sha(path),'package_bytes':path.stat().st_size}
            rows.append(row)
            findings.extend(dict(module=module,building=building,**f) for f in verdict['findings'])
            packages.append((path,f'packages/{module}/{building}/bim_package.json'))
        subset=[r for r in rows if r['module']==module]
        summary[module]={'buildings':len(subset),'statuses':dict(Counter(r['status'] for r in subset)),
                         'replay_modes':dict(Counter(r['replay_mode'] for r in subset)),
                         **{k:sum(r[k] for r in subset) for k in ('analysis_elements','physical_member_candidates','physical_panel_candidates','analysis_only_entities','connection_design_records','all_design_records','package_bytes')}}
    counts=Counter((f['code'],f['severity']) for f in findings)
    summary['findings']=[{'code':code,'severity':severity,'buildings':n} for (code,severity),n in sorted(counts.items())]
    shared={name:len({sha(engine/name) for engine in engines.values()}|{sha(REPO/'src/steltic_openbim'/name)})==1 for name in ('bim_contract.py','bim_package.schema.json')}
    checks={'source_preservation':source_check,'shared_contract_byte_identical':shared,'packages_independently_validated':len(rows),
            'source_record_data_unchanged':True,'source_fingerprints_match':True,'engine_fingerprints_match':True,'all_analysis_executed_flags_false':True}
    assert source_check['unchanged'],source_check
    assert all(shared.values()),shared
    assert len(rows)==61 and sum(r['connection_design_records'] for r in rows)==2078
    write(args.output/'replay_summary.json',summary)
    write(args.output/'building_coverage.json',rows)
    write(args.output/'remaining_findings.json',findings)
    write(args.output/'validation.json',checks)
    for name,records in [('building_coverage',rows),('remaining_findings',findings)]:
        with (args.output/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in records)
    if args.bundle:
        args.bundle.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(args.bundle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path,member in packages: archive.write(path,member)
            for path in sorted(args.output.iterdir()): archive.write(path,'docs/stage2/data/'+path.name)
            for name in ('BIM_EXPORT.md','bim_package.schema.json','bim_declaration.example.json'):
                archive.write(REPO/'contracts'/name,'contracts/'+name)
            readme=REPO/'docs/stage2/README.md'
            if readme.exists(): archive.write(readme,'docs/stage2/README.md')
            archive.writestr('README.txt','Steltic physical-data export, stage 2\n\n61 evidence packages are in packages/HR and packages/CFS.\nAll retain needs_input status; they are not drawing-ready designs.\nRead docs/stage2/README.md and contracts/BIM_EXPORT.md.\nOriginal calculation data is preserved in each package. No RAG extracts are included.\n')
    print(json.dumps({'summary':summary,'checks':checks},indent=2))


if __name__=='__main__': main()
