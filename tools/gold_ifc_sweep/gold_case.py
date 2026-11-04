"""One bounded stage of the gold IFC round trip, with reproducible evidence."""
import collections
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(os.environ.get('STELTIC_SWEEP_WORKSPACE',Path(__file__).resolve().parents[2])).resolve()
sys.path[:0] = [str(ROOT / 'work/stage12'), str(ROOT / 'work/repos/steltic_openBIM/src')]
from sweep_support import read, save, sha

OUT = ROOT / 'outputs/workflow_gold_61'
if not (ROOT/'outputs/workflow_61/sweep_plan.json').is_file():
    raise RuntimeError('Set STELTIC_SWEEP_WORKSPACE to the existing verification workspace containing outputs/workflow_61/sweep_plan.json.')
BASE = os.environ.get('STELTIC_SWEEP_HUB_URL','http://127.0.0.1:8300').rstrip('/')+'/m/steltic_openbim/api/project/'


def emit(case, stage, **details):
    print(json.dumps(dict(case=case, stage=stage, **details)), flush=True)


def snapshot_hashes(case):
    return {name:sha(OUT/case/'snapshot'/name) for name in ('source.json','state.json','design_model.json')}


def export(case):
    from filelock import FileLock
    out=OUT/case
    with FileLock(str(out/'export.lock'),timeout=2400):
        report=read(out/'source_export.json') if (out/'source_export.json').exists() else {}
        exporter=sha(ROOT/'work/repos/steltic_openBIM/src/steltic_openbim/ifc_export.py')
        if (report.get('exporter_sha256')==exporter and (out/'source.ifc').exists()
                and report.get('sha256')==sha(out/'source.ifc')
                and report.get('source_snapshot_sha256')==snapshot_hashes(case)):
            emit(case,'source_export_cached')
            return
        _export(case)


def _export(case):
    from steltic_openbim.ifc_export import export_drawing
    out = OUT / case
    assert read(out / 'binding.json')['status'] == 'passed'
    start = time.time()
    report = export_drawing(out / 'snapshot', out / 'source.ifc')
    report['elapsed_seconds'] = time.time()-start
    report['exporter_sha256'] = sha(ROOT / 'work/repos/steltic_openBIM/src/steltic_openbim/ifc_export.py')
    report['source_snapshot_sha256'] = snapshot_hashes(case)
    save(out / 'source_export.json', report)
    emit(case, 'source_export', seconds=round(report['elapsed_seconds'], 1), counts=report['counts'],
         megabytes=round((out/'source.ifc').stat().st_size/1048576, 2))


def api_call(client, method, url, **kwargs):
    response = client.request(method, url, **kwargs)
    if response.status_code != 200:
        raise RuntimeError(f'{method} {url}: {response.status_code}: {response.text[:2000]}')
    return response.json()


def download(client, url, target):
    digest = hashlib.sha256()
    with client.stream('GET', url) as response:
        response.raise_for_status()
        with target.open('wb') as stream:
            for chunk in response.iter_bytes(1024*1024):
                stream.write(chunk)
                digest.update(chunk)
    return digest.hexdigest()


def import_build(client, case, label, source):
    out = OUT / case
    project = 'GoldRoundTrip_' + case + ('_returned' if label == 'returned' else '')
    url = BASE + project + '/ifc'
    old = api_call(client, 'GET', url)['imported']
    if old and old['source_sha256']==sha(source):
        # An interrupted build leaves its immutable, already-inspected upload.
        # Build a new review revision instead of uploading identical bytes again.
        uploaded=old
    else:
        form = {'revision': str(old['revision'])} if old else {}
        with source.open('rb') as stream:
            uploaded = api_call(client, 'POST', url+'/import', files={'file': (source.name, stream, 'application/x-step')}, data=form)
    assert uploaded['source_sha256'] == sha(source)
    save(out / (label+'_upload.json'), uploaded)
    emit(case, label+'_imported', counts=uploaded['counts'])
    guard = {k: uploaded[k] for k in ('revision', 'source_sha256')}
    built = api_call(client, 'POST', url+'/build', json=dict(guard, options=dict(scope='all', units='auto',
                     note='Gold design transport verification. No redesign, analysis or drawing engines.')))
    assert built['status'] == 'built'
    assert built['counts']['unrendered'] == 0, built['counts']
    assert built['counts']['excluded_by_scope'] == 0
    current = api_call(client, 'GET', url)['imported']
    keys = ('revision', 'source_sha256', 'status', 'options', 'counts', 'source_schema')
    assert all(current[k] == built[k] for k in keys)
    model_path = out / (label+'_review.json')
    model_sha = download(client, url+'/import/file/model.json', model_path)
    # Download the exact original exposed by Hub; don't just trust its metadata.
    original_sha = download(client, url+'/import/file/original.ifc', out/(label+'_downloaded.ifc'))
    assert original_sha == sha(source)
    save(out / (label+'_hub.json'), dict(project=project, url=url, state=built, api_model_sha256=model_sha,
                                        geometry_engine_sha256=sha(ROOT/'work/repos/steltic_openBIM/src/steltic_openbim/ifc_import.py'),
                                        downloaded_original_ifc_sha256=original_sha))
    emit(case, label+'_built', counts=built['counts'])
    return url, built


