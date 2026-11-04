"""Check completed exchanges against their matched, original architectural input."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
from audit_sources import ROOT,OUT,read,save,sha

def one(path):
    result=read(path)
    if result['status']!='passed':return None
    target=path.parent/'architectural_comparison.json'
    binding=dict(checker=sha(ROOT/'work/stage15/check_outputs.py'),
                 algorithms=sha(ROOT/'work/stage13/geometry_checks.py'),returned_ifc=sha(path.parent/'returned.ifc'))
    if target.is_file() and read(target).get('check_binding')==binding:return read(target)
    with (path.parent/'checks.log').open('w',encoding='utf-8') as log:
        run=subprocess.run([sys.executable,str(ROOT/'work/stage15/check_outputs.py'),result['key'],result['variant']],stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if run.returncode:
        value=dict(key=result['key'],variant=result['variant'],status='check_failed',reason='See checks.log')
    else:
        value=read(target);value['key']=result['key'];value['check_binding']=binding
    save(target,value)
    print(json.dumps(dict(key=result['key'],variant=result['variant'],status=value['status'],issues=[i['code'] for i in value.get('issues',[])])),flush=True)
    return value

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(one,OUT.glob('*/exchange_*/result.json')))
    save(OUT/'architectural_summary.json',[v for v in values if v])
