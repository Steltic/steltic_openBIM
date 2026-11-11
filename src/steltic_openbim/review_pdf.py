"""Complete paginated A1 design drawing sets for the varied review cases."""
import math,json,hashlib
from collections import defaultdict
from pathlib import Path
from .review_cases import build_model
from .connection_details import prepare
from .assembly_pdf import draw_assembly
from .design_pdf import DesignSheets,feet,physical_axis,wall_plan_sections,section,specifications,compact_references,opening_level,INK,BLUE,GREY,LIGHT,ASSUMED
from .drawing_workflow import write_json,fingerprint
from .drawing_pdf import feature_vertices

def refs(values):
    return compact_references(values)


def omitted_detail_families(pilot):
    """User-selected PDF scope; the physical model and IFC stay complete."""
    return {'hr27':{'review_core_base','review_core_wall'},
            'hr28':{'review_edge_bars','review_edge_chord_corner'}}.get(pilot,set())


def scale_for(bounds,width=1530,height=1050):
    return max(15,math.ceil(max((bounds[0][1]-bounds[0][0])*72/width,(bounds[1][1]-bounds[1][0])*72/height)/5)*5)


def is_base_connection(connection,lookup):
    family=connection['detail_ref']['id'];primary=lookup[connection['member_ids'][0]]
    explicit=family.endswith('_base') or family in ('hr_column_base','hr_embedded_column_base','sill_anchor_group','review_rod_foundation')
    post_base=family in ('review_cfs_post','review_sliding_post','test_walkway_support') and abs(connection['point'][2]-min(q[2] for q in primary['axis']))<.1
    sill=family=='review_cfs_sill' and primary['level']==1
    return explicit or post_base or sill


def base_members(model):
    """All physical support bases, independent of the deepest embedment datum."""
    lookup={m['id']:m for m in model['members']};selected=set()
    for c in model['connections']:
        if is_base_connection(c,lookup):selected.update(c['member_ids'])
    datum=next((z for k,_,z in model['levels'] if k==0),0)
    result=[]
    for m in model['members']:
        a,b=physical_axis(m);lo,hi=sorted((a[2],b[2]));vertical=hi-lo>2 and math.dist(a[:2],b[:2])<1
        at_datum=vertical and lo<=datum+36 and hi>=datum-36
        track=m['kind'] in ('bottom_track','ordinary_track') and m['level']==1
        if (m['id'] in selected and vertical) or at_datum or track:result.append(m)
    return result

