"""Dimensioned source-workline sheets for ordinary HR jobs needing physical data."""
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path

from .design_pdf import DesignSheets,feet,INK,LIGHT,GREY,ASSUMED,BLUE
from .drawing_pdf import feature_vertices
from .drawing_workflow import write_json,fingerprint
from .source_worklines import build


class WorklineSheets(DesignSheets):
    def start(self,number,title,scale='NTS',refs=()):
        if self.page:self.c.showPage()
        self.page+=1;self.current=number
        self.rows.append(dict(number=number,title=title,page=self.page,scale=scale,query_ids=list(refs)))
        c=self.c;c.setStrokeColor(INK);c.setLineWidth(1);c.rect(34,34,self.W-68,self.H-68)
        self.text(55,self.H-70,'STELTIC / OPENBIM',17,font='Helvetica-Bold')
        self.text(55,self.H-112,title,25,font='Helvetica-Bold')
        self.text(self.W-390,self.H-69,number,27,font='Helvetica-Bold')
        self.text(self.W-390,self.H-96,'A1 landscape | '+scale,13)
        self.line((34,122),(self.W-34,122))
        self.text(55,96,self.p['building_id'],16,font='Helvetica-Bold')
        self.text(55,71,f"REV {self.s['revision']} | SOURCE WORKLINES | PROVISIONAL COORDINATION",12,ASSUMED,font='Helvetica-Bold')
        self.text(55,49,'S = captured source geometry | Dashed amber = proposal, TBD - resolve query | No fabrication or construction issue',11)
        self.text(self.W-650,95,'Source '+self.s['source_model_sha256'][:24],11)
        self.text(self.W-650,72,'Physical offsets, cuts and connection placement remain TBD.',11)
        self.text(self.W-200,49,f'Sheet {self.page} / {number}',12)

    def table(self,number,title,headers,widths,rows):
        page=0;y=0
        for row in rows:
            wrapped=[self.lines(str(t),w-20,11) for t,w in zip(row,widths)]
            height=max(len(t) for t in wrapped)*15+18
            if y-height<180:
                page+=1;self.start(number+f'{page:02}',title+f' ({page})');y=self.H-180;x=65
                for t,w in zip(headers,widths):self.text(x,y,t,13,font='Helvetica-Bold');x+=w
                y-=35
            x=65
            for lines,w in zip(wrapped,widths):
                for i,line in enumerate(lines):self.text(x,y-i*15,line,11)
                x+=w
            y-=height;self.line((65,y+12),(self.W-65,y+12),LIGHT,.5)


def plot(sh,number,title,members,axes=(0,1),features=(),model=None,plane_z=None):
    pts=[p for m in members for p in m['axis']]
    if not pts:return
    limits=[(min(p[i] for p in pts),max(p[i] for p in pts)) for i in axes]
    need=max(max(12,b-a)*72/d for (a,b),d in zip(limits,(sh.W-850,sh.H-520)))
    scale=next((v for v in (10,20,25,50,75,100,125,150,200,250,300,400,500,750,1000) if v>=need),math.ceil(need/100)*100)
    sh.start(number,title,'1:'+str(scale),[r['id'] for r in sh.s['requests'] if not r['confirmed']])
    tr,s=sh.grid_view(limits,axes,scale,origin=(210,310))
    groups=defaultdict(list)
    for member in members:
        p,q=[tr(v) for v in member['axis']]
        sh.line(p,q,BLUE if member['kind']=='brace' else INK,1.1 if member['kind']=='column' else .7)
        if math.dist(p,q)<2:
            sh.c.setStrokeColor(INK);sh.c.rect(p[0]-3,p[1]-3,6,6,stroke=1,fill=0)
        groups[member['mark']].append((member,p,q))
    reserved=[]
    for f in features:
        pp=[tr(p) for p in feature_vertices(f)];color=BLUE if f['confirmed'] else ASSUMED
        for p,q in zip(pp,pp[1:]+pp[:1]):sh.line(p,q,color,1.2,None if f['confirmed'] else [5,3])
        center=tuple(sum(p[i] for p in pp)/len(pp) for i in (0,1));reserved.append(center)
        sh.label(center[0],center[1],f['id']+(' / confirmed' if f['confirmed'] else ' / TBD'),10,color)
    sh.representative_marks(groups,30,reserved)
    if axes[1]==2:
        for item in model['levels']:
            z=item['elevation_in'];p=tr([limits[0][0],limits[0][0],z]);q=tr([limits[0][1],limits[0][1],z])
            sh.line(p,q,LIGHT,.4,[8,4]);sh.label(p[0]-125,p[1]+4,f"L{item['level']} {feet(z)}",10)
    visible_ids={m['id'] for m in members};occupied=list(reserved)
    labelled={r['member_id'] for r in sh.labels if r['sheet']==sh.current}
    for m in members:
        if m['id'] in labelled:occupied.append(tr([(a+b)/2 for a,b in zip(*m['axis'])]))
    count=0
    for joint in model['joints']:
        if plane_z is not None and abs(joint['point'][2]-plane_z)>1e-5:continue
        ends=[e for e in joint['member_ends'] if e['member_id'] in visible_ids]
        if len(ends)<2:continue
        p=tr(joint['point'])
        if not (210<=p[0]<=sh.W-590 and 310<=p[1]<=sh.H-220):continue
        if any(abs(p[0]-x)<190 and abs(p[1]-y)<100 for x,y in occupied):continue
        sh.callout(p,joint['id']+' / C-TBD',dx=20,dy=25);occupied.append(p);count+=1
        if count==8:break
    x=sh.W-570;y=sh.H-180
    notes=[model['basis'],'Grid letters/numbers are drawing identifiers assigned to source column worklines; dimensions are measured from the saved source coordinates.',
           'M marks identify source section groups. J marks identify captured workline junctions. C-TBD: select and locate the applicable source connection detail; see C-series schedules.',
           'MODEL-OPENINGS: dashed zones are illustrative proposals. Their dimensions are omitted until resolved in the request register.']
    y=sh.panel_notes(notes,x=x,y=y,width=485)-15
    sh.text(x,y,'SOURCE MEMBER MARKS',14,font='Helvetica-Bold');y-=28
    for mark,rows in sorted(groups.items()):
        m=rows[0][0];y=sh.wrap(x,y,f"{mark}  {m['profile_id'] or 'TBD'} / {m['kind']} / {len(rows)} in view",485,11,15)-8
    sh.text(210,165,'Full occurrence IDs, coordinates and analysis references: member_index.json. Diagram lines are source reference axes.',11,GREY)
    sh.views[-1]['member_ids']=[m['id'] for m in members]


