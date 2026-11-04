"""Send physical answers to the imported native job, using its module API."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter,HTTPException,Request
from fastapi.concurrency import run_in_threadpool

from .drawing_workflow import fingerprint,name,StaleRevision


def router(store,jobs,service_urls):
    routes=APIRouter()
    services={k:str(v).rstrip('/') for k,v in (service_urls or {}).items() if v}

    def source(project):
        current=store.current(project)
        if current is None:raise HTTPException(404,'Import a native job first')
        state=current[1];binding=state.get('native_source')
        if not binding:raise HTTPException(404,'Choose a job export to connect its native information requests')
        module,job=binding['module'],name(binding['job'])
        if module not in services:raise HTTPException(503,'Start the updated '+module+' module to answer its information requests')
        # Validate configured root and job identity; uploaded JSON cannot choose a URL.
        jobs.path(module,job)
        return state,module,job

    def native(module,job,method,operation,body=None):
        # Hub starts its local modules with one per-launch secret. Never forward
        # browser headers/cookies, or send that local secret to a remote service.
        headers={}
        if urlsplit(services[module]).hostname in ('127.0.0.1','localhost','::1'):
            token=os.environ.get('STELTIC_HUB_TOKEN')
            if token:headers['X-Steltic-Hub-Token']=token
        try:
            with httpx.Client(timeout=httpx.Timeout(180,connect=10)) as client:
                response=client.request(method,services[module]+'/api/physical/'+job+'/'+operation,json=body,headers=headers)
        except httpx.HTTPError as ex:raise HTTPException(502,'The '+module+' module did not answer; your existing drawings remain available') from ex
        try:value=response.json()
        except ValueError:raise HTTPException(502,'Native module returned an unexpected response') from None
        if response.status_code>=400:raise HTTPException(response.status_code,value.get('detail','Native request failed'))
        return value

    @routes.get('/api/project/{p}/drawings/native-requests')
    def register(p:str):
        state,module,job=source(p)
        return dict(native(module,job,'GET','requests'),module=module,job=job,drawing_revision=state['revision'])

    @routes.post('/api/project/{p}/drawings/native-answers')
    async def answer(p:str,request:Request):
        raw=await request.body()
        if len(raw)>2*1024*1024:raise HTTPException(413,'Decision exceeds 2 MB')
        try:body=json.loads(raw)
        except ValueError:raise HTTPException(422,'Provide a decision object') from None
        if not isinstance(body,dict):raise HTTPException(422,'Provide a decision object')
        def update():
            # The native revision/hash independently protects concurrent Hub/module
            # edits. A drawing publication conflict never loses the saved answer.
            state,module,job=source(p)
            if body.get('drawing_revision')!=state['revision']:raise HTTPException(409,'Refresh drawings before answering')
            decision={k:v for k,v in body.items() if k!='drawing_revision'}
            saved=native(module,job,'POST','answers',decision)
            try:
                native(module,job,'POST','replay',dict(expected_revision=saved['revision'],expected_sha256=saved['sha256']))
                package,_=jobs.load_current(module,job)
                updated=store.import_package(p,package,state['revision'],native_source=dict(module=module,job=job))
            except (HTTPException,ValueError,StaleRevision) as ex:
                return dict(saved=True,native_revision=saved['revision'],drawings_updated=False,
                            message='Answer saved in '+module+'. '+str(getattr(ex,'detail',str(ex))))
            return dict(saved=True,native_revision=saved['revision'],drawings_updated=True,drawing_revision=updated['revision'])
        return await run_in_threadpool(update)

    return routes
