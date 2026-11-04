import pytest
import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.api.aggregate
import ifcopenshell.api.spatial

from test_ifc import fixture_ifc
from steltic_openbim import ifc_import
from steltic_openbim.ifc_export import export_import
from steltic_openbim.ifc_handoff import prepare


def fixture(path):
    model=fixture_ifc(path);ground=model.by_type('IfcBuildingStorey')[0]
    upper=ifcopenshell.api.root.create_entity(model,ifc_class='IfcBuildingStorey',name='Upper')
    ifcopenshell.api.aggregate.assign_object(model,products=[upper],relating_object=model.by_type('IfcProject')[0])
    ifcopenshell.api.spatial.assign_container(model,products=[model.by_type('IfcBeam')[0]],relating_structure=upper)
    ifcopenshell.api.spatial.unassign_container(model,products=model.by_type('IfcWall'))
    model.write(str(path));return model,ground.GlobalId,upper.GlobalId


def test_bounded_storey_reviews_cover_every_product_and_return_the_full_graph(tmp_path,monkeypatch):
    path=tmp_path/'source.ifc';model,ground,upper=fixture(path);source=path.read_bytes()
    graph={e.id():e.to_string() for e in model};expected={r.GlobalId for r in ifc_import.products(model)}
    monkeypatch.setattr(ifc_import,'MAX_TRIANGLES',12)
    with pytest.raises(ValueError,match='choose one storey'):
        ifc_import.build_review(path,{'scope':'all'})
    seen=set()
    for selected in (ground,upper,'unassigned'):
        review=ifc_import.build_review(path,{'scope':'all','storey':selected})
        ids={o['guid'] for o in review['objects']+review['unrendered']}
        assert not ids&seen;seen|=ids
        assert review['counts']['triangles']==12
        assert review['counts']['selected']==len(ids)
        assert review['counts']['source_products']==len(expected)
        assert review['options']['storey']==selected
    assert seen==expected and path.read_bytes()==source
    batches=list(ifc_import.iter_storey_reviews(path,dict(scope='all')))
    assert len(batches)==3
    assert sum(r['counts']['selected'] for r in batches)==len(expected)
    assert {o['guid'] for r in batches for o in r['objects']+r['unrendered']}==expected
    output=tmp_path/'returned.ifc'
    report=export_import(path,output,dict(source_sha256='fixture',revision=1,status='reviewed',options=review['options']))
    assert report['schema_errors']==[]
    returned=ifcopenshell.open(str(output))
    assert all(returned.by_id(ident).to_string()==line for ident,line in graph.items())


@pytest.mark.parametrize('selected',['missing-guid',None,False,[],{}])
def test_unknown_or_malformed_storey_cannot_silently_select_all(tmp_path,selected):
    path=tmp_path/'source.ifc';model,_,_=fixture(path)
    with pytest.raises(ValueError,match='storey'):
        ifc_import.review_options(dict(storey=selected),ifc_import.metadata(model))


def test_storey_limited_design_handoff_discloses_its_partial_scope(tmp_path):
    path=tmp_path/'source.ifc';_,ground,_=fixture(path)
    review=ifc_import.build_review(path,dict(storey=ground))
    geometry,brief=prepare(path,review,dict(filename='source.ifc',source_sha256='fixture',revision=1),'Example brief')
    assert any('only the selected storey' in text for text in geometry['warnings'])
    assert 'outside this design handoff' in brief


def test_large_storey_splits_into_disjoint_groups_without_relaxing_limits(tmp_path,monkeypatch):
    path=tmp_path/'source.ifc';model,ground,_=fixture(path);original=model.by_type('IfcColumn')[0]
    for n in range(2):
        extra=ifcopenshell.api.root.create_entity(model,ifc_class='IfcColumn',name='Extra '+str(n))
        extra.Representation=original.Representation;extra.ObjectPlacement=original.ObjectPlacement
        ifcopenshell.api.spatial.assign_container(model,products=[extra],relating_structure=model.by_guid(ground))
    model.write(str(path))
    monkeypatch.setattr(ifc_import,'REVIEW_GROUP_SIZE',2);monkeypatch.setattr(ifc_import,'MAX_TRIANGLES',24)
    with pytest.raises(ValueError,match='numbered review group'):
        ifc_import.build_review(path,dict(storey=ground))
    batches=list(ifc_import.iter_storey_reviews(path,{}))
    assert len(batches)==4
    seen=[]
    for batch in batches:
        assert batch['counts']['triangles']<=24
        seen.extend(o['guid'] for o in batch['objects']+batch['unrendered'])
    assert len(seen)==len(set(seen))==len(ifc_import.products(model))
    last=ifc_import.build_review(path,dict(storey=ground,group=2))
    assert last['counts']['selected']==1 and last['counts']['review_groups']==2
    geometry,brief=prepare(path,last,dict(filename='source.ifc',source_sha256='fixture',revision=1),'Example brief')
    assert 'only the selected numbered review group' in brief
    with pytest.raises(ValueError,match='outside'):
        ifc_import.build_review(path,dict(storey=ground,group=3))
