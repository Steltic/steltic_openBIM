"""Shared physical model construction for the twenty source-bound review cases."""
from __future__ import annotations
import copy,math,re
from collections import Counter,defaultdict
from .review_cases import CASES,catalog,scenario
from .drawing_workflow import fingerprint
from .pilots.model import add,sub,mul,dot,cross,unit
from .assembly_templates import number

MIL={18:.0188,27:.0283,30:.0312,33:.0346,43:.0451,54:.0566,68:.0713,97:.1017,118:.1242,137:.1438}
LIP={125:.188,137:.375,162:.5,200:.625,250:.625,300:.625,350:1}

class CaseModel:
    def __init__(self,key,package,state,source):
        self.key=key;self.case=CASES[key];self.package=package;self.state=state;self.source=source
        self.raw=source['calc'];self.config=copy.deepcopy(source['configuration']);self.cfg=self.config.get('cfg',{})
        self.profiles={};self.members=[];self.panels=[];self.connections=[];self.openings=[];self.notes=[];self.changes=[];self.excluded=[]
        self.levels=[];self.grids={};self.views=[];self.walls=[]
        self.records={r['id']:r for r in package['design_records']};self.used_records=set();self.bounds=None

    def profile(self,label,**options):
        label=str(label).strip().replace('×','x');label=re.sub(r'\s*[xX]\s*','X',label).upper()
        if label in self.profiles:return label
        base=catalog().get(label)
        if base:
            self.profiles[label]=copy.deepcopy(base);self.profiles[label]['id']=label
            if label.startswith('S') and base['family']=='i':self.profiles[label]['family']='i_tapered'
            return label
        match=re.fullmatch(r'(\d+)X(\d{3,4}[STUZ]\d{3}-\d{2,3})(/BOX)?',label)
        if match:
            return self.pack(self.profile(match[2]),int(match[1]),'box' if match[3] else options.get('arrangement','back_to_back'),label=label,**{k:v for k,v in options.items() if k!='arrangement'})
        match=re.fullmatch(r'(\d{3,4})([STUZ])(\d{3})-(\d{2,3})',label)
        if match:
            d,kind,b,mil=match.groups();code=int(b);mil=int(mil);t=MIL[mil];width={162:1.625,137:1.375}.get(code,code/100)
            depth=int(d)/100+(2*t+.0625 if kind=='T' else 0)
            return self.custom(label,'z' if kind=='Z' else 'channel',dict(d=depth,b=width,t=t,lip=LIP.get(code,.625) if kind in ('S','Z') else 0),basis='S: producer designator geometry; rolled corners omitted',lip_angle_deg=50 if kind=='Z' else 90)
        match=re.fullmatch(r'(?:HSS|BOX)([\d./-]+)X([\d./-]+)X([\d./-]+)',label)
        if match:
            d,w,t=map(number,match.groups());return self.custom(label,'rhs',dict(h=d,b=w,t=t*(.93 if label.startswith('HSS') else 1)),basis='S: labelled rectangular section; A500 design wall thickness where applicable')
        match=re.fullmatch(r'BOX([\d.]+)X([\d./]+)',label)
        if match:
            d,t=map(number,match.groups());return self.custom(label,'rhs',dict(h=d,b=d,t=t),basis='S: source welded plate box')
        match=re.fullmatch(r'HSS([\d.]+)X([\d.]+)',label)
        if match:
            d,t=map(float,match.groups());return self.custom(label,'chs',dict(d=d,t=.93*t),basis='S: A500 circular HSS, design wall thickness')
        match=re.fullmatch(r'ROD([\d./-]+)',label)
        if match:return self.custom(label,'round',dict(d=number(match[1])),basis='S: source rod diameter')
        match=re.fullmatch(r'L([\d./-]+)X([\d./-]+)X([\d./-]+)',label)
        if match:
            h,w,t=map(number,match.groups());return self.custom(label,'angle',dict(h=h,b=w,t=t),basis='S: section designation; rolled corner omitted')
        match=re.fullmatch(r'PL([\d./]+)X([\d./]+)',label)
        if match:
            w,t=map(number,match.groups());return self.custom(label,'flat',dict(width=w,thickness=t),basis='S: source plate/strap')
        raise ValueError(self.key+': no physical section definition for '+label)

    def custom(self,label,family,dimensions,**extra):
        self.profiles[label]=dict(id=label,family=family,dimensions=dimensions,**extra);return label

    def pack(self,pid,n=2,arrangement='box',label=None,gap=.125,pair_spacing=None):
        p=self.profiles[pid];t=p['dimensions']['t'];width=p['dimensions']['b']
        label=label or f'A-{n}X{pid}-{arrangement}-{gap:g}'
        if label in self.profiles:return label
        comps=[]
        if arrangement=='box':
            for j in range(n//2):
                centre=(j-(n/2-1)/2)*(2*width+gap)
                comps.extend([dict(profile_id=pid,offset=[centre-width,0],rotation_deg=0),dict(profile_id=pid,offset=[centre+width,0],rotation_deg=180)])
        else:
            sep=pair_spacing or 2*width+gap+t
            for j in range(n//2):
                centre=(j-(n/2-1)/2)*sep
                comps.extend([dict(profile_id=pid,offset=[centre-(gap+t)/2,0],rotation_deg=180),dict(profile_id=pid,offset=[centre+(gap+t)/2,0],rotation_deg=0)])
        return self.custom(label,'built_up',{},components=comps,pair_spacing_in=pair_spacing or 2*width+gap+t,basis='A: explicit physical ply arrangement; source section/count retained')

    def depth(self,pid):
        p=self.profiles[pid]
        if p['family']=='built_up':return max(self.depth(c['profile_id']) for c in p['components'])
        d=p['dimensions'];return d.get('d',d.get('h',d.get('depth',d.get('thickness',6))))

    def member(self,mid,pid,kind,a,b,level=1,basis='S',records=(),local_y=None,source=None,**extra):
        if math.dist(a,b)<.01:raise ValueError('Zero length '+mid)
        if pid not in self.profiles:pid=self.profile(pid)
        axis=unit(sub(b,a))
        if local_y is None:local_y=[0,1,0] if abs(axis[2])>.999 else unit(cross([0,0,1],axis))
        else:local_y=unit(sub(local_y,mul(axis,dot(axis,local_y))))
        m=dict(id=mid,profile_id=pid,kind=kind,axis=[list(a),list(b)],local_y=local_y,end_offsets=[[0,0,0],[0,0,0]],level=level,basis=basis,
               source_member_id=source,design_record_ids=[r for r in records if r],material_id='source_steel' if basis=='S' else 'assumed_test_steel',**extra)
        self.members.append(m);self.used_records.update(m['design_record_ids']);return m

    def panel(self,pid,kind,vertices,thickness,level,basis='S',records=(),**extra):
        p=dict(id=pid,kind=kind,vertices=vertices,thickness_in=thickness,level=level,basis=basis,design_record_ids=[r for r in records if r],**extra)
        self.panels.append(p);self.used_records.update(p['design_record_ids']);return p

    def record(self,table,short):
        if short is None:return None
        name=table+'/'+short
        return name if name in self.records else next((r for r in self.records if r.endswith('/'+short)),None)

    def connection(self,cid,family,point,members,records=(),parameters=None,basis='A',title=None):
        ids=[m['id'] if isinstance(m,dict) else m for m in members];refs=[r for r in records if r]
        if not ids:raise ValueError('Connection without an attached physical member '+cid)
        c=dict(id=cid,point=list(point),member_ids=list(dict.fromkeys(ids)),detail_ref={'id':family},design_record_ids=refs,parts=[],basis=basis)
        if parameters:c['parameters']=parameters
        if title:c['title']=title
        self.connections.append(c);self.used_records.update(refs);return c

    def ends(self,m,family,records=(),**extra):
        for end,p in enumerate(m['axis']):self.connection(m['id']+':'+str(end),family,p,[m],records,**extra)

    def note(self,kind,text):self.notes.append(dict(id=self.key.upper()+'-'+kind,answer=text,basis='A - user-authorized fictional test input'))

    def finish(self):
        if not self.members:raise ValueError('Empty physical case '+self.key)
        ids=[m['id'] for m in self.members]
        if len(set(ids))!=len(ids):raise ValueError('Duplicate member IDs '+self.key)
        lookup={m['id']:m for m in self.members};attached=Counter(i for c in self.connections for i in c['member_ids'])
        missing=[m['id'] for m in self.members if not attached[m['id']] and m['kind'] not in ('plate_wall_tie','shear_stud','foundation_context')]
        if missing:raise ValueError(f'{self.key}: members without any connection: {missing[:20]}')
        groups=defaultdict(list)
        for m in self.members:groups[m['kind'],m['profile_id'],round(math.dist(*m['axis'])*16)/16,m['basis']].append(m)
        schedule=[];counts=Counter()
        prefixes={'column':'C','stud':'S','chord':'CH','joist':'J','purlin':'P','girt':'G','rafter':'R','beam':'B','girder':'B','moment_beam':'M','brace':'BR','truss_chord':'TC','truss_web':'TW'}
        for (kind,pid,length,basis),ms in sorted(groups.items()):
            prefix=prefixes.get(kind,'T');counts[prefix]+=1;mark=f'{prefix}{counts[prefix]:03}'
            for m in ms:m['mark']=mark
            schedule.append(dict(mark=mark,kind=kind,profile_id=pid,length_in=length,count=len(ms),basis=basis,levels=sorted({m['level'] for m in ms}),connection_refs=[],member_ids=[m['id'] for m in ms]))
        allpoints=[p for m in self.members for p in m['axis']]
        bounds=[[min(p[i] for p in allpoints),max(p[i] for p in allpoints)] for i in range(3)]
        if not self.grids:
            self.grids={axis:[(str(j+1) if i==0 else chr(65+j),x) for j,x in enumerate(sorted({round(p[i],3) for m in self.members if m['kind']=='column' for p in m['axis']}))] for i,axis in enumerate(('x','y'))}
        assumptions=[dict(id=k,answer=v,basis='A - user-authorized fictional test input') for k,v in scenario(self.key)['answers'].items()]+self.notes
        return dict(schema='steltic.design_drawing_model',version=1,pilot=self.key,title=self.case.get('drawing_title',self.case['source_building'].replace('_',' ')),fictional=True,
            source_sha256=fingerprint(self.package),scenario=copy.deepcopy(self.state['design_scenario']),members=self.members,profiles=list(self.profiles.values()),panels=self.panels,
            materials=[dict(id='source_steel',basis='S',specification='Grades and material requirements in source records'),dict(id='assumed_test_steel',basis='A',specification='Fictional geometry supplement; no new capacity verification')],
            openings=self.openings,connections=self.connections,member_schedule=schedule,details=[],grids=self.grids,levels=self.levels,changes=self.changes,
            assumptions=assumptions,bounds=bounds,extra_views=self.views,wall_layouts=self.walls,excluded_analysis_elements=self.excluded,
            record_coverage=dict(used=sorted(self.used_records),retained_without_physical_occurrence=sorted(set(self.records)-self.used_records)))
