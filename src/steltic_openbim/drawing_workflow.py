"""Revisioned, non-blocking information requests for coordination drawings.

The saved design stays immutable. Provisional acceptance authorises drawing a
labelled proposal, never silently confirms its dimensions or structural design.
"""
from __future__ import annotations
import copy
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import uuid

from .validation import inspect_package


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',value):
        raise ValueError('Use a project name containing letters, numbers, hyphens or underscores')
    return value


class StaleRevision(ValueError): pass


def bounds(package):
    from .source_worklines import required,build
    if required(package):
        pts=[p for m in build(package)['members'] for p in m['axis']]
        return [(min(p[i] for p in pts)/12,max(p[i] for p in pts)/12) for i in range(3)]
    pts=[p for m in package['physical']['members'] for p in m['axis']]
    pts += [p for panel in package['physical']['panels'] for p in panel['vertices']]
    if not pts: raise ValueError('A drawing package needs some finite physical geometry')
    return [(min(p[i] for p in pts)/12,max(p[i] for p in pts)/12) for i in range(3)]


PROPOSALS={
 'HR-SETOUT':'Use the displayed top-of-steel arrangement, centred shear-plate groups and source base types for coordination. Final vertical datums, plate alignment and interfaces are TBD - resolve query.',
 'HR-PENTHOUSE':'Use the source penthouse profiles in the displayed local zone. Exact occurrence coordinates and connection applicability are TBD - resolve query.',
 'CFS16-FRAME-SETOUT':'Use the displayed four-channel frames and source worklines for coordination. Clear-span datum, channel pair spacing and final cutbacks are TBD - resolve query.',
 'CFS16-SECONDARY-SETOUT':'Use source sections, laps and regular flange-brace stations. Attachment offsets, nested section fit and remaining brace endpoints are TBD - resolve query.',
 'CFS8-FLOOR':'Use the displayed platform framing arrangement for coordination. Exact floor stack, bearing fit, interruptions and final datums are TBD - resolve query.',
 'HR-OPENINGS':'Show two stair and two lift/shaft coordination zones on each level, near the plan edges and central service area. Locations and sizes are illustrative, not a new framing design; all are TBD - resolve query.',
 'HR-BASE-STUDS':'Retain the embedded-base design reference and show a stud-zone callout. Stud count/spacing layout is TBD - resolve query; do not choose between the conflicting specifications.',
 'HR-DETAILS':'Retain source-defined connections and required brace stations. Show missing kicker, erection-tab, splice and deck attachment details as labelled TBD callouts.',
 'HR-SEPARATION':'Show a provisional adjacent-building coordination line on the west face. Face selection and clearance are TBD - resolve query; verify against the existing building.',
 'CFS16-DOORS':'Show one provisional personnel door near the middle of each long side wall, away from end bracing. Both door sizes and positions are TBD - resolve query; no egress compliance is inferred.',
 'CFS16-BRACKETS':'Show the source bolt-group envelopes and reference their designed specifications. Final gusset boundaries and base bolt set-out remain TBD - resolve query.',
 'CFS16-END-BRACING':'Use the displayed end-wall side zones for the provisional strap layout. Final bay limits and corner girt zoning remain TBD - resolve query.',
 'CFS8-OPENINGS':'Show a provisional entrance at the stem end and regularly distributed window symbols on the exterior walls at each storey. Sizes, count and positions are illustrative and all marked TBD - resolve query; structural framing is not cut.',
 'CFS8-CHORDS':'Retain the displayed spaced chord-pack envelope so the rod-bracket interface is visible. Pack spacing and spacer details remain TBD - resolve query pending engineering reconciliation.',
 'CFS8-ROOF-INTERFACE':'Show the roof envelope and ordinary truss stations, with a labelled supplier zone at the valley. Valley/girder-truss arrangement and reactions are TBD - resolve query.',
 'CFS8-WALKWAY-EDGE':'Show a dashed outer support line along the walkway edge. Beam/post sizes, spacing and foundations remain TBD - resolve query pending the walkway design.',
 'CFS8-STUD-SETOUT':'Use the displayed party-wall grid and chord replacements provisionally. Final wall starting positions and intersections remain TBD - resolve query.',
 'CFS8-DETAILS':'Show the placed connection families and source specifications. Missing gusset boundaries, screw/anchor set-out and side-plate extents remain TBD - resolve query.',
}
EXTERNAL={'HR-OPENINGS','HR-SEPARATION','CFS16-DOORS','CFS8-OPENINGS','CFS8-ROOF-INTERFACE','CFS8-WALKWAY-EDGE','MODEL-OPENINGS'}