def generate(package,state,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);model=build(package)
    model['source_model_sha256']=fingerprint(package)
    model['title']=package['building_id']
    model['profiles']=package['physical']['profiles']
    model['grids']={axis:[(chr(65+i) if axis=='x' and i<26 else str(i+1),pos) for i,pos in enumerate(values)] for axis,values in model['grids'].items()}
    sh=WorklineSheets(package,state,dest,model);sh.c.setTitle(package['building_id']+' - source workline coordination drawings')
    sh.start('G001','Drawing basis and recovered source coverage')
    y=sh.H-190
    counts=model['counts']
    for text in [f"{counts['drawn_occurrences']:,} captured member occurrences | {counts['levels']} levels | {counts['source_connection_records']} source connection schedules.",
                 'The supplied physical declarations contain unverified occurrence geometry. This set uses the actual captured model worklines, with source section assignments and level elevations. Group prototypes and catch-all declarations are not shown as building members.',
                 model['basis'],
                 'Plans show every captured level, source grid distances, member marks and joint references. Selected frame sections show the vertical arrangement. The connection schedules retain all source specifications, without claiming unresolved part geometry or joint applicability.',
                 'Requests are accepted provisionally and do not block the set. Dashed opening proposals carry no dimensions until the user confirms them. Source connection contradictions or missing physical detail need engineering reconciliation in an updated package.',
                 'G-series: basis and requests. S100: source base worklines. S101+: level plans. S201+: frame sections. M-series: source section counts. C-series: original connection specifications. A-series: opening coordinates or TBD.']:
        y=sh.wrap(65,y,text,sh.W-150,18,27)-30
    y=sh.wrap(65,y,f"Captured element coverage: {counts['drawn_occurrences']} drawn, {counts['excluded_or_unsupported']} excluded or unsupported. Source geometry and calculation files are unchanged.",sh.W-150,17,25)
    for i,r in enumerate(state['requests'],2):
        sh.start('G'+f'{i:03}',r['question']);y=sh.H-200
        for title,text in [('Request',r['id']+' / '+r['status']),('Proposal',r['proposal']),('Basis',r['evidence']),('Information',r.get('resolution') or (r['notes'][-1]['note'] if r['notes'] else 'Awaiting quantitative information. Drawings proceed provisionally.'))]:
            sh.text(65,y,title,17,font='Helvetica-Bold');y-=35;y=sh.wrap(65,y,text,sh.W-150,17,25)-40
    ms=model['members'];base_z=model['levels'][0]['elevation_in']
    base=[m for m in ms if m['kind']=='column' and min(p[2] for p in m['axis'])<=base_z+1e-5]
    plot(sh,'S100','Base column worklines',base,model=model,plane_z=base_z)
    for item in model['levels'][1:]:
        k=item['level'];selected=[m for m in ms if m['level']==k]
        plot(sh,f'S{100+k:03}',f"Level {k} framing / elevation {feet(item['elevation_in'])}",selected,
             features=[f for f in state['features'] if f['level']==k and f['plane']=='xy'],model=model,plane_z=item['elevation_in'])
    section=0
    for axis in (0,1):
        for name,pos in model['grids']['xy'[axis]]:
            selected=[m for m in ms if all(abs(p[axis]-pos)<1e-5 for p in m['axis'])]
            if not selected:continue
            section+=1
            plot(sh,f'S{200+section:03}',f"Frame section on {'XY'[axis]} grid {name}",selected,axes=(1-axis,2),model=model)
    groups=Counter((m['level'],m['mark'],m['kind'],m['profile_id']) for m in ms)
    sh.table('M','Source member section schedule',['Level','Mark','Kind','Section','Occurrences','Basis'],[110,110,200,260,150,sh.W-960],
             [(level,mark,kind,profile,n,'Captured section / source workline. Physical cut length and fit TBD.') for (level,mark,kind,profile),n in sorted(groups.items())])
    for i,record in enumerate(model['source_connection_records'],1):
        sh.start(f'C{i:03}','Source connection specification / applicability TBD');y=sh.H-190
        sh.text(65,y,record['id'],17,font='Helvetica-Bold');y-=45
        y=sh.wrap(65,y,'SOURCE RECORD - retained without redesign. Exact occurrence applicability, plate geometry, fastener set-out, weld location and related physical interfaces: TBD - resolve MODEL-CONNECTIONS.',sh.W-150,16,24)-35
        data=record['data'];priority=['type','section','components','design_basis','limit_state','demand','capacity','cited']
        for key in priority+[k for k in data if k not in priority]:
            if key=='id':continue
            if key not in data:continue
            value=data[key]
            fields=[(sub,content) for sub,content in value.items()] if isinstance(value,dict) else [('',value)]
            if y<245:sh.start(f'C{i:03}-{sh.page}','Source connection specification / continued');y=sh.H-190
            sh.text(65,y,key.replace('_',' ').upper(),14,font='Helvetica-Bold');y-=28
            for sub,content in fields:
                text=json.dumps(content,ensure_ascii=False,sort_keys=True) if isinstance(content,(dict,list)) else str(content)
                lines=sh.lines((sub.replace('_',' ')+': ' if sub else '')+text,sh.W-180,16)
                for line in lines:
                    if y<185:
                        sh.start(f'C{i:03}-{sh.page}','Source connection specification / continued');y=sh.H-190
                    sh.text(80,y,line,16);y-=23
            y-=18
    rows=[]
    for f in state['features']:
        dims=[feet(f[k]*12) if f['confirmed'] else 'TBD' for k in ('x_ft','y_ft','z_ft','width_ft','height_ft')]
        rows.append([f['id'],f['level'],f['kind'],*dims,'confirmed' if f['confirmed'] else 'resolve query'])
        if f['confirmed']:sh.dimensions.append(dict(kind='confirmed_opening',feature_id=f['id'],query_id=f['query_id'],values_ft={k:f[k] for k in ('x_ft','y_ft','z_ft','width_ft','height_ft')},confirmed=True))
    if rows:sh.table('A','Opening and coordination-zone schedule',['ID','Level','Type','X','Y','Z','Width','Height','Status'],[160,90,250,250,250,250,250,250,sh.W-1880],rows)
    sh.c.save()
    write_json(dest/'source_workline_model.json',model)
    write_json(dest/'member_index.json',model['members'])
    write_json(dest/'source_records.json',package['design_records'])
    report=dict(schema='steltic.drawing_set',revision=state['revision'],building_id=package['building_id'],
        source_model_sha256=fingerprint(package),decision_state_sha256=fingerprint({k:v for k,v in state.items() if k not in ('sheets','artifacts')}),
        drawing_status=state['drawing_status'],can_generate=True,open_requests=sum(not r['confirmed'] for r in state['requests']),
        representation='captured_source_worklines',counts=counts,sheets=sh.rows,dimensions=sh.dimensions,views=sh.views,labels=sh.labels,callouts=sh.callouts,
        pdf_sha256=hashlib.sha256((dest/'drawings.pdf').read_bytes()).hexdigest(),
        artifacts=['drawings.pdf','drawing_manifest.json','information_requests.json','source_workline_model.json','member_index.json','source_records.json'],
        limits=[model['basis'],'Opening proposals do not cut or redesign framing.','Source connection schedules are not resolved assembled connection drawings.'])
    write_json(dest/'drawing_manifest.json',report)
    return report
