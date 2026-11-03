import copy,json
from pathlib import Path
import numpy as np
import pytest
import ifcopenshell
import ifcopenshell.api.geometry
import ifcopenshell.api.owner
import ifcopenshell.api.root
import ifcopenshell.api.unit
from fastapi import FastAPI
from fastapi.testclient import TestClient

from steltic_openbim.drawing_workflow import DrawingStore,initial_state,write_json
from steltic_openbim.ifc_export import export_drawing,export_import,schema_errors
from steltic_openbim.ifc_import import open_model,metadata,build_review,review_options
from steltic_openbim.ifc_api import router
from steltic_openbim import local_guard


def fixture_ifc(path,schema='IFC4'):
    """Independent source: millimetres, mapped extrusion and rotated local placements."""
    m=ifcopenshell.file(schema=schema)
    person=ifcopenshell.api.owner.add_person(m,identification='test',family_name='Synthetic')
    org=ifcopenshell.api.owner.add_organisation(m,identification='test',name='Synthetic fixture')
    ifcopenshell.api.owner.add_person_and_organisation(m,person=person,organisation=org)
    ifcopenshell.api.owner.add_application(m,application_developer=org,version='1',application_full_name='IFC regression fixture',application_identifier='TEST')
    project=ifcopenshell.api.root.create_entity(m,ifc_class='IfcProject',name='Millimetre source')
    unit=ifcopenshell.api.unit.add_si_unit(m,unit_type='LENGTHUNIT',prefix='MILLI')
    ifcopenshell.api.unit.assign_unit(m,units=[unit])
    ctx=ifcopenshell.api.context.add_context(m,context_type='Model')
    body=ifcopenshell.api.context.add_context(m,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=ctx)
    storey=ifcopenshell.api.root.create_entity(m,ifc_class='IfcBuildingStorey',name='Ground');storey.Elevation=0.
    ifcopenshell.api.aggregate.assign_object(m,products=[storey],relating_object=project)
    section=m.create_entity('IfcRectangleProfileDef',ProfileType='AREA',ProfileName='200x300',Position=m.create_entity('IfcAxis2Placement2D',Location=m.create_entity('IfcCartesianPoint',Coordinates=(0.,0.))),XDim=200.,YDim=300.)
    solid=m.create_entity('IfcExtrudedAreaSolid',SweptArea=section,Position=m.create_entity('IfcAxis2Placement3D',Location=m.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.))),ExtrudedDirection=m.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)),Depth=3000.)
    rep=m.create_entity('IfcShapeRepresentation',ContextOfItems=body,RepresentationIdentifier='Body',RepresentationType='SweptSolid',Items=[solid])
    mapping=m.create_entity('IfcRepresentationMap',MappingOrigin=m.create_entity('IfcAxis2Placement3D',Location=m.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.))),MappedRepresentation=rep)
    for i,cls in enumerate(('IfcColumn','IfcBeam','IfcWall')):
        e=ifcopenshell.api.root.create_entity(m,ifc_class=cls,name=cls+' fixture')
        target=m.create_entity('IfcCartesianTransformationOperator3D',LocalOrigin=m.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)),Scale=1.)
        item=m.create_entity('IfcMappedItem',MappingSource=mapping,MappingTarget=target)
        mapped=m.create_entity('IfcShapeRepresentation',ContextOfItems=body,RepresentationIdentifier='Body',RepresentationType='MappedRepresentation',Items=[item])
        ifcopenshell.api.geometry.assign_representation(m,product=e,representation=mapped)
        matrix=np.eye(4);matrix[:3,3]=[100+i*5,200,0]
        if i==1:matrix[:3,:3]=[[0,0,1],[0,1,0],[-1,0,0]]
        ifcopenshell.api.spatial.assign_container(m,products=[e],relating_structure=storey)
        ifcopenshell.api.geometry.edit_object_placement(m,product=e,matrix=matrix)
    ifcopenshell.api.root.create_entity(m,ifc_class='IfcBeam',name='No geometry supplied')
    m.write(str(path));return m


@pytest.mark.parametrize('schema',['IFC2X3','IFC4','IFC4X3'])
def test_import_mapped_rotated_geometry_units_and_missing_data(tmp_path,schema):
    path=tmp_path/'source.ifc';fixture_ifc(path,schema)
    before=path.read_bytes();meta=metadata(open_model(path))
    assert meta['units']['scale_to_m']==.001
    assert meta['counts']['products']==4
    assert {'missing_geometry','missing_storey','missing_material'}<={f['code'] for f in meta['findings']}
    result=build_review(path,{'scope':'structural','units':'auto'})
    assert result['counts']['selected']==3 and result['counts']['displayed']==2 and result['counts']['unrendered']==1
    assert result['counts']['excluded_by_scope']==1
    col=next(o for o in result['objects'] if o['ifc_class']=='IfcColumn')
    beam=next(o for o in result['objects'] if o['ifc_class']=='IfcBeam')
    assert np.allclose(col['bounds_m'],[[99.9,100.1],[199.85,200.15],[0,3]])
    assert np.allclose(beam['bounds_m'],[[105,108],[199.85,200.15],[-.1,.1]])
    assert path.read_bytes()==before