def initial_requests(package):
    from .review_cases import CASES,scenario
    key=next((k for k,c in CASES.items() if c['source_sha256']==fingerprint(package)),None)
    if key:
        evidence=copy.deepcopy(package.get('review',{}).get('items',[]))
        return [dict(id=iid,question='Confirm fictional '+iid.rsplit('-',1)[-1].lower()+' inputs',
            evidence='Consolidated source review findings retained with this request.',source_review_items=evidence,
            proposal=answer,kind='default',accepted=True,acceptance='provisional_drawing_policy',confirmed=False,
            status='provisional',assignee='design_agent',entity_ids=[],resolution_mode='information',notes=[],
            default_reason='Accepted as a drawing proposal; quantitative test inputs require explicit adoption.')
            for iid,answer in scenario(key)['answers'].items()]
    from .source_worklines import required,request_items
    items=request_items(package) if required(package) else copy.deepcopy(package.get('review',{}).get('items',[]))
    if not items:
        for f in inspect_package(package)['findings']:
            if f['severity']=='needs_input':
                items.append(dict(id=f['code'],title=f['message'],kind='missing',basis=f['message'],entity_ids=f.get('entity_ids',[])))
    result=[]
    seen=set()
    for item in items:
        if item.get('status')=='resolved' or item['id'] in seen: continue
        seen.add(item['id']); iid=item['id']
        proposed=PROPOSALS.get(iid) or item.get('proposed') or (
            'Use the available source geometry for coordination and identify the remaining scope with a TBD - resolve query callout. No unsupplied dimensions or structural capacity are asserted.')
        result.append(dict(id=iid,question=item['title'],evidence=item.get('basis',''),proposal=proposed,
            kind='default',accepted=True,acceptance='provisional_drawing_policy',confirmed=False,status='provisional',
            assignee='external' if iid in EXTERNAL or item.get('kind')=='delegated' else 'design_agent',
            entity_ids=item.get('entity_ids',[]),resolution_mode='opening_layout' if iid in ('HR-OPENINGS','CFS16-DOORS','CFS8-OPENINGS','MODEL-OPENINGS') else 'information',
            notes=[],default_reason='Accepted for provisional drawings. Quantitative information is still outstanding.'))
    return result


def initial_features(package,requests):
    """Explicitly authored illustrative geometry, isolated from designed members."""
    if any(r['id']=='MODEL-OPENINGS' for r in requests):
        from .source_worklines import opening_features
        return opening_features(package)
    if not any(r['id'] in EXTERNAL for r in requests):return []
    ids={r['id'] for r in requests}; out=[]; b=bounds(package)
    def feature(q,kind,plane,x,y,z,w,h,level):
        out.append(dict(id=f'P{len(out)+1:03}',query_id=q,kind=kind,plane=plane,x_ft=x,y_ft=y,z_ft=z,
                        width_ft=w,height_ft=h,level=level,confirmed=False,geometry_role='illustrative_proposal'))
    levels=sorted({m.get('level',1) for m in package['physical']['members']})
    if 'CFS16-DOORS' in ids:
        for x in (b[0][0],b[0][1]): feature('CFS16-DOORS','personnel door','yz',x,136,0,3,7,1)
    if 'HR-OPENINGS' in ids:
        for level,z in enumerate((16,30,44,58,72,86),1):
            for kind,x,y,w,h in [('stair zone',12,12,12,18),('stair zone',156,90,12,18),('lift/shaft zone',78,48,8,8),('lift/shaft zone',94,48,8,8)]:
                feature('HR-OPENINGS',kind,'xy',x,y,z,w,h,level)
    if 'CFS8-OPENINGS' in ids:
        feature('CFS8-OPENINGS','entrance door','xz',68.5,0,0,3,7,1)
        for level,z in enumerate((0,10,19.667,29.334),1):
            for x in (21,49,91,119): feature('CFS8-OPENINGS','window','xz',x,130,z+3,4,4,level)
            for x in (47,93): feature('CFS8-OPENINGS','window','yz',x,35,z+3,4,4,level)
    if 'HR-SEPARATION' in ids: feature('HR-SEPARATION','existing-building interface','yz',-2,0,0,120,86,1)
    if 'CFS8-WALKWAY-EDGE' in ids:
        for level,z in enumerate((10,19.667,29.334),1): feature('CFS8-WALKWAY-EDGE','walkway outer support line','yz',41,0,z,84,0,level)
    if 'CFS8-ROOF-INTERFACE' in ids: feature('CFS8-ROOF-INTERFACE','supplier valley zone','xy',47,84,44.751,46,23,4)
    return out


def initial_state(package,revision):
    verdict=inspect_package(package)
    if verdict['status']=='invalid': raise ValueError('Invalid physical geometry: '+ '; '.join(f['message'] for f in verdict['findings'] if f['severity']=='error')[:1500])
    requests=initial_requests(package)
    return dict(schema='steltic.drawing_workflow',version=1,revision=revision,building_id=package['building_id'],
        source_model_sha256=fingerprint(package),source_readiness=verdict['status'],drawing_status='provisional' if requests else 'source_geometry',
        can_generate=True,requests=requests,features=initial_features(package,requests),events=[],
        policy={'proposals_accepted_for_drawing':True,'unconfirmed_dimensions':'TBD - resolve query',
                'source_design_immutable':True,'structural_analysis_unchanged':True})