def roundtrip(case):
    from filelock import FileLock
    out=OUT/case
    announced=False
    while (OUT/'capacity_control.json').exists():
        control=read(OUT/'capacity_control.json')
        if not control.get('exclusive_case') or control['exclusive_case']==case:break
        if not announced:emit(case,'waiting_for_large_model_capacity');announced=True
        time.sleep(2)
    with FileLock(str(out/'roundtrip.lock'),timeout=3900):
        if all((out/name).exists() for name in ('source_hub.json','returned_hub.json','returned_export.json','source_review.json','returned_review.json','returned.ifc')):
            source=read(out/'source_hub.json');returned=read(out/'returned_hub.json')
            if (source['state']['source_sha256']==sha(out/'source.ifc')
                    and returned['state']['source_sha256']==sha(out/'returned.ifc')==read(out/'returned_export.json')['sha256']
                    and source['api_model_sha256']==sha(out/'source_review.json')
                    and returned['api_model_sha256']==sha(out/'returned_review.json')):
                emit(case,'hub_roundtrip_cached')
                return
        _roundtrip(case)


def _roundtrip(case):
    import httpx
    out = OUT / case
    start = time.time()
    with httpx.Client(timeout=httpx.Timeout(1320, connect=30), trust_env=False) as client:
        url, state = import_build(client, case, 'source', out/'source.ifc')
        guard = {k: state[k] for k in ('revision', 'source_sha256')}
        report = api_call(client, 'POST', url+'/export', json=dict(guard, source='ifc_import'))
        save(out/'returned_export.json', report)
        assert not report['schema_errors']
        actual_sha = download(client, url+'/export/'+report['key']+'/model.ifc', out/'returned.ifc')
        assert actual_sha == report['sha256']
        emit(case, 'returned_export', megabytes=round((out/'returned.ifc').stat().st_size/1048576, 2))
        import_build(client, case, 'returned', out/'returned.ifc')
    save(out/'hub_timing.json', dict(elapsed_seconds=time.time()-start))


def graph_rows(path):
    # Files here are emitted by IfcOpenShell in STEP-id order, one declaration
    # per line; strings escape newlines. Fail on unsupported formatting.
    with path.open('r', encoding='utf-8') as stream:
        in_data = False
        for line in stream:
            text = line.strip()
            if text == 'DATA;':
                in_data = True
            elif in_data and text == 'ENDSEC;':
                return
            elif in_data:
                assert re.match(r'^#\d+=IFC[A-Z0-9_]+\(.*\);$', text), 'Unexpected STEP serialization'
                yield text


