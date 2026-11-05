import hashlib,io,subprocess
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from steltic_openbim import ifc_store,ifc_api
from steltic_openbim.drawing_workflow import DrawingStore,write_json


def inspection(action,source,output,*args):
    assert action=='inspect' and Path(source).read_bytes().startswith(b'ISO-10303-21')
    result=dict(counts=dict(products=150000),schema='IFC4')
    write_json(Path(output),result)
    return result


def test_spooled_upload_never_reads_entire_file_and_keeps_exact_source(tmp_path,monkeypatch):
    monkeypatch.setattr(ifc_store,'worker',inspection)
    raw=b'ISO-10303-21;'+b'x'*(3*ifc_store.UPLOAD_CHUNK+37)
    class Bounded(io.BytesIO):
        def read(self,n=-1):
            assert 0<n<=ifc_store.UPLOAD_CHUNK
            return super().read(n)
    store=ifc_store.IFCStore(DrawingStore(tmp_path))
    state=store.upload_stream('building','building.ifc',Bounded(raw))
    folder,published=store.current('building')
    assert state==published and state['source_sha256']==hashlib.sha256(raw).hexdigest()
    assert (folder/'original.ifc').read_bytes()==raw


def test_oversize_stream_and_failed_inspection_preserve_published_source(tmp_path,monkeypatch):
    monkeypatch.setattr(ifc_store,'worker',inspection)
    store=ifc_store.IFCStore(DrawingStore(tmp_path));raw=b'ISO-10303-21; old source'
    state=store.upload('building','source.ifc',raw);before=store.current('building')
    monkeypatch.setattr(ifc_store,'MAX_FILE',100)
    with pytest.raises(ValueError,match='exceeds'):
        store.upload_stream('building','oversize.ifc',io.BytesIO(b'ISO-10303-21;'+b'x'*101),state['revision'])
    assert store.current('building')==before
    def fail(*args):raise ValueError('invalid imported model')
    monkeypatch.setattr(ifc_store,'worker',fail)
    with pytest.raises(ValueError,match='invalid imported model'):
        store.upload_stream('building','invalid.ifc',io.BytesIO(b'ISO-10303-21; broken'),state['revision'])
    assert store.current('building')==before and (before[0]/'original.ifc').read_bytes()==raw


def test_api_passes_spooled_file_and_rejects_oversize_before_inspection(tmp_path,monkeypatch):
    monkeypatch.setattr(ifc_store,'worker',inspection)
    def no_raw(*args):raise AssertionError('API must not copy the whole upload into bytes')
    monkeypatch.setattr(ifc_store.IFCStore,'upload',no_raw)
    app=FastAPI();app.include_router(ifc_api.router(DrawingStore(tmp_path)))
    with TestClient(app) as client:
        raw=b'ISO-10303-21;'+b'x'*(2*ifc_store.UPLOAD_CHUNK)
        r=client.post('/api/project/large/ifc/import',files={'file':('large.ifc',raw)})
        assert r.status_code==200,r.text
        monkeypatch.setattr(ifc_api,'MAX_FILE',10)
        r=client.post('/api/project/large/ifc/import',files={'file':('large.ifc',raw)},data={'revision':1})
        assert r.status_code==413
        assert client.get('/api/project/large/ifc/import/file/original.ifc').content==raw


def test_large_source_gets_bounded_extended_worker_deadline(tmp_path,monkeypatch):
    source=tmp_path/'structural';source.mkdir();(source/'source.json').write_text('large model')
    monkeypatch.setattr(ifc_store,'LARGE_SOURCE_BYTES',1)
    def timeout(cmd,timeout):
        assert timeout==7200
        raise subprocess.TimeoutExpired(cmd,timeout)
    monkeypatch.setattr(ifc_store,'run_worker',timeout)
    with pytest.raises(ValueError,match='exceeded 120 minutes'):
        ifc_store.worker('export_structural',source,tmp_path/'report.json')
