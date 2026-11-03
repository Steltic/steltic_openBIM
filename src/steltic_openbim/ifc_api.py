"""Local IFC upload, review and export endpoints."""
import re
from fastapi import APIRouter,HTTPException,Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .drawing_workflow import StaleRevision
from .ifc_store import IFCStore,MAX_FILE


def router(drawings):
    r=APIRouter();store=IFCStore(drawings)
    def invoke(fn,*args):
        try:return fn(*args)
        except StaleRevision as ex:raise HTTPException(409,str(ex)) from ex
        except (ValueError,KeyError,TypeError) as ex:raise HTTPException(422,str(ex)) from ex
    async def body(request):
        try:value=await request.json()
        except ValueError:raise HTTPException(422,'Provide a JSON object')
        if not isinstance(value,dict):raise HTTPException(422,'Provide a JSON object')
        return value

    @r.get('/api/project/{p}/ifc')
    def state(p):return invoke(store.state,p)

    @r.post('/api/project/{p}/ifc/import')
    async def upload(p,request:Request):
        form=await request.form();file=form.get('file')
        if file is None or not hasattr(file,'read'):raise HTTPException(422,'Choose an IFC file')
        raw=await file.read(MAX_FILE+1)
        if len(raw)>MAX_FILE:raise HTTPException(413,'IFC exceeds 100 MB')
        revision=form.get('revision');revision=invoke(int,revision) if revision else None
        return await run_in_threadpool(invoke,store.upload,p,file.filename,raw,revision)

    @r.post('/api/project/{p}/ifc/build')
    async def build(p,request:Request):return await run_in_threadpool(invoke,store.build,p,await body(request))

    @r.post('/api/project/{p}/ifc/review')
    async def review(p,request:Request):return await run_in_threadpool(invoke,store.review,p,await body(request))

    @r.post('/api/project/{p}/ifc/export')
    async def export(p,request:Request):return await run_in_threadpool(invoke,store.export,p,await body(request))

    @r.post('/api/project/{p}/ifc/handoff')
    async def handoff(p,request:Request):return await run_in_threadpool(invoke,store.handoff,p,await body(request))

    @r.get('/api/project/{p}/ifc/handoff/{key}/{filename}')
    def handoff_file(p,key,filename):
        if not re.fullmatch(r'h-[a-f0-9]{32}',key) or filename not in ('hr_brief.txt','architectural_geometry.json'):raise HTTPException(404)
        path=invoke(store.root,p)/'handoffs'/key/filename
        if not path.is_file() or not (path.parent/'summary.json').is_file():raise HTTPException(404)
        return FileResponse(path,filename=filename,media_type='text/plain' if filename.endswith('.txt') else 'application/json',headers={'Cache-Control':'no-store'})

    @r.get('/api/project/{p}/ifc/import/file/{filename}')
    def imported_file(p,filename,revision:str=''):
        if filename not in ('original.ifc','inspection.json','model.json'):raise HTTPException(404)
        current=invoke(store.current,p)
        if current is None:raise HTTPException(404)
        directory=current[0]
        if revision:
            if not re.fullmatch(r'r\d{4,}-[a-f0-9]{12}',revision):raise HTTPException(404)
            directory=store.root(p)/'imports'/revision
            if not (directory/'state.json').is_file():raise HTTPException(404)
        path=directory/filename
        if not path.is_file():raise HTTPException(404)
        return FileResponse(path,media_type='application/json' if filename.endswith('.json') else 'application/x-step',headers={'Cache-Control':'no-store'})

    @r.get('/api/project/{p}/ifc/export/{key}/{filename}')
    def exported_file(p,key,filename):
        if not re.fullmatch(r'e-[a-f0-9]{32}',key) or filename not in ('model.ifc','report.json'):raise HTTPException(404)
        path=invoke(store.root,p)/'exports'/key/filename
        if not path.is_file() or not (path.parent/'report.json').is_file():raise HTTPException(404)
        return FileResponse(path,filename=p+'.ifc' if filename.endswith('.ifc') else filename,
                            media_type='application/x-step' if filename.endswith('.ifc') else 'application/json',headers={'Cache-Control':'no-store'})
    return r
