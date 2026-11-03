"""A worker timeout must preserve the last published IFC review."""
import subprocess
from pathlib import Path
import pytest
from steltic_openbim import ifc_store
from steltic_openbim.drawing_workflow import DrawingStore,write_json


@pytest.mark.parametrize('status',['questions','built'])
def test_timeout_preserves_published_source_and_returns_actionable_error(tmp_path,monkeypatch,status):
    drawings=DrawingStore(tmp_path)
    store=ifc_store.IFCStore(drawings)
    folder=store.directory('case',1)
    original=b'ISO-10303-21; original retained source'
    (folder/'original.ifc').write_bytes(original)
    write_json(folder/'inspection.json',{'units':{'known':True}})
    state=dict(revision=1,source_sha256='source',filename='source.ifc',status=status,options={})
    old_review=b'{"counts":{"displayed":12}}'
    if status=='built':(folder/'model.json').write_bytes(old_review)
    store.publish('case',folder,state)
    def timeout(cmd,**kwargs):
        assert kwargs['timeout']==1200
        assert cmd[3]=='build'
        Path(cmd[5]).write_text('partial unpublished output',encoding='utf-8')
        raise subprocess.TimeoutExpired(cmd,kwargs['timeout'])
    monkeypatch.setattr(ifc_store.subprocess,'run',timeout)
    with pytest.raises(ValueError,match='exceeded twenty minutes'):
        store.build('case',dict(revision=1,source_sha256='source',options={'scope':'all','units':'auto'}))
    assert store.current('case')==(folder,state)
    assert (folder/'original.ifc').read_bytes()==original
    if status=='built':assert (folder/'model.json').read_bytes()==old_review
    else:assert not (folder/'model.json').exists()
