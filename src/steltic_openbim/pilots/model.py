"""Deterministic physical model authoring and evidence-backed review records.

Physical profile coordinates: local y is width; local z = axis cross local y
is depth. This differs from some OpenSees element conventions; recipes convert
explicitly. Axis is the reference workline; end_offsets locate solid endpoints.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path

from ..bim_contract import COLLECTIONS, DRAWING_TABLES, validate


def add(a,b): return [x+y for x,y in zip(a,b)]
def sub(a,b): return [x-y for x,y in zip(a,b)]
def mul(a,s): return [x*s for x in a]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def length(a): return math.sqrt(dot(a,a))
def unit(a): return mul(a,1/length(a))
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stable_hash(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def points(a,b,step):
    n=int(math.floor((b-a)/step+1e-8))
    values=[a+i*step for i in range(n+1)]
    if abs(values[-1]-b)>1e-6: values.append(b)
    return values


class Model:
    def __init__(self, source, catalog, recipe):
        lock=json.loads(Path(__file__).with_name('inputs.lock.json').read_text())[recipe]
        signature={k:source[k] for k in ['building_id','module','schema_version','analysis','physical','design_records','design_context','layout_evidence']}
        signature['source_files']=source['provenance']['source_files']
        if stable_hash(signature)!=lock['source_signature']:
            raise ValueError('Pilot recipe is bound to a different source revision; review changes before reusing it')
        self.source=copy.deepcopy(source)
        self.p=copy.deepcopy(source)
        self.p['physical']={k:[] for k in COLLECTIONS}
        self.p['physical'].update(analysis_only=copy.deepcopy(source['physical']['analysis_only']),record_dispositions=[],joint_dispositions=[],coverage={})
        self.ph=self.p['physical']; self.catalog=catalog
        self.records={r['id']:r for r in source['design_records']}
        self.members={}; self.profiles={}; self.joints={}; self.used=set()
        self.p['review']={'recipe':recipe,'recipe_version':'1','items':[], 'checks':[],
            'purpose':'Engineering design model review; not fabrication or construction release',
            'source_package_sha256':stable_hash(source),
            'original_brief':lock['brief'],
            'recipe_sources':{p.name:digest(p) for p in sorted(Path(__file__).parent.glob('*')) if p.suffix in ('.py','.json')},
            'coordinate_convention':'Inches; Z up. Profile local_y = width, axis cross local_y = depth; solids use axis + end_offsets.',
            'source_precedence':['completed calculation package','job configuration and schedules','original brief'],
            'user_scope':'Designed structural scope with delegated items and unresolved locations shown explicitly.'}
        specs={'steel':'ASTM A992 Fy50','plate':'ASTM A572 Grade 50','angle':'ASTM A36',
            'cfs50':'ASTM A1003 Grade 50','cfs33':'ASTM A1003 Grade 33','cfs55':'CFS Z-section Fy55; source schedule',
            'cfs_strap':'ASTM A1008 SS Grade 50 (or A1003 ST50H)','tube':'ASTM A500 Grade C',
            'boltA325':'ASTM F3125 Grade A325, threads included','boltA490':'ASTM F3125 Grade A490, threads excluded',
            'bolt':'ASTM F3125; grade specified by referenced connection record','rod':'ASTM A449; source hold-down schedule',
            'anchor':'ASTM F1554 Grade 36','screw':'ASTM C1513; source screw schedule','weld':'E70XX',
            'concrete':'Normal-weight concrete; source design strength','wsp':'Wood structural panel; source diaphragm schedule',
            'deck':'Profiled steel deck; delegated manufacturer','envelope':'Delegated assembly envelope, not a designed section'}
        self.ph['materials']=[{'id':k,'specification':v} for k,v in specs.items()]

    def record(self,rid):
        return self.records[rid]['data']

    def refs(self,ids):
        for rid in ids:
            if rid not in self.records: raise ValueError('Unknown source record '+rid)
        self.used.update(ids)
        return sorted(set(ids))

    def profile(self,name):
        if name not in self.profiles:
            p=copy.deepcopy(self.catalog[name]); p.update(id=name,status='declared')
            self.profiles[name]=p; self.ph['profiles'].append(p)
        return name

    def custom_profile(self,name,family,dimensions,**kw):
        if name not in self.profiles:
            self.profiles[name]=dict(id=name,status='declared',family=family,dimensions=dimensions,**kw)
            self.ph['profiles'].append(self.profiles[name])
        return name

    def builtup(self,name,section,n,gap=0,pair_spacing=None):
        """Web pairs with an explicit joint gap; components use web-midline origins."""
        if name in self.profiles: return name
        self.profile(section); d=self.profiles[section]['dimensions']; t=d['t']; b=d['b']
        centers=[0] if n==2 else [-((pair_spacing or (2*b+gap))/2),((pair_spacing or (2*b+gap))/2)]
        assert n in (2,4)
        components=[]
        for center in centers:
            for sign in [-1,1]:
                components.append({'profile_id':section,'offset':[center+sign*(gap+t)/2,0], 'rotation_deg':0 if sign>0 else 180})
        return self.custom_profile(name,'built_up',{},components=components,basis='Constituent profiles from engine catalogue; explicit web gap and pair spacing in recipe',web_gap_in=gap,pair_spacing_in=pair_spacing)

    def flat(self,width,thickness):
        return self.custom_profile(f'PL{width:g}x{thickness:g}','flat',{'width':width,'thickness':thickness})

    def member(self,mid,a,b,profile,kind,refs=(),level=1,local_y=None,material=None,offsets=None,analysis_ids=(),**kw):
        if mid in self.members: raise ValueError('Duplicate member '+mid)
        if profile not in self.profiles: self.profile(profile)
        if material is None: material='cfs33' if self.profiles[profile].get('Fy')==33 else 'cfs50'
        axis=unit(sub(b,a))
        if local_y is None:
            local_y=unit(cross([0,0,1],axis)) if abs(axis[2])<0.99 else [1,0,0]
        m=dict(id=mid,kind=kind,status='declared',axis=[list(a),list(b)],local_y=list(local_y),profile_id=profile,material_id=material,
            reference_line='explicit physical workline; profile origin defined by catalogue',end_offsets=offsets or [[0,0,0],[0,0,0]],analysis_ids=list(analysis_ids),
            design_record_ids=self.refs(refs),level=level,**kw)
        self.members[mid]=m; self.ph['members'].append(m)
        return m

    def joint(self,jid,point,ends=(),supports=()):
        if jid in self.joints: raise ValueError('Duplicate joint '+jid)
        es=[]
        for mid,end in ends:
            e=self.members[mid]['axis'][0 if end=='start' else 1]
            es.append({'member_id':mid,'end':end,'joint_offset':sub(point,e)})
        attachments=[]
        for mid in supports:
            m=self.members[mid]; a,b=m['axis']; v=sub(b,a)
            t=dot(sub(point,a),v)/dot(v,v)
            if not -1e-6<=t<=1+1e-6: raise ValueError(f'Support outside member: {jid} {mid} {t}')
            t=max(0,min(1,t)); attachments.append({'member_id':mid,'station':t,'offset':sub(point,add(a,mul(v,t)))})
        j=dict(id=jid,point=list(point),member_ends=es,attachments=attachments)
        self.joints[jid]=j; self.ph['joints'].append(j)
        return j

    def connect(self,jid,refs,parts=(),template='source_design_detail',**kw):
        refs=self.refs(refs)
        # Detail refs resolve inside this very package: immutable original record
        # and its source pointer, not an opaque URL or missing library asset.
        detail={'id':template,'revision':'1','source_record_ids':refs,'content_sha256':stable_hash([self.records[r] for r in refs])}
        c=dict(id='C:'+jid,joint_id=jid,scope='designed',design_record_ids=refs,parts=list(parts),detail_ref=detail,
            representation='Placed design connection with full source specification; omitted shop dimensions are review items')
        c.update(kw)
        self.ph['connections'].append(c)
        return c

    def ends(self,m,refs,template='source_design_detail',supports=(None,None)):
        for i,end in enumerate(['start','end']):
            j=self.joint(f'{m["id"]}:{end}',m['axis'][i],[(m['id'],end)], [supports[i]] if supports[i] else [])
            self.connect(j['id'],refs,template=template)

    def panel(self,pid,vertices,thickness,material,kind,refs=(),level=1,**kw):
        p=dict(id=pid,kind=kind,status='declared',vertices=vertices,thickness=thickness,material_id=material,design_record_ids=self.refs(refs),level=level,**kw)
        self.ph['panels'].append(p); return p

    def item(self,iid,title,kind,basis,entities=(),proposed=None,resolution=None):
        self.p['review']['items'].append(dict(id=iid,title=title,kind=kind,status='coordination_required',basis=basis,
            entity_ids=list(entities),proposed=proposed,resolution=resolution))

    def interface(self,iid,party,basis,refs=(),entities=()):
        self.ph['interfaces'].append(dict(id=iid,scope='delegated',responsible_party=party,basis=basis,representation=basis,detail_ref={'id':iid,'revision':'1'},design_record_ids=self.refs(refs),entity_ids=list(entities)))

    def finish(self,coverage):
        self.ph['coverage']=coverage
        used_materials={r['material_id'] for key in ('members','panels') for r in self.ph[key]}
        used_materials.update(part['material_id'] for c in self.ph['connections'] for part in c.get('parts',[]))
        self.ph['materials']=[r for r in self.ph['materials'] if r['id'] in used_materials or r.get('design_record_ids')]
        # No generic "covered" escape hatch: every unassigned drawing record
        # remains a real needs_input finding in the contract validator.
        findings=validate(self.p)
        self.p['readiness']={'status':'invalid' if any(f['severity']=='error' for f in findings) else ('needs_input' if findings else 'ready'),'findings':findings,
            'counts':{k:len(self.ph[k]) for k in COLLECTIONS}}
        self.p['review']['unmapped_drawing_records']=sorted(r for r in self.records if self.records[r]['table'] in DRAWING_TABLES and r not in self.used)
        return self.p


def box(pid,origin,size,x=(1,0,0),y=(0,1,0),material='plate',kind='plate'):
    return dict(id=pid,kind=kind,material_id=material,geometry=dict(type='box',origin=list(origin),size=list(size),x_axis=list(x),y_axis=list(y)))


def cylinder(pid,origin,axis,radius,extent,material='bolt',kind='bolt'):
    return dict(id=pid,kind=kind,material_id=material,geometry=dict(type='cylinder',origin=list(origin),axis=list(axis),radius=radius,length=extent))
