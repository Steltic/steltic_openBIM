"""Local geometric completion of retained HR brace selections, in inches."""
import math
from .pilots.model import add, sub, mul, dot, unit
from .assembly_scene import bounds
from .pilots.geometry import member_faces, extrude


def column_face_at_gusset(profiles,pid,weak):
    """Read the actual outer steel face in the gusset plane, including boxed columns."""
    from shapely.geometry import LineString,Polygon
    from .pilots.geometry import strips
    line=LineString([(-1e5,0.),(1e5,0.)]);edges=[]
    for ring in strips(profiles[pid],profiles):
        points=[(u,v) if weak else (-v,u) for u,v in ring]
        cut=Polygon(points).intersection(line)
        if not cut.is_empty:edges.append(cut.bounds[2])
    if not edges:raise ValueError('No column steel crosses the selected gusset plane: '+pid)
    return max(edges)


def support_selection(ctx,role,field,part_id,default):
    from .hr_detail_selections import SelectionConflict
    try:
        result=ctx.selected.get((role,field))
        return default if result is None else result
    except SelectionConflict as issue:
        original=next((s for s in ctx.model.get('connection_assemblies',[]) if s['id']==ctx.c.get('assembly_id')),None)
        weld=next((w for w in (original or {}).get('welds',[]) if w['id']==part_id),None)
        if not weld:raise
        issue.record(ctx.package,ctx.c['id'])
        ctx.a.notes.append('REVIEW REQUIRED. Competing '+role+' '+field+' values. The prior weld dimension is retained.')
        return math.dist(weld['a'],weld['b']) if field=='length_in' else weld['size']


def bound_base_plate(ctx):
    """Locate the separately selected column base in this brace occurrence frame."""
    from .bim_assemblies import transformed
    from .pilots.geometry import part_faces
    from .pilots.model import cross
    physical=ctx.package.get('physical',{})
    connections=physical.get('connections',[])
    current=next((c for c in connections if c['id']==ctx.c['id']),None)
    if not current or not current.get('assembly_instance'):return None
    frame=current['assembly_instance'];column=frame['bindings'].get('COLUMN')
    if not column:return None
    matches=[c for c in connections if c.get('detail_ref',{}).get('legacy_family') in ('review_base','review_wall_base')
             and column in c['member_ids'] and math.dist(c.get('point',frame['origin']),frame['origin'])<.01
             and c.get('assembly_instance')]
    if len(matches)!=1:return None
    other=matches[0]['assembly_instance']
    template=next((t for t in physical['assemblies'] if t['id']==other['template_id']),None)
    part=next((p for p in (template or {}).get('parts',[]) if p['id']=='P1' and 'base plate' in p.get('parameters',{}).get('description','').lower()),None)
    if not part:return None
    base_c=next((c for c in ctx.model.get('connections',[]) if c['id']==matches[0]['id']),None)
    if base_c:
        from .assembly_templates import build_scene
        base=build_scene(ctx.model,ctx.package,base_c)
        plate=next((q for q in base['parts'] if q['id']==part['id']),None)
        faces=plate['faces'] if plate else part_faces(part,ctx.p)
    else:faces=part_faces(part,ctx.p)
    axes=(frame['x_axis'],frame['y_axis'],cross(frame['x_axis'],frame['y_axis']))
    located=[]
    for face in faces:
        ring=[]
        for q in face:
            world=sub(transformed(q,other),frame['origin'])
            ring.append([dot(world,axis) for axis in axes])
        located.append(ring)
    if not located:return None
    return bounds(located),matches[0]['id'],part['id'],located