def plan(sh,k,kind):
    m=sh.m;bounds=[tuple(m['bounds'][i]) for i in (0,1)];grids=None
    if m['pilot'] in ('cfs10','cfs18') and k in (1,2) and kind=='floor':
        # Enlarge the separated wing and dimension its own worklines and gap.
        if m['pilot']=='cfs10':
            bounds=[(1200,2168),(480,960)]
            grids={'x':[('9',1200),('O1',1208),('O2',2168)],'y':[('OA',480),('OB',720),('C',960)]}
        else:
            bounds=[(1800,2400),(0,600)]
            grids={'x':[('13',1800),('M1',1818),('M2',2382),('17',2400)],'y':[('A',0),('MA',24),('MB',208),('MC',392),('MD',576),('B',600)]}
    scale=scale_for(bounds);tr,s=sh.grid_view(bounds,(0,1),scale,(180,340),grids=grids)
    level=next((z for n,_,z in m['levels'] if n==k),0);selected=[]
    bases={v['id'] for v in base_members(m)} if kind=='base' else set()
    for member in m['members']:
        a,b=physical_axis(member);z0,z1=min(a[2],b[2]),max(a[2],b[2]);vertical=abs(z1-z0)>2 and math.dist(a[:2],b[:2])<1
        if kind=='base':use=member['id'] in bases
        elif kind=='walls':use=member['level']==k and member['kind'] in ('stud','chord','hold_down_rod','bottom_track','top_track','ordinary_track','strap','opening_jamb','opening_header','opening_sill','column','walkway_post')
        elif kind=='roof':use=(member['level']==k and z1>=level-40) or (member['level']==1 and sh.m['pilot'] in ('cfs17','cfs19','cfs25','cfs26','cfs27','cfs28','cfs30','hr33') and member['kind'] not in ('girt','stud','opening_jamb','opening_header'))
        else:use=member['level']==k and (z0>=level-40 or vertical and z1>=level-40)
        if use:selected.append(member)
    for p in m['panels']:
        if p['kind'] in ('floor','roof') and p['level']==k:
            vertices=[tr(q) for q in p['vertices']]
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):sh.line(a,b,LIGHT,.7)
    reserved=[];opening_hosts={p['id']:p for p in m['panels']}
    for f in m['openings']:
        if opening_level(f,opening_hosts)==k and f['plane']=='xy':
            pts=[tr(q) for q in feature_vertices(f)];reserved.append(tuple(sum(q[i] for q in pts)/len(pts) for i in (0,1)))
    groups=sh.draw_members(selected,tr,(0,1),s);sh.representative_marks(groups,28,reserved)
    selected_ids={q['id'] for q in selected};seen=set();points=[];lookup={v['id']:v for v in m['members']}
    for c in m['connections']:
        if kind=='base' and not is_base_connection(c,lookup):continue
        if kind=='floor' and not level-40<=c['point'][2]<=level+6:continue
        if kind=='roof' and c['point'][2]<level-40:continue
        if c['drawing_ref'] in seen or not any(i in selected_ids for i in c['member_ids']):continue
        p=tr(c['point'])
        if any(math.dist(p,q)<100 for q in points):continue
        sh.callout(p,c['drawing_ref'],35,30);seen.add(c['drawing_ref']);points.append(p)
        if len(seen)>=10:break
    for f in m['openings']:
        if opening_level(f,opening_hosts)!=k:continue
        if f['plane']=='xy':sh.opening(f,tr,9)
        elif kind=='walls' or kind=='base':
            vertices=feature_vertices(f);pa,pb=tr(vertices[0]),tr(vertices[1]);sh.line(pa,pb,ASSUMED,2)
    sh.panel_notes([f'{kind.upper()} / '+next((label for n,label,z in m['levels'] if n==k),str(k)),
        'Source grids and workline dimensions. Steel sections, floor-edge geometry and opening positions are listed in the member/opening schedules.',
        'A = adopted fictional input. Source member selection, fastener specification and original design records remain traceable. No new capacity check is implied.',
        f'{len(selected):,} physical members in this view; repeated marks identify like members. Exact instance axes and joint references: member_index.json.',
        'Sections S2xx use named grid / wall planes. Every C-series sheet contains an assembled elevation, a true section and an isometric with parts and attachments.',
        'Openings S3xx; source specifications S7xx. Additional complete geometry and assumption records accompany this PDF.'],x=sh.W-540,width=460)
    if not selected:raise ValueError('Empty review plan '+sh.current)


def core_plan(sh):
    selected=[m for m in sh.m['members'] if m['level']==1 and m['kind'] in ('composite_wall','wall_closure')]
    groups=defaultdict(list)
    for m in selected:
        if m.get('core_group'):groups[m['core_group']].extend(q for poly in wall_plan_sections(m,sh.profiles) for q in poly)
    pts=[q for rows in groups.values() for q in rows]
    bounds=[(min(q[i] for q in pts)-36,max(q[i] for q in pts)+36) for i in (0,1)]
    scale=scale_for(bounds,1450,1000);tr,s=sh.grid_view(bounds,(0,1),scale,(180,380))
    marks=sh.draw_members(selected,tr,(0,1),s);sh.representative_marks(marks,12)
    for name,rows in sorted(groups.items()):
        x0,x1=min(q[0] for q in rows),max(q[0] for q in rows);y0,y1=min(q[1] for q in rows),max(q[1] for q in rows)
        sh.dim(tr([x0,y0,0]),tr([x1,y0,0]),-25,value=x1-x0,basis='S',ref=name+' outer X extent')
        sh.dim(tr([x0,y0,0]),tr([x0,y1,0]),25,value=y1-y0,basis='S',ref=name+' outer Y extent')
        sh.label(*tr([(x0+x1)/2,(y0+y1)/2,0]),name+' core pier',13,BLUE)
    sh.panel_notes(['L1 core footprint from the actual steel plate profiles; source outside dimensions shown.',
        'Each pier has two steel faceplates and a source 1 in free-end closure. Overall wall thickness is 18 in; concrete infill is omitted from this steel set-out view.',
        'Faceplate thickness changes by storey; see the member schedule, pier source records and the separate assembled core details.',
        'The framing plans show these same footprints at each storey. Coupling-beam embedments, ties, diaphragm studs, panel splices and caps each have their own located C-series details.',
        'A: story splices, non-load-bearing roof caps and local fit proposals remain explicitly identified. This drawing does not certify new capacity or fabrication.'],x=sh.W-540,width=460)

