"""Own-output IFC exchange through the production openBIM API. No Hub mutation."""
import collections
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

from audit_sources import ROOT,OUT,read,save,sha
CODE=Path(os.environ.get('OPENBIM_AUDIT_CODE',ROOT/'work/repos/steltic_openBIM/src'))
sys.path.insert(0,str(CODE))
os.environ['PYTHONPATH']=str(CODE)
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from fastapi import FastAPI
from fastapi.testclient import TestClient
from steltic_openbim.drawing_workflow import DrawingStore,fingerprint
from steltic_openbim.ifc_api import router
from steltic_openbim.ifc_store import IFCStore
from steltic_openbim.validation import inspect_package


def code_hashes():
    return {str(p.relative_to(CODE)):sha(p) for p in sorted(CODE.rglob('*')) if p.suffix in ('.py','.json','.js')}


def call(client,method,url,**kwargs):
    response=client.request(method,url,**kwargs)
    if response.status_code!=200:raise RuntimeError(f'{method} {url}: {response.status_code}: {response.text[:2500]}')
    return response.json()


def download(client,url,path):
    response=client.get(url);assert response.status_code==200,response.text[:1000]
    path.write_bytes(response.content)
    return sha(path)


def build(client,base,source,dest,label):
    with source.open('rb') as stream:
        state=call(client,'POST',base+'/import',files={'file':(source.name,stream,'application/x-step')})
    assert state['source_sha256']==sha(source)
    state=call(client,'POST',base+'/build',json=dict(revision=state['revision'],source_sha256=state['source_sha256'],
        options=dict(scope='all',units='auto',note='Own-output exchange audit; no design, drawing or supplementation.')))
    assert state['status']=='built'
    proof=dict(state=state,api_model_sha256=download(client,base+'/import/file/model.json',dest/(label+'_review.json')))
    # Bind the review to the actual download, not only a claimed filename/hash.
    assert download(client,base+'/import/file/original.ifc',dest/(label+'_downloaded.ifc'))==sha(source)
    save(dest/(label+'_api.json'),proof)
    return state


def graph_rows(path):
    inside=False
    for line in path.open(encoding='utf-8'):
        row=line.strip()
        if row=='DATA;':inside=True
        elif inside and row=='ENDSEC;':return
        elif inside:
            assert re.fullmatch(r'#\d+=IFC[A-Z0-9_]+\(.*\);',row),'Unexpected IFC STEP serialization'
            yield row


def compare(dest,package,state):
    import ifcopenshell
    import ifcopenshell.util.element as eu
    from steltic_openbim.source_worklines import required,build as captured,physical_view
    report=read(dest/'source_export.json')
    assert report['sha256']==sha(dest/'source.ifc')
    assert read(dest/'returned_export.json')['sha256']==sha(dest/'returned.ifc')
    actual=iter(graph_rows(dest/'returned.ifc'));classes=collections.Counter();count=0
    for expected in graph_rows(dest/'source.ifc'):
        assert next(actual,None)==expected,'An original IFC entity changed'
        classes[expected.split('=',1)[1].split('(',1)[0]]+=1;count+=1
    added=list(actual)
    assert added and all(r.split('=',1)[1].split('(',1)[0] in ('IFCPROPERTYSET','IFCPROPERTYSINGLEVALUE','IFCRELDEFINESBYPROPERTIES') for r in added)
    model=ifcopenshell.open(str(dest/'source.ifc'))
    props=eu.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert props['SourceModelSHA256']==fingerprint(package)==state['source_model_sha256']
    assert not props.get('SupplementProvenance')
    assert json.loads(props['DesignRecords'])==package['design_records']
    assert props['SourceReadiness']==report['source_validation']['status']
    assert json.loads(props['SourceFindings'])==report['source_validation']['findings']
    assert props['SourceFreshnessChecked'] is True
    physical=captured(package) if required(package) else physical_view(package)
    c=report['counts']
    assert c['members']==len(physical['members'])
    assert c['panel_surfaces']+c.get('panel_reference_boundaries',0)==len(physical.get('panels',[]))
    assert c['opening_references']==len(physical.get('openings',[]))
    assert c['connection_references']==sum(not x.get('parts') for x in physical.get('connections',[]))
    expected_parts=sum(len(x.get('parts',[])) for x in physical.get('connections',[]))
    assert c['connection_parts']+c['connection_reference_parts']==expected_parts,'Connection parts were dropped'
    del model,props,physical;gc.collect()
    signatures=[];findings=[];counts=[]
    for label in ('source','returned'):
        proof=read(dest/(label+'_api.json'));path=dest/(label+'_review.json')
        assert proof['api_model_sha256']==sha(path)
        assert proof['state']['source_sha256']==sha(dest/(label+'.ifc'))
        review=read(path)
        assert review['counts']==proof['state']['counts']
        assert review['counts']['displayed']==len(report['objects'])
        assert review['counts']['unrendered']==0 and review['counts']['excluded_by_scope']==0
        assert len({o['guid'] for o in review['objects']})==len(review['objects'])
        signatures.append(dict(objects={o['guid']:fingerprint(o) for o in review['objects']},
            bounds=review['bounds_m'],storeys=review['storeys'],units=review['source_units']))
        findings.append([dict(code=f['code'],count=f['count']) for f in review['checks']]);counts.append(review['counts'])
        del review;gc.collect()
    assert signatures[0]==signatures[1],'Product geometry or data changed across exchange'
    return dict(status='passed',source_sha256=sha(dest/'source.ifc'),returned_sha256=sha(dest/'returned.ifc'),
        original_entities_unchanged=True,entities_compared=count,entity_classes=dict(classes),added_review_entities=len(added),
        products_compared=len(signatures[0]['objects']),every_product_geometry_and_data_identical=True,
        source_coverage=dict(c,design_records=len(package['design_records'])),review_counts=counts[0],
        source_findings=findings[0],returned_findings=findings[1],schema_errors=[])


