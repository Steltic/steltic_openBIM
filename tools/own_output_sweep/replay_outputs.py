"""Re-export existing job declarations locally, without editing or redesigning jobs."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from audit_sources import ROOT,OUT,read,save,sha

def one(row):
    key=row['key'];job=Path(row['job']);folder=OUT/key
    calc='design/calc_package.json' if row['module']=='HR' else 'design/calc_package_cfs.json'
    if not (job/'cfg.py').is_file() or not (job/calc).is_file():
        result=dict(key=key,case=row['case'],status='unavailable',reason='The saved job has no cfg.py and calculation package pair.')
    else:
        started=time.time();module='hr' if row['module']=='HR' else 'cfs'
        repo=ROOT/'work/repos'/('steltic' if module=='hr' else 'steltic_cfs')
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
        target=folder/'replay/bim_package.json';target.parent.mkdir(exist_ok=True)
        try:
            with (folder/'replay.log').open('w',encoding='utf-8') as stream:
                run=subprocess.run([str(ROOT/f'work/envs/{module}/Scripts/python.exe'),'-m','steltic.bim_export',
                                    'replay',str(job),'--output',str(target),'--timeout','240'],cwd=repo,
                                   stdout=stream,stderr=subprocess.STDOUT,timeout=270,
                                   env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8','STELTIC_BIM_REVISION':head},
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if run.returncode:raise RuntimeError('Native model-only export failed; see replay.log')
            package=read(target)
            assert package['provenance']['analysis_executed'] is False
            assert package['provenance']['mode']=='model_only_replay'
            assert all(sha(job/name)==value for name,value in package['provenance']['source_files'].items())
            assert all(sha(job/name)==value for name,value in row['files'].items())
            result=dict(key=key,case=row['case'],status='exported',producer=head,package_sha256=sha(target),
                        source_files_unchanged=True,original_recorded_package_unchanged=True,
                        stored_readiness=package['readiness']['status'],
                        findings=package['readiness']['findings'],physical_counts={k:len(v) for k,v in package['physical'].items() if isinstance(v,list)},
                        connection_parts=sum(len(c.get('parts',[])) for c in package['physical']['connections']),
                        design_records=len(package['design_records']),seconds=time.time()-started,
                        llm_calls=0,redesign=False,analysis_solve=False,drawings=False,supplements=False)
        except Exception as exc:
            result=dict(key=key,case=row['case'],status='failed',error=str(exc),seconds=time.time()-started)
    save(folder/'replay_result.json',result)
    print(json.dumps({k:result[k] for k in ('key','status','stored_readiness','connection_parts','seconds') if k in result}),flush=True)
    return result

if __name__=='__main__':
    rows=[read(p) for p in OUT.glob('*/source_audit.json')]
    assert len(rows)==67
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(one,rows))
    save(OUT/'replay_summary.json',results)
    print(json.dumps(dict(exports=sum(r['status']=='exported' for r in results),failed=sum(r['status']=='failed' for r in results),unavailable=sum(r['status']=='unavailable' for r in results))),flush=True)
