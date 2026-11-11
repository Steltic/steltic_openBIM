"""A1 dimensioned design-test sheets, with an auditable model and callout index.

All geometry is in inches; printed scales convert inches to 72 PDF points.
The original engineering package is immutable. A means authored test input.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from fractions import Fraction
import math
import hashlib
import re
from pathlib import Path

from .drawing_pdf import Sheets,ascii_text,feature_vertices
from .drawing_workflow import write_json,fingerprint
from .design_geometry import build_model,length
from .pilots.geometry import strips,member_faces,part_faces,clip_axis
from .pilots.model import add,sub,mul,unit,cross

INK='#243d49'; LIGHT='#c1cdcf'; GREY='#687b80'; ASSUMED='#946320'; BLUE='#275e75'


def inches(value):
    n=round(abs(value)*16); whole,part=divmod(n,16)
    frac=str(Fraction(part,16)) if part else ''
    return ('-' if value<0 else '')+(str(whole) if whole or not part else '')+('-' if whole and part else '')+frac+'"'


def feet(value):
    n=round(abs(value)*16); ft,rem=divmod(n,192)
    return ('-' if value<0 else '')+str(ft)+"'-"+inches(rem/16)


def physical_axis(m): return [add(p,o) for p,o in zip(m['axis'],m['end_offsets'])]


def opening_level(opening,hosts):
    """Read the declared level or its actual host, without changing geometry."""
    if opening.get('level') is not None:return opening['level']
    host=hosts.get(opening.get('host_id'),{})
    if host.get('level') is not None:return host['level']
    raise ValueError('Opening has no declared or host level: '+opening['id'])


def wall_plan_sections(member,profiles):
    """Actual wide wall sections, which cannot be drawn as vertical-axis dots."""
    if member['kind'] not in ('composite_wall','wall_closure'):return []
    a,b=physical_axis(member)
    if math.dist(a[:2],b[:2])>.001:return []
    y=member['local_y'];z=cross(unit(sub(b,a)),y)
    return [[add(a,add(mul(y,u),mul(z,v))) for u,v in polygon]
            for polygon in strips(profiles[member['profile_id']],profiles)]


def compact_references(values):
    """Compress only consecutive sheet numbers, preserving every detail ID."""
    groups=defaultdict(set);other=set()
    for value in values:
        match=re.fullmatch(r'([^/]+)/([A-Za-z]+)(\d+)',value)
        if match:groups[(match[1],match[2])].add(int(match[3]))
        else:other.add(value)
    result=[]
    for (detail,prefix),numbers in sorted(groups.items()):
        ordered=sorted(numbers);i=0
        while i<len(ordered):
            j=i
            while j+1<len(ordered) and ordered[j+1]==ordered[j]+1:j+=1
            result.append(f'{detail}/{prefix}{ordered[i]:03}'+(f'-{prefix}{ordered[j]:03}' if j>i else ''))
            i=j+1
    return ', '.join(result+sorted(other))


class DesignSheets(Sheets):
    def __init__(self,package,state,dest,model):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.pagesizes import A1,landscape
        self.W,self.H=landscape(A1)
        self.c=Canvas(str(dest/'drawings.pdf'),pagesize=(self.W,self.H),pageCompression=1,invariant=1)
        self.c.setTitle(model['title']+' - dimensioned design test drawings')
        self.c.setAuthor('Steltic openBIM');self.p,self.s,self.m=package,state,model
        self.rows=[];self.dimensions=[];self.page=0;self.views=[];self.labels=[];self.callouts=[]
        self.profiles={p['id']:p for p in model['profiles']};self.lookup={m['id']:m for m in model['members']}

    def line(self,a,b,color=INK,width=.7,dash=None):
        c=self.c;c.setStrokeColor(color);c.setLineWidth(width);c.setDash(dash or [])
        c.line(*a,*b);c.setDash([])

    def center(self,x,y,t,size=12,color=INK,font='Helvetica'):
        self.c.setFillColor(color);self.c.setFont(font,size);self.c.drawCentredString(x,y,ascii_text(t))

    def start(self,number,title,scale='NTS',refs=()):
        if self.page:self.c.showPage()
        self.page+=1;self.current=number
        self.rows.append(dict(number=number,title=title,page=self.page,scale=scale,assumption_ids=list(refs)))
        c=self.c;c.setStrokeColor(INK);c.setLineWidth(1);c.rect(34,34,self.W-68,self.H-68)
        self.text(55,self.H-70,'STELTIC  /  OPENBIM',17,font='Helvetica-Bold')
        self.text(55,self.H-112,title,27,font='Helvetica-Bold')
        self.text(self.W-390,self.H-69,number,27,font='Helvetica-Bold')
        self.text(self.W-390,self.H-96,'A1 landscape | '+scale,13)
        self.line((34,122),(self.W-34,122))
        self.text(55,96,self.m['title'],16,font='Helvetica-Bold')
        self.text(55,71,f"REV {self.s['revision']} | FICTIONAL TEST BUILDING | DIMENSIONED DESIGN TEST SET",12,ASSUMED,font='Helvetica-Bold')
        self.text(55,49,'S = source design input   A = assumed test input   |   Dimensions ft-in unless noted   |   Not a construction issue',11)
        self.text(self.W-650,95,'Source '+self.s['source_model_sha256'][:24],11)
        self.text(self.W-650,72,'New/changed assumptions are not a new structural analysis.',11)
        self.text(self.W-200,49,f'Sheet {self.page} / {number}',12)

    def panel_notes(self,items,title='DRAWING NOTES',x=None,y=None,width=390):
        x=x or self.W-460;y=y or self.H-170
        self.text(x,y,title,16,font='Helvetica-Bold');y-=34
        for item in items:
            y=self.wrap(x,y,item,width,13,19)-18
        return y

    def dim(self,a,b,offset,label=None,value=None,basis='S',ref='',size=11,
            source=None,projection=None,model_points=None):
        dx,dy=b[0]-a[0],b[1]-a[1];ln=math.hypot(dx,dy)
        if ln<.1:return
        vx,vy=dx/ln,dy/ln;nx,ny=-vy,vx
        label=label or feet(value)
        tag=f'D{len(self.dimensions)+1}'
        # Mark the actual ink, so the independent reader can isolate each dimension.
        self.c.addLiteral(f'/StelticDim << /ID /{tag} >> BDC')
        p=(a[0]+nx*offset,a[1]+ny*offset);q=(b[0]+nx*offset,b[1]+ny*offset)
        for src,dst in ((a,p),(b,q)):
            self.line((src[0]+nx*3*(1 if offset>=0 else -1),src[1]+ny*3*(1 if offset>=0 else -1)),(dst[0]+nx*4*(1 if offset>=0 else -1),dst[1]+ny*4*(1 if offset>=0 else -1)),GREY,.45)
        self.line(p,q,GREY,.55)
        for pt in (p,q):self.line((pt[0]-vx*3-nx*3,pt[1]-vy*3-ny*3),(pt[0]+vx*3+nx*3,pt[1]+vy*3+ny*3),INK,.8)
        angle=math.degrees(math.atan2(dy,dx))
        if angle>90:angle-=180
        elif angle<=-90:angle+=180
        c=self.c;c.saveState();c.translate((p[0]+q[0])/2,(p[1]+q[1])/2);c.rotate(angle)
        self.center(0,5,label,size,ASSUMED if basis=='A' else INK);c.restoreState()
        self.c.addLiteral('EMC')
        projection=projection or getattr(self,'grid_projection',None)
        if projection and projection.get('sheet')!=self.current:
            projection=None
        self.dimensions.append(dict(id=tag,sheet=self.current,page=self.page,value_in=value,
            text=label,basis=basis,reference=ref,witnesses_pt=[list(a),list(b)],offset_pt=offset,
            font_size_pt=size,source=source,projection=projection,model_points=model_points))

    def label(self,x,y,t,size=10,color=INK):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        w=stringWidth(ascii_text(t),'Helvetica',size)
        self.c.setFillColor('white');self.c.rect(x-2,y-2,w+4,size+3,fill=1,stroke=0)
        self.text(x,y,t,size,color)

    def opening_cell(self,x,y,text,size,opening,field):
        tag=f'D{len(self.dimensions)+1}'
        self.c.addLiteral(f'/StelticDim << /ID /{tag} >> BDC')
        self.text(x,y,text,size)
        self.c.addLiteral('EMC')
        self.dimensions.append(dict(id=tag,page=self.page,sheet=self.current,text=text,
            value_in=opening[field]*12,basis='A' if opening.get('basis') else 'S',
            reference=opening['id']+' '+field,font_size_pt=size,anchor_pt=[x,y],
            source=dict(kind='opening_cell',id=opening['id'],field=field)))

    def bubble(self,x,y,t,r=13):
        self.c.setStrokeColor(GREY);self.c.setFillColor('white');self.c.circle(x,y,r,fill=1,stroke=1);self.center(x,y-4,t,11)

    def callout(self,p,ref,dx=35,dy=28):
        if ref in getattr(self,'excluded_detail_refs',set()):return
        q=(p[0]+dx,p[1]+dy);self.line(p,q,BLUE,.7)
        self.label(q[0]+3,q[1],ref,10,BLUE)
        self.callouts.append(dict(sheet=self.current,reference=ref,at=list(p)))

    def grid_view(self,bounds,axes,scale,origin=(215,280),grid_axes=True,grids=None):
        u,v=axes;s=72/scale;x,y=origin;(u0,u1),(v0,v1)=bounds
        def tr(p):return x+(p[u]-u0)*s,y+(p[v]-v0)*s
        self.grid_projection=dict(sheet=self.current,axes=list(axes),scale=scale,
            origin_pt=[x-u0*s,y-v0*s],bounds_in=bounds)
        w,h=(u1-u0)*s,(v1-v0)*s
        self.views.append(dict(sheet=self.current,axes=list(axes),bounds_in=bounds,origin_pt=list(origin),
                               grid_axes=grid_axes,scale_denominator=scale,points_per_inch=s))
        bar_offset=145;caption_offset=65
        if grid_axes:
            for axis,horizontal in ((u,True),(v,False)):
                if axis==2:continue
                gs=(grids or self.m['grids'])['xyz'[axis]];gs=sorted((g for g in gs if bounds[0 if horizontal else 1][0]-.1<=g[1]<=bounds[0 if horizontal else 1][1]+.1),key=lambda g:g[1])
                lanes=[];last=[]
                for _,pos in gs:
                    lane=next((i for i,p in enumerate(last) if (pos-p)*s>=32),len(last))
                    if lane==len(last):last.append(pos)
                    else:last[lane]=pos
                    lanes.append(lane)
                dim_offset=64+30*max(lanes,default=0)
                if horizontal:caption_offset=max(caption_offset,65+30*max(lanes,default=0))
                short=any((b-a)*s<40 for (_,a),(_,b) in zip(gs,gs[1:]))
                overall_offset=dim_offset+(56 if short else 36)
                if horizontal:bar_offset=max(bar_offset,overall_offset+45)
                for (name,pos),lane in zip(gs,lanes):
                    gap=27+30*lane
                    if horizontal:
                        xx=x+(pos-u0)*s;self.line((xx,y-gap),(xx,y+h+gap),LIGHT,.5,[9,3,2,3]);self.bubble(xx,y-gap,name);self.bubble(xx,y+h+gap,name)
                    else:
                        yy=y+(pos-v0)*s;self.line((x-gap,yy),(x+w+gap,yy),LIGHT,.5,[9,3,2,3]);self.bubble(x-gap,yy,name);self.bubble(x+w+gap,yy,name)
                previous_short=False
                for (n1,a),(n2,b) in zip(gs,gs[1:]):
                    pa=(x+(a-u0)*s,y) if horizontal else (x,y+(a-v0)*s)
                    pb=(x+(b-u0)*s,y) if horizontal else (x,y+(b-v0)*s)
                    is_short=(b-a)*s<40
                    offset=dim_offset+(34 if previous_short else 20) if is_short else dim_offset
                    previous_short=is_short and not previous_short
                    self.dim(pa,pb,-offset if horizontal else offset,value=b-a,ref='Grid '+n1+'-'+n2,size=10,
                             source=dict(kind='grid',axis=axis,names=[n1,n2],override=grids is not None))
                if gs:
                    a,b=gs[0][1],gs[-1][1]
                    pa=(x+(a-u0)*s,y) if horizontal else (x,y+(a-v0)*s)
                    pb=(x+(b-u0)*s,y) if horizontal else (x,y+(b-v0)*s)
                    self.dim(pa,pb,-overall_offset if horizontal else overall_offset,value=b-a,ref='Overall grid dimension',size=12,
                             source=dict(kind='grid',axis=axis,names=[gs[0][0],gs[-1][0]],override=grids is not None))
        self.text(x,y+h+caption_offset,'Scale 1:'+str(scale)+' at A1 | Workline dimensions',12,GREY)
        bar=120 if scale<=100 else 240
        self.line((x,y-bar_offset),(x+bar*s,y-bar_offset),INK,3);self.text(x,y-bar_offset-20,'0',10);self.text(x+bar*s-15,y-bar_offset-20,feet(bar),10)
        return tr,s

    def draw_members(self,members,tr,axes,s,mark_mode='groups'):
        marks=defaultdict(list);seen=set()
        for m in members:
            a,b=physical_axis(m);p,q=tr(a),tr(b);seg=tuple(round(v,2) for v in (*p,*q))
            if seg in seen:continue
            seen.add(seg);basis=m['basis'];color=ASSUMED if basis=='A' else INK
            primary=m['kind'] in ('column','moment_beam','girder','rafter','chord','girder_truss','walkway_post','walkway_edge_beam')
            sections=wall_plan_sections(m,self.profiles) if axes==(0,1) else []
            for polygon in sections:
                pts=[tr(v) for v in polygon];path=self.c.beginPath();path.moveTo(*pts[0])
                for v in pts[1:]:path.lineTo(*v)
                path.close();self.c.setStrokeColor(color);self.c.setFillColor('#dbe6eb');self.c.setLineWidth(.65);self.c.drawPath(path,stroke=1,fill=1)
            if not sections:self.line(p,q,color,1.1 if primary else .45)
            if not sections and math.dist(p,q)<2:
                self.c.setStrokeColor(color);self.c.rect(p[0]-2.5,p[1]-2.5,5,5,stroke=1,fill=0)
            marks[m['mark']].append((m,p,q))
            if mark_mode=='all' and math.dist(p,q)>25 and m['kind'] not in ('flange_kicker','opening_trimmer','opening_header'):
                mid=((p[0]+q[0])/2,(p[1]+q[1])/2)
                self.label(mid[0]+3,mid[1]+3,m['mark'],10,color)
                self.labels.append(dict(sheet=self.current,member_id=m['id'],mark=m['mark']))
        return marks

    def representative_marks(self,groups,max_labels=24,reserved=()):
        occupied=list(reserved)
        # Small members are intentionally called out by a repeated group, not at every station.
        for mark,rows in sorted(groups.items(),key=lambda kv:(-len(kv[1]),kv[0]))[:max_labels]:
            for m,p,q in rows:
                x,y=(p[0]+q[0])/2,(p[1]+q[1])/2
                if any(abs(x-a)<85 and abs(y-b)<30 for a,b in occupied):continue
                occupied.append((x,y));self.label(x+5,y+5,mark+(' (typ)' if len(rows)>1 else ''),11,ASSUMED if m['basis']=='A' else BLUE)
                self.labels.append(dict(sheet=self.current,member_id=m['id'],mark=mark));break

    def opening(self,f,tr,size=11):
        pts=[tr(p) for p in feature_vertices(f)];p=self.c.beginPath();p.moveTo(*pts[0])
        for pt in pts[1:]:p.lineTo(*pt)
        p.close();self.c.setStrokeColor(ASSUMED if f.get('basis') else BLUE);self.c.setLineWidth(1.5);self.c.drawPath(p)
        self.line(pts[0],pts[2],ASSUMED,.55);self.line(pts[1],pts[3],ASSUMED,.55)
        cx=sum(p[0] for p in pts)/4;cy=sum(p[1] for p in pts)/4
        self.label(cx+3,cy+4,f['id']+(' A' if f.get('basis') else ' S'),size,ASSUMED)


def plan_connections(model,selected,level,kind):
    """Located occurrences for this view, not every joint on a tall column."""
    from .review_pdf import is_base_connection
    lookup={m['id']:m for m in model['members']};ids={m['id'] for m in selected}
    z=next((z for k,_,z in model['levels'] if k==level),0)
    result=[]
    for c in model['connections']:
        if not ids.intersection(c['member_ids']):continue
        if kind=='base' and not is_base_connection(c,lookup):continue
        if kind=='floor' and not z-40<=c['point'][2]<=z+6:continue
        if kind=='roof' and c['point'][2]<z-40:continue
        result.append(c)
    return result


def plan(sh,level,kind='floor'):
    m=sh.m;pilot=m['pilot'];allm=m['members']
    if pilot=='hr22':
        z=dict((lev,z) for lev,_,z in m['levels'])[level] if level else 0
        selected=[a for a in allm if (a['level']==level and a['kind']!='column' and a['kind']!='flange_kicker') or (a['kind']=='column' and min(p[2] for p in a['axis'])<=z<=max(p[2] for p in a['axis']))]
        axes=(0,1);bounds=((0,2160),(0,1440));scale=100;origin=(210,280)
    elif pilot=='cfs16':
        kinds={'column','endwall_post','door_header','opening_jamb','opening_header'} if kind=='base' else {'rafter','purlin','purlin_nested','eave_strut','strap'}
        selected=[a for a in allm if a['kind'] in kinds];axes=(1,0);bounds=((0,3300),(0,720));scale=150;origin=(210,675)
    else:
        axes=(0,1);bounds=((0,1680),(0,1560));scale=100;origin=(260,300)
        if kind=='roof':selected=[a for a in allm if 'truss' in a['kind'] or (a['kind']=='top_track' and a['level']==4)]
        elif kind=='base':selected=[a for a in allm if a['level']==1 and a['kind'] in ('bottom_track','chord','hold_down_rod','walkway_post')]
        elif kind=='walls':selected=[a for a in allm if a['level']==level and a['kind'] in ('bottom_track','stud','intersection_stud','chord','opening_jamb','opening_header','strap')]
        else:selected=[a for a in allm if a['level']==level and a['kind'] in ('joist','opening_trimmer','opening_header','rim_track','top_track','walkway_joist','walkway_edge_beam','collector','junction_collector')]
    tr,s=sh.grid_view(bounds,axes,scale,origin)
    groups=sh.draw_members(selected,tr,axes,s,'all' if pilot=='hr22' and kind!='base' else 'groups')
    if pilot!='hr22' or kind=='base':sh.representative_marks(groups)
    if pilot=='cfs8' and kind in ('base','roof','floor','walls'):
        perimeter=[[0,1008,0],[564,1008,0],[564,0,0],[1116,0,0],[1116,1008,0],[1680,1008,0],[1680,1560,0],[0,1560,0],[0,1008,0]]
        for a,b in zip(perimeter,perimeter[1:]):sh.line(tr(a),tr(b),GREY,.9)
    opening_hosts={p['id']:p for p in m['panels']}
    for f in m['openings']:
        show=f['plane']=='xy' and opening_level(f,opening_hosts)==level and kind not in ('base','walls')
        show|=f['plane']!='xy' and (pilot=='cfs16' and kind=='base' or pilot=='cfs8' and kind=='walls' and opening_level(f,opening_hosts)==level)
        if show:sh.opening(f,tr)
    if kind=='base' and pilot=='cfs8':
        for p in m['panels']:
            if p['kind']=='assumed_footing':
                pts=[tr(q) for q in p['vertices']]
                for a,b in zip(pts,pts[1:]+pts[:1]):sh.line(a,b,ASSUMED,1)
    if pilot=='hr22':cuts=[([0,720,0],[2160,720,0],'A/S201'),([1080,0,0],[1080,1440,0],'B/S202')]
    elif pilot=='cfs16':cuts=[([0,1650,0],[720,1650,0],'A/S201')]
    else:cuts=[([840,0,0],[840,1560,0],'A/S201'),([0,720,0],[1680,720,0],'B/S202')]
    for a,b,ref in cuts:
        p,q=tr(a),tr(b);sh.line(p,q,BLUE,.9,[14,4,2,4]);sh.callout(q,ref,25,25)
        for xx,yy in (p,q):
            path=sh.c.beginPath();path.moveTo(xx-5,yy+7);path.lineTo(xx+5,yy+7);path.lineTo(xx,yy+18);path.close()
            sh.c.setFillColor(BLUE);sh.c.drawPath(path,fill=1,stroke=0)
    notes=['S: source-defined framing. A: assumed geometry and supplementary members. Member marks refer to S6xx; marks are types, with every instance retained in member_index.json.',
           'Grid dimensions locate member worklines. Member schedule lengths are workline lengths, not fabrication cut lengths.',
           'Openings: clear sizes and coordinates are scheduled on S301. New frames are A; source analysis has not been rerun.']
    if pilot=='hr22':notes+=['Floor elevations are TOS. Slab/deck is 6-1/4 in above TOS (A).','Typical secondary beam spacing: 10 ft. Grid bays: 30 ft.','Roof local reinforcement: Grids 3-5/B-C. Same main roof elevation (A).']
    elif pilot=='cfs16':notes+=['60 ft between frame worklines; nominal clear span 58 ft 10 in (A).','Frames 1-23 at 12 ft 6 in centres. Purlins use source 24 in laps.','Doors O01/O02 lie between Grids 11-12. End bracing remains outside both source overhead doors.']
    else:notes+=['Ordinary studs/joists at 16 in centres (S). Wall framing and opening locations: S111-S114.','Grid W is the local walkway line X=41 ft, 6 ft west of SW. Main plans omit a second bubble beside Grid 4.','Roof: 2 ft truss stations, girder at G, diminishing valley overframing above the head roof (A).']
    notes.append(f'{len(selected):,} members represented in this view. Repeated-member leaders identify groups; full instance mapping is in the model index.')
    y=sh.panel_notes(notes)
    sh.text(sh.W-460,y-12,'CONNECTION CALLOUTS',15,font='Helvetica-Bold');y-=42
    connections=plan_connections(m,selected,level,kind)
    refs=sorted({c['drawing_ref'] for c in connections})
    for ref in refs:
        if y<185:
            sh.text(sh.W-460,y,'Further joint variants: connection index / member index.',10);break
        detail=next(d for d in m['details'] if d['reference']==ref)
        y=sh.wrap(sh.W-460,y,ref+'  '+detail['family'].replace('_',' '),390,11,16)-7
    # Place at least one anchored callout for each family that occurs in the view.
    used=set()
    for c in connections:
        ref=c['drawing_ref']
        if ref in used or len(used)>=6:continue
        p=tr(c['point']);sh.callout(p,ref,25,18+len(used)%3*14);used.add(ref)


def section(sh,normal,station,along,title,scale,bounds,origin=(215,340),band=1):
    axes=(along,2);tr,s=sh.grid_view(bounds,axes,scale,origin)
    selected=[];limits=[(-1e8,1e8) for _ in range(3)]
    limits[normal]=(station-band,station+band);limits[along]=bounds[0];limits[2]=bounds[1]
    for m in sh.m['members']:
        a,b=physical_axis(m)
        if clip_axis(a,b,limits):selected.append(m)
    # Clip actual extruded sections, including members crossing the cut plane.
    # Project each unique edge once to avoid heavy duplicate lines at a web/flange.
    groups=defaultdict(list);edges=set()
    for m in selected:
        for face in member_faces(m,sh.profiles,limits):
            pts=[tr(p) for p in face]
            for a,b in zip(pts,pts[1:]+pts[:1]):
                key=tuple(sorted((tuple(round(v,2) for v in a),tuple(round(v,2) for v in b))))
                if key in edges:continue
                edges.add(key);sh.line(a,b,ASSUMED if m['basis']=='A' else INK,.45)
        a,b=physical_axis(m);clip=clip_axis(a,b,limits)
        if clip:
            pts=[tr([a[i]+(b[i]-a[i])*t for i in range(3)]) for t in clip]
            groups[m['mark']].append((m,*pts))
    sh.representative_marks(groups,28)
    # The actual physical member ends (including source eccentricities) define the cut.
    for lev,label,z in sh.m['levels']:
        if bounds[1][0]<=z<=bounds[1][1]:
            p=[0,0,z];p[along]=bounds[0][1];p[normal]=station;x,y=tr(p)
            sh.line((origin[0],y),(x+45,y),LIGHT,.5,[8,4]);sh.text(x+52,y-4,label+' '+feet(z),11)
    levels=[z for _,_,z in sh.m['levels'] if bounds[1][0]<=z<=bounds[1][1]]
    for a,b in zip(levels,levels[1:]):
        p=[0,0,a];q=[0,0,b];p[along]=q[along]=bounds[0][0];p[normal]=q[normal]=station
        sh.dim(tr(p),tr(q),70,value=b-a,ref='Level interval',source=dict(kind='levels'),model_points=[p,q])
    sh.panel_notes([title,f'Cut at {"XYZ"[normal]}={feet(station)}. The section shows members in the stated plane; line weights and member marks distinguish repeated framing.',
        'Dimensioned level datums are workpoints/FFLs as named. Steel edges use physical section offsets; dimensions do not imply cut lengths.',
        'Opening and interface details: S3xx. Assembled connections: C-series. Source specifications are carried in S7xx.',
        'A members, fastener layouts and new supports are fictional test assumptions. Source design checks are retained separately.'])
    for ref in sorted({r for m in selected for r in m['connection_refs']})[:7]:
        m=next(m for m in selected if ref in m['connection_refs']);a,b=physical_axis(m);clip=clip_axis(a,b,limits)
        sh.callout(tr([a[i]+(b[i]-a[i])*clip[0] for i in range(3)]),ref,35,30)
    for f in sh.m['openings']:
        pts=feature_vertices(f)
        if max(abs(p[normal]-station) for p in pts)<band and f['plane']!='xy':sh.opening(f,tr)
    for panel in sh.m['panels']:
        if panel['kind']!='assumed_footing':continue
        ps=panel['vertices']
        if min(p[normal] for p in ps)<=station<=max(p[normal] for p in ps):
            a=min(p[along] for p in ps);b=max(p[along] for p in ps);z=ps[0][2]
            if a<bounds[0][0] or b>bounds[0][1]:continue
            points=[]
            for uu,vv in ((a,z),(b,z),(b,z+panel['thickness_in']),(a,z+panel['thickness_in'])):
                p=[0,0,vv];p[along]=uu;p[normal]=station;points.append(tr(p))
            for a,b in zip(points,points[1:]+points[:1]):sh.line(a,b,ASSUMED,1.1)
    if sh.current=='S202' and sh.m['pilot']=='cfs8':
        sh.dim(tr([564,station,468]),tr([1116,station,468]),90,value=552,basis='A',ref='Stem roof span',size=14)
        sh.dim(tr([492,station,0]),tr([564,station,0]),-140,value=72,basis='A',ref='Walkway workline width',size=12)
    if not selected:raise ValueError('An empty section must not be published: '+sh.current)


def opening_schedule(sh):
    headers=['ID','TYPE / BASIS','LEVEL','PLANE','X','Y','Z BASE','CLEAR WIDTH','CLEAR HEIGHT']
    rows=[];opening_hosts={p['id']:p for p in sh.m['panels']}
    for f in sh.m['openings']:
        rows.append([f['id'],f['kind']+(' / A' if f.get('basis') else ' / S'),str(opening_level(f,opening_hosts)),f['plane'].upper(),*[feet(f[k]*12) for k in ('x_ft','y_ft','z_ft','width_ft','height_ft')]])
    table(sh,headers,rows,[120,330,100,100,205,205,205,225,225],x=80,y=sh.H-185,row_height=25,font=11,
          openings=sh.m['openings'])
    sh.text(80,195,'Coordinates are the lower-left opening corner in the named plane, relative to the main XYZ origin. XY clear height is the second plan dimension.',12)
    sh.text(80,170,'A openings and their headers/trimmers are assumed test inputs; S openings are retained from the source. Levels for wall openings name the storey.',12,ASSUMED)


def table(sh,headers,rows,widths,x=70,y=None,row_height=30,font=12,openings=None):
    y=y or sh.H-185;xx=x
    for label,w in zip(headers,widths):sh.text(xx+7,y,label,font,font='Helvetica-Bold');xx+=w
    sh.line((x,y-12),(x+sum(widths),y-12),INK,.8);y-=row_height
    for i,row in enumerate(rows):
        if i%2==0:
            sh.c.setFillColor('#f1f4f4');sh.c.rect(x,y-8,sum(widths),row_height,fill=1,stroke=0)
        xx=x
        for col,(value,w) in enumerate(zip(row,widths)):
            lines=sh.lines(value,w-14,font)
            if len(lines)>2:raise ValueError('Table cell exceeds its allocated row: '+str(value))
            for j,line in enumerate(lines):
                if openings is not None and col>=4:
                    sh.opening_cell(xx+7,y-j*(font+2),line,font,openings[i],
                                    ('x_ft','y_ft','z_ft','width_ft','height_ft')[col-4])
                else:sh.text(xx+7,y-j*(font+2),line,font)
            xx+=w
        y-=row_height
    if y<145:raise ValueError('Table overflows drawing border on '+sh.current)


def opening_detail(sh):
    fs=[f for f in sh.m['openings'] if f.get('basis')]
    # One actual enlarged opening for each plane/type; each references the full set-out schedule.
    examples=[]
    for f in sorted(fs,key=lambda f:0 if f['plane']=='xy' else 1):
        if not any((a['plane']=='xy')==(f['plane']=='xy') for a in examples):examples.append(f)
    for idx,f in enumerate(examples[:2]):
        axes=tuple('xyz'.index(a) for a in f['plane']);normal=next(i for i in range(3) if i not in axes)
        verts=feature_vertices(f);lo=[min(p[i] for p in verts) for i in range(3)];hi=[max(p[i] for p in verts) for i in range(3)]
        scale=30 if f['plane']=='xy' else 12;s=72/scale;ox=220+idx*1000;oy=610
        tr=lambda p:(ox+(p[axes[0]]-lo[axes[0]])*s,oy+(p[axes[1]]-lo[axes[1]])*s)
        selected=[m for m in sh.m['members'] if m.get('assumption_id')==f['query_id'] and ('TEST-'+f['id']+'-') in m['id']]
        groups=sh.draw_members(selected,tr,axes,s);sh.representative_marks(groups,6)
        sh.opening(f,tr,13)
        view=dict(sheet=sh.current,axes=list(axes),scale=scale,origin_pt=[ox-lo[axes[0]]*s,oy-lo[axes[1]]*s])
        for field,end,offset in [('width_ft',1,-65),('height_ft',3,65)]:
            sh.dim(tr(verts[0]),tr(verts[end]),offset,value=f[field]*12,basis='A',
                   ref=f['id']+' clear '+field[:-3],size=14,source=dict(kind='opening',id=f['id'],field=field),
                   projection=view,model_points=[verts[0],verts[end]])
        sh.text(ox-50,sh.H-205,f['id']+' / '+f['kind'].upper()+' - 1:'+str(scale),20,font='Helvetica-Bold')
        y=480
        for m in selected[:6]:
            y=sh.wrap(ox-50,y,m['mark']+'  '+m['profile_id']+'  '+m['kind'].replace('_',' '),850,14,21)-8
        refs=sorted({r for m in selected for r in m['connection_refs']})
        sh.wrap(ox-50,y-10,'End connections '+', '.join(refs)+'. Additional openings follow the same framing rule; clear coordinates and sizes are on S301.',850,14,21)
    sh.text(80,190,'Opening frames are shown at their physical axes outside the clear opening. A supplementary design framing; source capacity checks have not been extended.',13,ASSUMED)


def interfaces(sh):
    pilot=sh.m['pilot']
    # A generously spaced coordinate diagram complements the main section set.
    if pilot=='hr22':
        columns=[m for m in sh.m['members'] if m['kind']=='column' and m['axis'][0][0]==0]
        half=max(max(sh.profiles[m['profile_id']]['dimensions']['d'],sh.profiles[m['profile_id']]['dimensions']['bf'])/2 for m in columns)
        s=8;ox,oy=1000,720
        sh.c.setStrokeColor(INK);sh.c.rect(ox-half*s,oy,2*half*s,150)
        face=ox-(half+14)*s;sh.line((face,oy-80),(face,oy+250),ASSUMED,2)
        sh.dim((face,oy+150),(ox-half*s,oy+150),80,value=14,basis='A',ref='HR-SEPARATION',size=16,
               source=dict(kind='west_separation',assumption='HR-SEPARATION'),
               projection=dict(sheet=sh.current,axes=[0,2],scale=72/s,origin_pt=[ox,oy]),
               model_points=[[-half-14,0,150/s],[-half,0,150/s]])
        sh.text(face-240,oy+280,'EXISTING WING FACE (A)',18);sh.text(ox-60,oy-130,'GRID 1',16)
        sh.panel_notes(['14 in assumed clear seismic/coordination separation measured from the largest outer column envelope at the west face.',
            'Existing-building face X = '+feet(-half-14)+'. The dimension is a fictional test coordination answer, not an existing-building survey.',
            'Floor steel TOS: 16, 30, 44, 58, 72 and 86 ft. Slab/deck top is 6-1/4 in higher (A).',
            'Gravity splices occur 48 in above the source floor level. Lateral CJP splices, continuity and doubler variants: S7xx.'],x=160,y=sh.H-210,width=620)
    elif pilot=='cfs16':
        s=2.1;ox,oy=240,600
        sh.line((ox,oy),(ox,oy+504),INK,3);sh.line((ox+1512,oy),(ox+1512,oy+504),INK,3)
        sh.line((ox,oy+504),(ox+756,oy+655.2),INK,3);sh.line((ox+756,oy+655.2),(ox+1512,oy+504),INK,3)
        sh.dim((ox,oy),(ox+1512,oy),-65,value=720,ref='Frame axis span',size=16)
        sh.dim((ox+7*s,oy+180),(ox+(720-7)*s,oy+180),60,value=706,basis='A',ref='Nominal clear between 14 in column faces',size=16)
        sh.text(ox,oy-140,'A 60 ft column-axis span supersedes the brief wording of 60 ft clear.',16,ASSUMED)
        sh.panel_notes(['Roof workpoint pitch: 1:5. Eaves 20 ft; ridge 26 ft.',
            'Four-channel main section: pair centres 6-3/8 in; within-pair web gaps 3/8 in. Local 3/8 in assembly gaps at knee/apex cuts (A).',
            'Purlin/girt normal workline offset 11 in (A). Lap 24 in (S). Nominal nesting gap 1/8 in (A).',
            'See the C-series assembled bracket and secondary details linked by the callouts.'],y=sh.H-210)
    else:
        s=8;ox,oy=330,720
        # Exact platform stack, section through the supported joist end.
        sh.c.setStrokeColor(INK);sh.c.rect(ox,oy,40*s,12*s);sh.c.rect(ox,oy+12*s,40*s,.75*s)
        sh.line((ox+20*s,oy-180),(ox+20*s,oy),INK,3)
        sh.dim((ox+40*s,oy),(ox+40*s,oy+12*s),-75,value=12,basis='S',ref='Joist depth',size=16)
        sh.dim((ox,oy+12*s),(ox,oy+12.75*s),70,label='3/4" WSP (A)',value=.75,basis='A',ref='CFS8-FLOOR',size=16)
        sh.text(ox,oy+180,'PLATFORM FLOOR / 1:9',20,font='Helvetica-Bold')
        sh.text(ox,oy-240,'First bearing plane +8\'-11-1/4"; FFL +10\'-0"',16)
        sh.panel_notes(['Floor FFLs: 0; 10 ft; 19 ft 8 in; 29 ft 4 in. Roof bearing: 39 ft. Ridge: 44 ft 9 in.',
            '12 in joist + 3/4 in WSP. Squash block: 12 in bearing gap. Joist bearing 2-1/2 in; interrupted rim fit 1/8 in (A).',
            'Walkway: 8 in joists and HSS8x4 edge beam top flanges 3/4 in below FFL (A), hung at the ledger/edge beam. Grid W X=41 ft, 6 ft outside SW.',
            'Seven HSS6x6 posts at 14 ft centres. Illustrative pads 6 x 6 ft x 2 ft 6 in thick (A). Guards 42 in high with posts at 4 ft maximum centres (A).',
            'Roof valley trusses bear above the main head roof. Girder line G at the stem/head junction; source uplift is retained, added gravity/girder reactions are assumed.'],x=1130,y=sh.H-230,width=1050)
    sh.text(100,190,'All assumptions on this sheet are adopted for the fictional test set. Source requirements and changed geometry remain separately identifiable.',13,ASSUMED)


def connection_parameters(sh,family,connection):
    """Dimensioned representative assembly, plus complete source variants in S7xx."""
    records={r['id']:r['data'] for r in sh.p['design_records']}
    text=' '.join(str(records.get(r,{}).get('selection',records.get(r,{}).get('components',''))) for r in connection.get('design_record_ids',[]))
    p=dict(kind='clip',width=6,height=6,rows=3,cols=2,diameter=.19,pitch=1,gauge=1,edge=.5,thickness=.0566,basis='A',notes=[])
    if family=='hr_column_base':p.update(kind='embedded',width=47,height=96,rows=12,cols=2,diameter=.875,pitch=6,gauge=34,edge=6,thickness=3.25,notes=['S: 96 in embedment; 47 in end plate (representative W36X395).','A: 48 studs total, four rows of 12 at 6 in pitch; Z=-90 to -24 in. Source conflicting 12 in zone is superseded.','Gravity-base variant: S7xx.'])
    elif family=='hr_column_splice_48in_above_floor':p.update(kind='splice',width=12,height=24,rows=4,cols=2,diameter=.75,pitch=6,gauge=6,edge=3,thickness=.75,notes=['A: 3/4 x 12 x 24 in erection plates.','S: lateral column CJP splices; gravity splice variants and bolts in S7xx.','Locate splice 48 in above indicated floor. Erection plate layout is A.'])
    elif family=='hr_rbs_joint':
        beam=next(m for m in sh.m['members'] if m.get('rbs'));rbs=beam['rbs'];bf=sh.profiles[beam['profile_id']]['dimensions']['bf']
        p.update(kind='rbs',width=rbs['a_in']+rbs['b_in']+6,height=bf,rbs=rbs,basis='S',rows=0,cols=0,thickness=sh.profiles[beam['profile_id']]['dimensions']['tf'],notes=['S: '+beam['profile_id']+' flange plan. RBS a/b/c and protected zone vary by beam profile; see S7xx.','S: flange/web CJP. A: 3/8 x 6 x 12 in erection tab with 4 x 3/4 in bolts at 3 in pitch.','Continuity/doubler plates use the source joint-by-level schedule.'])
    elif family=='hr_infill_shear_plate_cope':p.update(kind='plate',width=5,height=15,rows=5,cols=1,diameter=.75,pitch=3,gauge=0,edge=1.5,thickness=.25,notes=['S: 5 x 3/4 in A325 bolts at 3 in; 1-1/2 in vertical edges.','S: W30X99 cope 1-3/4 deep x 6 in long. New W18X40 uses the small-beam test detail.'])
    elif family=='hr_simple_shear_plate':p.update(kind='plate',width=4.75,height=17.25,rows=6,cols=1,diameter=.875,pitch=3,gauge=0,edge=1.125,thickness=.5,notes=['S: 6 x 7/8 in A490 bolts; 3 in pitch; 1-1/8 in vertical edges.','S: 5/16 in fillets both sides. Beam/plate edge dimensions and pretensioning: source variants S7xx.'])
    elif family=='hr_required_bottom_flange_brace':p.update(kind='kicker',width=36,height=36,notes=['A: L3x3x1/4 kicker to the source brace station.','S: station spacing/protected zone depends on beam profile; member source design note in the source record index.','A: 3/8 in end tab; 2 x 3/4 in bolts at 3 in.'])
    elif family in ('cfs_knee_3x4','cfs_apex_3x3'):p.update(kind='knee' if 'knee' in family else 'apex',width=12,height=13 if 'knee' in family else 10,rows=4 if 'knee' in family else 3,cols=3,diameter=.75,pitch=3,gauge=4,edge=2,thickness=.375,notes=['S: 3/8 in A572-50 bracket and 3/4 in A325 bolts.','A: bracket boundary is the union of the dimensioned leg envelopes; 2 in edges. Pattern repeats for each pair/leg.','A: 3/8 in assembly gap at joint-bisector member cuts.'])
    elif family=='cfs_portal_pinned_base':p.update(kind='base',width=14,height=16,rows=2,cols=2,diameter=.75,pitch=12,gauge=10,edge=2,thickness=.75,notes=['S: 14 x 16 x 3/4 in plate; 4 x 3/4 in anchors.','A: anchors on 10 x 12 in rectangle. Web group: 2x2 bolts, 3 in pitch/gauge, 2 in edges per pair.'])
    elif family=='test_floor_opening':
        if sh.m['pilot']=='hr22':p.update(kind='plate',width=5,height=10,rows=3,cols=1,diameter=.75,pitch=3,gauge=0,edge=2,thickness=.375,notes=['A: W18X40 trimmers/headers; 3/8 x 5 x 10 in shear plate, 3 x 3/4 in bolts at 3 in, 2 in end edges.','A: 1/4 in fillet weld both sides to support. Includes local W18X40 roof reinforcement.'])
        else:p.update(kind='clip',width=6,height=10,rows=4,cols=2,diameter=.25,pitch=2,gauge=3,edge=1.5,thickness=.125,notes=['A: paired 1200S300-97 trimmers/headers; 1/8 in clip plate at each ply.','A: 8 No.14 screws per leg in 4x2 pattern at 2 x 3 in. Transfer every cut joist to the new frame.'])
    elif family=='test_wall_opening':p.update(kind='clip',width=6,height=8,rows=3,cols=2,diameter=.25,pitch=2,gauge=3,edge=1.5,thickness=.125,notes=['A: double jambs outside clear opening; header sizes on S302 and member schedule.','A: 1/8 in clips, 6 No.14 per leg, 2 in pitch x 3 in gauge. Window sill uses the header profile.'])
    elif family=='test_walkway_support':p.update(kind='base',width=12,height=12,rows=2,cols=2,diameter=.75,pitch=8,gauge=8,edge=2,thickness=.75,notes=['A: HSS6x6 post, 12 x 12 x 3/4 in base, 4 x 3/4 in anchors on 8 in square. 6 x 6 ft x 30 in pad.','A: HSS8x4 edge beam, 1/2 x 8 x 10 in seat plate, 4 x 5/8 in bolts; 1/4 in weld to post.'])
    elif family=='test_guard':p.update(kind='base',width=6,height=6,rows=2,cols=2,diameter=.5,pitch=4,gauge=4,edge=1,thickness=.375,notes=['A: HSS2x2x1/8 rail/posts, 42 in above FFL, posts 4 ft maximum centres.','A: 6 x 6 x 3/8 base plate; 4 x 1/2 in bolts on 4 in square; 3/16 in weld.'])
    elif family=='test_roof_truss':p.update(kind='truss',width=24,height=18,rows=4,cols=3,diameter=.25,pitch=1.5,gauge=1.5,edge=1,thickness=.125,notes=['A: paired 600S162-68 chords / 600S162-54 webs. Girder: four 800S200-97 plies; valley overframing above head roof.','A: 1/8 in paired gussets, 12 No.14 per attached member end on 1-1/2 in grid; 1 in minimum edges.','A: regular heel 2 kip down; S uplift 1.06 kip. Girder ends 24 kip down/12 kip up assumed; no new capacity check.'])
    elif any(a in family for a in ('chord','hold_down')):p.update(kind='bracket',width=5.5,height=10,rows=7,cols=4,diameter=.25,pitch=1,gauge=1,edge=1,thickness=.25,notes=['S: rod/bracket sizes and screw counts vary by wall line. This sketch shows the SS 28-screw arrangement.','A: 1 in screw grid; side plates 1 in beyond group. Source clear gap/plate/rod variant takes precedence.','A: chord spacer plates 1/4 in at 24 in centres, 4 No.14 each.'])
    elif family=='cfs_strap':p.update(kind='strap',width=8,height=10,rows=7,cols=5,diameter=.25,pitch=1,gauge=1,edge=2,thickness=.1438,notes=['Representative 8x97 strap end: S 35 No.14 screws; count, strap size and gusset thickness vary by location. See S7xx.','A: screw grid 1 in, minimum sheet edge 1/2 in; gusset extends 2 in beyond the group.','Source strap end-to-chord/track groups are separate; do not substitute a generic screw count.'])
    elif family=='cfs_scheduled_strap':p.update(kind='strap',width=8,height=11,rows=8,cols=5,diameter=.216,pitch=1,gauge=1,edge=2,thickness=.125,notes=['Representative side-wall strap: S 6 in x 118 mil with 40 No.12 each end.','Roof strap: S 3-1/2 in x 97 mil, 19 No.12 each end. End-wall: S 3 in x 68 mil, 12 No.12 each end.','A: 1 in grid in a 1/8 in gusset extending 2 in beyond the group. The source counts govern each variant.'])
    elif family=='cfs_scheduled_flange_kicker':p.update(kind='kicker',width=24,height=18,rows=0,cols=0,notes=['S: regular L2x2x1/8 kickers, 30 in workline length; 3 No.12 screws each end at main frames.','S: end-wall regular braces use 2 No.12. A: new knee/apex clips use two 1/4 in screws per leg; door-jamb top kickers are 31-1/2 in long.'])
    elif family in ('cfs_scheduled_door_header','cfs_scheduled_endwall_post'):p.update(kind='clip',width=4,height=7,rows=2,cols=1,diameter=.5,pitch=3,gauge=0,edge=2,thickness=.25,notes=['S: L4x4x1/4 clips, 2 x 1/2 in A325-N bolts. End-wall post bases: two 5/8 in F1554 Gr36 anchors.','A: bolt pitch 3 in, ends 2 in. Source post-top kicker screw counts and slotted-top requirements are retained in S7xx.'])
    elif family in ('cfs_joist','cfs_bearing_stiffener','cfs_squash_block','cfs_rim_track','cfs_top_track','cfs_bottom_track'):p.update(kind='bearing',width=18,height=12,rows=3,cols=1,diameter=.19,pitch=4.5,gauge=0,edge=1.5,notes=['S: 12 in joist; 2-1/2 in bearing; full bearing stiffener 362S162-43, 3 No.10 web screws.','A: 12 in squash-block bearing gap; 3/4 in WSP; 1/8 in rim fit.','Floor-to-wall shear groups vary by wall/story; source counts on S7xx remain required.'])
    elif family=='sill_anchor_group':p.update(kind='anchor',width=36,height=6,rows=1,cols=3,diameter=.75,pitch=0,gauge=12,edge=6,thickness=.1017,notes=['S: anchor diameter/count by braced wall bay in S7xx.','A: first/last anchors 6 in from bay ends; equally space remaining anchors. This sketch illustrates the end offsets, not a universal count.'])
    elif family in ('cfs_scheduled_purlin','cfs_scheduled_purlin_nested','cfs_scheduled_girt','cfs_scheduled_endwall_girt','cfs_scheduled_eave_strut'):p.update(kind='lap',width=24,height=8,rows=2,cols=2,diameter=.25,pitch=3,gauge=6,edge=2,thickness=.0566,notes=['S: section, connection fastener selection and lap from source secondary-member record.','S: 24 in lap where scheduled. A: 11 in normal workline offset, 1/8 in nested-Z gap, selected hand.','A: illustrated end clip 2 in legs with two 1/4 in screws each leg.'])
    else:
        matches=re.findall(r'(\d+)\s+No\.?\s*(\d+)',text,re.I)
        if matches:
            count,num=map(int,matches[0]);cols=min(4,count);rows=math.ceil(count/cols)
            p.update(rows=rows,cols=cols,count=count,height=max(6,rows-1+2),width=max(6,cols-1+2),diameter=.25 if num==14 else .19)
        elif family=='cfs_stud':p.update(rows=1,cols=1,count=1)
        p['notes']=['S: source connection selection and fastener counts in the variant schedule S7xx.','A: local screw set-out at 1 in centres, 1/2 in minimum edges; clip/plate extents accommodate that group.']
    if text:p['source_selection']=text
    p['family']=family
    return p


def diagram(sh,p,x,y,w,h):
    """Conventional local detail at a stated scale; each drawn dimension is audited."""
    width,height=p['width'],p['height'];scale=next(n for n in (2,3,4,6,8,10,12,16,24,32,48) if width*72/n<w-130 and height*72/n<h-130);s=72/scale
    ox=x+(w-width*s)/2;oy=y+(h-height*s)/2
    def tr(a):return ox+a[0]*s,oy+a[1]*s
    sh.c.setStrokeColor(INK);sh.c.setLineWidth(1.2)
    k=p['kind']
    if k not in ('embedded','rbs','kicker'):sh.c.rect(ox,oy,width*s,height*s)
    if k=='embedded':
        sh.c.rect(ox,oy-3.25*s,width*s,3.25*s)
        sh.c.rect(ox+(width-34)*s/2,oy,34*s,height*s)
        sh.line(tr((width/2,0)),tr((width/2,height+8)),GREY,.5,[7,3])
    if k in ('bearing','clip','lap'):
        sh.line(tr((-3,0)),tr((width+3,0)),INK,2);sh.line(tr((0,0)),tr((0,height+3)),INK,2)
        sh.line(tr((width/2,0)),tr((width/2,height)),GREY,.6)
    if k=='rbs':
        aa,bb,cc=[p['rbs'][key] for key in ('a_in','b_in','c_in')]
        rad=(bb*bb+4*cc*cc)/(8*cc)
        path=sh.c.beginPath()
        for side in (0,1):
            points=[(0,side*height),(aa,side*height)]
            for i in range(25):
                xx=bb*i/24;cut=math.sqrt(max(0,rad*rad-(xx-bb/2)**2))-(rad-cc)
                points.append((aa+xx,cut if side==0 else height-cut))
            points.append((width,side*height))
            for a,b in zip(points,points[1:]):sh.line(tr(a),tr(b),INK,1.3)
        sh.line(tr((0,0)),tr((0,height)),INK,2)
        sh.dim(tr((0,height)),tr((aa,height)),55,label='a='+inches(aa),value=aa,basis='S',ref='RBS a')
        sh.dim(tr((aa,height)),tr((aa+bb,height)),55,label='b='+inches(bb),value=bb,basis='S',ref='RBS b')
        sh.label(ox+10,oy-70,'c='+inches(cc)+' each flange edge (S)',12,BLUE)
    if k=='kicker':
        sh.line(tr((0,0)),tr((width,height)),INK,3)
        sh.line(tr((-4,0)),tr((4,0)),INK,2);sh.line(tr((width-4,height)),tr((width+4,height)),INK,2)
        sh.dim(tr((0,0)),tr((width,height)),32,label=inches(math.hypot(width,height))+' workline',value=math.hypot(width,height),basis=p['basis'],ref='Kicker workline')
    if k in ('bracket','splice'):sh.line(tr((width/2,-4)),tr((width/2,height+4)),INK,1.5)
    if k=='truss':
        sh.line(tr((0,0)),tr((width,height)),INK,3);sh.line(tr((0,0)),tr((width,0)),INK,3)
    if k in ('knee','apex'):
        sh.text(x+20,y+h-24,'ONE LEG / GROUP; REPEAT AT EACH PAIR',11,BLUE)
    rows,cols=p['rows'],p['cols'];pitch,gauge=p['pitch'],p['gauge']
    if k not in ('kicker','rbs','truss'):
        for row in range(rows):
            for col in range(cols):
                if row*cols+col>=p.get('count',rows*cols):continue
                xx=(width-(cols-1)*gauge)/2+col*gauge;yy=(height-(rows-1)*pitch)/2+row*pitch
                if k=='embedded':yy=6+row*6
                cx,cy=tr((xx,yy));sh.c.circle(cx,cy,max(1.6,p['diameter']*s/2),fill=0,stroke=1)
        if cols>1:sh.dim(tr(((width-(cols-1)*gauge)/2,height)),tr(((width+(cols-1)*gauge)/2,height)),35,label=f'{cols-1} @ {inches(gauge)}',value=(cols-1)*gauge,basis=p['basis'],ref='Fastener gauge')
        if rows>1:
            bottom=6 if k=='embedded' else (height-(rows-1)*pitch)/2
            sh.dim(tr((width,bottom)),tr((width,bottom+(rows-1)*pitch)),-40,label=f'{rows-1} @ {inches(pitch)}',value=(rows-1)*pitch,basis=p['basis'],ref='Fastener pitch')
    sh.dim(tr((0,0)),tr((width,0)),-40,label=inches(width),value=width,basis=p['basis'],ref='Representative assembly width',size=12)
    sh.dim(tr((0,0)),tr((0,height)),50,label=inches(height),value=height,basis=p['basis'],ref='Representative assembly height',size=12)
    sh.text(x+20,y+5,'1:'+str(scale)+' | Inches | '+('Flange' if k=='rbs' else 'Plate')+' t='+inches(p['thickness'])+' | '+p['basis'],11)


def detail_page(sh,details):
    for i,d in enumerate(details):
        col=i%2;row=i//2;x=70+col*1130;y=sh.H-760-row*650;w=1090;h=610
        sh.c.setStrokeColor(LIGHT);sh.c.rect(x,y,w,h)
        sh.text(x+20,y+h-32,d['reference']+'  '+d['family'].replace('_',' ').upper(),16,font='Helvetica-Bold')
        representative=next(c for c in sh.m['connections'] if c['detail_ref']['id']==d['family'])
        p=connection_parameters(sh,d['family'],representative)
        diagram(sh,p,x+20,y+100,520,445)
        yy=y+h-80
        for note in p['notes']:yy=sh.wrap(x+575,yy,note,485,13,19)-18
        sh.wrap(x+20,y+75,'Representative design arrangement. Source variant dimensions and specifications in S7xx; adopted A supplements override only the named missing input.',1040,11,16)


def specifications(package,model):
    refs=defaultdict(set)
    for c in model['connections']:
        for rid in c.get('design_record_ids',[]):refs[rid].add(c['drawing_ref'])
    out=[]
    for r in package['design_records']:
        if r['id'] not in refs and not r['id'].startswith('connections/'):continue
        data=r['data']
        if data.get('rows'):
            for i,row in enumerate(data['rows']):
                keys=('story','level','item','zone','section','rod','connection','selection','lap','spacing_ft','span_ft','screws_per_bay','screws_per_end','length_in','governing')
                fields=[]
                for k in keys:
                    if row.get(k) is None:continue
                    v=str(row[k])
                    if k in ('story','level','screws_per_bay','screws_per_end'):v=k.replace('_',' ')+' '+v
                    elif k.endswith('_ft'):v=k[:-3].replace('_',' ')+' '+v+' ft'
                    elif k.endswith('_in'):v=k[:-3].replace('_',' ')+' '+v+' in'
                    fields.append(v)
                if fields:out.append(dict(id=r['id']+f'/row-{i+1}',references=sorted(refs[r['id']]),text='; '.join(fields)))
        text=data.get('selection') or data.get('components') or data.get('design_note') or data.get('section') or data.get('type')
        if not text:continue
        note='' if refs[r['id']] else ' | Retained source schedule: no separately located joint in this drawing model; no extra joint is implied.'
        out.append(dict(id=r['id'],references=sorted(refs[r['id']]),text=str(text)+note))
    return out


def generate(package,state,dest,*,prepared_model=None):
    if not all(r['confirmed'] for r in state['requests']):raise ValueError('Design-test sheets require all adopted test answers to remain confirmed')
    from .review_cases import CASES
    if state['design_scenario']['id'] in CASES:
        from .review_pdf import generate as generate_review
        return generate_review(package,state,dest)
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);model=prepared_model if prepared_model is not None else build_model(package,state)
    from .connection_details import prepare
    from .assembly_pdf import draw_assembly
    assemblies=model['connection_assemblies'] if prepared_model is not None else prepare(model,package)
    refinement=' CFS8 roof webs are paired 600S162-54, four-ply at the girder, to match the actual node gusset planes; this is an explicit A refinement to the roof-interface answer.' if model['pilot']=='cfs8' else ''
    if not any(a['id']=='ASSEMBLED-JOINTS' for a in model['assumptions']):
        model['assumptions'].append(dict(id='ASSEMBLED-JOINTS',basis='A - user-authorized fictional test input',answer='Develop the source connections as assembled design details. A labels adopted fitting geometry, bracket returns, clip extents, local fastener set-out and erection fittings.'+refinement+' Exact source variant and occurrence mapping is retained in connection_assemblies.json; no new capacity calculation is implied.'))
    sh=DesignSheets(package,state,dest,model);jobs=[]
    def queue(number,title,fn,scale='NTS'):jobs.append((number,title,scale,fn))
    # The complete sheet list is available before the cover is painted.
    def cover():
        sh.text(90,sh.H-205,'DIMENSIONED DESIGN DRAWINGS',31,font='Helvetica-Bold')
        sh.text(90,sh.H-255,model['title'],24,BLUE)
        sh.wrap(90,sh.H-315,'All outstanding information requests have explicit adopted answers for this fictional test building. Geometry, dimensions and detail references use those answers; A identifies assumed inputs. The original HR/CFS calculation package is retained unchanged.',980,18,27)
        y=sh.H-455
        for note in [f"{len(model['members']):,} members / {len(model['connections']):,} located connection references / {len(model['details'])} detail families.",
            f"{len(state['requests'])} adopted test answers. {len(model['openings'])} scheduled openings. All dimensions are in feet-inches unless a detail says inches.",
            'S source input is carried from the completed design. A is a user-authorized fictional test assumption, including new opening framing, roof/walkway supplements and missing fastener set-out.',
            'This is a design drawing test set, not a fabrication package. Workline lengths are not cut lengths. Source capacity checks have not been rerun for the adopted changes.',
            'Member_index.json maps each mark to every instance and its joint references. Design_model.json retains source IDs, changed members and assumptions. Source_records.json retains all engineering records.',
            'Sections are taken from the drawing model at their named planes. Plans identify section cuts and connection callouts. Read the full source variant schedule with every representative detail.']:
            y=sh.wrap(90,y,note,980,15,23)-30
        sh.text(1250,sh.H-205,'SHEET INDEX',21,font='Helvetica-Bold');yy=sh.H-245
        categories=[('G','General notes / answers / sheet index'),('S0','Grid and foundation set-out'),('S1','Floor, roof and wall plans'),('S2','Building sections and elevations'),('S3','Openings and interfaces'),('C','Assembled connection details and variants'),('S6','Member mark schedules'),('S7','Original source specifications')]
        for prefix,title in categories:
            numbers=[n for n,_,_,_ in jobs if n.startswith(prefix)]
            if not numbers:continue
            sh.text(1250,yy,numbers[0]+' - '+numbers[-1],12,font='Helvetica-Bold');yy-=25
            sh.text(1250,yy,title+f' ({len(numbers)} sheets)',12);yy-=42
        sh.text(1250,yy-20,'Full numbered sheet index follows the answer register.',13)
    queue('G001','Drawing index and design-test basis',cover)
    def assumptions():
        y=sh.H-195
        for i,a in enumerate(model['assumptions']):
            sh.text(90,y,a['id']+' / A - ADOPTED FICTIONAL TEST ANSWER',14,ASSUMED,font='Helvetica-Bold');y-=26
            y=sh.wrap(90,y,a['answer'],2140,13,19)-23
        if y<150:raise ValueError('Assumption register overflow')
    queue('G002','Adopted answers and drawing assumptions',assumptions)
    queue('S001','Grid and column-base set-out' if model['pilot']!='cfs8' else 'Grid, ground wall and walkway support set-out',lambda:plan(sh,0,'base'),'1:100 / 1:150')
    pilot=model['pilot']
    if pilot=='hr22':
        for lev in range(1,7):queue(f'S{100+lev}',('Roof' if lev==6 else 'Level '+str(lev))+' framing plan',lambda lev=lev:plan(sh,lev),'1:100')
        queue('S201','Section A / Grid C - east-west frame',lambda:section(sh,1,720,0,'SECTION A: Grid C, looking north',125,((0,2160),(-120,1080)),(215,390),22),'1:125')
        queue('S202','Section B / Grid 4 - north-south frame',lambda:section(sh,0,1080,1,'SECTION B: Grid 4, looking east',100,((0,1440),(-120,1080)),(270,330),22),'1:100')
    elif pilot=='cfs16':
        queue('S101','Roof framing and bracing plan',lambda:plan(sh,1,'roof'),'1:150')
        queue('S201','Section A / Grid 12 portal frame',lambda:section(sh,1,1650,0,'SECTION A: Frame 12, looking along +Y',40,((0,720),(0,330)),(240,430),12),'1:40')
        queue('S202','Grid 1 end-wall elevation',lambda:section(sh,1,0,0,'End-wall elevation, overhead door retained',40,((0,720),(0,330)),(240,430),16),'1:40')
        queue('S203','West side-wall elevation',lambda:section(sh,0,-11,1,'Side-wall girt workline; two end braced bays',150,((0,3300),(0,330)),(215,640),17),'1:150')
    else:
        for lev in range(1,4):queue(f'S{100+lev}','Floor '+str(lev+1)+' framing plan',lambda lev=lev:plan(sh,lev),'1:100')
        queue('S104','Roof trusses, girder and valley plan',lambda:plan(sh,4,'roof'),'1:100')
        for lev in range(1,5):queue(f'S{110+lev}','Storey '+str(lev)+' wall framing and opening plan',lambda lev=lev:plan(sh,lev,'walls'),'1:100')
        queue('S201','Section A / Grid 6 longitudinal building cut',lambda:section(sh,0,840,1,'SECTION A: X=70 ft, looking east',90,((0,1560),(-36,570)),(230,490),9),'1:90')
        queue('S202','Section B / stem transverse and walkway cut',lambda:section(sh,1,720,0,'SECTION B: Y=60 ft, looking north',60,((456,1152),(-36,570)),(310,390),12),'1:60')
        queue('S203','North-wall elevation / Grid J',lambda:section(sh,1,1560,0,'North exterior wall with scheduled windows',100,((0,1680),(0,570)),(230,490),9),'1:100')
        queue('S204','West stem / walkway elevation',lambda:section(sh,0,564,1,'West stem wall at SW; window and walkway-door openings',75,((0,1008),(0,570)),(300,440),9),'1:75')
        queue('S205','Walkway edge elevation / local Grid W',lambda:section(sh,0,492,1,'Walkway support line W at X=41 ft; seven posts at 14 ft centres',75,((-40,1048),(-36,410)),(300,480),4),'1:75')
    queue('S301','Opening clear sizes and coordinate schedule',lambda:opening_schedule(sh))
    queue('S302','Opening framing enlargements',lambda:opening_detail(sh),'As shown')
    queue('S303','Dimensioned interfaces and datum reconciliation',lambda:interfaces(sh),'As shown')
    for scene in assemblies:
        queue(scene['sheet'],scene['title'],lambda scene=scene:draw_assembly(sh,scene),'As shown')
        from .assembly_legend import continuation_jobs
        for number,title,draw in continuation_jobs(sh,scene):queue(number,title,draw)
    schedule=model['member_schedule']
    for start in range(0,len(schedule),34):
        chunk=schedule[start:start+34]
        def draw_schedule(chunk=chunk):
            rows=[[a['mark'],a['kind'].replace('_',' '),a['profile_id'],feet(a['length_in']),str(a['count']),a['basis'],','.join(map(str,a['levels'])),compact_references(a['connection_refs'])] for a in chunk]
            table(sh,['MARK','MEMBER TYPE','SECTION','WORKLINE LENGTH','QTY','BASIS','LEVELS','END / JOINT DETAILS'],rows,[110,300,410,230,80,80,170,760],row_height=37,font=12)
            sh.text(80,180,'Repeated marks share type, profile, workline length (nearest 1/16 in), basis and connection references. Exact axes and instance positions: member_index.json.',12)
        queue(f'S{601+start//34}','Member mark schedule / '+str(start//34+1),draw_schedule)
    specs=specifications(package,model);pages=[];current=[];height=0
    for r in specs:
        lines=len(sh.lines(r['text'],1035,12));block=62+lines*17
        if height+block>1260:pages.append(current);current=[];height=0
        current.append(r);height+=block
    if current:pages.append(current)
    for start in range(0,len(pages),2):
        columns=pages[start:start+2]
        def draw_specs(columns=columns):
            for col,items in enumerate(columns):
                x=80+col*1130;y=sh.H-185
                for r in items:
                    sh.text(x,y,r['id'],13,font='Helvetica-Bold');y-=20
                    y=sh.wrap(x,y,'DETAIL '+', '.join(r['references'])+' | S - source specification',1035,10,13)-9
                    y=sh.wrap(x,y,r['text'],1035,12,17)-20
                if y<140:raise ValueError('Source specification overflow')
            sh.text(80,165,'Source variants are reproduced for traceability. G002 and A-labelled detail supplements supersede the specifically resolved missing/conflicting inputs.',12,ASSUMED)
        queue(f'S{701+start//2}','Source connection variants / '+str(start//2+1),draw_specs)
    # Paginated index is inserted before the drawing sheets, with all detail variants.
    index_jobs=list(jobs);index_pages=[]
    for start in range(0,len(index_jobs),84):
        chunk=index_jobs[start:start+84]
        def draw_index(chunk=chunk):
            for i,(number,title,scale,_) in enumerate(chunk):
                col=i//42;row=i%42;x=80+col*1130;y=sh.H-195-row*31
                sh.text(x,y,number,12,font='Helvetica-Bold');sh.text(x+100,y,title[:100],11)
        index_pages.append((f'G{10+start//84:03}','Complete sheet index / '+str(start//84+1),'NTS',draw_index))
    jobs[2:2]=index_pages
    for number,title,scale,fn in jobs:sh.start(number,title,scale);fn()
    sh.c.save()
    sheet_ids={r['number'] for r in sh.rows}
    for c in sh.callouts:
        if c['reference'].split('/')[-1] not in sheet_ids:raise ValueError('Dangling drawing reference '+c['reference'])
    index={m['id']:{k:m[k] for k in ('mark','kind','profile_id','axis','level','basis','source_member_id','connection_refs')} for m in model['members']}
    model['detail_parameters']={s['id']:dict(reference=s['reference'],family=s['family'],occurrences=s['occurrence_count'],geometry_sha256=s['geometry_sha256']) for s in assemblies}
    write_json(dest/'connection_assemblies.json',dict(schema='steltic.connection_assemblies',version=1,source_sha256=fingerprint(package),assemblies=assemblies))
    write_json(dest/'design_model.json',model);write_json(dest/'member_index.json',index);write_json(dest/'source_records.json',package['design_records'])
    write_json(dest/'adopted_answers.json',dict(scenario=state['design_scenario'],answers=model['assumptions'],features=state['features']))
    report=dict(schema='steltic.drawing_manifest',version=2,revision=state['revision'],building_id=package['building_id'],source_model_sha256=fingerprint(package),
        drawing_status=state['drawing_status'],can_generate=True,fictional=True,open_requests=0,sheets=sh.rows,dimensions=sh.dimensions,views=sh.views,member_labels=sh.labels,
        callouts=sh.callouts,counts=dict(members=len(model['members']),connections=len(model['connections']),marks=len(schedule),detail_families=len({s['family'] for s in assemblies}),detail_variants=len(assemblies),openings=len(model['openings'])),
        model_sha256=fingerprint(model),pdf_sha256=hashlib.sha256((dest/'drawings.pdf').read_bytes()).hexdigest(),
        decision_state_sha256=fingerprint({k:v for k,v in state.items() if k not in ('sheets','artifacts')}),
        artifacts=['drawings.pdf','drawing_manifest.json','information_requests.json','design_model.json','member_index.json','source_records.json','adopted_answers.json','connection_assemblies.json'])
    write_json(dest/'drawing_manifest.json',report)
    return report
