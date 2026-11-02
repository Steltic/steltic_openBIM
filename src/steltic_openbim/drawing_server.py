"""Hub-installable openBIM module, sharing the User-designed building query widget."""
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .drawing_workflow import DrawingStore
from .drawing_api import router
from . import local_guard

app=FastAPI(title='Steltic openBIM drawings')
local_guard.install(app)
app.include_router(router(DrawingStore(os.environ.get('OPENBIM_JOBS','openbim_jobs')),{'HR':os.environ.get('HR_JOBS'),'CFS':os.environ.get('CFS_JOBS')}))


@app.get('/healthz')
def health(): return {'ok':True}


@app.get('/',response_class=HTMLResponse)
def index():
    return '''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Steltic openBIM drawings</title>
    <style>body{font:15px/1.5 'Segoe UI',Arial;background:#f3f5ef;color:#243e43;margin:0}header,main{max-width:1180px;margin:auto;padding:24px}header{border-bottom:1px solid #ccd7ce}h1{margin:5px 0}input,select,textarea,button{font:inherit}button{cursor:pointer}a{color:#245d70}</style>
    <header><small>STELTIC / OPENBIM</small><h1>Drawings and information requests</h1><label>Project <input id="project" value="Project"></label><button id="open">Open project</button></header><main id="drawing-root"></main>
    <script src="/openbim-ui.js"></script><script>const q=new URLSearchParams(location.search),p=document.getElementById('project');p.value=q.get('project')||'Project';function openProject(){StelticDrawingQueries.mount(document.getElementById('drawing-root'),p.value)}document.getElementById('open').onclick=openProject;openProject();</script></html>'''
