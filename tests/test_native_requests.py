"""Hub decisions return to the matching native job and survive refresh failures."""
import json
from pathlib import Path
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from steltic_openbim.native_requests import router
from steltic_openbim import bim_assemblies as A
from steltic_openbim.ifc_store import IFCStore
from steltic_openbim.ifc_export import export_structural
from steltic_openbim.drawing_workflow import DrawingStore,write_json


class Store:
    state=dict(revision=3,native_source=dict(module='CFS',job='Example'))
    def current(self,p):return None,dict(self.state)
    def import_package(self,p,package,revision,native_source=None):
        assert revision==3 and package=={'native':'updated'} and native_source==self.state['native_source']
        return dict(revision=4)


class Jobs:
    def path(self,module,job):assert (module,job)==('CFS','Example');return Path('unused')
    def load_current(self,module,job):return {'native':'updated'},{}


@pytest.mark.parametrize('url,expected',[('http://127.0.0.1:8402','local-launch'),('https://example.invalid',None)])
def test_native_requests_use_only_local_launch_credentials(monkeypatch,url,expected):
    monkeypatch.setenv('STELTIC_HUB_TOKEN','local-launch')
    app=FastAPI();app.include_router(router(Store(),Jobs(),{'CFS':url}));client=TestClient(app)
    def native(request):
        assert request.headers.get('x-steltic-hub-token')==expected
        assert 'cookie' not in request.headers and 'authorization' not in request.headers
        return httpx.Response(200,json=dict(requests=[],revision=7,sha256='current'))
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(native),**kw))
    result=client.get('/api/project/Test/drawings/native-requests',headers={'authorization':'user browser credential','cookie':'secret=browser'})
    assert result.status_code==200


def test_native_writeback_and_drawing_refresh_failure(monkeypatch):
    store=Store();app=FastAPI();app.include_router(router(store,Jobs(),{'CFS':'http://native'}));client=TestClient(app)
    calls=[];fail=[]
    def native(request):
        calls.append((request.method,request.url.path,json.loads(request.content) if request.content else None))
        if request.url.path.endswith('/requests'):return httpx.Response(200,json=dict(requests=[],revision=7,sha256='current'))
        if request.url.path.endswith('/answers'):return httpx.Response(200,json=dict(revision=8,sha256='updated'))
        return httpx.Response(409,json=dict(detail='refresh native model')) if fail else httpx.Response(200,json=dict(readiness=dict(status='ready')))
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(native),**kw))
    assert client.get('/api/project/Test/drawings/native-requests').json()['module']=='CFS'
    body=dict(drawing_revision=3,request_id='Q',action='confirm',author='Engineer',note='Selected values',expected_revision=7,expected_sha256='current')
    response=client.post('/api/project/Test/drawings/native-answers',json=body)
    assert response.status_code==200,response.text
    assert response.json()['drawings_updated'] is True
    assert calls[-2][1]=='/api/physical/Example/answers' and 'drawing_revision' not in calls[-2][2]
    assert calls[-1][2]==dict(expected_revision=8,expected_sha256='updated')
    fail.append(True)
    result=client.post('/api/project/Test/drawings/native-answers',json=body).json()
    assert result['saved'] and not result['drawings_updated'] and 'Answer saved in CFS' in result['message']
    assert client.post('/api/project/Test/drawings/native-answers',json=dict(body,drawing_revision=2)).status_code==409


def test_instanced_connection_exports_actual_mesh_and_component_data(tmp_path):
    import ifcopenshell,ifcopenshell.geom,ifcopenshell.util.element
    package=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())
    c=package['physical']['connections'][0];member=package['physical']['members'][0]
    template=dict(id='CLIP',parts=c.pop('parts'),source_record_ids=c['design_record_ids'],
        receivers=[dict(id='M',kind='member',axis=member['axis'],profile_id=member['profile_id'])],basis='Synthetic source selection')
    template['revision']=A.fingerprint(template);package['physical']['assemblies']=[template]
    joint=next(j for j in package['physical']['joints'] if j['id']==c['joint_id'])
    c.update(parts=[],assembly_instance=dict(template_id='CLIP',revision=template['revision'],origin=joint['point'],x_axis=[1,0,0],y_axis=[0,1,0],bindings=dict(M=member['id'])))
    path=tmp_path/'jobs/Example/design/bim_package.json';path.parent.mkdir(parents=True);write_json(path,package)
    store=IFCStore(DrawingStore(tmp_path/'projects'),{'HR':path.parents[2]})
    store.import_structural('Return',dict(module='HR',job='Example'))
    report=export_structural(store.structural_current('Return')[0],tmp_path/'return.ifc')
    assert report['counts']['connection_assemblies']==1 and report['counts']['connection_references']==0
    model=ifcopenshell.open(str(tmp_path/'return.ifc'));assembly=model.by_type('IfcElementAssembly')[0]
    shape=ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(),assembly)
    assert len(shape.geometry.verts)>0
    props=ifcopenshell.util.element.get_psets(assembly)['Steltic_Coordination']
    assert json.loads(props['SourceEntity'])['assembly_instance']==c['assembly_instance']
    project=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert json.loads(project['AssemblyTemplates'])==[template]