def bind_support_span(ctx,label,coordinate):
    """Bind each finite weld segment to the piece occupying its full station interval."""
    from .pilots.model import cross
    a=ctx.a
    host=next((p for p in a.parts if p['id']==label),None)
    if not host:return
    physical=ctx.package.get('physical',{})
    c=next((c for c in physical.get('connections',[]) if c['id']==ctx.c['id']),None)
    frame=(c or {}).get('assembly_instance',{});bound=frame.get('bindings',{}).get(label)
    if not bound:return
    axes=(frame['x_axis'],frame['y_axis'],cross(frame['x_axis'],frame['y_axis']))
    def local(q):return [dot(sub(q,frame['origin']),v) for v in axes]
    start=host['member']['axis'][0];span=sorted(p[coordinate] for p in host['member']['axis']);pieces=[]
    transverse=[i for i in range(3) if i!=coordinate]
    def station(at):
        point=list(start);point[coordinate]=at;return point
    for m in physical['members']:
        if m['profile_id']!=host['profile_id']:continue
        ends=[local(add(p,o)) for p,o in zip(m['axis'],m['end_offsets'])]
        if any(abs(p[i]-start[i])>.01 for i in transverse for p in ends):continue
        lo,hi=sorted(p[coordinate] for p in ends);lo=max(lo,span[0]);hi=min(hi,span[1])
        if hi-lo>.01:pieces.append((lo,hi,m['id'],[dot(m['local_y'],v) for v in axes]))
    if len(pieces)<2 or not any(row[2]==bound for row in pieces):return
    pieces.sort();ranges=[]
    # Overlapping source members at one station need an explicit occupancy
    # decision; the source renderer cannot assign one continuous weld twice.
    if any(b[0]<a[1]-.01 for a,b in zip(pieces,pieces[1:])):return
    a.parts.remove(host)
    for i,(lo,hi,mid,y) in enumerate(pieces):
        role=label if mid==bound else f'{label}-PIECE-{i+1}'
        part=a.member(role,host['profile_id'],station(lo),station(hi),y=y,description='Actual contiguous '+label.lower()+' receiver')
        part['located_extension']=mid!=bound
        ranges.append((lo,hi,role))
    revised=[]
    for weld in a.welds:
        if label not in weld['connects']:
            revised.append(weld);continue
        start,end=weld['a'],weld['b'];delta=sub(end,start)
        if abs(delta[coordinate])<1e-7:
            piece=next((r for r in ranges if r[0]-.01<=start[coordinate]<=r[1]+.01),None)
            if piece:weld['connects']=[piece[2] if r==label else r for r in weld['connects']]
            revised.append(weld);continue
        segments=[]
        for lo,hi,role in ranges:
            t0,t1=sorted(((lo-start[coordinate])/delta[coordinate],(hi-start[coordinate])/delta[coordinate]))
            t0=max(t0,0.);t1=min(t1,1.)
            if t1-t0<1e-7:continue
            segments.append(dict(weld,id=weld['id'] if role==label else weld['id']+'-'+role,
                a=add(start,mul(delta,t0)),b=add(start,mul(delta,t1)),
                connects=[role if r==label else r for r in weld['connects']]))
        for index,segment in enumerate(segments):
            segment.update(source_weld_id=weld.get('source_weld_id',weld['id']),segment_index=index,
                selected_total_length_in=math.dist(start,end),segment_count=len(segments))
        revised.extend(segments)
    a.welds=revised


def reinforcement(assembly, label, profile, start, axis, side, width, thickness, length):
    """Fit the inside of a reinforcing plate to the represented tube surface."""
    y = [0., 1., 0.]
    normal = [-axis[2], 0., axis[0]]
    dims = profile['dimensions']
    if profile['family'] == 'chs':
        radius = dims['d']/2
        # member_faces represents the CHS as 32 planar sectors. A rolled plate
        # must follow those very faces for both longitudinal welds to land.
        sectors = 32
        segment = 2*radius*math.sin(math.pi/sectors)
        centre = 0 if side > 0 else sectors//2
        low, high = centre-width/(2*segment), centre+width/(2*segment)
        stations = [low, *range(math.floor(low)+1, math.ceil(high)), high]
        def polygon_point(at, r):
            i = math.floor(at)
            fraction = at-i
            p = [r*math.cos(i*2*math.pi/sectors), r*math.sin(i*2*math.pi/sectors)]
            q = [r*math.cos((i+1)*2*math.pi/sectors), r*math.sin((i+1)*2*math.pi/sectors)]
            return [a+(b-a)*fraction for a,b in zip(p,q)]
        inner = [polygon_point(s, radius) for s in stations]
        outer = [polygon_point(s, radius+thickness/math.cos(math.pi/sectors)) for s in stations]
        # The ring is counter-clockwise in the right-handed section frame.
        ring = list(reversed(inner))+outer
        faces = extrude(ring, start, add(start,mul(axis,length)), y)
        plate = assembly.part(label, 'Source reinforcement fitted to the CHS surface',
            faces, 'A', 'plate', geometry={'type':'mesh','faces':faces}, thickness=thickness)
        edges = [add(start,add(mul(y,q[0]),mul(normal,q[1]))) for q in (inner[0],inner[-1])]
    else:
        breadth = dims.get('b',dims.get('width'))
        if not breadth:
            raise ValueError('Missing reinforcement support dimension for '+profile['id'])
        base = add(start, add(mul(y,side*breadth/2),mul(normal,-side*width/2)))
        plate = assembly.box(label,base,[length,thickness,width],'A',
            'Source reinforcement fitted to the planar brace side',x=axis,y=mul(y,side))
        edges = [base,add(base,mul(normal,side*width))]
    plate['parameters'] = {'width_in':width,'length_in':length,'thickness_in':thickness}
    return plate, edges


