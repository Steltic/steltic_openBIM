"""Vector coordination drawing sets from the physical package, with TBD masking."""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path

from .drawing_workflow import bounds,fingerprint,write_json
from .pilots.geometry import layer,COLORS,member_faces,part_faces


INK='#213b43'; MUTED='#66756e'; AMBER='#a26125'; BLUE='#37677c'


def ascii_text(value):
    return str(value).replace('\u2013','-').replace('\u2014','-').replace('\u2032',"'").replace('\u2033','"').replace('\u00d7','x').encode('ascii','replace').decode()


def feet(inches):
    n=round(abs(inches)*16)/16; ft=int(n//12); rem=n-ft*12
    return ('-' if inches<0 else '')+f'{ft}\'-{rem:g}"'


def feature_vertices(f):
    if 'source_vertices' in f: return f['source_vertices']
    x,y,z=[f[k]*12 for k in ('x_ft','y_ft','z_ft')]; w,h=f['width_ft']*12,f['height_ft']*12
    if f['plane']=='xy': return [[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]]
    if f['plane']=='xz': return [[x,y,z],[x+w,y,z],[x+w,y,z+h],[x,y,z+h]]
    return [[x,y,z],[x,y+w,z],[x,y+w,z+h],[x,y,z+h]]


def source_openings(package):
    """Keep source opening geometry and provenance separate from proposed overlays."""
    panels={p['id']:p for p in package['physical']['panels']}; out=[]
    for opening in package['physical'].get('openings',[]):
        vertices=opening['vertices']; lo=[min(p[i] for p in vertices)/12 for i in range(3)]
        hi=[max(p[i] for p in vertices)/12 for i in range(3)]; spans=[b-a for a,b in zip(lo,hi)]
        normal=min(range(3),key=lambda i:spans[i]); axes=[i for i in range(3) if i!=normal]
        out.append(dict(id='SRC-'+opening['id'],kind=opening.get('kind') or 'opening',plane=''.join('xyz'[i] for i in axes),
            level=opening.get('level',panels.get(opening.get('host_id'),{}).get('level',1)),x_ft=lo[0],y_ft=lo[1],z_ft=lo[2],
            width_ft=spans[axes[0]],height_ft=spans[axes[1]],query_id='Source design',confirmed=True,
            geometry_role='source_opening',source_vertices=vertices,
            design_record_ids=opening.get('design_record_ids',[])))
    return out


class Sheets:
    def __init__(self,package,state,dest):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.pagesizes import A3,landscape
        self.W,self.H=landscape(A3); self.c=Canvas(str(dest/'drawings.pdf'),pagesize=(self.W,self.H),pageCompression=1,invariant=1)
        self.c.setTitle(package['building_id']+' - coordination drawings')
        self.c.setAuthor('Steltic openBIM')
        self.p,self.s=package,state; self.rows=[]; self.dimensions=[]; self.page=0
        self.styles={'primary':.65,'secondary':.28,'walls':.35,'bracing':.5,'roof':.45,'interface':.4}

    def text(self,x,y,text,size=9,color=INK,font='Helvetica'):
        self.c.setFillColor(color); self.c.setFont(font,size); self.c.drawString(x,y,ascii_text(text))

    def lines(self,text,width,size=9):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        words=[]
        for word in ascii_text(text).split():
            part=''
            for char in word:
                if part and stringWidth(part+char,'Helvetica',size)>width:
                    words.append(part); part=''
                part+=char
            if part: words.append(part)
        lines=[]; line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if stringWidth(candidate,'Helvetica',size)>width and line:
                lines.append(line); line=word
            else: line=candidate
        if line: lines.append(line)
        return lines

    def wrap(self,x,y,text,width,size=9,leading=13):
        for line in self.lines(text,width,size):
            self.text(x,y,line,size); y-=leading
        return y

    def start(self,number,title,scale='NTS',refs=()):
        if self.page: self.c.showPage()
        self.page+=1; self.current=number
        self.rows.append(dict(number=number,title=title,page=self.page,scale=scale,query_ids=list(refs)))
        c=self.c; c.setStrokeColor(INK); c.setLineWidth(.7); c.rect(22,22,self.W-44,self.H-44)
        self.text(36,self.H-46,'STELTIC / OPENBIM',11,font='Helvetica-Bold')
        self.text(36,self.H-70,title,18,font='Helvetica-Bold')
        self.text(self.W-220,self.H-46,number,16,font='Helvetica-Bold')
        self.text(self.W-220,self.H-66,'Scale '+scale+' / A3 landscape',8)
        c.line(22,78,self.W-22,78)
        self.text(36,59,self.p['building_id'],10,font='Helvetica-Bold')
        self.text(36,42,'REV '+str(self.s['revision'])+' | '+self.s['drawing_status'].upper()+' | Source '+self.s['source_model_sha256'][:16],8)
        self.text(36,29,'Dashed amber = proposal. TBD - resolve query. Source framing is retained; opening proposals do not cut or redesign it.',7,AMBER)
        self.text(self.W-170,55,'Sheet '+str(self.page)+' | '+number,9)
        self.text(self.W-170,38,'Dimensions: ft-in unless noted',7)

    def notes(self,features=()):
        x=self.W-235; y=self.H-110
        self.text(x,y,'DRAWING INFORMATION',10,font='Helvetica-Bold'); y-=22
        y=self.wrap(x,y,'Proposals are accepted for this drawing issue. Items remain open until quantitative information is supplied and applied.',190,8,11)-10
        for r in self.s['requests']:
            label=r['id']+' / '+('RESOLVED' if r['confirmed'] else 'TBD - resolve query')
            self.text(x,y,label,7,BLUE if r['confirmed'] else AMBER,font='Helvetica-Bold'); y-=12
            y=self.wrap(x,y,r['question'],190,7,10)-9
        if features:
            y-=4; self.text(x,y,'OPENING / ZONE SYMBOLS',8,font='Helvetica-Bold'); y-=15
            for f in features[:9]:
                self.text(x,y,f['id']+' : '+f['query_id']+(' / confirmed' if f['confirmed'] else ' / TBD'),7); y-=11
            if len(features)>9: self.text(x,y,'See opening schedule for all symbols.',7)

    def plot(self,number,title,members,panels=(),axes=(0,1),features=(),show_extent=False):
        pts=[p for m in members for p in m['axis']]+[p for panel in panels for p in panel['vertices']]
        if not pts: pts=[[0,0,0],[12,12,12]]
        limits=[(min(p[i] for p in pts),max(p[i] for p in pts)) for i in axes]
        x0,y0,w,h=75,155,self.W-365,self.H-275
        rotated=axes==(0,1) and (limits[1][1]-limits[1][0])>1.5*max(1,limits[0][1]-limits[0][0])
        if rotated: axes=(1,0); limits.reverse()
        dx,dy=[max(12,b-a) for a,b in limits]
        need=max(dx*72/w,dy*72/h)
        denom=next((s for s in (5,10,20,25,50,75,100,150,200,250,300,400,500,750,1000) if s>=need),math.ceil(need/100)*100)
        scale=72/denom; ox=x0+(w-dx*scale)/2; oy=y0+(h-dy*scale)/2
        def project(p): return (ox+(p[axes[0]]-limits[0][0])*scale,oy+(p[axes[1]]-limits[1][0])*scale)
        self.start(number,title+(' - rotated plan' if rotated else ''),'1:'+str(denom),[r['id'] for r in self.s['requests'] if not r['confirmed']])
        c=self.c; c.saveState(); clip=c.beginPath(); clip.rect(x0-5,y0-5,w+10,h+10); c.clipPath(clip,stroke=0)
        seen=set()
        for m in members:
            a,b=[project(p) for p in m['axis']]; key=tuple(sorted((a,b)))
            if key in seen: continue
            seen.add(key); k=layer(m['kind']); c.setStrokeColor(COLORS.get(k,BLUE)); c.setLineWidth(self.styles.get(k,.3))
            if math.dist(a,b)<.5: c.rect(a[0]-1.5,a[1]-1.5,3,3,fill=0)
            else: c.line(*a,*b)
        for p in panels:
            c.setStrokeColor('#89968b'); c.setLineWidth(.4)
            poly=[project(v) for v in p['vertices']]; path=c.beginPath(); path.moveTo(*poly[0])
            for v in poly[1:]+poly[:1]: path.lineTo(*v)
            c.drawPath(path)
        projected_features={}
        for f in features:
            poly=[project(v) for v in feature_vertices(f)]
            key=(tuple(poly),f['confirmed'])
            if key in projected_features: projected_features[key][1].append(f['id'])
            else: projected_features[key]=[f,[f['id']],poly]
        for f,ids,poly in projected_features.values():
            c.setStrokeColor(BLUE if f['confirmed'] else AMBER); c.setLineWidth(1); c.setDash([] if f['confirmed'] else [3,2])
            path=c.beginPath(); path.moveTo(*poly[0])
            for v in poly[1:]+poly[:1]: path.lineTo(*v)
            c.drawPath(path); c.setDash([])
            px,py=poly[0]; label=','.join(ids)+(' / source' if f.get('geometry_role')=='source_opening' else ' / confirmed' if f['confirmed'] else ' / TBD')
            from reportlab.pdfbase.pdfmetrics import stringWidth
            c.setFillColor('#ffffff'); c.rect(px+2,py+3,stringWidth(label,'Helvetica',6)+3,9,stroke=0,fill=1)
            self.text(px+3,py+5,label,6,BLUE if f['confirmed'] else AMBER)
        c.restoreState(); self.notes(features)
        # Overall source workline dimensions only. Ambiguous frame set-out stays TBD.
        if show_extent:
            unresolved=next((r['id'] for r in self.s['requests'] if r['id'] in ('CFS16-FRAME-SETOUT','CFS8-FLOOR') and not r['confirmed']),None)
            for axis_index,(a,b) in enumerate(limits):
                value='TBD - resolve '+unresolved if unresolved else feet(b-a)
                if axis_index==0:
                    yy=oy-24; c.setStrokeColor(MUTED); c.setLineWidth(.4); c.line(ox,yy,ox+dx*scale,yy)
                    c.line(ox,yy-4,ox,yy+4); c.line(ox+dx*scale,yy-4,ox+dx*scale,yy+4); self.text(ox+dx*scale/2-30,yy+5,value,8)
                else:
                    self.text(x0,y0-50,'Overall '+('XYZ'[axes[1]])+' workline extent: '+value,8)
                if not unresolved: self.dimensions.append(dict(sheet=number,kind='source_workline_extent',axis=axes[axis_index],value_in=b-a,evidence='physical member/panel source axes'))
        self.text(x0,y0-68,'View axes: '+ 'XYZ'[axes[0]]+' right / '+'XYZ'[axes[1]]+' up. Source worklines shown; profiles are in the member schedule.',8,MUTED)

    def tables(self,rows,headers,widths,prefix,title,perpage=33):
        page=0; y=0; count=perpage
        for row in rows or [['']*len(headers)]:
            cells=[self.lines(text,width-12,7) for text,width in zip(row,widths)]
            height=max(18,max(len(lines) for lines in cells)*9+9)
            if y-height<100 or count>=perpage:
                page+=1; count=0; self.start(prefix+str(page).zfill(2),title+f' ({page})')
                y=self.H-110; x0=40
                for header,width in zip(headers,widths): self.text(x0,y,header,9,font='Helvetica-Bold'); x0+=width
                y-=22
            x0=40
            for lines,width in zip(cells,widths):
                for index,line in enumerate(lines): self.text(x0,y-index*9,line,7)
                x0+=width
            y-=height; count+=1
            self.c.setStrokeColor('#d5ddd5'); self.c.setLineWidth(.3); self.c.line(36,y+10,self.W-36,y+10)

    def details(self):
        ph=self.p['physical']; joints={j['id']:j for j in ph['joints']}; profiles={p['id']:p for p in ph['profiles']}; groups=defaultdict(list)
        for c in ph['connections']: groups[c.get('detail_ref',{}).get('id',c['id'])].append(c)
        for page,offset in enumerate(range(0,len(groups),4),1):
            self.start('S3'+str(page).zfill(2),'Connection families - source geometry and TBD interfaces')
            for idx,(family,cs) in enumerate(list(groups.items())[offset:offset+4]):
                x=40+(idx%2)*550; top=self.H-110-(idx//2)*325; w=520; h=235
                self.text(x,top,family,10,font='Helvetica-Bold'); self.text(x,top-16,f'{len(cs)} occurrences / representative {cs[0]["id"]}',7)
                c=next((c for c in cs if c.get('parts')),cs[0]); center=joints[c['joint_id']]['point']; crop=[(v-45,v+45) for v in center]
                faces=[]
                for m in ph['members']:
                    if m.get('profile_id') not in profiles or not m.get('end_offsets'): continue
                    try: fs=member_faces(m,profiles,crop)
                    except (KeyError,ValueError,TypeError): fs=[]
                    faces.extend((f,False) for f in fs)
                for part in c.get('parts',[]):
                    try: faces.extend((f,True) for f in part_faces(part,profiles))
                    except (KeyError,ValueError,TypeError): pass
                def raw(p):
                    a,b,z=[p[i]-center[i] for i in range(3)]; return [a*.8-b*.6,z*.9-a*.26-b*.35]
                pp=[raw(p) for face,_ in faces for p in face]
                if pp:
                    bx=[(min(p[i] for p in pp),max(p[i] for p in pp)) for i in range(2)]
                    sc=min((w-50)/max(1,bx[0][1]-bx[0][0]),(h-45)/max(1,bx[1][1]-bx[1][0]))
                    canvas=self.c; canvas.saveState(); cp=canvas.beginPath(); cp.rect(x,top-h,w,h-25); canvas.clipPath(cp,stroke=0)
                    for face,part in sorted(faces,key=lambda f:f[1]):
                        pts=[(x+w/2+(raw(p)[0]-(bx[0][0]+bx[0][1])/2)*sc,top-h/2-10+(raw(p)[1]-(bx[1][0]+bx[1][1])/2)*sc) for p in face]
                        canvas.setStrokeColor(AMBER if part else '#8599a2'); canvas.setLineWidth(.3 if part else .14)
                        path=canvas.beginPath(); path.moveTo(*pts[0])
                        for v in pts[1:]+pts[:1]: path.lineTo(*v)
                        canvas.drawPath(path)
                    canvas.restoreState()
                else: self.text(x+35,top-95,'Source detail reference; geometric set-out TBD - resolve query.',9,AMBER)
                self.text(x,top-h-10,'Part set-out / cuts / unresolved attachments: TBD - resolve query. Detail view NTS.',7,AMBER)
                self.wrap(x,top-h-23,'Source: '+', '.join(c.get('design_record_ids',[])),w,7,9)
                self.c.setStrokeColor('#d5ddd5'); self.c.line(x,top-h-45,x+w,top-h-45)


def generate(package,state,dest):
    if state.get('design_scenario') and state.get('drawing_status')=='design_test':
        from .design_pdf import generate as design_generate
        return design_generate(package,state,dest)
    if not package['physical']['members']:
        from .design_scenarios import available_scenario
        from .review_cases import CASES
        if available_scenario(package) in CASES:
            from .review_provisional import generate as provisional
            return provisional(package,state,dest)
    from .source_worklines import required,physical_view
    if required(package):
        from .source_workline_pdf import generate as workline_generate
        return workline_generate(package,state,dest)
    if package['physical']['members'] and all(m.get('status')=='declared' for m in package['physical']['members']):
        from .physical_pdf import generate as physical_generate
        return physical_generate(package,state,dest)
    dest=Path(dest); dest.mkdir(parents=True,exist_ok=True); sh=Sheets(package,state,dest); ph=physical_view(package)
    members=ph['members']; levels=sorted({m.get('level',1) for m in members}); requests=state['requests']
    all_features=source_openings(package)+state['features']
    sh.start('G001','Drawing basis and issue register')
    y=sh.H-120
    for text in [f"Revision {state['revision']} - {state['drawing_status']}. {len(members):,} physical members; {len(ph['connections']):,} located connection specifications.",
                 'Issue purpose: engineering coordination drawings with explicitly provisional information. Information requests do not hold up this drawing set.',
                 'Solid framing follows the supplied design. Dashed amber symbols and zones are proposals. Every unconfirmed opening, position and unresolved detail is labelled TBD - resolve query, with no quantitative dimension string.',
                 'Accepting a proposal for drawing does not confirm its numbers. Confirmed opening layouts update the drawing overlay and its dimension schedule. They do not cut members or certify opening support framing; source design follow-up remains separate.',
                 'This set includes base/framing plans for every supplied level, roof plan, elevations, every placed connection family, member schedules, opening/zone schedules and the information-request register. Views use source worklines; profiles, connection references and delegated scope are retained.',
                 'Changes to the physical source package create a new revision and reset provisional assumptions; prior drawing sets and answers stay in revision history.']:
        y=sh.wrap(42,y,text,1080,11,17)-18
    sh.text(42,y,'Sheet series',12,font='Helvetica-Bold'); y-=26
    for row in ('G001 basis | G002+ information requests','S100 base / support plan | S101+ level framing | S190 roof','S201/202 elevations | S301+ connection families','S401+ members | S501+ connection register | A601+ openings / zones'):
        sh.text(42,y,row,11); y-=23
    sh.text(42,y-18,'Full source and revision hashes are in drawing_manifest.json.',9,MUTED)
    page=2; y=0
    for r in requests:
        fields=[(r['question'],11,15),('Proposal: '+r['proposal'],9,13),('Basis: '+r['evidence'],8,11)]
        if r.get('resolution'): fields.append(('Quantitative resolution: '+r['resolution'],9,13))
        if r['notes']: fields.append(('Latest information: '+r['notes'][-1]['note'],8,11))
        block=52+sum(len(sh.lines(text,1080,size))*leading+6 for text,size,leading in fields)
        if y<95+min(block,600):
            sh.start('G'+str(page).zfill(3),'Information requests - accepted provisional proposals'); page+=1; y=sh.H-115
        sh.text(42,y,r['id']+' / '+r['assignee'].replace('_',' ')+' / '+r['status'],11,AMBER,font='Helvetica-Bold'); y-=22
        for text,size,leading in fields:
            for line in sh.lines(text,1080,size):
                if y<130:
                    sh.start('G'+str(page).zfill(3),'Information requests - '+r['id']+' continued'); page+=1; y=sh.H-115
                sh.text(42,y,line,size); y-=leading
            y-=6
        sh.text(42,y,'Dimensions: '+('see confirmed opening schedule' if r['confirmed'] else 'TBD - resolve query')+' | Provisional drawings proceed.',8,AMBER); y-=30
    base=[m for m in members if m.get('level',1)==1 and m['kind'] in ('column','chord','endwall_post','bottom_track')]
    sh.plot('S100','Base and support worklines',base or [m for m in members if m.get('level',1)==1],axes=(0,1),show_extent=True)
    for level in levels:
        ms=[m for m in members if m.get('level',1)==level]
        panels=[p for p in ph['panels'] if p.get('level',1)==level and p['kind'] in ('floor','deck_envelope')]
        fs=[f for f in all_features if f['level']==level]
        sh.plot('S'+str(100+level),'Level '+str(level)+' framing and coordination openings',ms,panels,features=fs,show_extent=True)
    roof=[p for p in ph['panels'] if p['kind'] in ('roof','truss_envelope')]
    sh.plot('S190','Roof framing and delegated interfaces',[m for m in members if m.get('level',1)==max(levels)],roof,features=[f for f in all_features if 'valley' in f['kind']],show_extent=True)
    sh.plot('S201','X-Z framing elevation',members,roof,axes=(0,2),features=[f for f in all_features if f['plane']=='xz'])
    sh.plot('S202','Y-Z framing elevation',members,roof,axes=(1,2),features=[f for f in all_features if f['plane']=='yz'])
    sh.details()
    grouped=Counter((m.get('level',1),m['kind'],m.get('profile_id') or 'TBD') for m in members)
    sh.tables([(str(l),kind,profile,str(n),'Source profile / length and final set-out TBD') for (l,kind,profile),n in sorted(grouped.items())],
              ['Level','Member family','Profile','Count','Drawing basis'],[60,190,260,60,540],'S4','Member schedule')
    groups=defaultdict(list)
    for c in ph['connections']: groups[c.get('detail_ref',{}).get('id',c['id'])].append(c)
    sh.tables([(family,str(len(cs)),', '.join(cs[0].get('design_record_ids',[]))[:210],'TBD - resolve query; source specification retained') for family,cs in groups.items()],
              ['Connection family','Count','Representative source records','Placement/detail status'],[235,60,490,325],'S5','Connection occurrence register',25)
    features=[]
    for f in all_features:
        if f['confirmed']:
            dims=[feet(f[k]*12) for k in ('x_ft','y_ft','z_ft','width_ft','height_ft')]
            sh.dimensions.append(dict(kind='source_opening' if f.get('geometry_role')=='source_opening' else 'confirmed_opening',feature_id=f['id'],query_id=f['query_id'],values_ft={k:f[k] for k in ('x_ft','y_ft','z_ft','width_ft','height_ft')},confirmed=True))
        else: dims=['TBD']*5
        features.append([f['id'],str(f['level']),f['kind'],*dims,f['query_id']+(' / confirmed' if f['confirmed'] else ' / resolve query')])
    if features: sh.tables(features,['ID','Level','Opening / zone','X','Y','Base Z','Width','Height','Information request'],[75,45,135,95,95,95,95,95,285],'A6','Opening and coordination-zone schedule')
    sh.c.save()
    report=dict(schema='steltic.drawing_set',revision=state['revision'],building_id=package['building_id'],source_model_sha256=fingerprint(package),decision_state_sha256=fingerprint({k:v for k,v in state.items() if k not in ('sheets','artifacts')}),
        drawing_status=state['drawing_status'],can_generate=True,open_requests=sum(not r['confirmed'] for r in requests),sheets=sh.rows,dimensions=sh.dimensions,
        pdf_sha256=hashlib.sha256((dest/'drawings.pdf').read_bytes()).hexdigest(),omitted_dimensions_policy='Every unconfirmed proposed feature has TBD entries; known source workline extents are distinguished from proposals.',
        limits=['Coordination opening overlays do not cut or redesign structural members.','Connection family views use source geometry and retain unresolved details as TBD.','No new structural analysis or fabrication release.'])
    write_json(dest/'drawing_manifest.json',report)
    return report