def reconcile_state(package,state):
    """Re-run readiness after a renderer upgrade, without discarding saved answers."""
    fresh=initial_state(package,state['revision']);result=copy.deepcopy(state)
    result['source_readiness']=fresh['source_readiness']
    ids={r['id'] for r in result['requests']}
    added={r['id'] for r in fresh['requests'] if r['id'] not in ids}
    result['requests'] += [r for r in fresh['requests'] if r['id'] in added]
    existing={f['id'] for f in result['features']}
    result['features'] += [f for f in fresh['features'] if f['query_id'] in added and f['id'] not in existing]
    if any(not r['confirmed'] for r in result['requests']):result['drawing_status']='provisional'
    return result


def apply_answer(package,state,body):
    if body.get('revision')!=state['revision'] or body.get('source_model_sha256')!=state['source_model_sha256']:
        raise StaleRevision('The drawings changed. Refresh before saving this answer.')
    result=copy.deepcopy(state); requests={r['id']:r for r in result['requests']}
    iid=body.get('id'); request=requests.get(iid)
    if request is None: raise ValueError('Unknown information request')
    author=str(body.get('author','')).strip(); note=str(body.get('note','')).strip()
    if not author or len(author)>160 or not note or len(note)>12000: raise ValueError('Provide your name and a concise information/source note')
    action=body.get('action','information')
    if action=='resolve_openings':
        if request['resolution_mode']!='opening_layout': raise ValueError('This request needs updated source design information')
        supplied=body.get('features'); expected={f['id'] for f in result['features'] if f['query_id']==iid}
        if not isinstance(supplied,list) or len(supplied)>1000: raise ValueError('Supply the confirmed opening layout')
        if not supplied and body.get('confirm_no_openings') is not True: raise ValueError('Explicitly confirm if there are no openings')
        fresh=[]; used={f['id'] for f in result['features'] if f['query_id']!=iid}; bb=bounds(package)
        from .source_worklines import required,build,physical_view
        allowed_levels=({m['level'] for m in build(package)['members']} if required(package)
                        else {m.get('level',1) for m in physical_view(package)['members']})
        for f in supplied:
            if not isinstance(f,dict): raise ValueError('Each opening needs a name, level, plane and five dimensions in feet')
            fid=f.get('id')
            if not isinstance(fid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',fid) or fid in used: raise ValueError('Opening IDs must be unique')
            used.add(fid)
            if f.get('plane') not in ('xy','xz','yz'): raise ValueError('Choose a valid opening plane')
            for k in ('x_ft','y_ft','z_ft','width_ft','height_ft'):
                v=f.get(k)
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): raise ValueError('All opening coordinates and sizes must be finite numbers in feet')
            if not (0<f['width_ft']<=100 and 0<f['height_ft']<=100): raise ValueError('Opening sizes must be positive and at most 100 ft')
            if any(not lo-10<=f[k]<=hi+10 for k,(lo,hi) in zip(('x_ft','y_ft','z_ft'),bb)): raise ValueError('Opening coordinates are outside the building vicinity')
            if type(f.get('level')) is not int or f['level'] not in allowed_levels: raise ValueError('Opening level must exist in the model')
            fresh.append({k:f[k] for k in ('id','plane','level','x_ft','y_ft','z_ft','width_ft','height_ft')})
            fresh[-1].update(kind=str(f.get('kind','opening'))[:80],query_id=iid,confirmed=True,geometry_role='confirmed_coordination_opening',confirmed_by=author)
        result['features']=[f for f in result['features'] if f['query_id']!=iid]+fresh
        request.update(status='resolved',confirmed=True,resolution=note)
    elif action=='information':
        request['notes'].append(dict(author=author,note=note))
        request['status']='resolved' if request['confirmed'] else 'information_received'
    elif action=='reopen':
        request.update(status='provisional',confirmed=False)
        for f in result['features']:
            if f['query_id']==iid: f.update(confirmed=False,geometry_role='illustrative_proposal')
    else: raise ValueError('Unknown answer action')
    result['revision']+=1
    result['drawing_status']='provisional' if any(not r['confirmed'] for r in result['requests']) else ('design_test' if result.get('design_scenario') else 'coordinated')
    if result.get('design_scenario'):
        for feature in result['features']:
            feature['basis']='A - user-authorized fictional test input'
        if action=='resolve_openings':
            request['resolution_basis']='user_authorized_fictional_assumption'
    result['events'].append(dict(revision=result['revision'],id=iid,action=action,author=author,note=note,source_model_sha256=state['source_model_sha256']))
    return result