def slot_for_gusset(assembly, brace, gusset, thickness, width=None):
    """Cut the portion of the finite tube occupied by the final plate outline."""
    from shapely.geometry import Polygon, box
    start, end = brace['member']['axis']
    axis = unit(sub(end,start))
    depth_axis = [-axis[2],0,axis[0]]
    profile = assembly.profiles[brace['profile_id']]
    dims=profile['dimensions']
    depth=dims.get('h',dims.get('d'))
    if profile['family'] not in ('rhs','chs') or not depth:
        return None
    outline=Polygon([(dot(sub(q,start),axis),dot(sub(q,start),depth_axis)) for q in gusset['polygon']])
    # The tube wall can intersect only the part of the plate inside its actual
    # section envelope. Projecting every remote free-edge corner would overcut.
    engagement=outline.intersection(box(0,-depth/2,1e5,depth/2))
    if engagement.is_empty or engagement.bounds[2]<=1e-5:
        raise ValueError('Gusset does not engage the selected brace: '+brace['id'])
    length=engagement.bounds[2]+.0625
    width=thickness+.0625 if width is None else float(width)
    if width+1e-7<thickness:
        raise ValueError('Selected slot width is narrower than the gusset')
    return dict(start_in=0.,end_in=length,width_in=width,centre_in=0.,section_axis=0,
                basis='OpenBIM fit to actual gusset envelope; 1/16 in end relief',
                selected_plate_thickness_in=thickness)


def fit_detail_slot(assembly, width=None):
    parts={p['id']:p for p in assembly.parts}
    brace,gusset=parts['BRACE'],parts['GUSSET']
    slot=slot_for_gusset(assembly,brace,gusset,gusset['thickness'],width)
    if not slot:
        return
    member=brace['member']
    if slot['end_in']>=math.dist(*member['axis']):
        start,end=member['axis']
        member['axis'][1]=add(start,mul(unit(sub(end,start)),slot['end_in']+12))
    member['slots']=[slot]
    brace['faces']=member_faces(member,assembly.profiles)
    brace['bounds']=bounds(brace['faces'])


def fit_brb_rows(selected,axis,support_station,column_clearance=None):
    """Fit the specified row spacing without imposing a second source pitch."""
    rows=selected['rows'];count=selected['count'];dia=selected['diameter'];pitch=selected['pitch']
    if rows<1 or count<2*rows or count%rows or pitch<=dia:
        raise ValueError('Invalid selected BRB bolt count/rows/pitch')
    edge=max(1.5*dia,2.)
    other_pitch=selected.get('orthogonal_pitch') or 3*dia
    across=count//rows
    choices=[]
    for row_axis,n_along,n_across,s_along,s_across in (
            ('transverse',across,rows,other_pitch,pitch),('longitudinal',rows,across,pitch,other_pitch)):
        width=(n_across-1)*s_across+2*edge
        start=max(support_station+edge,support_station+(width/2*abs(axis[0])+.125)/abs(axis[2]))
        if column_clearance is not None:
            start=max(start,(column_clearance+width/2*abs(axis[2])+.125)/axis[0])
        far=start+2*edge+(n_along-1)*s_along+max(2*edge,4.)
        layout=dict(row_axis=row_axis,along_count=n_along,across_count=n_across,
                    along_pitch=s_along,across_pitch=s_across,adopted_orthogonal_pitch=other_pitch)
        choices.append((far,start,layout))
    _,start,layout=min(choices,key=lambda item:item[0])
    return start,layout


