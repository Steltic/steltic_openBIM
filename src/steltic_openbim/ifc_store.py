"""Immutable IFC source/review revisions, with the drawing store's project lock."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import uuid

from .drawing_workflow import StaleRevision,write_json,fingerprint,initial_state
from .job_sources import JobSources

MAX_FILE=2*1024*1024*1024
UPLOAD_CHUNK=1024*1024
# Detailed connection models can approach the product/triangle limits while
# other local design jobs are running. Keep a finite deadline with headroom.
WORKER_TIMEOUT_SECONDS=1200
LARGE_WORKER_TIMEOUT_SECONDS=7200
LARGE_SOURCE_BYTES=100*1024*1024


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def terminate_worker(proc):
    """Stop this owned worker tree, including the Windows venv child process."""
    try:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    finally:
        try:proc.kill()
        except ProcessLookupError:pass


def run_worker(cmd,timeout):
    options={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
    with subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,encoding='utf-8',errors='replace',**options) as proc:
        try:stdout,stderr=proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_worker(proc)
            proc.communicate(timeout=10)
            raise
        return subprocess.CompletedProcess(cmd,proc.returncode,stdout,stderr)


def worker(action,source,output,*args):
    cmd=[sys.executable,'-m','steltic_openbim.ifc_worker',action,str(source),str(output),*[str(a) for a in args]]
    path=Path(source);path=path/'source.json' if path.is_dir() else path
    timeout=LARGE_WORKER_TIMEOUT_SECONDS if path.is_file() and path.stat().st_size>LARGE_SOURCE_BYTES else WORKER_TIMEOUT_SECONDS
    try:
        result=run_worker(cmd,timeout)
    except subprocess.TimeoutExpired:
        duration='twenty minutes' if timeout==1200 else f'{timeout//60} minutes'
        raise ValueError(f'IFC processing exceeded {duration}. Choose a storey/review group or export a smaller discipline.') from None
    if result.returncode:raise ValueError('IFC processing failed: '+(result.stderr or result.stdout)[-1000:])
    return read(output)


class IFCStore:
    def __init__(self,drawings,source_roots=None):
        self.drawings=drawings;self.jobs=JobSources(source_roots)

    def root(self,p):return self.drawings.project(p)/'ifc'

    def structural_current(self,p):
        pointer=self.root(p)/'structural_current.json'
        if not pointer.is_file():return None
        key=read(pointer)['directory']
        if not re.fullmatch(r'r\d{4,}-[a-f0-9]{12}',key):raise ValueError('Invalid structural revision pointer')
        folder=self.root(p)/'structural'/key
        return folder,read(folder/'state.json')

    def import_structural(self,p,body):
        with self.drawings.lock(p):
            old=self.structural_current(p)
            if old and body.get('revision')!=old[1]['revision']:
                raise StaleRevision('The structural source changed. Refresh before importing.')
            module,job=body.get('module'),body.get('job')
            package,source_evidence=self.jobs.load_current(module,job)
            initial=initial_state(package,old[1]['revision']+1 if old else 1)
            if (old and old[1]['source_model_sha256']==fingerprint(package) and old[1]['source_job']==job and old[1]['source_module']==module
                    and old[1]['source_readiness']==initial['source_readiness'] and old[1]['requests']==initial['requests']
                    and old[1].get('source_evidence')==source_evidence):
                return old[1]
            from .source_worklines import required
            state={k:initial[k] for k in ('revision','building_id','source_model_sha256','source_readiness','requests')}
            state.update(schema='steltic.ifc_physical_source',source_module=module,source_job=job,
                         source_evidence=source_evidence,
                         source_status=initial['drawing_status'],
                         representation='captured_source_worklines' if required(package) else 'physical_geometry',
                         counts={k:len(v) for k,v in package['physical'].items() if isinstance(v,list)})
            dest=self.root(p)/'structural'/f'r{state["revision"]:04}-{uuid.uuid4().hex[:12]}'
            dest.mkdir(parents=True)
            write_json(dest/'source.json',package);write_json(dest/'state.json',state)
            pointer=self.root(p)/('structural-'+uuid.uuid4().hex+'.tmp')
            write_json(pointer,dict(directory=dest.name))
            os.replace(pointer,self.root(p)/'structural_current.json')
            return state

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
        return self.upload_stream(p,filename,io.BytesIO(raw),revision)

    def upload_stream(self,p,filename,stream,revision=None):
        """Copy a spooled upload in bounded chunks; publish only after inspection."""
        if not isinstance(filename,str) or not filename.lower().endswith('.ifc'):raise ValueError('Choose an uncompressed .ifc file; export IFC STEP from Revit')
        stream.seek(0);header=stream.read(1024)
        if b'ISO-10303-21' not in header:raise ValueError('Choose an IFC STEP file, not RVT, IFCXML or IFCZIP')
        stream.seek(0)
        with self.drawings.lock(p):
            old=self.current(p)
            if old and revision!=old[1]['revision']:raise StaleRevision('Refresh before replacing the imported IFC')
            n=old[1]['revision']+1 if old else 1;dest=self.directory(p,n)
            digest=hashlib.sha256();size=0;original=dest/'original.ifc'
            try:
                with original.open('wb') as out:
                    while chunk:=stream.read(UPLOAD_CHUNK):
                        size+=len(chunk)
                        if size>MAX_FILE:raise ValueError(f'The IFC file exceeds {MAX_FILE//(1024*1024)} MB; export a smaller model')
                        digest.update(chunk);out.write(chunk)
            except Exception:
                original.unlink(missing_ok=True)
                raise
            meta=worker('inspect',dest/'original.ifc',dest/'inspection.json')
            state=dict(revision=n,source_sha256=digest.hexdigest(),filename=Path(filename.replace('\\','/')).name,
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
            source=body.get('source');current=self.drawings.current(p) if source=='steltic' else self.structural_current(p) if source=='structural' else self.current(p) if source=='ifc_import' else None
            if current is None:raise ValueError('Choose an available HR/CFS job source, Steltic drawing set or built IFC review')
            folder,state=current;sha=state['source_model_sha256'] if source in ('steltic','structural') else state['source_sha256']
            if body.get('revision')!=state['revision'] or body.get('source_sha256')!=sha:raise StaleRevision('The source changed. Refresh before exporting.')
            if source=='ifc_import' and state['status'] not in ('built','reviewed'):raise ValueError('Build the imported IFC review model first')
            dest=self.root(p)/'exports'/('e-'+uuid.uuid4().hex);dest.mkdir(parents=True)
            if source in ('steltic','structural'):
                report=worker('export' if source=='steltic' else 'export_structural',folder,dest/'report.json')
            else:report=worker('export_import',folder/'original.ifc',dest/'report.json',folder/'state.json')
            if source=='steltic' and read(folder/'source.json').get('module')=='HR':
                # The PDF and source revision remain immutable in the drawing
                # store. Certify those exact bytes alongside the freshly emitted IFC.
                capture=state.get('native_source') or {}
                job_root=None
                if capture.get('module')=='HR' and capture.get('job') and 'HR' in self.jobs.roots:
                    try:
                        expected=self.jobs.path('HR',capture['job'])
                        job_root=expected.parent.parent if expected.parent.name=='design' else expected.parent
                    except (ValueError,FileNotFoundError):
                        # Preserve the provisional pair and its specific missing
                        # source evidence in the detached delivery certificate.
                        pass
                certificate=worker('verify_delivery',dest,dest/'delivery_certificate.json',folder,
                                   *([job_root] if job_root else []))
                report.update(delivery_status='verified' if certificate['passed'] else 'provisional',
                              delivery_certificate='delivery_certificate.json',
                              verification_findings=certificate['findings'])
            elif source=='structural':
                report['delivery_status']='individual_physical_source_export'
            report.update(key=dest.name,source_directory=folder.name);write_json(dest/'report.json',report)
            if body.get('final') and report.get('delivery_status')=='provisional':
                raise ValueError('HR delivery verification failed. Inspect the detached delivery certificate and findings.')
            return report

    def state(self,p):
        current=self.current(p);drawing=self.drawings.current(p);structural=self.structural_current(p)
        result=dict(imported=None,drawing=None,structural=None,sources=self.jobs.list(),exports=[],history=[],handoffs=[])
        if structural:
            _,s=structural;result['structural']=dict(s,source_sha256=s['source_model_sha256'])
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
