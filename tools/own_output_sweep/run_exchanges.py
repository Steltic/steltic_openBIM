"""Bounded own-output audit; never launches native design or drawing engines."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
from audit_sources import ROOT,OUT,read,save


def one(task):
    key,variant=task;dest=OUT/key/('exchange_'+variant);dest.mkdir(exist_ok=True)
    with (dest/'run.log').open('w',encoding='utf-8') as log:
        proc=subprocess.run([sys.executable,str(ROOT/'work/stage15/exchange_case.py'),key,variant],
            stdout=log,stderr=subprocess.STDOUT,timeout=5400,
            env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'},
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    result=read(dest/'result.json') if (dest/'result.json').is_file() else dict(key=key,variant=variant,status='failed',error='See run.log')
    print(json.dumps({k:result.get(k) for k in ('key','variant','status','stage','products_compared','error')}),flush=True)
    return result


if __name__=='__main__':
    candidates=read(OUT/'candidates.json')
    tasks=[(r['key'],v) for r in candidates for v in ('saved','replay')]
    if len(sys.argv)>1:tasks=[t for t in tasks if t[0] in sys.argv[1:]]
    # Start the largest case early; two workers cap peak geometry memory.
    tasks.sort(key=lambda t:(0 if t[0]=='cfs2' else 1,t[0],t[1]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(one,tasks))
    save(OUT/('exchange_summary.json' if len(sys.argv)==1 else 'exchange_smoke.json'),results)
