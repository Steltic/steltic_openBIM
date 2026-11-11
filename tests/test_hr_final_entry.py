import copy
import json
from pathlib import Path

import pytest

from steltic_openbim.drawing_workflow import DrawingStore,fingerprint,write_json
from steltic_openbim.ifc_store import IFCStore
from steltic_openbim.saved_delivery import digest_file


def captured_job(tmp_path):
    root=tmp_path/'hr-jobs'/'FutureBuilding'
    (root/'design').mkdir(parents=True)
    for name,content in [('cfg.py','building = 1'),('design/calc_package.json','{}'),
                         ('design/member_schedule.csv','section\nW8X10\n'),('report.html','<p>Saved design</p>')]:
        (root/name).write_text(content,encoding='utf-8')
    consistency=dict(result='PASS',n_issues=0,issues=[],cfg_sha256=digest_file(root/'cfg.py'),
                     calc_package_sha256=digest_file(root/'design/calc_package.json'))
    write_json(root/'design/consistency_result.json',consistency)
    source=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    source['physical'].setdefault('assemblies',[])
    h=dict(schema='steltic.hr_source_handoff',version=1,material_schedule={},building_id=source['building_id'],source_conflicts=[],
           records={'connections/c1':{'fields':[]}},occurrences={},source_files={
               str(path.relative_to(root)).replace('\\','/'):digest_file(path) for path in root.rglob('*') if path.is_file()},
           source_bindings={'native_content_sha256':fingerprint(source)})
    h['contract_sha256']=fingerprint(h);source['source_handoff']=h
    write_json(root/'design/bim_package.json',source)
    return root,source


def test_captured_hr_final_uses_the_matching_verified_document_pair(tmp_path):
    root,source=captured_job(tmp_path)
    drawings=DrawingStore(tmp_path/'projects');store=IFCStore(drawings,{'HR':root.parent})
    state=store.import_structural('project',{'module':'HR','job':root.name})
    selection=dict(source='structural',source_sha256=state['source_model_sha256'],revision=state['revision'])
    with pytest.raises(ValueError,match='drawing revision'):store.export('project',dict(selection,final=True))
    state=drawings.import_package('project',source,native_source={'module':'HR','job':root.name})
    good=store.export('project',dict(selection,final=True))
    assert good['delivery_status']=='verified'
    directory,issued=drawings.current('project')
    (directory/'drawings.pdf').write_bytes((directory/'drawings.pdf').read_bytes()+b'\nreplaced\n')
    with pytest.raises(ValueError,match='verification failed'):store.export('project',dict(selection,final=True))
    assert len(list((drawings.project('project')/'ifc'/'exports').glob('*/delivery_certificate.json')))==2


def test_retained_register_exports_an_immutable_revision_and_real_ifc(tmp_path,monkeypatch):
    from steltic_openbim import physical_pdf,review_pdf
    from steltic_openbim.saved_delivery import render_native_revision
    root,new=captured_job(tmp_path);prior=copy.deepcopy(new)
    p=prior['physical'];model=copy.deepcopy(p);model.update(pilot='hr32',scenario='approved test layout',title='Future building',
          source_sha256='original',connection_assemblies=[],member_schedule=[],assumptions=[])
    for c in model['connections']:
        c.update(drawing_ref='1/C001',detail_ref={'id':'located'},parameters={},member_ids=['beam'])
    folder=tmp_path/'retained';folder.mkdir()
    write_json(folder/'original.json',prior);write_json(folder/'design_model.json',model)
    write_json(folder/'drawing_manifest.json',dict(building_id=prior['building_id'],revision=1,source_model_sha256='original',
               model_sha256=fingerprint(model),sheets=[{'number':'G001'}]))
    # Use a compact real PDF writer at the approved-register renderer boundary.
    # Source binding, drawing production, IFC export and persisted state stay live.
    monkeypatch.setattr(review_pdf,'render_model',lambda package,state,out,*args:physical_pdf.generate(package,state,out))
    out=tmp_path/'delivery';result=render_native_revision(root/'design/bim_package.json',out,
                                          folder/'design_model.json',folder/'original.json')
    assert (out/'drawings.pdf').read_bytes().startswith(b'%PDF')
    assert (out/'model.ifc').read_bytes().startswith(b'ISO-10303-21')
    assert json.loads((out/'state.json').read_bytes())['schema']=='steltic.ifc_physical_source'
    assert result['ifc_sha256']==digest_file(out/'model.ifc')
