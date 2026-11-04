"""A schema-valid IFC must not imply a complete or current native source."""
import hashlib
import json

import ifcopenshell
import ifcopenshell.util.element
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from steltic_openbim.drawing_workflow import write_json
from steltic_openbim.ifc_api import router
from steltic_openbim.ifc_export import export_structural
from steltic_openbim.ifc_store import IFCStore
from test_ifc_physical_source import setup


@pytest.mark.parametrize('module',['HR','CFS'])
def test_reloading_changed_job_evidence_cannot_replace_accepted_snapshot(tmp_path,module):
    package,path,drawings,roots=setup(tmp_path,module)
    cfg=path.parents[1]/'cfg.py';cfg.write_text('original job input',encoding='utf-8')
    package['provenance']['source_files']={'cfg.py':hashlib.sha256(cfg.read_bytes()).hexdigest()}
    write_json(path,package)
    app=FastAPI();app.include_router(router(drawings,roots));client=TestClient(app)
    url='/api/project/Example/ifc'
    first=client.post(url+'/structural/import',json=dict(module=module,job='Example')).json()
    assert first['source_evidence']==dict(source_freshness_checked=True,tracked_files=1)
    store=IFCStore(drawings,roots);folder=store.structural_current('Example')[0]
    cfg.write_text('changed job input',encoding='utf-8')
    response=client.post(url+'/structural/import',json=dict(module=module,job='Example',revision=1))
    assert response.status_code==422 and 'source_stale' in response.json()['detail']
    assert store.structural_current('Example')[1]==first
    # The previously accepted revision is still an immutable historical source.
    result=export_structural(folder,tmp_path/'historical.ifc')
    assert result['source_sha256']==first['source_model_sha256']
    cfg.unlink()
    response=client.post(url+'/structural/import',json=dict(module=module,job='Example',revision=1))
    assert response.status_code==422 and 'source_missing' in response.json()['detail']
    assert store.structural_current('Example')[1]==first


def test_existing_request_does_not_hide_a_new_physical_finding(tmp_path):
    package,path,drawings,roots=setup(tmp_path,'HR')
    package['review']={'recipe':'synthetic_review','recipe_version':'1.0','items':[{'id':'coordination_note','title':'Confirm the documented interface','kind':'delegated','basis':'Existing source note','status':'coordination_required','entity_ids':[]}]}
    package['physical']['connections'][0]['parts'][0]['geometry']['origin']=[1000,0,0]
    assert package['readiness']['status']=='ready'
    write_json(path,package);before=path.read_bytes()
    store=IFCStore(drawings,roots)
    state=store.import_structural('Example',dict(module='HR',job='Example'))
    assert state['source_readiness']=='needs_input' and state['source_status']=='provisional'
    assert {'coordination_note','physical_remote_part'} <= {r['id'] for r in state['requests']}
    assert all(r['proposal'] and r['accepted'] and not r['confirmed'] for r in state['requests'])
    report=export_structural(store.structural_current('Example')[0],tmp_path/'provisional.ifc')
    assert report['schema_errors']==[] and report['source_status']=='provisional'
    assert report['source_validation']['status']=='needs_input'
    model=ifcopenshell.open(str(tmp_path/'provisional.ifc'))
    props=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert props['SourceReadiness']=='needs_input'
    assert 'physical_remote_part' in {f['code'] for f in json.loads(props['SourceFindings'])}
    assert json.loads(props['DesignRecords'])==package['design_records']
    assert path.read_bytes()==before and drawings.current('Example') is None
    assert not list(tmp_path.rglob('*.pdf'))


def test_export_rechecks_old_ready_snapshot_and_reports_provisional_status(tmp_path):
    package,path,drawings,roots=setup(tmp_path,'CFS')
    package['physical']['connections'][0]['parts'][0]['geometry']['origin']=[1000,0,0]
    write_json(path,package);store=IFCStore(drawings,roots)
    store.import_structural('Example',dict(module='CFS',job='Example'))
    folder,state=store.structural_current('Example')
    state.update(source_status='source_geometry',source_readiness='ready',requests=[])
    write_json(folder/'state.json',state);before=(folder/'state.json').read_bytes()
    report=export_structural(folder,tmp_path/'checked.ifc')
    assert report['source_validation']['status']=='needs_input' and report['source_status']=='provisional'
    assert (folder/'state.json').read_bytes()==before


def test_empty_provenance_is_not_advertised_as_verified_evidence(tmp_path):
    _,_,drawings,roots=setup(tmp_path,'HR')
    state=IFCStore(drawings,roots).import_structural('Example',dict(module='HR',job='Example'))
    assert state['source_evidence']==dict(source_freshness_checked=False,tracked_files=0)


@pytest.mark.parametrize('provenance',[None,[],{'source_files':[]}])
def test_malformed_provenance_is_an_input_error(tmp_path,provenance):
    package,path,drawings,roots=setup(tmp_path,'HR')
    package['provenance']=provenance;write_json(path,package)
    app=FastAPI();app.include_router(router(drawings,roots));client=TestClient(app)
    response=client.post('/api/project/Example/ifc/structural/import',json=dict(module='HR',job='Example'))
    assert response.status_code==422 and 'Invalid physical geometry' in response.json()['detail']
    assert IFCStore(drawings,roots).structural_current('Example') is None
