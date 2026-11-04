"""Direct HR/CFS returns must not require or create a drawing revision."""
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.element
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from steltic_openbim.drawing_workflow import DrawingStore,write_json
from steltic_openbim.ifc_api import router
from steltic_openbim.ifc_export import export_structural,schema_errors
from steltic_openbim.ifc_import import build_review
from steltic_openbim.ifc_store import IFCStore


def setup(tmp_path,module):
    package=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())
    package['module']=module
    source=tmp_path/'source_jobs'/'Example'/'design'/'bim_package.json'
    source.parent.mkdir(parents=True);write_json(source,package)
    drawings=DrawingStore(tmp_path/'projects')
    roots={module:source.parents[2]}
    return package,source,drawings,roots


@pytest.mark.parametrize('module',['HR','CFS'])
def test_direct_job_export_without_drawing_engine_preserves_source_and_geometry(tmp_path,monkeypatch,module):
    package,path,drawings,roots=setup(tmp_path,module);before=path.read_bytes()
    def forbidden(*args,**kwargs):raise AssertionError('Drawing engine must not run')
    monkeypatch.setattr(drawings,'publish',forbidden)
    monkeypatch.setattr('steltic_openbim.drawing_pdf.generate',forbidden)
    app=FastAPI();app.include_router(router(drawings,roots));client=TestClient(app)
    base='/api/project/Direct/ifc'
    assert client.get(base).json()['sources']==[dict(module=module,job='Example')]
    response=client.post(base+'/structural/import',json=dict(module=module,job='Example'))
    assert response.status_code==200,response.text
    state=response.json();assert state['revision']==1
    body=dict(source='structural',revision=1,source_sha256=state['source_model_sha256'])
    response=client.post(base+'/export',json=body);assert response.status_code==200,response.text
    report=response.json();assert report['physical_revision']==1 and 'drawing_revision' not in report
    target=tmp_path/'return.ifc'
    target.write_bytes(client.get(base+'/export/'+report['key']+'/model.ifc').content)
    assert not schema_errors(target)
    review=build_review(target,dict(units='auto',scope='all'))
    assert review['counts']['unrendered']==0 and report['counts']['member_surfaces']==1
    beam=next(o for o in review['objects'] if o['ifc_class']=='IfcBeam')
    assert beam['bounds_m'][0]==pytest.approx([0,3.048])
    properties=beam['properties']['Steltic_Coordination']
    assert properties['PhysicalSourceRevision']==1 and 'DrawingRevision' not in properties
    model=ifcopenshell.open(str(target))
    props=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert props['SourceModule']==module and props['SourceJob']=='Example'
    assert path.read_bytes()==before and drawings.current('Direct') is None
    assert not list((tmp_path/'projects').rglob('*.pdf'))
    assert client.get(base).json()['drawing'] is None


def test_source_replacement_is_guarded_and_export_uses_immutable_snapshot(tmp_path):
    package,path,drawings,roots=setup(tmp_path,'HR')
    store=IFCStore(drawings,roots)
    first=store.import_structural('Direct',dict(module='HR',job='Example'))
    first_folder=store.structural_current('Direct')[0]
    package['physical']['members'][0]['axis'][1][0]=240
    package['physical']['joints'][1]['point'][0]=240
    write_json(path,package)
    from steltic_openbim.drawing_workflow import StaleRevision
    with pytest.raises(StaleRevision):store.import_structural('Direct',dict(module='HR',job='Example'))
    second=store.import_structural('Direct',dict(module='HR',job='Example',revision=1))
    assert second['revision']==2 and second['source_model_sha256']!=first['source_model_sha256']
    with pytest.raises(StaleRevision):store.export('Direct',dict(source='structural',revision=1,source_sha256=first['source_model_sha256']))
    old=export_structural(first_folder,tmp_path/'old.ifc')
    assert old['source_sha256']==first['source_model_sha256']
    write_json(first_folder/'source.json',package)
    with pytest.raises(ValueError,match='fingerprint changed'):export_structural(first_folder,tmp_path/'changed.ifc')
    again=store.import_structural('Direct',dict(module='HR',job='Example',revision=2))
    assert again==second


