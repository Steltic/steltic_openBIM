import copy
import json
from pathlib import Path
import zipfile
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from steltic_openbim import inspect_package
from steltic_openbim.drawing_workflow import DrawingStore,StaleRevision,initial_state,apply_answer,fingerprint
from steltic_openbim.drawing_api import router
from steltic_openbim.drawing_pdf import generate
from steltic_openbim.pilots import cfs16


@pytest.fixture(scope='module')
def warehouse():
    with zipfile.ZipFile(Path(__file__).parent/'fixtures/stage3_replay_inputs.zip') as z:
        source=json.loads(z.read('cfs16/bim_package.json'))
    catalog=json.loads(Path(cfs16.__file__).with_name('catalog.json').read_text())
    return cfs16.build(source,catalog)


def answer(state):
    f=copy.deepcopy(state['features'][0]);f.update(y_ft=100,width_ft=3.25)
    return dict(revision=state['revision'],source_model_sha256=state['source_model_sha256'],id='CFS16-DOORS',action='resolve_openings',author='TEST REVIEWER',note='Test-only layout; one door confirmed for this fixture.',features=[f])


def test_provisional_acceptance_is_not_quantitative_acceptance(warehouse):
    before=fingerprint(warehouse);s=initial_state(warehouse,1)
    assert s['can_generate'] and s['drawing_status']=='provisional'
    assert all(r['accepted'] and r['proposal'] and not r['confirmed'] for r in s['requests'])
    assert inspect_package(warehouse)['status']=='needs_input'
    assert fingerprint(warehouse)==before
    assert all(not f['confirmed'] for f in s['features'])


def test_dimensions_hidden_then_updated_without_altering_source(warehouse,tmp_path):
    s=initial_state(warehouse,1);before=fingerprint(warehouse)
    first=generate(warehouse,s,tmp_path/'r1')
    assert not any(d['kind']=='confirmed_opening' for d in first['dimensions'])
    reader=PdfReader(tmp_path/'r1/drawings.pdf')
    txt='\n'.join(reader.pages[x['page']-1].extract_text() for x in first['sheets'] if x['title'].startswith('Opening'))
    assert 'P001' in txt and 'TBD' in txt and 'resolve query' in txt
    assert 'SRC-DOOR-0' in txt and "14'-0\"" in txt
    resolved=apply_answer(warehouse,s,answer(s));after=generate(warehouse,resolved,tmp_path/'r2')
    assert resolved['revision']==2 and len(resolved['features'])==1 and resolved['features'][0]['confirmed']
    dims=[d for d in after['dimensions'] if d['kind']=='confirmed_opening']
    assert dims[0]['values_ft']['y_ft']==100 and dims[0]['values_ft']['width_ft']==3.25
    reader=PdfReader(tmp_path/'r2/drawings.pdf')
    txt='\n'.join(reader.pages[x['page']-1].extract_text() for x in after['sheets'] if x['title'].startswith('Opening'))
    assert "3'-3\"" in txt and "100'-0\"" in txt
    assert first['pdf_sha256']!=after['pdf_sha256'] and fingerprint(warehouse)==before


@pytest.mark.parametrize('field,value',[('x_ft',float('nan')),('width_ft',0),('y_ft',100000),('level',99)])
def test_bad_quantities_cannot_be_confirmed(warehouse,field,value):
    s=initial_state(warehouse,1);a=answer(s);a['features'][0][field]=value
    with pytest.raises(ValueError): apply_answer(warehouse,s,a)


def test_stale_answers_and_notes_cannot_close_request(warehouse):
    s=initial_state(warehouse,1);a=answer(s);a['revision']=0
    with pytest.raises(StaleRevision): apply_answer(warehouse,s,a)
    a=answer(s);a.update(action='information',note='Please consider moving the doors.')
    r=apply_answer(warehouse,s,a)
    assert all(not x['confirmed'] for x in r['requests'])
    assert r['requests'][0]['notes'] and not r['features'][0]['confirmed']
    resolved=apply_answer(warehouse,s,answer(s))
    note=dict(a,revision=resolved['revision'])
    updated=apply_answer(warehouse,resolved,note)
    request=next(r for r in updated['requests'] if r['id']=='CFS16-DOORS')
    assert request['confirmed'] and request['status']=='resolved'
    assert updated['features']==resolved['features']