def test_units_must_be_answered_if_missing(tmp_path):
    p=tmp_path/'no-units.ifc';m=fixture_ifc(p);m.by_type('IfcProject')[0].UnitsInContext=None;m.write(str(p))
    meta=metadata(open_model(p));assert not meta['units']['known']
    with pytest.raises(ValueError,match='explicitly choose'):review_options({},meta)
    result=build_review(p,{'units':'mm'})
    assert result['bounds_m'][0][0]==pytest.approx(99.9)


def test_structural_subclasses_and_spaces_are_retained(tmp_path):
    path=tmp_path/'subclasses.ifc';m=fixture_ifc(path)
    beam=ifcopenshell.api.root.create_entity(m,ifc_class='IfcBeamStandardCase',name='Standard-case beam')
    space=ifcopenshell.api.root.create_entity(m,ifc_class='IfcSpace',name='Architectural space')
    rows=metadata(m)['products'];lookup={r['guid']:r for r in rows}
    assert lookup[beam.GlobalId]['structural'] and lookup[beam.GlobalId]['linear_structural']
    assert lookup[space.GlobalId]['ifc_class']=='IfcSpace'
    with pytest.raises(ValueError,match='options as an object'):review_options([],metadata(m))


def drawing_source(tmp_path):
    p=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())
    state=initial_state(p,1);folder=tmp_path/'drawing';folder.mkdir()
    write_json(folder/'source.json',p);write_json(folder/'state.json',state)
    return folder,p,state


def test_steltic_export_schema_roundtrip_coordinates_and_stable_ids(tmp_path):
    folder,p,state=drawing_source(tmp_path);out=tmp_path/'first.ifc'
    report=export_drawing(folder,out)
    assert not schema_errors(out) and report['counts']['members']==1 and report['counts']['member_surfaces']==1
    review=build_review(out,{'units':'auto'})
    beam=next(o for o in review['objects'] if o['ifc_class']=='IfcBeam')
    assert np.allclose(beam['bounds_m'],[[0,3.048],[-.0508,.0508],[-.1016,.1016]])
    assert beam['sections']==['TEST']
    second=export_drawing(folder,tmp_path/'second.ifc')
    assert [o['guid'] for o in report['objects']]==[o['guid'] for o in second['objects']]


def test_recovered_worklines_export_every_occurrence_without_inventing_solids(tmp_path):
    from test_source_worklines import grouped_package
    p=grouped_package();s=initial_state(p,1);s['representation']='captured_source_worklines'
    folder=tmp_path/'drawing';folder.mkdir();write_json(folder/'source.json',p);write_json(folder/'state.json',s)
    report=export_drawing(folder,tmp_path/'axes.ifc')
    assert report['counts']['members']==16 and report['counts']['reference_axes']==16
    assert report['counts']['member_surfaces']==report['counts']['connection_parts']==0
    model=build_review(tmp_path/'axes.ifc',{'units':'auto'})
    assert model['counts']['displayed']==16 and all(o['lines'] and not o['faces'] for o in model['objects'])


def test_review_export_preserves_all_source_products_and_records_notes(tmp_path):
    src=tmp_path/'source.ifc';m=fixture_ifc(src);ids={e.GlobalId for e in m.by_type('IfcProduct')}
    state=dict(revision=2,source_sha256='synthetic',status='reviewed',options={'scope':'structural','units':'auto'},review_note='Geometry reviewed; material grades TBD')
    out=tmp_path/'review.ifc';report=export_import(src,out,state)
    actual=ifcopenshell.open(str(out))
    assert ids=={e.GlobalId for e in actual.by_type('IfcProduct')}
    assert 'Geometry reviewed' in out.read_text() and report['source']=='ifc_import'


def test_ifc_api_revision_guard_history_and_failure_preserves_source(tmp_path):
    p=tmp_path/'source.ifc';fixture_ifc(p);raw=p.read_bytes()
    app=FastAPI();local_guard.install(app);app.include_router(router(DrawingStore(tmp_path/'jobs')));c=TestClient(app)
    base='/api/project/IFCTest/ifc'
    assert c.post(base+'/import',files={'file':('bad.ifc',b'not ifc')}).status_code==422
    first=c.post(base+'/import',files={'file':('source.ifc',raw)});assert first.status_code==200,first.text
    state=first.json();guard={k:state[k] for k in ('revision','source_sha256')}
    built=c.post(base+'/build',json=dict(guard,options={'scope':'structural','units':'auto'}));assert built.status_code==200,built.text
    assert c.post(base+'/build',json=dict(guard,options={})).status_code==409
    current=c.get(base).json();assert len(current['history'])==2
    assert c.get(base+'/import/file/original.ifc').content==raw
    saved=current['imported'];guard={k:saved[k] for k in ('revision','source_sha256')}
    exported=c.post(base+'/export',json=dict(guard,source='ifc_import'));assert exported.status_code==200,exported.text
    report=exported.json();assert c.get(base+'/export/'+report['key']+'/model.ifc').content.startswith(b'ISO-10303-21')
    assert c.post(base+'/import',files={'file':('bad.ifc',b'ISO-10303-21; broken')},data={'revision':saved['revision']}).status_code==422
    assert c.get(base).json()['imported']['revision']==saved['revision']
    assert c.post(base+'/review',json=dict(guard,confirm=True,note='Review only')).status_code==200
    assert c.post(base+'/build',json={},headers={'Origin':'https://other.invalid'}).status_code==403