def compare(case):
    import ifcopenshell
    import ifcopenshell.util.element as element_util
    import ifcopenshell.util.unit as unit_util
    out = OUT / case
    binding = read(out/'binding.json')
    report = read(out/'source_export.json')
    assert report['sha256'] == sha(out/'source.ifc')
    assert read(out/'returned_export.json')['sha256'] == sha(out/'returned.ifc')
    # This compares EVERY declaration, including grids, units, placements,
    # materials, profiles, voids, properties and all connectivity relationships.
    actual = iter(graph_rows(out/'returned.ifc'))
    classes = collections.Counter()
    checked = 0
    for expected in graph_rows(out/'source.ifc'):
        got = next(actual, None)
        assert got == expected, 'Source STEP entity changed: '+expected[:100]
        classes[expected.split('=', 1)[1].split('(', 1)[0]] += 1
        checked += 1
    added = list(actual)
    assert added and all(row.split('=', 1)[1].split('(', 1)[0] in
                        ('IFCPROPERTYSET', 'IFCPROPERTYSINGLEVALUE', 'IFCRELDEFINESBYPROPERTIES') for row in added)
    source = read(out/'snapshot/source.json')
    physical = read(out/'snapshot/design_model.json')
    model = ifcopenshell.open(str(out/'source.ifc'))
    props = element_util.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert props['SourceModelSHA256'] == binding['source_model_sha256']
    expected_state=read(out/'snapshot/state.json')
    assert json.loads(props['SupplementProvenance'])==expected_state['supplement_provenance']
    assert expected_state['supplement_provenance']['native_replay_sha256']==sha(out/'native_replay/bim_package.json')
    assert expected_state['supplement_provenance']['physical_model_sha256']==sha(out/'snapshot/design_model.json')
    assert json.loads(props['DesignRecords']) == source['design_records']
    references = [c for c in physical['connections'] if not c.get('parts')]
    assert json.loads(props['UnlocatedConnectionReferences']) == references
    assert unit_util.calculate_unit_scale(model) == 1.
    c = report['counts']
    assert c['members'] == len(physical['members'])
    assert c['panel_surfaces'] == len(physical['panels'])
    assert c['opening_references'] == len(physical['openings'])
    assert c['connection_references'] == len(references)
    assert len({o['guid'] for o in report['objects']}) == len(report['objects'])
    source_coverage = dict(members=c['members'], panels=c['panel_surfaces'], openings=c['opening_references'],
                           connection_references=c['connection_references'], connection_parts=c['connection_parts'],
                           design_records=len(source['design_records']), member_surfaces=c['member_surfaces'],
                           reference_axes=c['reference_axes'])
    del model, physical, source, props, references
    gc.collect()
    reviews = []
    review_counts = []
    findings = []
    for label in ('source', 'returned'):
        proof = read(out/(label+'_hub.json'))
        file = out/(label+'_review.json')
        assert sha(file) == proof['api_model_sha256']
        assert proof['state']['source_sha256'] == sha(out/(label+'.ifc'))
        review = read(file)
        assert review['schema'] == 'steltic.ifc_review' and review['units'] == 'm'
        assert review['options']['scope'] == 'all'
        assert review['counts'] == proof['state']['counts']
        assert review['counts']['displayed'] == len(report['objects'])
        assert review['counts']['unrendered'] == 0
        assert review['counts']['excluded_by_scope'] == 0
        assert len({o['guid'] for o in review['objects']}) == len(review['objects'])
        # Hash every complete per-product review record, including world vertices,
        # faces/lines, storey, section, material and properties. No sampled objects.
        signatures = {o['guid']: hashlib.sha256(json.dumps(o, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                      for o in review['objects']}
        reviews.append(dict(objects=signatures, bounds_m=review['bounds_m'], storeys=review['storeys'], units=review['source_units']))
        review_counts.append(review['counts'])
        findings.append([dict(code=f['code'], count=f['count']) for f in review['checks']])
        del review
        gc.collect()
    assert reviews[0] == reviews[1], 'Imported geometry or per-product data changed'
    result = dict(case=case, module=binding['module'], title=binding['title'], status='passed',
                  scope='Gold HR/CFS model-only replay with saved physical supplements; IFC import/export transport.',
                  native_replay=True, source_files_unchanged=binding['source_files_unchanged'],
                  saved_designs_match=binding['design_records_match'], llm_calls=0, redesign=False, drawings=False,
                  source_replay_binding_matches=True,
                  schema_errors=[], source_coverage=source_coverage, entities_compared=checked,
                  entity_classes=dict(classes), original_entities_unchanged=True, added_review_entities=len(added),
                  products_compared=len(reviews[0]['objects']), every_product_geometry_and_data_identical=True,
                  review_counts=review_counts[0], source_findings=findings[0], returned_findings=findings[1],
                  source_sha256=sha(out/'source.ifc'), returned_sha256=sha(out/'returned.ifc'),
                  source_export_seconds=report['elapsed_seconds'], hub_seconds=read(out/'hub_timing.json')['elapsed_seconds'],
                  limitations=['Existing fictional coordination supplements are retained and attributed.',
                               'Source geometry/data findings remain visible; this is not a new structural design approval.',
                               'Connections without placed hardware retain complete design records and declared references; no placements are invented.'])
    save(out/'result.json', result)
    emit(case, 'passed', entities=checked, products=result['products_compared'])


if __name__ == '__main__':
    action, case = sys.argv[1:]
    {'export': export, 'roundtrip': roundtrip, 'compare': compare}[action](case)
