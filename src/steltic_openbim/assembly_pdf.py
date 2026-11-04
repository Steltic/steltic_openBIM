"""Three coordinated views of one physical connection assembly per detail sheet."""
import math
from .assembly_scene import section_polygons
from .mesh_display import display_faces,feature_edges
from .pilots.model import cross,dot,sub,unit

COLORS={'member':('#dce7ec','#294e63'),'plate':('#f2dfb4','#8b642a'),
        'fastener':('#d1d8dc','#394c55'),'rod':('#d1d8dc','#394c55'),
        'panel':('#e6ece4','#6a8068'),'concrete':('#f5f5f3','#b3b6b4'),'grout':('#eee9dc','#a49673')}


def path_polygon(canvas,pts,fill,stroke,width=.65,edges=None):
    if len(pts)<3:return
    path=canvas.beginPath();path.moveTo(*pts[0])
    for p in pts[1:]:path.lineTo(*p)
    path.close();canvas.setFillColor(fill);canvas.setStrokeColor(stroke);canvas.setLineWidth(width);canvas.drawPath(path,fill=1,stroke=0 if edges is not None else 1)
    if edges is not None:
        for a,b,show in zip(pts,pts[1:]+pts[:1],edges):
            if show:canvas.line(*a,*b)


def projection(scene,mode):
    if mode=='front':
        axes=scene['front_axes'];missing=next(i for i in range(3) if i not in axes)
        return lambda p:(p[axes[0]],p[axes[1]],p[missing]),axes
    if mode=='section':
        axes=[i for i in range(3) if i!=scene['section_axis']]
        return lambda p:(p[axes[0]],p[axes[1]],p[scene['section_axis']]),axes
    # View from front/right/above. Local Z remains vertical in the axonometric view.
    return lambda p:(.8660254*(p[0]-p[1]),.5*(p[0]+p[1])+p[2],p[0]+p[1]-p[2]),None


