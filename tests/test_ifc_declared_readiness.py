"""Incomplete source evidence must remain visible through the IFC return path."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from steltic_openbim.drawing_workflow import DrawingStore
from steltic_openbim.ifc_api import router
from steltic_openbim.ifc_export import export_structural
from steltic_openbim.ifc_import import metadata,open_model
from steltic_openbim.ifc_store import IFCStore
from test_ifc_physical_source import setup


def source(tmp_path,properties):
    _,_,drawings,roots=setup(tmp_path,'HR');store=IFCStore(drawings,roots)
    store.import_structural('Example',dict(module='HR',job='Example'))
    path=tmp_path/'source.ifc';export_structural(store.structural_current('Example')[0],path)
    model=open_model(path)
    # Author source declarations as an external IFC producer would supply them.
    project=model.by_type('IfcProject')[0]
    pset=next(r.RelatingPropertyDefinition for r in project.IsDefinedBy if r.RelatingPropertyDefinition.Name=='Steltic_Coordination')
    existing={p.Name:p for p in pset.HasProperties}
    for key,value in properties.items():
        text=json.dumps(value) if isinstance(value,(dict,list)) else value
        existing[key].NominalValue=model.create_entity('IfcText',text)
    model.write(str(path));return path


@pytest.mark.parametrize('readiness',['needs_input','ready'])
def test_producer_findings_survive_actual_api_build_export_and_reimport(tmp_path,readiness):
    findings=[dict(code='connection_fastener_quantity',severity='needs_input',message='Assembly requires four supplied bolt occurrences',entity_ids=['C1','C2'])]
    path=source(tmp_path,dict(SourceReadiness=readiness,SourceFindings=findings))
    app=FastAPI();app.include_router(router(DrawingStore(tmp_path/'projects')));client=TestClient(app)
    def build(project,raw):
        base='/api/project/'+project+'/ifc'
        state=client.post(base+'/import',files={'file':('source.ifc',raw,'application/x-step')}).json()
        built=client.post(base+'/build',json=dict(revision=state['revision'],source_sha256=state['source_sha256'],options=dict(scope='all',units='auto')))
        assert built.status_code==200,built.text
        review=client.get(base+'/import/file/model.json').json()
        finding=next(f for f in review['checks'] if f['code']=='declared_source_connection_fastener_quantity')
        assert finding['count']==2 and finding['source_entity_ids']==['C1','C2']
        assert 'not independently recomputed' in finding['provenance']
        return base,built.json(),review
    base,state,first=build('Incoming',path.read_bytes())
    response=client.post(base+'/export',json=dict(source='ifc_import',revision=state['revision'],source_sha256=state['source_sha256']))
    assert response.status_code==200,response.text
    returned=client.get(base+'/export/'+response.json()['key']+'/model.ifc').content
    _,_,second=build('Returned',returned)
    assert first['objects']==second['objects'] and first['checks']==second['checks']
    assert not list(tmp_path.rglob('*.pdf'))


@pytest.mark.parametrize('value',['broken JSON',{},[dict(code='gap',message='Missing parts',severity='needs_input',entity_ids=[1])]])
def test_malformed_source_findings_are_visible_without_blocking_geometry(tmp_path,value):
    path=source(tmp_path,dict(SourceReadiness='needs_input',SourceFindings=value))
    result=metadata(open_model(path))
    assert any(f['code']=='source_readiness_unreadable' for f in result['findings'])
    assert result['counts']['products']>0


def test_incomplete_flag_without_details_remains_an_information_request(tmp_path):
    path=source(tmp_path,dict(SourceReadiness='needs_input',SourceFindings=[]))
    assert any(f['code']=='declared_source_incomplete' for f in metadata(open_model(path))['findings'])


def test_ready_source_does_not_clear_independent_import_findings(tmp_path):
    path=source(tmp_path,dict(SourceReadiness='ready',SourceFindings=[]))
    model=open_model(path)
    model.by_type('IfcBeam')[0].Representation=None
    problems=metadata(model)['findings']
    assert any(f['code']=='missing_geometry' for f in problems)
    assert not any(f['code'].startswith('declared_source_') for f in problems)
