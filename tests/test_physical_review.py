import copy
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.pset
import ifcopenshell.util.element
import pytest

from steltic_openbim.drawing_workflow import initial_state, write_json
from steltic_openbim.ifc_export import export_drawing
from steltic_openbim.ifc_import import build_review, metadata
from steltic_openbim.physical_review import review_physical


def package():
    return json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())


@pytest.mark.parametrize('name', ['6xCHANNEL', 'box-6xCHANNEL'])
def test_named_plies_count_each_constituent_without_inventing_a_pair(name):
    physical=dict(profiles=[dict(id=name,family='built_up',components=[
        dict(profile_id='CHANNEL',offset=[i*3,0],rotation_deg=0) for i in range(3)])])
    before=copy.deepcopy(physical)
    result=review_physical(physical)
    assert result['status']=='needs_review' and not result['structural_design_approval']
    assert result['findings'][0]['examples'][0]['named_count']==6
    assert result['findings'][0]['examples'][0]['component_count']==3
    assert physical==before
    physical['profiles'][0]['components']*=2
    assert not review_physical(physical)['findings']


def test_arbitrary_names_and_mixed_components_do_not_establish_a_ply_count():
    physical=dict(profiles=[dict(id='6xCHANNEL',family='built_up',components=[dict(profile_id='OTHER')]),
                            dict(id='FRAME-A',family='built_up',components=[dict(profile_id='CHANNEL')])])
    assert not review_physical(physical)['findings']


def test_remote_connection_uses_transformed_part_bounds_not_only_origin():
    physical=package()['physical']
    geometry=physical['connections'][0]['parts'][0]['geometry']
    geometry.update(origin=[0,-100,0],size=[200,1,1],x_axis=[0,1,0],y_axis=[-1,0,0])
    assert not review_physical(physical)['findings']  # Long rotated part reaches the joint.
    geometry['origin']=[0,-1000,0]
    result=review_physical(physical)
    assert result['findings'][0]['code']=='physical_remote_part'


def test_physical_findings_survive_ifc_export_and_reimport_without_moving_objects(tmp_path):
    p=package();ph=p['physical']
    ph['connections'][0]['parts'][0]['geometry']['origin']=[1200,0,0]
    ph['panels']=[dict(id='wall',kind='wall',status='declared',material_id='steel',thickness=.5,
                       vertices=[[0,0,0],[120,0,0],[120,0,120],[0,0,120]])]
    ph['openings']=[dict(id='door',host_id='wall',vertices=[[150,0,0],[180,0,0],[180,0,84],[150,0,84]])]
    folder=tmp_path/'source';folder.mkdir()
    write_json(folder/'source.json',p);write_json(folder/'state.json',initial_state(p,1))
    before=(folder/'source.json').read_bytes()
    out=tmp_path/'return.ifc';report=export_drawing(folder,out)
    assert not report['schema_errors']
    assert {f['code'] for f in report['physical_checks']['findings']}=={'physical_opening_host','physical_remote_part'}
    model=ifcopenshell.open(str(out))
    checks=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_PhysicalChecks']
    assert not checks['StructuralDesignApproval']
    assert json.loads(checks['Findings'])==report['physical_checks']['findings']
    review=build_review(out,{'units':'auto','scope':'all'})
    assert {'declared_physical_opening_host','declared_physical_remote_part'}<={f['code'] for f in review['checks']}
    part=next(o for o in review['objects'] if o['ifc_class']=='IfcPlate')
    assert part['bounds_m'][0][0]==pytest.approx(1200*.0254)
    assert (folder/'source.json').read_bytes()==before


@pytest.mark.parametrize('raw', ['not JSON', '{}', '[null]', '[{"title":"bad","count":true}]'])
def test_malformed_source_findings_do_not_break_import(tmp_path,raw):
    p=package();folder=tmp_path/'source';folder.mkdir()
    write_json(folder/'source.json',p);write_json(folder/'state.json',initial_state(p,1))
    out=tmp_path/'source.ifc';export_drawing(folder,out);model=ifcopenshell.open(str(out))
    project=model.by_type('IfcProject')[0]
    pset=next(r.RelatingPropertyDefinition for r in project.IsDefinedBy if r.RelatingPropertyDefinition.Name=='Steltic_PhysicalChecks')
    ifcopenshell.api.pset.edit_pset(model,pset=pset,properties={'Findings':raw})
    assert 'physical_checks_unreadable' in {f['code'] for f in metadata(model)['findings']}
