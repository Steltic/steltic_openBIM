"""Run the authorized zero-LLM gold IFC sweep through the installed Hub."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from gold_case import OUT, ROOT, emit, read, save, sha, snapshot_hashes


def run(case):
    out = OUT / case
    try:
        exporter = sha(ROOT/'work/repos/steltic_openBIM/src/steltic_openbim/ifc_export.py')
        old = read(out/'source_export.json') if (out/'source_export.json').exists() else {}
        reuse_export = (old.get('exporter_sha256') == exporter and (out/'source.ifc').exists()
                        and sha(out/'source.ifc') == old.get('sha256')
                        and old.get('source_snapshot_sha256') == snapshot_hashes(case))
        # The Hub stage checks all cached IFC/review hashes under its file lock.
        # One source proof alone cannot establish that the return is reusable.
        stages = ([] if reuse_export else ['export']) + ['roundtrip', 'compare']
        for stage in stages:
            save(out/'progress.json', dict(case=case, status='running', stage=stage, started=time.time(), pid=os.getpid()))
            emit(case, stage+'_starting')
            with (out/(stage+'.log')).open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, str(Path(__file__).with_name('gold_case.py')), stage, case],
                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True,
                               timeout=3900 if stage == 'roundtrip' else 1800,
                               env={**os.environ, 'PYTHONIOENCODING':'utf-8'},
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            emit(case, stage+'_finished')
        result = read(out/'result.json')
        save(out/'progress.json', dict(case=case, status='passed', finished=time.time()))
        emit(case, 'passed', products=result['products_compared'])
        return result
    except Exception:
        error = traceback.format_exc()
        if 'stage' in locals() and (out/(stage+'.log')).exists():
            error += '\n'+(out/(stage+'.log')).read_text(encoding='utf-8', errors='replace')[-3500:]
        failure = dict(case=case, status='failed', stage=stage if 'stage' in locals() else 'start', error=error)
        save(out/'progress.json', failure)
        emit(case, 'failed', error=error)
        return failure


if __name__ == '__main__':
    bindings = [read(p) for p in OUT.glob('*/binding.json')]
    assert len(bindings) == 61 and all(r['status']=='passed' for r in bindings)
    selected = [r for r in bindings if not sys.argv[1:] or r['case'] in sys.argv[1:]]
    # Smaller models can share the machine; large reviews run alone, with every
    # object included rather than lowering coverage to fit a concurrent queue.
    small = sorted([r for r in selected if r['members'] < 10000], key=lambda r:r['members'])
    large = sorted([r for r in selected if r['members'] >= 10000], key=lambda r:r['members'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda r:run(r['case']), small))
    results += [run(r['case']) for r in large]
    save(OUT/'run_summary.json', results)
    print(json.dumps(dict(passed=sum(r['status']=='passed' for r in results), failed=sum(r['status']!='passed' for r in results))), flush=True)
    raise SystemExit(0 if all(r['status']=='passed' for r in results) else 1)
