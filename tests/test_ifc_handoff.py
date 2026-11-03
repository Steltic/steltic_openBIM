import json
from pathlib import Path

import pytest
import numpy as np
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
from fastapi import FastAPI
from fastapi.testclient import TestClient

from steltic_openbim.drawing_workflow import DrawingStore
from steltic_openbim.ifc_api import router
from steltic_openbim.ifc_handoff import prepare,top_surfaces
from steltic_openbim.ifc_import import build_review
from steltic_openbim.ifc_export import property_set
from test_ifc import fixture_ifc


def test_sloped_surface_preserves_shared_ridge_without_plane_rounding_drift():
    south=dict(vertices=[[0,0,7.9248],[60.96,0,7.9248],[60.96,12.192,10.9728],[0,12.192,10.9728]],faces=[[0,1,2],[0,2,3]])
    north=dict(vertices=[[0,12.192,10.9728],[60.96,12.192,10.9728],[60.96,24.384,7.9248],[0,24.384,7.9248]],faces=[[0,1,2],[0,2,3]])
    for obj in (south,north):
        result=top_surfaces(obj)
        assert len(result)==1
        ridge=[p for p in result[0]['boundary_m'] if p[1]==12.192]
        assert len(ridge)==2 and all(p[2]==10.9728 for p in ridge)


def test_handoff_requires_built_current_revision_and_preserves_source(tmp_path):
    src=tmp_path/'source.ifc';fixture_ifc(src);raw=src.read_bytes()
    app=FastAPI();app.include_router(router(DrawingStore(tmp_path/'jobs')));client=TestClient(app);url='/api/project/demo/ifc'
    s=client.post(url+'/import',files={'file':('source.ifc',raw)}).json()
    guard={k:s[k] for k in ('revision','source_sha256')}
    assert client.post(url+'/handoff',json=dict(guard,brief='Office')).status_code==422
    s=client.post(url+'/build',json=dict(guard,options={})).json()
    assert client.post(url+'/handoff',json=dict(guard,brief='Office')).status_code==409
    guard={k:s[k] for k in ('revision','source_sha256')}
    assert client.post(url+'/handoff',json=dict(guard,brief='')).status_code==422
    r=client.post(url+'/handoff',json=dict(guard,brief='Office; HR selects all member sections.'))
    assert r.status_code==200,r.text
    key=r.json()['key'];brief=client.get(url+'/handoff/'+key+'/hr_brief.txt').text
    g=client.get(url+'/handoff/'+key+'/architectural_geometry.json').json()
    assert s['source_sha256'] in brief and 'Office; HR selects' in brief
    assert g['structural_members_inferred'] is False and g['warnings']
    assert client.get(url+'/import/file/original.ifc').content==raw
    assert client.get(url).json()['imported']['revision']==s['revision']


def test_cfs_handoff_routes_the_brief_and_preserves_legacy_hr_downloads(tmp_path):
    src=tmp_path/'source.ifc';fixture_ifc(src)
    app=FastAPI();app.include_router(router(DrawingStore(tmp_path/'jobs')))
    client=TestClient(app);url='/api/project/demo/ifc'
    state=client.post(url+'/import',files={'file':('source.ifc',src.read_bytes())}).json()
    guard=lambda s:{k:s[k] for k in ('revision','source_sha256')}
    state=client.post(url+'/build',json=dict(guard(state),options={})).json()
    assert client.post(url+'/handoff',json=dict(guard(state),target_module='OTHER',brief='Wall building')).status_code==422
    response=client.post(url+'/handoff',json=dict(guard(state),target_module='CFS',brief='CFS wall building; design all studs and connections.'))
    assert response.status_code==200,response.text
    summary=response.json();prefix=url+'/handoff/'+summary['key']
    assert summary['target_module']=='CFS' and summary['brief_filename']=='cfs_brief.txt'
    brief=client.get(prefix+'/cfs_brief.txt')
    assert brief.status_code==200 and brief.text.startswith('CFS DESIGN FROM AN ARCHITECTURAL IFC')
    assert 'normal CFS BIM export' in brief.text and 'normal HR BIM export' not in brief.text
    assert client.get(prefix+'/hr_brief.txt').status_code==404
    geometry=client.get(prefix+'/architectural_geometry.json').json()
    assert geometry['target_module']=='CFS' and len(geometry['walls'])==1
    current=client.get(url).json()
    assert current['target_module']=='CFS' and current['design_brief'].startswith('CFS wall building')
    # Existing callers that omit the module still receive the unchanged HR route.
    legacy=client.post(url+'/handoff',json=dict(guard(state),brief='HR office')).json()
    assert client.get(url+'/handoff/'+legacy['key']+'/hr_brief.txt').status_code==200


@pytest.mark.parametrize('units,factor',[('auto',1.),('in',25.4)])
def test_bearing_wall_axes_and_opening_hosts_use_source_placements(tmp_path,units,factor):
    src=tmp_path/'walls.ifc';model=fixture_ifc(src)
    wall=model.by_type('IfcWall')[0]
    property_set(model,wall,{'LoadBearing':True,'IsExternal':False},name='Pset_WallCommon')
    ctx=model.by_type('IfcGeometricRepresentationContext')[0]
    points=[model.create_entity('IfcCartesianPoint',Coordinates=coords) for coords in ((0.,0.),(4000.,0.))]
    line=model.create_entity('IfcPolyline',Points=points)
    rep=model.create_entity('IfcShapeRepresentation',ContextOfItems=ctx,RepresentationIdentifier='Axis',RepresentationType='Curve2D',Items=[line])
    wall.Representation.Representations=tuple(wall.Representation.Representations)+(rep,)
    matrix=np.eye(4);matrix[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]];matrix[:3,3]=[110,200,0]
    ifcopenshell.api.geometry.edit_object_placement(model,product=wall,matrix=matrix)
    door=ifcopenshell.api.root.create_entity(model,ifc_class='IfcDoor',name='Door in bearing wall')
    opening=ifcopenshell.api.root.create_entity(model,ifc_class='IfcOpeningElement',name='Door void')
    door.Representation=wall.Representation;door.ObjectPlacement=wall.ObjectPlacement
    opening.ObjectPlacement=wall.ObjectPlacement
    ifcopenshell.api.feature.add_feature(model,feature=opening,element=wall)
    ifcopenshell.api.feature.add_filling(model,opening=opening,element=door)
    model.write(str(src))
    review=build_review(src,{'units':units})
    geometry,_=prepare(src,review,dict(filename='walls.ifc',source_sha256='fixture',revision=2),'CFS residential design','CFS')
    w=geometry['walls'][0]
    assert w['load_bearing'] is True and w['is_external'] is False
    assert np.allclose(w['reference_axes_m'],np.array([[[110,200,0],[110,204,0]]])*factor)
    assert geometry['doors_windows'][0]['host_wall_guids']==[wall.GlobalId]
    structural=build_review(src,{'scope':'structural'})
    assert wall.GlobalId in {obj['guid'] for obj in structural['objects']}
