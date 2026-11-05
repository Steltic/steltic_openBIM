"""Large-model limits must retain complete geometry or reject the build."""
import numpy as np
import pytest
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.api.geometry
import ifcopenshell.api.root

from steltic_openbim import ifc_import
from test_ifc import fixture_ifc


def test_more_than_twenty_thousand_products_can_be_opened(tmp_path):
    model=ifcopenshell.file(schema='IFC4')
    model.create_entity('IfcProject',GlobalId=ifcopenshell.guid.new())
    for i in range(20001):
        model.create_entity('IfcBuildingElementProxy',GlobalId=ifcopenshell.guid.new(),Name=str(i))
    path=tmp_path/'many.ifc';model.write(str(path))
    assert len(ifc_import.open_model(path).by_type('IfcProduct'))==20001


def test_complete_detailed_building_above_old_hundred_thousand_limit_opens(tmp_path):
    model=ifcopenshell.file(schema='IFC4')
    model.create_entity('IfcProject',GlobalId=ifcopenshell.guid.new())
    for i in range(100001):
        model.create_entity('IfcElementAssembly',GlobalId=ifcopenshell.guid.new(),Name=str(i))
    path=tmp_path/'complete.ifc';model.write(str(path))
    assert len(ifc_import.open_model(path).by_type('IfcProduct'))==100001


def test_product_limit_rejects_before_review(tmp_path,monkeypatch):
    path=tmp_path/'source.ifc';model=fixture_ifc(path)
    monkeypatch.setattr(ifc_import,'MAX_PRODUCTS',len(model.by_type('IfcProduct'))-1)
    with pytest.raises(ValueError,match='products'):
        ifc_import.open_model(path)


def test_triangle_limit_rejects_instead_of_publishing_a_partial_model(tmp_path,monkeypatch):
    path=tmp_path/'source.ifc';fixture_ifc(path)
    monkeypatch.setattr(ifc_import,'MAX_TRIANGLES',12)
    with pytest.raises(ValueError,match='Review exceeds 12 triangles'):
        ifc_import.build_review(path,{'scope':'all','units':'auto'})


def test_batched_geometry_keeps_per_product_placements_and_opening_cuts(tmp_path):
    path=tmp_path/'source.ifc';model=fixture_ifc(path)
    column=model.by_type('IfcColumn')[0]
    opening=ifcopenshell.api.root.create_entity(model,ifc_class='IfcOpeningElement',name='Column test cut')
    context=column.Representation.Representations[0].ContextOfItems
    representation=ifcopenshell.api.geometry.add_wall_representation(model,context=context,length=.4,height=.5,thickness=.4)
    ifcopenshell.api.geometry.assign_representation(model,product=opening,representation=representation)
    matrix=np.eye(4);matrix[:3,3]=[99.8,199.8,1.]
    ifcopenshell.api.geometry.edit_object_placement(model,product=opening,matrix=matrix)
    model.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=column,RelatedOpeningElement=opening)
    model.write(str(path))
    review=ifc_import.build_review(path,{'scope':'all','units':'auto'})
    settings=ifcopenshell.geom.settings();settings.set('use-world-coords',True)
    settings.set('mesher-linear-deflection',.002)
    for obj in review['objects']:
        shape=ifcopenshell.geom.create_shape(settings,model.by_id(int(obj['id'])))
        expected=np.asarray(shape.geometry.verts).reshape((-1,3))
        actual=np.asarray(obj['vertices'])
        assert actual.shape==expected.shape
        assert np.allclose(actual,expected)
        assert obj['faces']==np.asarray(shape.geometry.faces).reshape((-1,3)).tolist()
    cut=next(o for o in review['objects'] if o['guid']==column.GlobalId)
    assert len(cut['faces'])>12


def test_iterator_failure_falls_back_without_dropping_source_objects(tmp_path,monkeypatch):
    path=tmp_path/'source.ifc';fixture_ifc(path)
    expected=ifc_import.build_review(path,{'scope':'all','units':'auto'})
    class BrokenIterator:
        def __init__(self,*args,**kwargs):pass
        def initialize(self):raise RuntimeError('Synthetic native iterator failure')
    monkeypatch.setattr(ifc_import.ifcopenshell.geom,'iterator',BrokenIterator)
    actual=ifc_import.build_review(path,{'scope':'all','units':'auto'})
    assert actual==expected
