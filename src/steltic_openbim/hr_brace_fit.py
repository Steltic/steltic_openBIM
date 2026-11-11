"""Local geometric completion of retained HR brace selections, in inches."""
import math
from .pilots.model import add, sub, mul, dot, unit
from .assembly_scene import bounds
from .pilots.geometry import member_faces, extrude


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
    axes=(frame['x_axis'],frame['y_axis'],cross(frame['x_axis'],frame['y_axis']))
    points=[]
    for face in part_faces(part,ctx.p):
        for q in face:
            world=sub(transformed(q,other),frame['origin'])
            points.append([dot(world,axis) for axis in axes])
    if not points:return None
    return [(min(q[i] for q in points),max(q[i] for q in points)) for i in range(3)],matches[0]['id'],part['id']


def bind_beam_span(ctx):
    """Split a continuous-looking drawing host at its real physical piece boundaries."""
    from .pilots.model import cross
    a=ctx.a
    beam=next((p for p in a.parts if p['id']=='BEAM'),None)
    if not beam:return
    physical=ctx.package.get('physical',{})
    c=next((c for c in physical.get('connections',[]) if c['id']==ctx.c['id']),None)
    frame=(c or {}).get('assembly_instance',{});bound=frame.get('bindings',{}).get('BEAM')
    if not bound:return
    axes=(frame['x_axis'],frame['y_axis'],cross(frame['x_axis'],frame['y_axis']))
    def local(q):return [dot(sub(q,frame['origin']),v) for v in axes]
    span=sorted(p[0] for p in beam['member']['axis']);z=beam['member']['axis'][0][2];pieces=[]
    for m in physical['members']:
        if m['profile_id']!=beam['profile_id']:continue
        ends=[local(add(p,o)) for p,o in zip(m['axis'],m['end_offsets'])]
        if any(abs(p[1])>.01 or abs(p[2]-z)>.01 for p in ends):continue
        lo,hi=sorted(p[0] for p in ends);lo=max(lo,span[0]);hi=min(hi,span[1])
        if hi-lo>.01:pieces.append((lo,hi,m['id'],[dot(m['local_y'],v) for v in axes]))
    if len(pieces)<2 or not any(row[2]==bound for row in pieces):return
    pieces.sort();ranges=[]
    # Overlapping source members at one station need an explicit occupancy
    # decision; the source renderer cannot assign one continuous weld twice.
    if any(b[0]<a[1]-.01 for a,b in zip(pieces,pieces[1:])):return
    a.parts.remove(beam)
    for i,(lo,hi,mid,y) in enumerate(pieces):
        role='BEAM' if mid==bound else f'BEAM-PIECE-{i+1}'
        part=a.member(role,beam['profile_id'],[lo,0,z],[hi,0,z],y=y,description='Actual contiguous beam receiver')
        part['located_extension']=mid!=bound
        ranges.append((lo,hi,role))
    revised=[]
    for weld in a.welds:
        if 'BEAM' not in weld['connects']:
            revised.append(weld);continue
        start,end=weld['a'],weld['b'];delta=sub(end,start)
        if abs(delta[0])<1e-7:
            piece=next((r for r in ranges if r[0]-.01<=start[0]<=r[1]+.01),None)
            if piece:weld['connects']=[piece[2] if r=='BEAM' else r for r in weld['connects']]
            revised.append(weld);continue
        segments=[]
        for lo,hi,role in ranges:
            t0,t1=sorted(((lo-start[0])/delta[0],(hi-start[0])/delta[0]))
            t0=max(t0,0.);t1=min(t1,1.)
            if t1-t0<1e-7:continue
            segments.append(dict(weld,id=weld['id'] if role=='BEAM' else weld['id']+'-'+role,
                a=add(start,mul(delta,t0)),b=add(start,mul(delta,t1)),
                connects=[role if r=='BEAM' else r for r in weld['connects']]))
        for index,segment in enumerate(segments):
            segment.update(source_weld_id=weld['id'],segment_index=index,
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


def bolted_brb_end(assembly, selected, axis, station, thickness, support_station):
    """Two source-selected splice plates join the finite core end to the gusset."""
    count,rows,pitch=selected['count'],selected['rows'],selected['pitch']
    dia=selected['diameter']
    if rows<1 or count<2*rows or count%rows or pitch<=dia:
        raise ValueError('Invalid selected BRB bolt count/rows/pitch')
    columns=count//rows
    edge=max(1.5*dia,2.)
    gauge=max(3*dia,pitch)
    width=(rows-1)*gauge+2*edge
    start=max(station,support_station+edge)
    first=start+edge
    last=first+(columns-1)*pitch
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
    for i,y in enumerate((-thickness/2-splice_t,thickness/2)):
        plate('SPLICE'+str(i),start,far+supplier_overlap,y,splice_t,'Source splice plate; openBIM fit thickness and outline')
    plate('CORE-END',far+.0625,far+supplier_overlap,-thickness/2,thickness,
          'Supplier core-end extension fitted between the outer splice plates')
    assembly.interfaces.append(dict(id='SPLICE-TO-CORE',kind='supplier_interface',basis='A',
        connects=['SPLICE0','CORE-END','SPLICE1'],
        description='Supplier-end engagement outside the source-selected bolted gusset group'))
    points=[at(first+i*pitch,-thickness/2-splice_t,(j-(rows-1)/2)*gauge)
            for i in range(columns) for j in range(rows)]
    group=assembly.fastener('GUSSET-BOLTS',points,[0,1,0],dia,thickness+2*splice_t,
        ['SPLICE0','GUSSET','SPLICE1'],f'{count} x {dia:g} in {selected["material"]} source splice bolts')
    group.update(functional_kind='bolt',selected_material=selected['material'])
    assembly.notes.append(f'S: {count} x {dia:g} in {selected["material"]} bolts in {rows} rows at {pitch:g} in. A: supplier-end station, cover plate geometry and remaining local set-out.')
    contour=[(at(s,0,z)[0],at(s,0,z)[2]) for s in (start,far) for z in (-width/2,width/2)]
    return at(far+supplier_overlap,0,0),contour,[group]