def run(key,variant):
    audit=read(OUT/key/'source_audit.json');job=Path(audit['job']);dest=OUT/key/('exchange_'+variant);dest.mkdir(exist_ok=True)
    source=OUT/key/('source.json' if variant=='saved' else 'replay/bim_package.json')
    result=dict(key=key,case=audit['case'],module=audit['module'],primary=audit['primary'],variant=variant,
        code_sha256=code_hashes(),llm_calls=0,redesign=False,analysis_solve=False,drawings=False,supplements=False)
    if not source.is_file():
        result.update(status='unavailable',reason='No saved physical package for this variant.');save(dest/'result.json',result);return result
    result['package_sha256']=sha(source)
    previous=read(dest/'result.json') if (dest/'result.json').is_file() else {}
    if previous.get('status')=='passed' and all(previous.get(k)==result.get(k) for k in ('code_sha256','package_sha256')):
        if previous['source_sha256']==sha(dest/'source.ifc') and previous['returned_sha256']==sha(dest/'returned.ifc'):
            return previous
    started=time.time();stage='snapshot'
    try:
        package=read(source);snapshot=OUT/'job_snapshots'/audit['module']/(key+'_'+variant)
        snapshot.mkdir(parents=True,exist_ok=True)
        tracked=set(package['provenance']['source_files'])|set(audit.get('current_tracked_source_files',{}))
        for name in tracked:
            original=(job/name).resolve();target=(snapshot/name).resolve()
            assert original.is_relative_to(job.resolve()) and target.is_relative_to(snapshot.resolve())
            if original.is_file():
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
                assert sha(target)==sha(original)
        package_path=snapshot/'design/bim_package.json';package_path.parent.mkdir(exist_ok=True)
        shutil.copy2(source,package_path)
        # These are byte-exact producer files. No drawing/supplement snapshot is read.
        verdict=inspect_package(package,snapshot);result['validation']=verdict
        result['copied_source_files']={n:sha(snapshot/n) for n in tracked if (snapshot/n).is_file()}
        drawings=DrawingStore(dest/'api_projects')
        def forbidden(*args,**kwargs):raise AssertionError('Drawing publication is forbidden during this audit')
        drawings.publish=forbidden
        app=FastAPI();app.include_router(router(drawings,{audit['module']:snapshot.parent}))
        client=TestClient(app);project='Audit_'+str(time.time_ns());base='/api/project/'+project+'/ifc'
        stage='source_import';response=client.post(base+'/structural/import',json=dict(module=audit['module'],job=snapshot.name))
        save(dest/'source_import_response.json',dict(status_code=response.status_code,body=response.json()))
        if verdict['status']=='invalid':
            assert response.status_code==422,'Invalid/stale native source was accepted'
            result.update(status='blocked_source',guard_passed=True,reason=response.json()['detail']);save(dest/'result.json',result);return result
        assert response.status_code==200,response.text[:2500]
        state=response.json();assert state['source_evidence']['source_freshness_checked']
        stage='source_export'
        report=call(client,'POST',base+'/export',json=dict(source='structural',revision=state['revision'],source_sha256=state['source_model_sha256']))
        save(dest/'source_export.json',report)
        assert not report['schema_errors']
        assert download(client,base+'/export/'+report['key']+'/model.ifc',dest/'source.ifc')==report['sha256']
        stage='source_build';imported=build(client,base,dest/'source.ifc',dest,'source')
        stage='return_export'
        returned=call(client,'POST',base+'/export',json=dict(source='ifc_import',revision=imported['revision'],source_sha256=imported['source_sha256']))
        save(dest/'returned_export.json',returned);assert not returned['schema_errors']
        assert download(client,base+'/export/'+returned['key']+'/model.ifc',dest/'returned.ifc')==returned['sha256']
        stage='return_build';build(client,base.replace(project,project+'_Return'),dest/'returned.ifc',dest,'returned')
        stage='comparison';result.update(compare(dest,package,state))
        result.update(source_readiness=report['source_validation']['status'],source_status=report['source_status'],
            representation=state['representation'],export_warnings=report['warnings'])
        assert drawings.current(project) is None and not list(dest.rglob('*.pdf'))
        assert not list(dest.rglob('design_model.json'))
        assert all(sha(job/name)==value for name,value in audit['files'].items())
        result['original_job_unchanged']=True
    except Exception as exc:
        result.update(status='failed',stage=stage,error=str(exc),traceback=traceback.format_exc())
    result['elapsed_seconds']=time.time()-started;save(dest/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ('key','variant','status','stage','products_compared','elapsed_seconds','error')}),flush=True)
    return result


if __name__=='__main__':
    result=run(*sys.argv[1:]);sys.exit(1 if result['status']=='failed' else 0)