def draw_view(sh,scene,mode,rect,title):
    x,y,w,h=rect;sh.text(x+12,y+h-24,title,16,font='Helvetica-Bold')
    sh.c.setStrokeColor('#c8d2d5');sh.c.setLineWidth(.6);sh.c.rect(x,y,w,h)
    project,axes=projection(scene,mode);parts=scene['parts'];edge_flags={}
    if mode=='section':
        polys=[]
        for part in parts:
            if part['kind']=='concrete':continue
            loops=section_polygons(part,scene['section_axis'],scene['section_at'])
            for loop in loops:polys.append((part,[(p[0],p[1],0) for p in loop]))
        if not polys:raise ValueError('Empty transverse section '+scene['id'])
    else:
        polys=[]
        for part in parts:
            if part['kind']=='concrete':continue
            faces=display_faces(part['faces'])
            flags=feature_edges(faces) if part.get('member',{}).get('rbs') else [None]*len(faces)
            for f,edges in zip(faces,flags):
                projected=[project(p) for p in f];polys.append((part,projected));edge_flags[id(projected)]=edges
        polys.sort(key=lambda row:sum(p[2] for p in row[1])/len(row[1]),reverse=True)
    pts=[p for _,face in polys for p in face]
    if mode!='section':
        pts += [project(p) for part in parts if part['kind']=='concrete' for face in part['faces'] for p in face]
    lo=[min(p[i] for p in pts) for i in (0,1)];hi=[max(p[i] for p in pts) for i in (0,1)]
    ext=[max(.1,hi[i]-lo[i]) for i in (0,1)]
    needed=max(ext[0]/max(1,w-230),ext[1]/max(1,h-200))*72
    denom=next((s for s in (1,1.5,2,2.5,3,4,5,6,8,10,12,16,20,24,32,40,50,75,100) if s>=needed),math.ceil(needed))
    scale=72/denom;ox=x+w/2-(lo[0]+hi[0])/2*scale;oy=y+h/2-10-(lo[1]+hi[1])/2*scale
    def tr(p):return ox+p[0]*scale,oy+p[1]*scale
    if mode!='section':
        # Context is drawn transparently so anchors and embedded members remain visible.
        for part in parts:
            if part['kind']!='concrete':continue
            for face in part['faces']:
                points=[tr(project(p)) for p in face]
                for aa,bb in zip(points,points[1:]+points[:1]):sh.line(aa,bb,'#aab5b4',.5,[5,4])
    for part,face in polys:
        fill,stroke=COLORS.get(part['kind'],COLORS['plate'])
        path_polygon(sh.c,[tr(p) for p in face],fill,stroke,.7 if part['kind']=='member' else .6,edge_flags.get(id(face)))
    if mode=='front' and scene['family']=='review_transfer_truss':
        for part in parts:
            if part['kind']!='member':continue
            for face in part['faces']:
                pts=[tr(project(p)) for p in face]
                for aa,bb in zip(pts,pts[1:]+pts[:1]):sh.line(aa,bb,'#527b91',.7,[5,3])
        sh.text(x+12,y+35,'Member outlines behind gussets shown dashed',10)
    if mode in ('front','iso'):
        # Long slots are drawing geometry, independent of the illustrative bolt solid.
        from .pilots.model import add,mul
        for group in scene['fasteners']:
            slot=group.get('slot')
            if not slot:continue
            along=unit(slot['direction']);across=unit(cross(group['axis'],along));radius=(group['diameter']+.0625)/2;half=max(0,(slot['length_in']-2*radius)/2)
            for point in group['points']:
                pts=[]
                for end in (1,-1):
                    for j in range(13):
                        angle=(-math.pi/2 if end==1 else math.pi/2)+j*math.pi/12
                        q=add(point,add(mul(along,end*half+radius*math.cos(angle)),mul(across,radius*math.sin(angle))));pts.append(tr(project(q)))
                for aa,bb in zip(pts,pts[1:]+pts[:1]):sh.line(aa,bb,'#a56518',1.1)
            pa=tr(project(group['points'][0]));sh.label(pa[0]+12,pa[1]+10,f'SLOT {slot["length_in"]:g} in [{slot["basis"]}]',10,'#a56518')
    # Transverse sections retain individual profile strips and cut fastener bodies.
    if mode=='section':
        sh.text(x+12,y+17,f"CUT {chr(65+scene['section_axis'])} AT LOCAL {'XYZ'[scene['section_axis']]}={scene['section_at']:g} in | scale 1:{denom:g}",11)
        for part,face in polys:
            if part['kind'] not in ('member','plate'):continue
            if len(face)>=3:
                points=[tr(p) for p in face];cx=sum(p[0] for p in points)/len(points);cy=sum(p[1] for p in points)/len(points)
                sh.line((cx-2,cy-2),(cx+2,cy+2),'#677e89',.5)
    else:sh.text(x+12,y+17,('AXONOMETRIC - NTS' if mode=='iso' else f'ASSEMBLED ELEVATION | scale 1:{denom:g}')+' | dimensions inches',11)
    # Labels use separate rails; one leader per component/group, no scattered text.
    visible={part['id'] for part,_ in polys};labels=[]
    labelled_groups=set()
    for part in parts:
        if part['id'] not in visible or (mode=='section' and part['kind']=='fastener'):continue
        label=part.get('annotation_group',part['id'])
        if label in labelled_groups:continue
        labelled_groups.add(label)
        bb=part['bounds'];center=[(a+b)/2 for a,b in bb]
        if mode=='section':center[scene['section_axis']]=scene['section_at']
        q=project(center);labels.append((q[1],label,tr(q),part))
    # These welds share one elevation and need rails even at small counts.
    rail_welds=mode=='front' and (len(scene['welds'])>10 or scene['family'] in (
        'review_cfs_hold_down','review_pg_seat','review_pg_pickup'))
    if rail_welds:
        for weld in scene['welds']:
            q=project([(a+b)/2 for a,b in zip(weld['a'],weld['b'])]);labels.append((q[1],weld['id'],tr(q),dict(kind='weld',basis=weld['basis'])))
    if mode in ('front','iso'):
        labels.sort(reverse=True)
        for i,(_,label,point,part) in enumerate(labels):
            right=(i%2==1);idx=i//2;tx=x+w-55 if right else x+18;ty=y+h-72-idx*max(23,min(42,(h-180)/max(1,math.ceil(len(labels)/2))))
            sh.line(point,(tx-8 if right else tx+37,ty+3),'#6d858f',.55)
            sh.label(tx,ty,label,12,'#a54841' if part['kind']=='weld' else '#8c6022' if part['basis']=='A' else '#294e63')
    if mode in ('front','section'):
        for d in scene['dimensions']:
            if d['view']!=mode:continue
            pa,pb=project(d['a']),project(d['b'])
            if math.dist(pa[:2],pb[:2])<.01:continue
            from .design_pdf import inches
            label=(d['label']+' / ' if d['label'] else '')+inches(d['value_in'])+' ['+d['basis']+']'
            sh.dim(tr(pa),tr(pb),d['offset'],label=label,value=d['value_in'],basis=d['basis'],ref=scene['reference'])
    if mode=='front':
        # Cut-plane trace is a true geometric slice, not a second view of a flat plate.
        if scene['section_axis'] in axes:
            ai=axes.index(scene['section_axis']);value=scene['section_at'];p=lo.copy();q=hi.copy();p[ai]=q[ai]=value
            sh.line(tr(p),tr(q),'#347b8f',.85,[9,3]);sh.label(*tr(q),'A-A',11,'#347b8f')
        for weld in scene['welds']:
            aa,bb=project(weld['a']),project(weld['b']);sh.line(tr(aa),tr(bb),'#ae4742',2)
            if not rail_welds:
                pt=tr([(aa[i]+bb[i])/2 for i in range(3)]);sh.label(pt[0]+7,pt[1]+4,weld['id'],10,'#a54841')
    sh.views.append(dict(sheet=sh.current,kind='connection_'+mode,assembly_id=scene['id'],scale_denominator=denom,points_per_inch=scale,
                         section_axis=scene['section_axis'] if mode=='section' else None,section_at=scene['section_at'] if mode=='section' else None))