def test_render_failure_leaves_previous_revision_current(warehouse,tmp_path,monkeypatch):
    from steltic_openbim import drawing_pdf
    store=DrawingStore(tmp_path);s=store.import_package('Test',warehouse)
    def fail(*args): raise RuntimeError('renderer failed')
    monkeypatch.setattr(drawing_pdf,'generate',fail)
    with pytest.raises(RuntimeError): store.answer('Test',answer(s))
    assert store.current('Test')[1]['revision']==1


def test_api_source_import_answers_history_and_path_confinement(warehouse,tmp_path):
    import hashlib
    job=tmp_path/'cfs'/'Example'/'design';job.mkdir(parents=True)
    package=copy.deepcopy(warehouse)
    source=b'# Synthetic source for the CFS warehouse test fixture\n'
    (job.parent/'cfg.py').write_bytes(source)
    package['provenance']['source_files']={'cfg.py':hashlib.sha256(source).hexdigest()}
    (job/'bim_package.json').write_text(json.dumps(package))
    store=DrawingStore(tmp_path/'drawings');app=FastAPI();app.include_router(router(store,{'CFS':tmp_path/'cfs'}));c=TestClient(app)
    assert c.get('/api/drawings/sources').json()['sources']==[{'module':'CFS','job':'Example'}]
    s=c.post('/api/project/Test/drawings/import',json={'module':'CFS','job':'Example'}).json()
    assert s['can_generate'] and c.get('/api/project/Test/drawings').json()['questions']['blocks_drawings'] is False
    before=c.get('/api/project/Test/drawings/file/drawings.pdf').content
    assert c.post('/api/project/Test/drawings/answers',json=answer(s)).status_code==200
    assert c.post('/api/project/Test/drawings/answers',json=answer(s)).status_code==409
    history=c.get('/api/project/Test/drawings/history').json()['revisions'];assert len(history)==2
    assert c.get('/api/project/Test/drawings/file/drawings.pdf',params={'revision':history[0]['directory']}).content==before
    assert c.get('/api/project/Test/drawings/file/source.json').status_code==404
    assert c.get('/api/project/Test/drawings/file/drawings.pdf?revision=../../private').status_code==404
    assert c.post('/api/project/Test/drawings/import',json={'module':'HR','job':'../../outside'}).status_code==422
    for raw in ('{invalid','[]','null'):
        assert c.post('/api/project/Test/drawings/answers',content=raw).status_code==422
    assert c.post('/api/project/Test/drawings/upload',files={'file':('bad.json',b'\xff')}).status_code==422
    replaced=copy.deepcopy(warehouse);replaced['building_id']='ChangedSource'
    assert c.post('/api/project/Test/drawings/upload',files={'file':('package.json',json.dumps(replaced))}).status_code==409
    r=c.post('/api/project/Test/drawings/upload',data={'revision':2},files={'file':('package.json',json.dumps(replaced))})
    assert r.status_code==200 and all(not r['confirmed'] for r in r.json()['requests'])


def test_invalid_model_is_not_masked_as_provisional(warehouse):
    p=copy.deepcopy(warehouse);p['physical']['members'][0]['axis'][0][0]=float('nan')
    with pytest.raises(ValueError,match='Invalid physical geometry'): initial_state(p,1)


def test_shared_store_prevents_two_pages_overwriting_each_other(warehouse,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    first=DrawingStore(tmp_path);second=DrawingStore(tmp_path)
    state=first.import_package('Shared',warehouse)
    def submit(store):
        try: return store.answer('Shared',answer(state))['revision']
        except StaleRevision: return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,[first,second]))
    assert sorted(map(str,results))==['2','stale']
    assert first.current('Shared')[1]['revision']==second.current('Shared')[1]['revision']==2
    before=first.current('Shared')[1]
    updated=second.regenerate('Shared',before)
    assert updated['revision']==3 and updated['features']==before['features']
    with pytest.raises(StaleRevision): first.regenerate('Shared',before)


def test_standalone_module_uses_hub_local_request_guard(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENBIM_JOBS',str(tmp_path))
    monkeypatch.setenv('STELTIC_HUB_TOKEN','test-token')
    from steltic_openbim.drawing_server import app
    client=TestClient(app)
    assert client.get('/healthz').status_code==200
    assert client.post('/api/project/Guard/drawings/answers',json={},headers={'origin':'https://untrusted.example'}).status_code==403
    assert client.get('/healthz',headers={'host':'untrusted.example'}).status_code==403
    assert client.get('/healthz',headers={'x-steltic-hub-token':'wrong'}).status_code==403
    assert client.get('/healthz',headers={'x-steltic-hub-token':'test-token'}).status_code==200
