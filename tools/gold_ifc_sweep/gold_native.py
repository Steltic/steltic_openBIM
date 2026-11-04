"""Rebuild gold model evidence locally; never invoke an LLM, design or drawing engine."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(os.environ.get('STELTIC_SWEEP_WORKSPACE',Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT / 'work/stage12'))
from sweep_support import cases, evidence, job_source, read, save, sha
from steltic_openbim.drawing_workflow import fingerprint

OUT = ROOT / 'outputs/workflow_gold_61'


def replay_case(row):
    out = OUT / row['id']
    out.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        model, original, location = evidence(row)
        source = ROOT / row['existing_coordination_model']
        job = job_source(row, original)
        module = 'hr' if row['module'] == 'HR' else 'cfs'
        repo = ROOT / 'work/repos' / ('steltic' if module == 'hr' else 'steltic_cfs')
        target = out / 'native_replay/bim_package.json'
        cmd = [str(ROOT / f'work/envs/{module}/Scripts/python.exe'), '-m', 'steltic.bim_export',
               'replay', str(job), '--output', str(target), '--timeout', '180']
        result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=210, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'})
        (out / 'native_replay.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        result.check_returncode()
        replay = read(target)
        assert replay['provenance']['mode'] == 'model_only_replay'
        assert replay['provenance']['analysis_executed'] is False
        mismatch = {name: {'original': expected, 'current': sha(job / name) if (job / name).is_file() else None}
                    for name, expected in original['provenance']['source_files'].items()
                    if not (job / name).is_file() or sha(job / name) != expected}
        assert not mismatch, mismatch
        canonical = lambda records: sorted(records, key=lambda r: r['id'])
        assert canonical(replay['design_records']) == canonical(original['design_records']), 'Saved design records changed'
        assert replay.get('analysis',{}) == original.get('analysis',{}), 'Gold model nodes/elements changed'
        assert all(sha(job / name) == expected for name, expected in replay['provenance']['source_files'].items())
        state = read(source.parent / 'state.json')
        assert state['source_model_sha256'] == fingerprint(original) == model['source_sha256']
        state.update(representation='existing_reviewed_coordination_model', source_module=row['module'],
                     source_job=original['building_id'], supplement_provenance=dict(
                         physical_model_sha256=sha(source), native_replay_sha256=sha(target),
                         source_files_and_design_records_match=True, adopted_fictional_inputs=True,
                         drawing_engine_run=False, design_or_analysis_run=False,
                         scope='Gold design IFC transport; existing adopted physical supplements retained.'))
        snapshot = out / 'snapshot'
        snapshot.mkdir(exist_ok=True)
        save(snapshot / 'source.json', original)
        save(snapshot / 'state.json', state)
        shutil.copyfile(source, snapshot / 'design_model.json')
        binding = dict(case=row['id'], module=row['module'], title=row['title'], status='passed',
                       gold_job=str(job), source_package_location=location,
                       physical_model_source=str(source), source_model_sha256=fingerprint(original),
                       native_replay_sha256=sha(target), physical_model_sha256=sha(source),
                       source_files_unchanged=True, tracked_files=len(replay['provenance']['source_files']),
                       original_tracked_files=len(original['provenance']['source_files']),
                       design_records_match=True, design_record_count=len(original['design_records']),
                       analysis_model_matches=True,
                       members=len(model.get('members', [])), panels=len(model.get('panels', [])),
                       openings=len(model.get('openings', [])), connections=len(model.get('connections', [])),
                       analysis_nodes=len(replay.get('analysis', {}).get('nodes', [])),
                       analysis_elements=len(replay.get('analysis', {}).get('elements', [])),
                       engine_version=replay['provenance'].get('engine_version'),
                       engine_files=replay['provenance'].get('engine_files'),
                       model_only_replay=True, llm_calls=0, design_run=False, analysis_run=False,
                       drawing_run=False, elapsed_seconds=round(time.time()-start, 2))
        save(out / 'binding.json', binding)
        print(json.dumps({k: binding[k] for k in ('case', 'status', 'members', 'design_record_count', 'elapsed_seconds')}), flush=True)
        return binding
    except Exception:
        failure = dict(case=row['id'], status='failed', error=traceback.format_exc(), elapsed_seconds=time.time()-start)
        save(out / 'binding.json', failure)
        print(json.dumps(failure), flush=True)
        return failure


if __name__ == '__main__':
    selected = [r for r in cases() if not sys.argv[1:] or r['id'] in sys.argv[1:]]
    # Two isolated native model builders, independent of the paid Hub job queues.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(replay_case, selected))
    save(OUT / 'native_replay_summary.json', results)
    raise SystemExit(0 if all(r['status'] == 'passed' for r in results) else 1)