def test_one_shaft_keeps_both_coincident_solver_roles_in_ifc_return(tmp_path):
    from test_bim_coincident_components import package as coincident
    package,path,drawings,roots=setup(tmp_path,'HR');member=package['physical']['members'][0]
    split=coincident();package['analysis']=split['analysis']
    for node,q in zip(package['analysis']['nodes'],member['axis']):node['point']=q
    member['analysis_ids']=['axial','bending'];member['analysis_component_roles']={'axial':'axial','bending':'flexural'}
    write_json(path,package);store=IFCStore(drawings,roots);store.import_structural('Direct',dict(module='HR',job='Example'))
    target=tmp_path/'combined.ifc';report=export_structural(store.structural_current('Direct')[0],target)
    assert report['counts']['member_surfaces']==1 and not schema_errors(target)
    review=build_review(target,dict(units='auto',scope='all'));beams=[r for r in review['objects'] if r['ifc_class']=='IfcBeam']
    assert len(beams)==1
    source=json.loads(beams[0]['properties']['Steltic_Coordination']['SourceEntity'])
    assert source['analysis_ids']==member['analysis_ids'] and source['analysis_component_roles']==member['analysis_component_roles']


def test_invalid_or_wrong_module_sources_do_not_replace_current(tmp_path):
    package,path,drawings,roots=setup(tmp_path,'HR');store=IFCStore(drawings,roots)
    first=store.import_structural('Direct',dict(module='HR',job='Example'))
    for job in ('../Example','C:/elsewhere','Example/design'):
        with pytest.raises(ValueError):store.import_structural('Direct',dict(module='HR',job=job,revision=1))
    package['module']='CFS';write_json(path,package)
    with pytest.raises(ValueError,match='selected module'):store.import_structural('Direct',dict(module='HR',job='Example',revision=1))
    package['module']='HR';package['physical']['members'][0]['axis']=[[0,0,0],[0,0,0]];write_json(path,package)
    with pytest.raises(ValueError,match='Invalid physical geometry'):store.import_structural('Direct',dict(module='HR',job='Example',revision=1))
    assert store.structural_current('Direct')[1]==first


def test_direct_legacy_source_remains_reference_worklines(tmp_path):
    from test_source_worklines import grouped_package
    _,path,drawings,roots=setup(tmp_path,'HR');write_json(path,grouped_package())
    store=IFCStore(drawings,roots);state=store.import_structural('Direct',dict(module='HR',job='Example'))
    assert state['representation']=='captured_source_worklines'
    report=export_structural(store.structural_current('Direct')[0],tmp_path/'axes.ifc')
    assert report['counts']['reference_axes']==16 and report['counts']['member_surfaces']==0


def test_reloading_source_recomputes_new_findings_without_mutating_old_revision(tmp_path):
    package,path,drawings,roots=setup(tmp_path,'HR')
    package['physical']['connections'][0]['parts'][0]['geometry']['origin']=[1000,0,0]
    write_json(path,package);store=IFCStore(drawings,roots)
    first=store.import_structural('Direct',dict(module='HR',job='Example'))
    folder=store.structural_current('Direct')[0]
    # Simulate a snapshot saved before these physical screens existed.
    old=dict(first,source_readiness='ready',requests=[],source_status='source_geometry')
    write_json(folder/'state.json',old);before=(folder/'state.json').read_bytes()
    fresh=store.import_structural('Direct',dict(module='HR',job='Example',revision=1))
    assert fresh['revision']==2 and fresh['source_readiness']=='needs_input'
    assert fresh['source_model_sha256']==old['source_model_sha256'] and fresh['requests']
    assert (folder/'state.json').read_bytes()==before
    assert store.import_structural('Direct',dict(module='HR',job='Example',revision=2))==fresh
