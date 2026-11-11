"""Compulsory independent readback of an HR PDF/IFC delivery revision."""
import json
import re
from pathlib import Path

from .drawing_workflow import fingerprint, write_json
from .generator_identity import generator_identity
from .saved_delivery import digest_file


def verify_delivery(output_dir,source_directory=None,job_root=None):
    output=Path(output_dir);source=Path(source_directory or output)
    def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
    checks={}
    findings=[]
    certificate=dict(schema='steltic.delivery_certificate',version=1,passed=False,
        status='verification_failed',checks=checks,findings=findings,files={},
        source_geometry_scope='HR design-to-drawing and IFC fidelity',generator=generator_identity())
    def run(name,fn):
        try:
            result=fn()
        except Exception as e:
            result={'passed':False,'findings':[{'issue':type(e).__name__+': '+str(e)}]}
        checks[name]=result
        if not result.get('passed'):
            findings.append({'check':name,'count':len(result.get('findings',[])),'detail':result.get('findings',[])[:3]})
        return result
    def inputs():
        problems=[];h=package.get('source_handoff',{})
        if h.get('schema')!='steltic.hr_source_handoff' or h.get('building_id')!=package.get('building_id'):
            problems.append('Missing bound HR source handoff for this building')
        elif fingerprint({k:v for k,v in h.items() if k!='contract_sha256'})!=h.get('contract_sha256'):
            problems.append('HR source contract digest differs from contents')
        if h.get('source_conflicts'):problems.append('Unresolved occurrence-scoped source conflict')
        problems.extend(package.get('provenance',{}).get('openbim_translation_findings',[]))
        if h.get('unresolved_crossing_interfaces'):problems.append('Unresolved source crossing location or applicability')
        bindings=h.get('source_bindings',{})
        candidate=source/'candidate_manifest.json'
        if candidate.is_file():
            saved=read(candidate)
            if (not saved.get('original_native_file_sha256') or saved['original_native_file_sha256']!=bindings.get('native_bim_file_sha256') or
                    not saved.get('original_native_content_sha256') or saved['original_native_content_sha256']!=bindings.get('native_content_sha256')):
                problems.append('Archived native file or original handoff body lacks a verified matching digest')
        else:
            original=package
            if state.get('original_hr_sha256'):
                original=read(source/'hr_original_source.json')
                if fingerprint(original)!=state['original_hr_sha256'] or original.get('source_handoff')!=h:
                    problems.append('Original native snapshot differs from the derived drawing source binding')
            if bindings.get('native_content_sha256')!=fingerprint({k:v for k,v in original.items() if k!='source_handoff'}):
                problems.append('Live physical delivery differs from the original authenticated native handoff')
        files=h.get('source_files',{})
        for required in ('design/calc_package.json','design/member_schedule.csv','report.html'):
            if not re.fullmatch(r'[0-9a-f]{64}',str(files.get(required,''))):
                problems.append('Missing original source digest for '+required)
        if job_root:
            root=Path(job_root).resolve()
            for name,expected in files.items():
                path=(root/name).resolve()
                if not path.is_relative_to(root) or not path.is_file() or digest_file(path)!=expected:
                    problems.append('Changed or missing original source file '+name)
        elif source_directory is not None:
            problems.append('Original HR job evidence is unavailable for this Hub revision')
        if state['source_model_sha256']!=model_hash or drawing.get('source_model_sha256')!=model_hash:
            problems.append('Drawing or revision refers to another handoff')
        if drawing.get('pdf_sha256')!=certificate['files'].get('drawings.pdf'):
            problems.append('Drawing PDF digest differs from drawing manifest')
        if ifc.get('sha256')!=certificate['files'].get('model.ifc') or ifc.get('source_sha256')!=model_hash:
            problems.append('IFC bytes or source identity differs from export manifest')
        if ifc.get('schema_errors') or ifc.get('warnings'):
            problems.append('IFC exporter reported unresolved schema or representation findings')
        if ifc.get('source_validation',{}).get('status')!='ready' or state.get('source_readiness') not in (None,'ready'):
            problems.append('Source physical validation is incomplete')
        if any(not r.get('confirmed') for r in state.get('requests',[])) or drawing.get('open_requests',0):
            problems.append('Open drawing information requests remain')
        if ifc.get('generator')!=certificate['generator']:
            problems.append('Installed verification source differs from the IFC producer identity')
        if drawing.get('generator')!=certificate['generator']:
            problems.append('Installed verification source differs from the PDF producer identity')
        if job_root and (Path(job_root)/'design/consistency_result.json').is_file():
            status=read(Path(job_root)/'design/consistency_result.json')
            if status.get('passed') is False or str(status.get('status','')).lower() in ('failed','stale','incomplete'):
                problems.append('Original HR consistency evidence is incomplete or failed')
        model_file=source/'design_model.json'
        if model_file.exists() and drawing.get('model_sha256')!=fingerprint(read(model_file)):
            problems.append('Serialized drawing model differs from its source-bound drawing manifest')
        certificate.update(building_id=package['building_id'],source_files=files,
            source_contract_sha256=h.get('contract_sha256'),source_model_sha256=model_hash,
            hr_generator=h.get('source_bindings',{}).get('generator_files'),
            scoped_omissions=drawing.get('omitted_detail_references',[]))
        return dict(passed=not problems,findings=problems,original_source_files_rehashed=bool(job_root))
    try:
        for name,path in [('drawings.pdf',source/'drawings.pdf'),('model.ifc',output/'model.ifc')]:
            certificate['files'][name]=digest_file(path)
        package=read(source/'source.json');state=read(source/'state.json')
        drawing=read(source/'drawing_manifest.json')
        ifc=read(output/'ifc_manifest.json') if (output/'ifc_manifest.json').exists() else read(output/'report.json')
        model_hash=fingerprint(package)
        run('source_bindings',inputs)
        from .pdf_verification import verify_dimensions
        pdf=run('pdf_readback',lambda:verify_dimensions(source,ifc_path=output/'model.ifc'))
        write_json(output/'pdf_verification.json',pdf)
        from .ifc_delivery_readback import verify_ifc
        run('ifc_readback',lambda:verify_ifc(output/'model.ifc',package,model_hash))
        def selection_check():
            from .source_selection_readback import verify_source_selections
            drawing_model=source/'design_model.json'
            return verify_source_selections(package,read(drawing_model) if drawing_model.is_file() else None)
        run('source_selections',selection_check)
        from .ifc_brace_readback import verify_member_clearance
        handoff=package.get('source_handoff',{})
        run('brace_member_clearance',lambda:verify_member_clearance(output/'model.ifc',package['physical'],
            handoff.get('crossing_interfaces',[]),handoff.get('records',{})))
        def assembly_check():
            from .ifc_assembly_verification import verify_assembly_fit
            return verify_assembly_fit(output/'model.ifc',package['physical'],package.get('source_handoff',{}))
        run('assembly_fit',assembly_check)
    except Exception as e:
        findings.append(dict(check='required_evidence',detail=type(e).__name__+': '+str(e)))
    certificate['passed']=not findings
    if certificate['passed']:certificate['status']='verified'
    write_json(output/'delivery_certificate.json',certificate)
    return certificate
