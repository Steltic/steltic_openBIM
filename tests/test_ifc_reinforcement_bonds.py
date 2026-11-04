import json
import math

import ifcopenshell
import ifcopenshell.util.element
import pytest

from test_bim_reinforcement_bonds import fixture
from test_ifc import drawing_source
from steltic_openbim.drawing_workflow import write_json
from steltic_openbim.ifc_export import export_drawing, export_import, schema_errors
from steltic_openbim.ifc_import import build_review


@pytest.mark.parametrize('kind',['reinforcement_bond_development','reinforcement_bond_lap'])
def test_ifc_keeps_bond_curves_and_typed_concrete_host_without_fabricated_hardware(tmp_path,kind):
    folder,package,state=drawing_source(tmp_path)
    physical=fixture(kind)
    # Deliberately collide the member and panel IDs: references remain typed.
    physical['panels'][0]['id']='bar0'
    physical['connections'][0]['assembly_instance']['bindings']['HOST']='bar0'
    write_json(folder/'design_model.json',physical)
    path=tmp_path/'bond.ifc';report=export_drawing(folder,path)
    assert report['schema_errors']==[] and report['counts']['connection_parts']==0
    assert report['counts']['connection_assemblies']==1
    model=ifcopenshell.open(str(path))
    assembly=model.by_type('IfcElementAssembly')[0]
    links=[r for r in model.by_type('IfcRelConnectsElements') if r.RelatingElement==assembly]
    assert len(links)==(3 if kind.endswith('lap') else 2)
    assert sum(r.RelatedElement.is_a('IfcSlab') for r in links)==1
    assert len({r.GlobalId for r in links})==len(links)
    props=ifcopenshell.util.element.get_psets(assembly)['Steltic_Coordination']
    assert props['GeometryRole']=='reinforcement_bond_reference'
    assert json.loads(props['ConnectedPanels'])==['bar0']
    project=ifcopenshell.util.element.get_psets(model.by_type('IfcProject')[0])['Steltic_Coordination']
    assert json.loads(project['AssemblyTemplates'])==physical['assemblies']
    review=build_review(path,dict(units='auto',scope='all'))
    obj=next(o for o in review['objects'] if o['ifc_class']=='IfcElementAssembly')
    lengths=[math.dist(line[0],line[-1])/.0254 for line in obj['lines']]
    assert sorted(lengths)==pytest.approx([25,25] if kind.endswith('lap') else [40])
    returned=tmp_path/'returned.ifc'
    export_import(path,returned,dict(options={},source_sha256=report['sha256'],revision=1,status='reviewed'))
    assert schema_errors(returned)==[]
    again=ifcopenshell.open(str(returned))
    assert {r.GlobalId for r in again.by_type('IfcRelConnectsElements')}=={r.GlobalId for r in links}
    returned_props=ifcopenshell.util.element.get_psets(again.by_type('IfcProject')[0])['Steltic_Coordination']
    assert returned_props['AssemblyTemplates']==project['AssemblyTemplates']
