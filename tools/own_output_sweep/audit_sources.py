"""Read-only inventory of actual updated-producer jobs; never use gold supplements."""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT=Path(os.environ.get('STELTIC_SWEEP_WORKSPACE',Path(__file__).resolve().parents[2])).resolve()
OUT=ROOT/'outputs/own_outputs_61'
PLAN=ROOT/'outputs/workflow_fresh_61/plan.json'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=True),encoding='utf-8')

def inspect_module(module):
    repo=ROOT/'work/repos'/('steltic' if module=='HR' else 'steltic_cfs')
    sys.path[:0]=[str(repo),str(ROOT/'work/repos/steltic_openBIM/src')]
    from steltic.agent import _completion_gate
    from steel_engine.bim_export import tracked_sources
    from steltic_openbim.validation import inspect_package
    from steltic_openbim.source_worklines import required
    results=[]
    for item in read(OUT/'candidates.json'):
        if item['module']!=module:continue
        job=Path(item['job']);folder=OUT/item['key'];folder.mkdir(parents=True,exist_ok=True)
        row=dict(item)
        files=['cfg.py','design/calc_package.json','design/calc_package_cfs.json','design/bim_package.json',
               'design/consistency_result.json','design/pipeline_results.json','design/bim_request.json',
               'architectural_input.json','architectural_handoff.txt']
        row['files']={name:sha(job/name) for name in files if (job/name).is_file()}
        row['job_exists']=job.is_dir()
        row['completion_problems']=_completion_gate(SimpleNamespace(_job_dir=lambda:job)) if job.is_dir() else ['No production job exists for this case.']
        row['current_completion_gate_passed']=not row['completion_problems']
        source=job/'design/bim_package.json'
        row['package_present']=source.is_file()
        if source.is_file():
            package=read(source)
            (folder/'source.json').write_bytes(source.read_bytes())
            if (job/'architectural_input.json').is_file():
                (folder/'architectural_input.json').write_bytes((job/'architectural_input.json').read_bytes())
            row['stored_readiness']=package.get('readiness',{}).get('status')
            row['provenance']={k:v for k,v in package.get('provenance',{}).items() if k!='source_files'}
            row['declared_source_files']=package.get('provenance',{}).get('source_files',{})
            row['physical_counts']={k:len(v) for k,v in package.get('physical',{}).items() if isinstance(v,list)}
            row['design_records']=len(package.get('design_records',[]))
            row['source_kind']=package.get('module')
            row['require_connection_parts']=package.get('require_connection_parts')
            row['current_validation']=inspect_package(package)
            row['source_freshness']=inspect_package(package,job)
            row['captured_worklines_required']=required(package)
            row['current_tracked_source_files']=tracked_sources(job)
            row['source_file_set_matches']=row['current_tracked_source_files']==row['declared_source_files']
            # Keep incomplete source packages intact. Do not refresh their data,
            # copy another job's design, or attach any design_model.json recipe.
            row['own_output_only']=True
            row['physical_supplements_used']=False
        else:
            row['missing_outputs']=[name for name in ('cfg.py','design/bim_package.json') if not (job/name).is_file()]
        save(folder/'source_audit.json',row)
        results.append(row)
        print(json.dumps(dict(case=row['case'],key=row['key'],module=module,package=row['package_present'],
                             complete=row['current_completion_gate_passed'],
                             validation=row.get('current_validation',{}).get('status'),
                             freshness=row.get('source_freshness',{}).get('status'))),flush=True)
    save(OUT/(module.lower()+'_source_audit.json'),results)

def prepare():
    OUT.mkdir(exist_ok=True)
    plan=read(PLAN);cases=plan['cases'];assert len(cases)==61
    base=Path.home()/'AppData/Local/Steltic/modules_data'
    candidates=[]
    for row in cases:
        status_file=ROOT/'outputs/workflow_fresh_61'/row['id']/'run_status.json'
        status=read(status_file) if status_file.is_file() else {}
        module='steltic' if row['module']=='HR' else 'steltic_cfs'
        candidates.append(dict(case=row['id'],key=row['id'],module=row['module'],title=row['title'],
                               project=row['project'],job=str(base/module/'sessions/local/jobs'/row['project']),
                               source_run_status=status.get('status','not_started'),primary=True,
                               status_evidence=str(status_file) if status else None))
    mapping={'CFS_01_Walls':'cfs1','CFS_17_TwinGable':'cfs17','CFS_29_Mezzanine':'cfs29',
             'HR_01_Office':'hr1','HR_02_School':'hr16','HR_03_Warehouse':'hr31'}
    for row in read(ROOT/'outputs/workflow_six/workflow_report.json')['cases']:
        project=row.get('design_run',{}).get('job',row['project'])
        module='steltic' if row['module']=='HR' else 'steltic_cfs'
        case=mapping[row['case']]
        candidates.append(dict(case=case,key=case+'_earlier',module=row['module'],title=row['title'],project=project,
                               job=str(base/module/'sessions/local/jobs'/project),source_run_status='done',primary=False,
                               status_evidence='outputs/workflow_six/workflow_report.json'))
    save(OUT/'candidates.json',candidates)
    save(OUT/'plan.json',dict(cases=61,modules={'HR':36,'CFS':25},candidate_runs=len(candidates),
         scope='Actual new-production jobs only; no saved gold physical supplements or legacy substitution.',
         llm_calls=0,redesign_runs=0,drawing_runs=0,source_mutations=False,
         mutation_policy={'steltic_openBIM':'Fix and merge','steltic':'Review list only','steltic_cfs':'Review list only','steltic_hub':'Review list only'}))
    repos={}
    for name in ('steltic','steltic_cfs','steltic_openBIM','steltic_hub'):
        folder=ROOT/'work/repos'/name
        repos[name]=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder,text=True).strip(),
                        status=subprocess.check_output(['git','status','--porcelain'],cwd=folder,text=True).strip())
    save(OUT/'initial_repositories.json',repos)
    print(json.dumps(dict(cases=len(cases),candidates=len(candidates))))

if __name__=='__main__':
    if len(sys.argv)>1:inspect_module(sys.argv[1])
    else:prepare()
