"""Hub-installable openBIM module, sharing the User-designed building query widget."""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse,Response
from .drawing_workflow import DrawingStore
from .drawing_api import router
from . import local_guard

app=FastAPI(title='Steltic openBIM drawings')
local_guard.install(app)
store=DrawingStore(os.environ.get('OPENBIM_JOBS','openbim_jobs'))
app.include_router(router(store,{'HR':os.environ.get('HR_JOBS'),'CFS':os.environ.get('CFS_JOBS')}))
from .ifc_api import router as ifc_router
app.include_router(ifc_router(store))


@app.get('/healthz')
def health(): return {'ok':True}


@app.get('/',response_class=HTMLResponse)
def index():
    return page('Steltic import','steltic')


@app.get('/ifc-import',response_class=HTMLResponse)
def ifc_import_page():return page('IFC import','import')


@app.get('/ifc-export',response_class=HTMLResponse)
def ifc_export_page():return page('IFC export','export')


@app.get('/ifc-ui.js')
def ifc_script():return asset('ifc_ui.js','text/javascript')


@app.get('/ifc-viewer.js')
def ifc_viewer():return asset('ifc_viewer.js','text/javascript')


@app.get('/ifc-ui.css')
def ifc_style():return asset('ifc_ui.css','text/css')


def asset(filename,media_type):
    return Response(Path(__file__).with_name(filename).read_text(encoding='utf-8'),media_type=media_type,headers={'Cache-Control':'no-cache'})


def page(title,mode):
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Steltic openBIM - TITLE</title>
    <link rel="stylesheet" href="/ifc-ui.css"><header><small>STELTIC / OPENBIM</small><h1>TITLE</h1><label>Project <input id="project" value="Project"></label> <button id="open">Open project</button>
    <nav aria-label="openBIM workflow"><a data-mode="steltic" href="/">Steltic import</a><a data-mode="import" href="/ifc-import">IFC import</a><a data-mode="export" href="/ifc-export">IFC export</a></nav></header><main id="drawing-root"></main>
    <script src="/openbim-ui.js"></script><script src="/ifc-viewer.js"></script><script src="/ifc-ui.js"></script>
    <script>const mode='MODE',q=new URLSearchParams(location.search),p=document.getElementById('project');p.value=q.get('project')||'Project';function openProject(){for(const a of document.querySelectorAll('nav a')){a.href=a.pathname+'?project='+encodeURIComponent(p.value);if(a.dataset.mode===mode)a.setAttribute('aria-current','page')}const root=document.getElementById('drawing-root');if(mode==='steltic')StelticDrawingQueries.mount(root,p.value);else StelticIFC.mount(root,p.value,mode)}document.getElementById('open').onclick=openProject;openProject();</script></html>'''.replace('TITLE',title).replace('MODE',mode)