def draw_assembly(sh,scene):
    sh.text(70,sh.H-160,f"{scene['reference']}  |  {scene['occurrence_count']} occurrence(s)  |  example {scene['representative_occurrence']}",13)
    sh.text(70,sh.H-183,'S = source design parameter   A = authored fictional fit/layout   |   Full source specifications remain in S7xx and source_records.json',12)
    draw_view(sh,scene,'front',(70,855,1090,620),'1  ASSEMBLED JOINT / ELEVATION')
    draw_view(sh,scene,'section',(1190,855,1120,620),'2  SECTION A-A / JOINED MEMBERS AND PLIES')
    draw_view(sh,scene,'iso',(70,155,1090,675),'3  ASSEMBLY / ISOMETRIC')
    x=1210;y=805;sh.text(x,y,'PARTS, ATTACHMENTS AND LOCAL DIMENSIONS',16,font='Helvetica-Bold');y-=31
    entries=[];groups={};part_labels={}
    for part in scene['parts']:
        label=part.get('annotation_group',part['id']);groups.setdefault(label,[]).append(part);part_labels[part['id']]=label
    def joined(ids):return ', '.join(dict.fromkeys(part_labels.get(i,i) for i in ids))
    for label,parts in groups.items():
        part=parts[0]
        description=part['description']
        if len(parts)>1 and part['kind']!='fastener':description+=f' | qty {len(parts)}; repeated group'
        if part.get('geometry',{}).get('type')=='box':description+=' | '+ ' x '.join(f'{v:g}' for v in part['geometry']['size'])+' in'
        if part['kind']=='fastener':
            description+=f" | qty {sum(p['count'] for p in parts)}; grip {part['grip']:g} in"
            if 'pattern' in part:
                pat=part['pattern'];description+=' | grid '+ ' / '.join(f'{n} at {d:g} in' for n,d in zip(pat['counts'],pat['spacing']) if n>1 and d is not None)
        basis=str(part['basis'])
        if basis not in ('S','A'):
            description+=' | Basis: '+basis
            basis='S/A' if 'S' in basis and 'A' in basis else 'S' if basis.startswith('S') else 'A'
        entries.append((label,basis,description))
    entries += [(w['id'],w['basis'],w['description']+' | '+joined(w['connects'])) for w in scene['welds']]
    entries += [(i['id'],i['basis'],i['description']+' | '+joined(i['connects'])) for i in scene.get('interfaces',[])]
    font=11;line=15
    estimate=sum(max(1,len(sh.lines(t,925,font)))*line+6 for _,_,t in entries)
    if estimate>480:font=10;line=13
    for label,basis,description in entries:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        label_size=min(11,11*56/max(1,stringWidth(label,'Helvetica-Bold',11)))
        sh.text(x,y,label,label_size,font='Helvetica-Bold');sh.text(x+64,y,basis,10,'#946320' if basis=='A' else '#243d49')
        y=sh.wrap(x+98,y,description,965,font,line)-6
    y-=9
    for note in scene['notes']:
        if y<220:break
        lines=sh.lines(note,1070,10)
        if y-len(lines)*14<190:break
        y=sh.wrap(x,y,note,1070,10,14)-10
    if y<155:raise ValueError('Assembly parts schedule overflow '+scene['id'])
    # Source/occurrence linkage is retained in a dedicated complete JSON index.
    sh.text(x,170,'Exact source variant, local assembly geometry and ALL notes: connection_assemblies.json / '+scene['id'],10)
