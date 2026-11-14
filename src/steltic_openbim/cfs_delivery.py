"""Deliver a native CFS drawing set and IFC model, with the delivery self-check.

    python -m steltic_openbim.cfs_delivery --job-root JOB --output DELIVERY

``JOB`` is a completed Steltic CFS job: its ``design/bim_package.json`` must be the READY
package exported after the engine's native physical builder ran, and ``report.html`` must be
the report rendered from the same calculation package.  The command writes

    DELIVERY/drawings.pdf, model.ifc, delivery_certificate.json  (+ source and manifests)

and exits non-zero unless the certificate passes.  Nothing in the job is modified.  This path
is separate from the HR delivery (``saved_delivery``) and is never taken for an HR package.
"""
import argparse
import json
from pathlib import Path

from .drawing_workflow import initial_state, write_json
from .validation import inspect_package


def deliver(job_root, output, *, package_path=None, verify=True):
    from . import cfs_native_pdf
    from .ifc_export import export_drawing
    job_root, output = Path(job_root), Path(output)
    package_path = Path(package_path) if package_path else job_root / 'design' / 'bim_package.json'
    package = json.loads(package_path.read_text(encoding='utf-8-sig'))
    if package.get('module') != 'CFS':
        raise ValueError('cfs_delivery handles CFS packages only; use saved_delivery for HR')
    if not cfs_native_pdf.is_native_cfs(package):
        raise ValueError('The CFS package has no recorded native physical design; run the CFS physical builder (steel_engine.cfs_physical) on the completed job first')
    validation = inspect_package(package, job_root)
    if validation['status'] != 'ready':
        raise ValueError('The CFS physical package is not ready: ' + json.dumps(validation['findings'][:3])[:600])
    output.mkdir(parents=True, exist_ok=False)
    state = initial_state(package, 1)
    # A CFS model locates every screw, so the template / joint lists run to tens of MB. The delivery carries them once, in
    # source.json; the IFC project keeps a count and fingerprint of each list and a part-count summary of every template.
    state.update(source_job=package['building_id'], source_module='CFS', representation='physical_geometry', compact_project_sources=True)
    with (output / 'source.json').open('w', encoding='utf-8') as stream:
        json.dump(package, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    write_json(output / 'state.json', state)
    write_json(output / 'source_validation.json', validation)
    drawing = cfs_native_pdf.generate(package, state, output)
    ifc = export_drawing(output, output / 'model.ifc')
    write_json(output / 'ifc_manifest.json', ifc)
    result = dict(schema='steltic.openbim_cfs_delivery', building_id=package['building_id'], source_model_sha256=state['source_model_sha256'],
                  pdf_sha256=drawing['pdf_sha256'], ifc_sha256=ifc['sha256'], sheets=len(drawing['sheets']), analysis_executed=False)
    if verify:
        from .cfs_delivery_verification import verify as check
        certificate = check(output, job_root)
        result['passed'] = certificate['passed']
        result['checks'] = [dict(name=c['name'], checked=c['checked'], passed=c['passed'], failure_count=c['failure_count']) for c in certificate['checks']]
    write_json(output / 'cfs_delivery_manifest.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--job-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--package', type=Path, help='Physical package (default JOB/design/bim_package.json)')
    parser.add_argument('--candidate-only', action='store_true', help='Render without the delivery check, to diagnose a failure')
    args = parser.parse_args(argv)
    try:
        result = deliver(args.job_root, args.output, package_path=args.package, verify=not args.candidate_only)
    except (OSError, ValueError) as ex:
        parser.exit(1, str(ex) + '\n')
    print(json.dumps(result))
    if not args.candidate_only and not result.get('passed'):
        parser.exit(2, 'CFS delivery verification failed. Inspect delivery_certificate.json.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
