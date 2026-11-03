import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from steltic_openbim.drawing_workflow import DrawingStore
from steltic_openbim.ifc_api import router
from steltic_openbim.ifc_handoff import top_surfaces
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
