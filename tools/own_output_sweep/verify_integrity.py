"""Verify original job bytes and the protected repositories were not changed."""
import subprocess
from pathlib import Path
from audit_sources import ROOT,OUT,read,save,sha

def main():
    problems=[];files=0;jobs=0
    for path in OUT.glob('*/source_audit.json'):
        audit=read(path);job=Path(audit['job']);expected={**audit.get('current_tracked_source_files',{}),**audit['files']}
        replay=path.parent/'replay/bim_package.json'
        if replay.is_file():
            for name,digest in read(replay).get('provenance',{}).get('source_files',{}).items():
                if name in expected and expected[name]!=digest:problems.append(dict(key=audit['key'],file=name,reason='Replay input changed during audit'))
                expected.setdefault(name,digest)
        jobs+=1
        for name,digest in expected.items():
            source=(job/name).resolve();assert source.is_relative_to(job.resolve())
            files+=1
            if not source.is_file() or sha(source)!=digest:problems.append(dict(key=audit['key'],file=name,reason='Original job evidence changed'))
    initial=read(OUT/'initial_repositories.json');repos={}
    for name in ('steltic','steltic_cfs','steltic_hub','steltic_openBIM'):
        folder=ROOT/'work/repos'/name
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=folder,text=True).strip()
        status=subprocess.check_output(['git','status','--porcelain'],cwd=folder,text=True).strip()
        repos[name]=dict(head=head,status=status,head_unchanged=head==initial[name]['head'],worktree_unchanged=status==initial[name]['status'])
        if name!='steltic_openBIM' and (head!=initial[name]['head'] or status!=initial[name]['status']):problems.append(dict(repo=name,reason='Protected repository changed'))
    queue=read(ROOT/'outputs/workflow_fresh_61/queue_control.json')
    assert queue.get('pause_all') is True,'The paid queue must stay stopped'
    assert not list(OUT.rglob('*.pdf')) and not list((OUT/'job_snapshots').rglob('design_model.json'))
    result=dict(status='passed' if not problems else 'failed',candidate_runs_checked=jobs,original_files_checked=files,problems=problems,
        repos=repos,paid_queue_still_stopped=True,analysis_solves=0,llm_calls=0,drawings=0,physical_supplements_used=False)
    save(OUT/'integrity.json',result)
    print({k:result[k] for k in ('status','candidate_runs_checked','original_files_checked','problems')})
    assert not problems

if __name__=='__main__':main()
