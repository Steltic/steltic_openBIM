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
    def timeout(cmd,timeout):
        assert timeout==1200
        assert cmd[3]=='build'
        Path(cmd[5]).write_text('partial unpublished output',encoding='utf-8')
        raise subprocess.TimeoutExpired(cmd,timeout)
    monkeypatch.setattr(ifc_store,'run_worker',timeout)
    with pytest.raises(ValueError,match='exceeded twenty minutes'):
        store.build('case',dict(revision=1,source_sha256='source',options={'scope':'all','units':'auto'}))
    assert store.current('case')==(folder,state)
    assert (folder/'original.ifc').read_bytes()==original
    if status=='built':assert (folder/'model.json').read_bytes()==old_review
    else:assert not (folder/'model.json').exists()


def test_timed_out_worker_terminates_its_owned_tree_and_drains_pipes(monkeypatch):
    calls=[]
    class Process:
        pid=12345
        def __enter__(self):return self
        def __exit__(self,*args):calls.append('closed')
        def communicate(self,timeout):
            calls.append(('communicate',timeout))
            if timeout==1200:raise subprocess.TimeoutExpired(['worker'],timeout)
            return '', ''
    proc=Process()
    def popen(cmd,**kwargs):
        assert kwargs['stdin']==subprocess.DEVNULL
        if ifc_store.os.name=='nt':assert kwargs['creationflags'] & subprocess.CREATE_NEW_PROCESS_GROUP
        else:assert kwargs['start_new_session'] is True
        return proc
    monkeypatch.setattr(ifc_store.subprocess,'Popen',popen)
    monkeypatch.setattr(ifc_store,'terminate_worker',lambda owned:calls.append(('terminate',owned.pid)))
    with pytest.raises(subprocess.TimeoutExpired):ifc_store.run_worker(['worker'],1200)
    assert calls==[('communicate',1200),('terminate',12345),('communicate',10),'closed']


def test_termination_targets_only_owned_process_group(monkeypatch):
    calls=[]
    class Process:
        pid=12345
        def kill(self):calls.append('kill')
    if ifc_store.os.name=='nt':
        def taskkill(cmd,**kwargs):
            assert cmd==['taskkill','/PID','12345','/T','/F']
            assert kwargs['timeout']==10 and kwargs['creationflags']==subprocess.CREATE_NO_WINDOW
            calls.append('tree')
        monkeypatch.setattr(ifc_store.subprocess,'run',taskkill)
    else:
        monkeypatch.setattr(ifc_store.os,'killpg',lambda pid,sig:calls.append('tree') if (pid,sig)==(12345,ifc_store.signal.SIGKILL) else pytest.fail('Wrong process group'))
    ifc_store.terminate_worker(Process())
    assert calls==['tree','kill']
