"""Render a new openBIM revision from authenticated saved HR design evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from .drawing_workflow import fingerprint, write_json
from .saved_assemblies import repair
from .validation import inspect_package


def read(path):
    return Path(path).read_text(encoding='utf-8-sig')


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check_inputs(package, model, manifest):
    contract = package.get('source_handoff', {})
    if contract.get('schema') != 'steltic.hr_source_handoff' or contract.get('version') != 1:
        raise ValueError('A versioned HR saved-design source handoff is required')
    data = {k: v for k, v in contract.items() if k != 'contract_sha256'}
    payload = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    if hashlib.sha256(payload.encode()).hexdigest() != contract['contract_sha256']:
        raise ValueError('HR source handoff digest differs from its contents')
    if package['building_id'] != contract['building_id'] or manifest['building_id'] != package['building_id']:
        raise ValueError('A drawing and handoff from the same HR job are required')
    if manifest['model_sha256'] != fingerprint(model):
        raise ValueError('The accepted drawing model differs from its manifest')
    if model['source_sha256'] != manifest['source_model_sha256']:
        raise ValueError('Drawing model and drawing manifest refer to different design snapshots')
    physical_revision = package['provenance'].get('physical_inputs', {})
    bindings = contract['source_bindings']
    native_content = bindings.get('native_content_sha256')
    native_body = {k: v for k, v in package.items() if k != 'source_handoff'}
    if not native_content or native_content != fingerprint(native_body):
        raise ValueError('The saved HR native package differs from its authenticated source body')
    if (physical_revision.get('sha256') != bindings.get('native_physical_sha256') or
            physical_revision.get('revision') != bindings.get('native_physical_revision')):
        raise ValueError('The HR handoff refers to a different physical revision')
    if 'report.html' not in contract['source_files']:
        raise ValueError('The original HR report hash is required')


def render_candidate(handoff, drawing_model, output, original_native=None):
    """Only the caller's new output directory is written. Original jobs stay read-only."""
    handoff, drawing_model, output = map(Path, (handoff, drawing_model, output))
    package = json.loads(read(handoff))
    model = json.loads(read(drawing_model))
    original_manifest = json.loads(read(drawing_model.with_name('drawing_manifest.json')))
    check_inputs(package, model, original_manifest)
    original_native_hash = digest_file(original_native) if original_native is not None else None
    if original_native_hash is not None and original_native_hash != package['source_handoff']['source_bindings'].get('native_bim_file_sha256'):
        raise ValueError('Archived native file differs from the authenticated HR source binding')
    output.mkdir(parents=True, exist_ok=False)
    source_hash = digest_file(handoff)
    original_records = fingerprint(package['design_records'])
    changes = repair(package, model)
    if fingerprint(package['design_records']) != original_records:
        raise ValueError('Saved design records changed during drawing preparation')
    validation = inspect_package(package)
    write_json(output/'source_validation.json', validation)
    if validation['status'] == 'invalid':
        raise ValueError('Invalid repaired physical package: '+str(validation['findings'][:3]))
    revision = original_manifest['revision'] + 1
    state = dict(schema='steltic.ifc_physical_source', revision=revision,
        building_id=package['building_id'], source_job=package['building_id'], source_module='HR',
        source_model_sha256=fingerprint(package), drawing_status='design_test', source_status='design_test',
        source_readiness=validation['status'], requests=[], design_scenario=model['scenario'],
        features=model['openings'], representation='physical_geometry')
    model['source_sha256'] = state['source_model_sha256']
    with (output/'source.json').open('w', encoding='utf-8') as stream:
        json.dump(package, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    write_json(output/'state.json', state)
    write_json(output/'information_requests.json', dict(requests=state['requests']))
    from .review_cases import CASES
    if model['pilot'] in CASES:
        from .review_pdf import render_model
        drawing = render_model(package, state, output, model, model['connection_assemblies'])
    else:
        from .design_pdf import generate
        drawing = generate(package, state, output, prepared_model=model)
    from .ifc_export import export_structural
    ifc = export_structural(output, output/'model.ifc')
    write_json(output/'ifc_manifest.json', ifc)
    contract = package['source_handoff']
    result = dict(schema='steltic.openbim_candidate', building_id=package['building_id'], revision=revision,
        source_contract_sha256=contract['contract_sha256'], source_files=contract['source_files'],
        input_handoff_sha256=source_hash, accepted_drawing_model_sha256=original_manifest['model_sha256'],
        original_native_file_sha256=original_native_hash,
        original_native_content_sha256=contract['source_bindings']['native_content_sha256'],
        native_physical_sha256=contract['source_bindings']['native_physical_sha256'],
        design_records_sha256=original_records, source_model_sha256=state['source_model_sha256'],
        repaired=changes, pdf_sha256=drawing['pdf_sha256'], ifc_sha256=ifc['sha256'],
        analysis_executed=False)
    write_json(output/'candidate_manifest.json', result)
    return result


def render_native_revision(handoff,output,approved_layout=None,prior_native=None):
    """Render a newly completed HR job through the ordinary physical drawing path."""
    from .native_hr_completion import complete_native_hr
    from .drawing_workflow import initial_state
    from .drawing_pdf import generate
    from .ifc_export import export_drawing
    handoff,output=Path(handoff),Path(output)
    original=json.loads(read(handoff));contract=original.get('source_handoff',{})
    if (contract.get('schema')!='steltic.hr_source_handoff' or contract.get('building_id')!=original['building_id'] or
            contract.get('contract_sha256')!=fingerprint({k:v for k,v in contract.items() if k!='contract_sha256'}) or
            contract.get('source_bindings',{}).get('native_content_sha256')!=fingerprint({k:v for k,v in original.items() if k!='source_handoff'})):
        raise ValueError('Fresh HR job needs an authenticated matching native handoff')
    if not original['physical']['members']:raise ValueError('Fresh HR physical member geometry is missing')
    retained=None;model=None
    if approved_layout:
        import copy
        from .retained_layout import bind_layout
        if not prior_native:raise ValueError('Retaining an approved register needs its original native geometry')
        model=json.loads(read(approved_layout))
        register=json.loads(read(Path(approved_layout).with_name('drawing_manifest.json')))
        package=copy.deepcopy(original)
        retained=bind_layout(json.loads(read(prior_native)),package,model,register)
        retained['prior_native_file_sha256']=digest_file(prior_native)
        repaired=repair(package,model)
        retained['repair']=repaired
        state=initial_state(package,register['revision']+1)
        state.update(design_scenario=model['scenario'],drawing_status='design_test',features=model['openings'])
    else:
        package=complete_native_hr(original)
        state=initial_state(package,1)
    state.update(original_hr_sha256=fingerprint(original),source_job=original['building_id'],source_module='HR')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'hr_original_source.json',original)
    write_json(output/'source.json',package);write_json(output/'state.json',state)
    write_json(output/'information_requests.json',{'requests':state['requests']})
    write_json(output/'source_validation.json',inspect_package(package))
    if model is None:
        drawing=generate(package,state,output)
        ifc=export_drawing(output,output/'model.ifc')
    else:
        from .review_cases import CASES
        from .ifc_export import export_structural
        model['source_sha256']=state['source_model_sha256']
        if model['pilot'] in CASES:
            from .review_pdf import render_model
            drawing=render_model(package,state,output,model,model['connection_assemblies'])
        else:
            from .design_pdf import generate as draw_approved
            drawing=draw_approved(package,state,output,prepared_model=model)
        ifc=export_structural(output,output/'model.ifc')
        retained['new_sheet_ids']=[s['number'] for s in drawing['sheets']]
        retained['missing_prior_sheets']=sorted(set(retained['prior_sheet_ids'])-set(retained['new_sheet_ids']))
        retained['added_sheets']=sorted(set(retained['new_sheet_ids'])-set(retained['prior_sheet_ids']))
        write_json(output/'retained_layout.json',retained)
    write_json(output/'ifc_manifest.json',ifc)
    result=dict(schema='steltic.openbim_native_revision',building_id=package['building_id'],
        source_model_sha256=state['source_model_sha256'],original_hr_sha256=state['original_hr_sha256'],
        source_contract_sha256=contract['contract_sha256'],input_handoff_sha256=digest_file(handoff),
        pdf_sha256=drawing['pdf_sha256'],ifc_sha256=ifc['sha256'],analysis_executed=False)
    if retained:result['retained_layout_sha256']=fingerprint(retained)
    write_json(output/'native_revision_manifest.json',result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', required=True, type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--drawing-model',type=Path)
    mode.add_argument('--native-revision',action='store_true',help='Render the new HR physical revision directly')
    parser.add_argument('--approved-layout',type=Path,help='Retain a checked original sheet register for a connection-only revision')
    parser.add_argument('--prior-native',type=Path,help='Original geometry for independent connection-only scope comparison')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--job-root', type=Path,
                        help='Original HR job used to rehash the saved design and report at certification')
    parser.add_argument('--original-native',type=Path,
                        help='Original archived native BIM package to hash before translating the handoff')
    parser.add_argument('--candidate-only', action='store_true',
                        help='Write rendered artifacts for inspection before certification')
    args = parser.parse_args(argv)
    if not args.candidate_only and args.job_root is None:
        parser.error('--job-root is required for final saved-design delivery verification')
    if (args.approved_layout or args.prior_native) and not (args.native_revision and args.approved_layout and args.prior_native):
        parser.error('--approved-layout and --prior-native must be used together with --native-revision')
    result = (render_native_revision(args.handoff,args.output,args.approved_layout,args.prior_native) if args.native_revision else
              render_candidate(args.handoff,args.drawing_model,args.output,args.original_native))
    if not args.candidate_only:
        from .delivery_verification import verify_delivery
        certificate = verify_delivery(args.output,job_root=args.job_root)
        if not certificate['passed']:
            parser.exit(2, 'Delivery verification failed. Inspect delivery_certificate.json.\n')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