def bolted_brb_end(assembly, selected, axis, station, thickness, support_station,layout=None,casing_depth=None,core=None):
    """Two source-selected splice plates join the finite core end to the gusset."""
    count,rows,pitch=selected['count'],selected['rows'],selected['pitch']
    dia=selected['diameter']
    if rows<1 or count<2*rows or count%rows or pitch<=dia:
        raise ValueError('Invalid selected BRB bolt count/rows/pitch')
    layout=layout or dict(row_axis='transverse',along_count=count//rows,across_count=rows,
                          along_pitch=3*dia,across_pitch=pitch,adopted_orthogonal_pitch=3*dia)
    columns=layout['along_count']
    edge=max(1.5*dia,2.)
    gauge=layout['across_pitch']
    width=(layout['across_count']-1)*gauge+2*edge
    start=max(station,support_station+edge)
    first=start+edge
    last=first+(columns-1)*layout['along_pitch']
    far=last+edge
    normal=[-axis[2],0,axis[0]]
    def at(s,y,z):
        return add(mul(axis,s),add([0,y,0],mul(normal,z)))
    def plate(label,s0,s1,y,t,description):
        points=[at(s,y,z) for s,z in ((s0,-width/2),(s1,-width/2),(s1,width/2),(s0,width/2))]
        return assembly.polygon(label,points,t,basis='A',description=description)
    splice_t=max(.5,thickness/2)
    # The source names gusset bearing and block shear for the full group. All
    # selected bolts pass through both splice plates and the central gusset.
    # The supplier extension joins the far (unbolted) ends of the outer plies.
    supplier_overlap=max(2*edge,4.)
    tail=far+supplier_overlap
    if core:
        from .brb_supplier_core import extension
        splice_end=extension(assembly,axis,far+.0625,tail,width,thickness,core)
    else:
        splice_end=tail
        edge_width=max(width,casing_depth or width)
        end_points=[at(s,-thickness/2,d) for s,d in ((far+.0625,-width/2),(tail,-edge_width/2),
                                                    (tail,edge_width/2),(far+.0625,width/2))]
        assembly.polygon('CORE-END',end_points,thickness,basis='A',description='Supplier core extension between splice plates')
    for i,y in enumerate((-thickness/2-splice_t,thickness/2)):
        plate('SPLICE'+str(i),start,splice_end,y,splice_t,'Source splice plate; openBIM fit thickness and outline')
    assembly.interfaces.append(dict(id='SPLICE-TO-CORE',kind='supplier_interface',basis='A',
        connects=['SPLICE0','CORE-END','SPLICE1'],
        description='Supplier-end engagement outside the source-selected bolted gusset group'))
    points=[at(first+i*layout['along_pitch'],-thickness/2-splice_t,(j-(layout['across_count']-1)/2)*gauge)
            for i in range(columns) for j in range(layout['across_count'])]
    group=assembly.fastener('GUSSET-BOLTS',points,[0,1,0],dia,thickness+2*splice_t,
        ['SPLICE0','GUSSET','SPLICE1'],f'{count} x {dia:g} in {selected["material"]} source splice bolts')
    group.update(functional_kind='bolt',selected_material=selected['material'],parameters=dict(
        selected_rows=rows,selected_row_spacing_in=pitch,**layout))
    assembly.notes.append(f'S: {count} x {dia:g} in {selected["material"]} bolts in {rows} rows at {pitch:g} in. A: row spacing oriented {layout["row_axis"]} to the brace; orthogonal spacing {layout["adopted_orthogonal_pitch"]:g} in. The finite group clears its actual supports.')
    contour=[(at(s,0,z)[0],at(s,0,z)[2]) for s in (start,far) for z in (-width/2,width/2)]
    return at(far+supplier_overlap,0,0),contour,[group]
