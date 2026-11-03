"""Immutable IFC source/review revisions, with the drawing store's project lock."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from .drawing_workflow import StaleRevision,write_json

MAX_FILE=100*1024*1024


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def worker(action,source,output,*args):
    cmd=[sys.executable,'-m','steltic_openbim.ifc_worker',action,str(source),str(output),*[str(a) for a in args]]
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:raise ValueError('IFC processing exceeded five minutes. Export a smaller model or discipline.') from None
    if result.returncode:raise ValueError('IFC processing failed: '+(result.stderr or result.stdout)[-1000:])
    return read(output)


class IFCStore:
    def __init__(self,drawings):self.drawings=drawings

    def root(self,p):return self.drawings.project(p)/'ifc'

    def current(self,p):
        pointer=self.root(p)/'current.json'
        if not pointer.is_file():return None
        key=read(pointer)['directory']
        if not re.fullmatch(r'r\d{4,}-[a-f0-9]{12}',key):raise ValueError('Invalid IFC revision pointer')
        directory=self.root(p)/'imports'/key
        return directory,read(directory/'state.json')

    def verify(self,current,body):
        if current is None:raise ValueError('Import an IFC file first')
        if body.get('revision')!=current[1]['revision'] or body.get('source_sha256')!=current[1]['source_sha256']:
            raise StaleRevision('The IFC review changed. Refresh before saving.')

    def directory(self,p,n):
        dest=self.root(p)/'imports'/f'r{n:04}-{uuid.uuid4().hex[:12]}'
        dest.mkdir(parents=True);return dest

    def publish(self,p,dest,state):
        write_json(dest/'state.json',state)
        pointer=self.root(p)/('current-'+uuid.uuid4().hex+'.tmp');write_json(pointer,dict(directory=dest.name))
        os.replace(pointer,self.root(p)/'current.json');return state

    def upload(self,p,filename,raw,revision=None):
        if not isinstance(filename,str) or not filename.lower().endswith('.ifc'):raise ValueError('Choose an uncompressed .ifc file; export IFC STEP from Revit')
        if len(raw)>MAX_FILE:raise ValueError('The IFC file exceeds 100 MB; export a smaller model')
        if b'ISO-10303-21' not in raw[:1024]:raise ValueError('Choose an IFC STEP file, not RVT, IFCXML or IFCZIP')
        with self.drawings.lock(p):
            old=self.current(p)
            if old and revision!=old[1]['revision']:raise StaleRevision('Refresh before replacing the imported IFC')
            n=old[1]['revision']+1 if old else 1;dest=self.directory(p,n)
            (dest/'original.ifc').write_bytes(raw)
            meta=worker('inspect',dest/'original.ifc',dest/'inspection.json')
            state=dict(revision=n,source_sha256=hashlib.sha256(raw).hexdigest(),filename=Path(filename.replace('\\','/')).name,
                       status='questions',options={},counts=meta['counts'],source_schema=meta['schema'])
            return self.publish(p,dest,state)

    def build(self,p,body):
        with self.drawings.lock(p):
            old=self.current(p);self.verify(old,body);folder,state=old
            from .ifc_import import review_options
            options=review_options(body.get('options',{}),read(folder/'inspection.json'))
            dest=self.directory(p,state['revision']+1)
            for f in ('original.ifc','inspection.json'):shutil.copyfile(folder/f,dest/f)
            write_json(dest/'options.json',options)
            model=worker('build',dest/'original.ifc',dest/'model.json',dest/'options.json')
            state=dict(state,revision=state['revision']+1,status='built',options=options,counts=model['counts'],review_note='')
            return self.publish(p,dest,state)

    def review(self,p,body):
        with self.drawings.lock(p):
            old=self.current(p);self.verify(old,body);folder,state=old
            if state['status'] not in ('built','reviewed'):raise ValueError('Build and inspect the model first')
            note=body.get('note','')
            if body.get('confirm') is not True:raise ValueError('Confirm that you reviewed the geometry and data findings')
            if not isinstance(note,str) or len(note)>5000:raise ValueError('Review note must be at most 5,000 characters')
            dest=self.directory(p,state['revision']+1)
            for f in ('original.ifc','inspection.json','model.json','options.json'):shutil.copyfile(folder/f,dest/f)
            return self.publish(p,dest,dict(state,revision=state['revision']+1,status='reviewed',review_note=note))

    def export(self,p,body):
        with self.drawings.lock(p):
            source=body.get('source');current=self.drawings.current(p) if source=='steltic' else self.current(p) if source=='ifc_import' else None
            if current is None:raise ValueError('Choose an available Steltic drawing set or built IFC review')
            folder,state=current;sha=state['source_model_sha256'] if source=='steltic' else state['source_sha256']
            if body.get('revision')!=state['revision'] or body.get('source_sha256')!=sha:raise StaleRevision('The source changed. Refresh before exporting.')
            if source=='ifc_import' and state['status'] not in ('built','reviewed'):raise ValueError('Build the imported IFC review model first')
            dest=self.root(p)/'exports'/('e-'+uuid.uuid4().hex);dest.mkdir(parents=True)
            report=worker('export',folder,dest/'report.json') if source=='steltic' else worker('export_import',folder/'original.ifc',dest/'report.json',folder/'state.json')
            report.update(key=dest.name,source_directory=folder.name);write_json(dest/'report.json',report)
            return report

    def state(self,p):
        current=self.current(p);drawing=self.drawings.current(p)
        result=dict(imported=None,drawing=None,exports=[],history=[],handoffs=[])
        if current:
            folder,state=current;meta=read(folder/'inspection.json')
            result['imported']=dict(state,directory=folder.name,inspection={k:v for k,v in meta.items() if k!='products'})
        if drawing:
            _,s=drawing;result['drawing']=dict(revision=s['revision'],source_sha256=s['source_model_sha256'],status=s['drawing_status'],
                representation=s.get('representation','physical_geometry'),counts=s.get('drawing_counts',{}))
        for f in sorted((self.root(p)/'imports').glob('*/state.json')):
            s=read(f);result['history'].append({k:s[k] for k in ('revision','filename','status','source_sha256')})
        for f in sorted((self.root(p)/'exports').glob('*/report.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            r=read(f);result['exports'].append({k:v for k,v in r.items() if k!='objects'})
        for f in sorted((self.root(p)/'handoffs').glob('*/summary.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            result['handoffs'].append(read(f))
            if 'design_brief' not in result:
                request=read(f.parent/'request.json')
                result['design_brief']=request['brief'];result['target_module']=request.get('target_module','HR')
                result['hr_brief']=request['brief']  # older embedded clients
        return result

    def handoff(self,p,body):
        with self.drawings.lock(p):
            old=self.current(p);self.verify(old,body);folder,state=old
            if state['status'] not in ('built','reviewed'):raise ValueError('Build the IFC review model first')
            brief=body.get('brief')
            target=body.get('target_module','HR')
            if target not in ('HR','CFS'):raise ValueError('Choose HR or CFS for the design handoff')
            if not isinstance(brief,str) or not brief.strip() or len(brief)>60000:raise ValueError('Provide a design brief of 1 to 60,000 characters')
            dest=self.root(p)/'handoffs'/('h-'+uuid.uuid4().hex);dest.mkdir(parents=True)
            write_json(dest/'request.json',dict(brief=brief,target_module=target))
            summary=worker('handoff',folder,dest/'summary.json',dest/'request.json')
            summary['key']=dest.name;write_json(dest/'summary.json',summary)
            return summary
