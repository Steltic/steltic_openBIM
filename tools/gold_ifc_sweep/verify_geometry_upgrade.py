"""Compare the new geometry path with every already-accepted Hub review."""
import json
from pathlib import Path
import subprocess
import sys
import time
from gold_case import OUT,ROOT,read,save,sha


def one(case):
    from steltic_openbim.ifc_import import build_review
    out=OUT/case
    proof=read(out/'source_hub.json')
    assert proof['api_model_sha256']==sha(out/'source_review.json')
    assert proof['state']['source_sha256']==sha(out/'source.ifc')
    previous=read(out/'source_review.json')
    start=time.time()
    current=build_review(out/'source.ifc',previous['options'])
    changed=[key for key in previous.keys()|current.keys() if previous.get(key)!=current.get(key)]
    result=dict(case=case,status='failed' if changed else 'passed',complete_review_identical=not changed,
                changed_fields=changed,products=current['counts']['displayed'],seconds=time.time()-start,
                source_sha256=sha(out/'source.ifc'),previous_review_sha256=proof['api_model_sha256'],
                importer_sha256=sha(ROOT/'work/repos/steltic_openBIM/src/steltic_openbim/ifc_import.py'))
    if changed:
        before={o['guid']:o for o in previous['objects']};after={o['guid']:o for o in current['objects']}
        result['changed_product_examples']=[dict(guid=g,fields=[k for k in before[g].keys()|after[g].keys() if before[g].get(k)!=after[g].get(k)]) for g in before.keys()&after.keys() if before[g]!=after[g]][:10]
    save(out/'geometry_upgrade_check.json',result)
    print(json.dumps({k:result[k] for k in ('case','status','products','seconds','changed_fields')}),flush=True)
    return not changed


if __name__=='__main__':
    if len(sys.argv)>1:raise SystemExit(0 if one(sys.argv[1]) else 1)
    cases=[read(p)['case'] for p in OUT.glob('*/result.json')]
    save(OUT/'geometry_upgrade_plan.json',dict(cases=cases,reason='Regression of every complete review before switching the native geometry path.'))
    results=[]
    for case in cases:
        completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),case],cwd=ROOT,
                                 timeout=1200,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        results.append(read(OUT/case/'geometry_upgrade_check.json'))
        if completed.returncode:break
    save(OUT/'geometry_upgrade_summary.json',results)
    assert len(results)==len(cases) and all(r['status']=='passed' for r in results)
