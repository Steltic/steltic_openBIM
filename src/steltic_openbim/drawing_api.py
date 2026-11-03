"""Shared local API mounted by Hub's existing query UI and the openBIM module."""
import json
from pathlib import Path

from fastapi import APIRouter,HTTPException,Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse,Response

from .drawing_workflow import DrawingStore,StaleRevision,name


def router(store:DrawingStore,source_roots=None):
    r=APIRouter(); roots={k:Path(v).resolve() for k,v in (source_roots or {}).items() if v}

    def source_path(module,job):
        if module not in roots: raise ValueError('Source module is not configured')
        folder=(roots[module]/name(job)).resolve()
        if not folder.is_relative_to(roots[module]): raise ValueError('Invalid source job path')
        for rel in ('design/bim_package.json','bim_package.json'):
            p=(folder/rel).resolve()
            if p.is_relative_to(folder) and p.is_file(): return p
        raise ValueError('No physical export exists for this job yet')

    def invoke(fn,*args):
        try: return fn(*args)
        except StaleRevision as ex: raise HTTPException(409,str(ex))
        except (ValueError,KeyError,TypeError) as ex: raise HTTPException(422,str(ex))

    def json_object(raw):
        value=json.loads(raw)
        if not isinstance(value,dict): raise ValueError('Provide a JSON object')
        return value

    async def body_object(request):
        return invoke(json_object,await request.body())

    @r.get('/api/drawings/sources')
    def sources():
        out=[]
        for module,root in roots.items():
            if not root.is_dir(): continue
            for folder in sorted(root.iterdir()):
                if not folder.is_dir(): continue
                try: source_path(module,folder.name)
                except ValueError: continue
                out.append(dict(module=module,job=folder.name))
        return {'sources':out}

    @r.get('/api/project/{p}/drawings')
    def state(p:str):
        current=invoke(store.current,p)
        if current is None: return {'state':'none','can_generate':False}
        state=current[1]
        from .design_scenarios import SCENARIOS
        scenario=next((key for key,value in SCENARIOS.items() if value['source_sha256']==state['source_model_sha256']),None)
        return dict(state,state='available',questions=store.questions(state),available_test_scenario=scenario)

    @r.post('/api/project/{p}/drawings/import')
    async def import_source(p:str,request:Request):
        body=await body_object(request)
        path=invoke(source_path,body.get('module'),body.get('job'))
        package=invoke(json_object,path.read_bytes())
        return await run_in_threadpool(invoke,store.import_package,p,package,body.get('revision'))

    @r.post('/api/project/{p}/drawings/upload')
    async def upload(p:str,request:Request):
        form=await request.form(); file=form.get('file')
        if file is None or not hasattr(file,'read'): raise HTTPException(400,'Choose a physical package JSON file')
        raw=await file.read(100*1024*1024+1)
        if len(raw)>100*1024*1024: raise HTTPException(413,'Physical package exceeds 100 MB')
        package=invoke(json_object,raw)
        revision=form.get('revision'); revision=invoke(int,revision) if revision else None
        return await run_in_threadpool(invoke,store.import_package,p,package,revision)

    @r.post('/api/project/{p}/drawings/answers')
    async def answers(p:str,request:Request):
        body=await body_object(request)
        return await run_in_threadpool(invoke,store.answer,p,body)

    @r.post('/api/project/{p}/drawings/fictional-design')
    async def fictional_design(p:str,request:Request):
        body=await body_object(request)
        return await run_in_threadpool(invoke,store.fictional_design,p,body)

    @r.get('/api/project/{p}/drawings/history')
    def history(p:str):
        base=invoke(store.project,p); rows=[]
        for f in sorted((base/'revisions').glob('*/state.json')):
            state=json.loads(f.read_text(encoding='utf-8'))
            rows.append(dict(revision=state['revision'],directory=f.parent.name,drawing_status=state['drawing_status'],source_model_sha256=state['source_model_sha256']))
        return {'revisions':rows}

    @r.post('/api/project/{p}/drawings/regenerate')
    async def regenerate(p:str,request:Request):
        body=await body_object(request)
        return await run_in_threadpool(invoke,store.regenerate,p,body)

    @r.get('/api/project/{p}/drawings/file/{filename}')
    def file(p:str,filename:str,revision:str=''):
        if filename not in ('drawings.pdf','drawing_manifest.json','information_requests.json','design_model.json','member_index.json','connection_index.json','source_records.json','adopted_answers.json','connection_assemblies.json','source_workline_model.json'): raise HTTPException(404)
        current=invoke(store.current,p)
        if current is None: raise HTTPException(404)
        directory=current[0]
        if revision:
            import re
            if not re.fullmatch(r'r\d{4,}-[a-f0-9]{12}',revision): raise HTTPException(404)
            directory=store.project(p)/'revisions'/revision
            if not (directory/'state.json').is_file(): raise HTTPException(404)
        if not (directory/filename).is_file():raise HTTPException(404)
        return FileResponse(directory/filename,media_type='application/pdf' if filename.endswith('.pdf') else 'application/json',headers={'Cache-Control':'no-store'})

    @r.get('/openbim-ui.js')
    def script(): return Response(Path(__file__).with_name('drawing_ui.js').read_text(encoding='utf-8'),media_type='text/javascript',headers={'Cache-Control':'no-cache'})
    return r