def generate(package,state,dest):
    if not all(r['confirmed'] for r in state['requests']):raise ValueError('Adopt the fictional answers before dimensioned review drawings')
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);m=build_model(package,state);assemblies=prepare(m,package);sh=DesignSheets(package,state,dest,m);jobs=[]
    omitted=omitted_detail_families(m['pilot'])
    published=[a for a in assemblies if a['family'] not in omitted]
    sh.excluded_detail_refs={a['reference'] for a in assemblies if a['family'] in omitted}
    def refs(values):return compact_references([r for r in values if r not in sh.excluded_detail_refs])
    def queue(number,title,fn,scale='NTS'):jobs.append((number,title,scale,fn))
    def cover():
        sh.text(90,sh.H-220,'DIMENSIONED DESIGN / ASSEMBLED CONNECTIONS',29,font='Helvetica-Bold')
        y=sh.H-290
        for line in [m['title'],f'{len(m["members"]):,} members | {len(m["connections"]):,} connection occurrences | {len(published)} published assembled variants',
            'FICTIONAL REVIEW SET - source designs preserved; explicit adopted inputs marked A.',
            'The C-series shows the connected members, plates, brackets, fastener groups and weld interfaces together. The section is a geometric cut through the same assembly.',
            'Source model and all original design records are retained. Adopted geometry has not been rerun through strength, drift, fatigue, foundation or supplier qualification checks.',
            'Workline dimensions are engineering design dimensions. Procurement lengths, weld procedures and fabrication tolerances require the later shop-drawing stage.',
            'Review the answer register first, then building plans and sections, followed by the joint variants. Each occurrence points to its own applicable assembled detail.',
            'SOURCE SHA256: '+fingerprint(package),
            'MODEL FILES: design_model.json, member_index.json, connection_assemblies.json, source_records.json and adopted_answers.json']:
            y=sh.wrap(90,y,line,2050,17,25)-28
        if omitted:
            y=sh.wrap(90,y,'PDF scope: '+('core base/wall detail sheets and standalone core views' if m['pilot']=='hr27' else 'concrete edge-bar and slab-edge detail sheets')+' omitted at user request. Their BIM geometry and original source records remain complete.',2050,17,25)-28
        sh.text(90,220,'Registered fictional review case. Read the adopted answers and source applicability schedules with the assembled details.',14,BLUE)
    queue('G001','Review basis and drawing contents',cover)
    # Assumptions and source-exclusion registers are fully paginated.
    blocks=[]
    for item in m['assumptions']:blocks.append((item['id'],'A - '+item['answer']))
    if m['excluded_analysis_elements']:blocks.append(('ANALYSIS IDEALIZATIONS',str(len(m['excluded_analysis_elements']))+' analysis strips/rigid zones/equivalent members have been replaced by the physical wall or truss system. Every excluded ID and replacement reason is retained in design_model.json.'))
    def text_pages(blocks,prefix,start,title):
        pages=[];current=[];used=0
        for label,text in blocks:
            lines=sh.lines(text,2050,13)
            for offset in range(0,len(lines),45):
                chunk=lines[offset:offset+45];height=50+len(chunk)*20
                if used+height>1250 and current:pages.append(current);current=[];used=0
                current.append((label+(' (continued)' if offset else ''),chunk));used+=height
        if current:pages.append(current)
        for i,rows in enumerate(pages):
            def draw(rows=rows):
                y=sh.H-190
                for label,lines in rows:
                    sh.text(80,y,label,14,font='Helvetica-Bold');y-=28
                    for line in lines:sh.text(80,y,line,13);y-=20
                    y-=22
                if y<145:raise ValueError('Text register overflow')
            queue(f'{prefix}{start+i:03}',title+f' / {i+1}',draw)
    text_pages(blocks,'G',2,'Adopted answers and physical scope')
    queue('S001','Grid and base set-out',lambda:plan(sh,0,'base'))
    if m['pilot']=='hr14':queue('S100','B1 auxiliary gravity framing',lambda:plan(sh,0,'floor'))
    last=max(k for k,_,_ in m['levels']);single=m['pilot'] in ('cfs17','cfs19','cfs25','cfs26','cfs27','cfs28','cfs30','hr33')
    if single:queue('S101','Roof framing and bracing plan',lambda:plan(sh,1,'roof'))
    else:
        for k,label,z in m['levels']:
            if k<=0:continue # Base/cellar support datums are covered by S001 and the sections.
            if m['pilot']=='hr31' and k==3:continue # Ridge is a datum; the hall roof is the level-2 framing assembly.
            queue(f'S{100+k:03}',label+' framing plan',lambda k=k:plan(sh,k,'roof' if k==last else 'floor'))
        if m['pilot'].startswith('cfs'):
            for k in range(1,last+1):queue(f'S{130+k:03}',f'Storey {k} wall framing plan',lambda k=k:plan(sh,k,'walls'))
    if m['pilot']!='hr27' and any(v['kind']=='composite_wall' for v in m['members']):
        queue('S150','Composite core footprint / L1',lambda:core_plan(sh))
    cuts=[]
    for normal in (0,1):
        values=[v for _,v in m['grids']['xy'[normal]]]
        for value in (values[0],values[len(values)//2]):cuts.append((normal,value,1-normal,None,f'Grid plane {"XY"[normal]}={feet(value)}'))
    for view in m.get('extra_views',[]):
        if m['pilot']=='hr27' and view['title'].startswith('Composite core'):continue
        along=0 if view['direction']=='X' else 1;cuts.append((1-along,view['station_in'],along,view.get('range_in'),view['title']))
    for member in m['members']:
        if m['pilot']=='hr27':continue
        if member['kind']!='composite_wall' or member['level']!=1:continue
        along=max(range(2),key=lambda i:abs(member['local_y'][i]));normal=1-along;station=member['axis'][0][normal]
        cuts.append((normal,station,along,None,'Composite core plane '+str('XY'[normal])+'='+feet(station)))
    for wall in m.get('wall_layouts',[]):
        along=0 if wall['direction']=='X' else 1
        if wall['level']!=1 or not wall['runs']:continue
        station=wall['runs'][0]['position_in'];ran=[min(r['start_in'] for r in wall['runs']),max(r['end_in'] for r in wall['runs'])];cuts.append((1-along,station,along,ran,'Wall '+wall['line']))
    seen=set()
    for normal,station,along,ran,title in cuts:
        key=(normal,round(station,3),tuple(ran or []))
        if key in seen:continue
        seen.add(key);bounds=(tuple(ran or m['bounds'][along]),tuple(m['bounds'][2]));scale=scale_for(bounds,1450,1030);index=len(seen)
        queue(f'S{200+index:03}',title+' / section and elevation',lambda normal=normal,station=station,along=along,title=title,scale=scale,bounds=bounds:section(sh,normal,station,along,title,scale,bounds,(180,340),12),'1:'+str(scale))
    # Flexible rows retain every item and reference without truncation.
    def tables(headers,rows,widths,prefix,start,title,font=11):
        pages=[];current=[];height=0
        for row in rows:
            cells=[sh.lines(str(value),width-16,font) for value,width in zip(row,widths)];rh=max(30,max(map(len,cells))*(font+3)+12)
            if height+rh>1190 and current:pages.append(current);current=[];height=0
            current.append((cells,rh));height+=rh
        if current:pages.append(current)
        for i,items in enumerate(pages):
            def draw(items=items):
                x=70;y=sh.H-190
                for name,w in zip(headers,widths):sh.text(x+8,y,name,font,font='Helvetica-Bold');x+=w
                y-=30
                for row,(cells,rh) in enumerate(items):
                    if row%2==0:sh.c.setFillColor('#f1f4f4');sh.c.rect(70,y-rh+10,sum(widths),rh,fill=1,stroke=0)
                    x=70
                    for col,(lines,w) in enumerate(zip(cells,widths)):
                        for j,line in enumerate(lines):
                            if prefix=='S' and start==301 and col>=4:
                                sh.opening_cell(x+8,y-j*(font+3),line,font,opening_by_id[cells[0][0]],
                                                ('x_ft','y_ft','z_ft','width_ft','height_ft')[col-4])
                            else:sh.text(x+8,y-j*(font+3),line,font)
                        x+=w
                    y-=rh
                if y<145:raise ValueError('Flexible table overflow')
            queue(f'{prefix}{start+i:03}',title+f' / {i+1}',draw)
    opening_rows=[];opening_hosts={p['id']:p for p in m['panels']}
    opening_by_id={f['id']:f for f in m['openings']}
    for f in m['openings']:
        opening_rows.append([f['id'],f['kind']+' / '+f.get('basis','A'),str(opening_level(f,opening_hosts)),f['plane'].upper(),*[feet(f[n]*12) for n in ('x_ft','y_ft','z_ft','width_ft','height_ft')]])
    tables(['ID','TYPE / BASIS','LEVEL','PLANE','X','Y','Z','WIDTH','HEIGHT'],opening_rows,[270,250,90,90,280,280,280,280,280],'S',301,'Dimensioned opening coordinate schedule')
    from .assembly_legend import continuation_jobs
    for scene in published:
        queue(scene['sheet'],scene['title'],lambda scene=scene:draw_assembly(sh,scene),'As shown')
        for number,title,draw in continuation_jobs(sh,scene):queue(number,title,draw)
    schedule=m['member_schedule'];rows=[[r['mark'],r['kind'],r['profile_id'],feet(r['length_in']),str(r['count']),r['basis'],','.join(map(str,r['levels'])),refs(r['connection_refs'])] for r in schedule]
    tables(['MARK','TYPE','SECTION','WORKLINE LENGTH','QTY','BASIS','LEVELS','JOINT REFERENCES'],rows,[105,250,430,220,70,70,200,755],'S',601,'Member mark schedule')
    specs=specifications(package,m);source_blocks=[]
    for r in specs:source_blocks.append((r['id'],r['text']+' | Assembled details: '+(refs(r['references']) or 'See retained BIM/source records; no detail sheet in this PDF scope.')))
    text_pages(source_blocks,'S',701,'Original source specification and applicability')
    # The numbered index is completed after all dynamic register pagination.
    catalog=list(jobs);indices=[]
    for start in range(0,len(catalog),80):
        chunk=catalog[start:start+80]
        def index(chunk=chunk):
            for j,(num,title,scale,_) in enumerate(chunk):
                x=80+(j//40)*1130;y=sh.H-195-(j%40)*31;sh.text(x,y,num,12,font='Helvetica-Bold');sh.text(x+95,y,title[:110],11)
        indices.append((f'G{20+start//80:03}','Complete numbered drawing index','NTS',index))
    jobs[1:1]=indices
    ids=[j[0] for j in jobs]
    if len(set(ids))!=len(ids):raise ValueError('Sheet number collision; expand the register namespace')
    for number,title,scale,fn in jobs:sh.start(number,title,scale);fn()
    sh.c.save();sheet_ids=set(ids)
    if any(c['reference'].split('/')[-1] not in sheet_ids for c in sh.callouts):raise ValueError('Dangling callout')
    m['detail_parameters']={s['id']:dict(reference=s['reference'],family=s['family'],occurrences=s['occurrence_count'],geometry_sha256=s['geometry_sha256']) for s in assemblies}
    def compact(path,value):path.write_text(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False),encoding='utf-8')
    compact(dest/'design_model.json',m);compact(dest/'connection_assemblies.json',dict(schema='steltic.connection_assemblies',version=1,source_sha256=fingerprint(package),assemblies=assemblies))
    compact(dest/'member_index.json',{mm['id']:{k:mm[k] for k in ('mark','kind','profile_id','axis','end_offsets','level','basis','source_member_id','connection_refs')} for mm in m['members']})
    write_json(dest/'source_records.json',package['design_records']);write_json(dest/'adopted_answers.json',dict(scenario=state['design_scenario'],answers=m['assumptions'],features=m['openings']))
    report=dict(schema='steltic.drawing_manifest',version=2,revision=state['revision'],building_id=package['building_id'],source_model_sha256=fingerprint(package),drawing_status=state['drawing_status'],can_generate=True,fictional=True,open_requests=0,sheets=sh.rows,dimensions=sh.dimensions,views=sh.views,member_labels=sh.labels,callouts=sh.callouts,
       counts=dict(members=len(m['members']),connections=len(m['connections']),marks=len(schedule),detail_families=len({s['family'] for s in assemblies}),detail_variants=len(assemblies),published_detail_variants=len(published),omitted_detail_variants=len(assemblies)-len(published),openings=len(m['openings'])),omitted_detail_references=sorted(sh.excluded_detail_refs),model_sha256=fingerprint(m),pdf_sha256=hashlib.sha256((dest/'drawings.pdf').read_bytes()).hexdigest(),decision_state_sha256=fingerprint({k:v for k,v in state.items() if k not in ('sheets','artifacts')}),artifacts=['drawings.pdf','drawing_manifest.json','information_requests.json','design_model.json','member_index.json','source_records.json','adopted_answers.json','connection_assemblies.json'])
    write_json(dest/'drawing_manifest.json',report);return report