class DrawingStore:
    """Shared local store; cross-process locks and one atomic revision pointer."""
    def __init__(self,root):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self._locks={}; self._guard=threading.Lock()

    def project(self,p): return self.root/name(p)/'openbim'

    @contextmanager
    def lock(self,p):
        from filelock import FileLock,Timeout
        with self._guard: thread_lock=self._locks.setdefault(name(p),threading.RLock())
        base=self.project(p); base.mkdir(parents=True,exist_ok=True)
        with thread_lock:
            try:
                with FileLock(str(base/'update.lock'),timeout=120): yield
            except Timeout:
                raise StaleRevision('Another drawing update is still running. Refresh and retry.') from None

    def current(self,p):
        base=self.project(p); pointer=base/'current.json'
        if not pointer.is_file(): return None
        key=json.loads(pointer.read_text())['directory']
        if not re.fullmatch(r'r\d{4,}-[a-f0-9]{12}',key): raise ValueError('Invalid drawing revision pointer')
        directory=base/'revisions'/key
        return directory,json.loads((directory/'state.json').read_text(encoding='utf-8'))

    def publish(self,p,package,state):
        from .drawing_pdf import generate
        base=self.project(p); key=f'r{state["revision"]:04}-{uuid.uuid4().hex[:12]}'
        directory=base/'revisions'/key; directory.mkdir(parents=True)
        write_json(directory/'source.json',package)
        report=generate(package,state,directory)
        state['sheets']=report['sheets']; state['artifacts']=report.get('artifacts',['drawings.pdf','drawing_manifest.json','information_requests.json'])
        state['representation']=report.get('representation','physical_geometry')
        state['drawing_counts']=report.get('counts',{})
        write_json(directory/'state.json',state)
        write_json(directory/'information_requests.json',self.questions(state))
        pointer=base/('current-'+uuid.uuid4().hex+'.tmp'); write_json(pointer,{'directory':key})
        os.replace(pointer,base/'current.json')
        return state

    def import_package(self,p,package,revision=None):
        with self.lock(p):
            current=self.current(p)
            if current and revision!=current[1]['revision']: raise StaleRevision('Refresh before replacing the source package')
            if current and current[1]['source_model_sha256']==fingerprint(package):
                updated=reconcile_state(package,current[1])
                if updated==current[1]:return current[1]
                updated['revision']+=1
                updated['events'].append(dict(revision=updated['revision'],action='readiness_rechecked',note='Rechecked source completeness with the current validator; existing answers retained.'))
                return self.publish(p,package,updated)
            n=current[1]['revision']+1 if current else 1
            state=initial_state(package,n)
            if current: state['events']=[dict(revision=n,action='source_replaced',previous_source_model_sha256=current[1]['source_model_sha256'],note='Previous answers retained in revision history; new source starts with provisional proposals.')]
            return self.publish(p,package,state)

    def answer(self,p,body):
        with self.lock(p):
            current=self.current(p)
            if current is None: raise ValueError('Import a physical package first')
            directory,state=current; package=json.loads((directory/'source.json').read_text(encoding='utf-8'))
            return self.publish(p,package,apply_answer(package,state,body))

    def fictional_design(self,p,body):
        from .design_scenarios import adopt_scenario
        with self.lock(p):
            current=self.current(p)
            if current is None: raise ValueError('Import a physical package first')
            directory,state=current;package=json.loads((directory/'source.json').read_text(encoding='utf-8'))
            return self.publish(p,package,adopt_scenario(package,state,body))

    def regenerate(self,p,body):
        with self.lock(p):
            current=self.current(p)
            if current is None: raise ValueError('Import a physical package first')
            directory,state=current
            if body.get('revision')!=state['revision'] or body.get('source_model_sha256')!=state['source_model_sha256']:
                raise StaleRevision('Refresh before regenerating the drawings')
            package=json.loads((directory/'source.json').read_text(encoding='utf-8'))
            state=reconcile_state(package,state)
            state['revision']+=1
            state['events'].append(dict(revision=state['revision'],action='regenerated',note='Drawing set regenerated with the current renderer; source and answers retained.'))
            return self.publish(p,package,state)

    @staticmethod
    def questions(state):
        return dict(schema='steltic.drawing_information_requests',revision=state['revision'],source_model_sha256=state['source_model_sha256'],
            ready=True,blocks_drawings=False,groups=[dict(group='Information requests',items=[dict(r,default=r['proposal'],needed_for='Quantitative coordination; provisional drawings proceed') for r in state['requests'] if r['assignee']=='external']),
                dict(group='Design-agent follow-up',items=[dict(r,default=r['proposal'],needed_for='Source design reconciliation; provisional drawings proceed') for r in state['requests'] if r['assignee']=='design_agent'])])
