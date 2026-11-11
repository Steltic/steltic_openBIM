"""Fit an integral clevis head and its separate, moving core to a located pin stack."""
import math
import re
from collections import defaultdict
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from .pilots.model import dot, mul
from .assembly_scene import bounds
from .brb_supplier_core import moving_head_projection


def allocate_ends(member, ends, opposite_trim=None):
    """Allocate the two casing ends together, preserving the actual checked core length."""
    core = member['supplier_core']
    travel = core['reported_elongation_in']
    if travel <= 0 or len(ends) not in (1,2) or (len(ends)==1 and opposite_trim is None):
        raise ValueError('A located opposite terminal and a positive HR travel are required')
    limits = []
    for connection_id, source, receiver in ends:
        pin = receiver['ufm_for_one_primary_leaf']['minimum_pin_station_in']
        nose = pin + source['pin_hole_diameter_in'] / 2 + source['extension_in']
        limits.append((connection_id, nose))
    head_thickness = 1.
    gap = travel + .0625
    work_length = math.dist(*member['axis'])
    nonyielding = work_length - core['yielding_length_in']
    # Keep a finite transition between the checked yielding length and each full
    # end. A notch is machined in the moving head wherever the stationary eye enters it.
    total = sum(nose + .125 + head_thickness + gap for _, nose in limits)+(opposite_trim or 0.)
    inset = max(0., (total - nonyielding + .5) / len(limits))
    return {cid:dict(front_in=nose+.125-inset, thickness_in=head_thickness,
                     required_travel_in=travel, casing_gap_in=gap)
            for cid,nose in limits}


def configure_selected_heads(package,model):
    """Bind the coupled movement space to authenticated pin/end selections before detailing."""
    from .saved_assemblies import material_for
    source=package.get('source_handoff',{});records=source.get('records',{})
    physical=package['physical'];catalog={row['id']:row for row in physical['materials']}
    physical_members={m['id']:m for m in physical['members']};physical_connections={c['id']:c for c in physical['connections']}
    members={m['id']:m for m in model['members']};connections={c['id']:c for c in model['connections']}
    engineering={r['id']:r['data'] for r in package.get('design_records',[])}
    groups=defaultdict(list);indexes={}
    for cid,c in connections.items():
        active=source.get('occurrences',{}).get(cid,{}).get('applications',[])
        for app in active:
            if not app.get('selected'):continue
            data=records[app['record_id']].get('data',{});pin=data.get('pin_stack');r=data.get('receiver_selection',{})
            if not pin or 'whitmore_clear_station_in' not in r.get('ufm_for_one_primary_leaf',{}):continue
            mid=r['brace_member_id'];m=members[mid]
            if (cid!=r['native_connection_id'] or m['axis']!=r['axis'] or app['record_id'] not in c['design_record_ids'] or
                    mid not in c['member_ids'] or math.dist(r['point_in'],c['point'])>1e-5):
                raise ValueError('Selected moving head does not belong to its source members and workpoint')
            end=min(range(2),key=lambda i:math.dist(r['point_in'],m['axis'][i]))
            if math.dist(r['point_in'],m['axis'][end])>1e-4 or (mid,end) in indexes:
                raise ValueError('Selected moving head has duplicate or unlocated supplier terminal')
            indexes[mid,end]=cid;groups[mid].append((cid,pin,r))
    for mid,ends in groups.items():
        member=members[mid];spec=member.get('supplier_core')
        if not spec:raise ValueError('Source-selected integral moving head lacks its supplier core: '+mid)
        opposite=None
        if len(ends)==1:
            end=next(i for i in (0,1) if (mid,i) not in indexes)
            opposite=math.dist(member['end_offsets'][end],[0.,0.,0.])
        allocated=allocate_ends(member,ends,opposite)
        for end in (0,1):
            cid=indexes.get((mid,end))
            if cid is None:continue
            fit=allocated[cid];start,far=member['axis'][end],member['axis'][1-end];length=math.dist(start,far)
            length_trim=fit['front_in']+fit['thickness_in']+fit['casing_gap_in']
            offset=[(b-a)*length_trim/length for a,b in zip(start,far)]
            for target in (member,physical_members[mid]):
                old=target['end_offsets'][end]
                if math.dist(old,[0.,0.,0.])>1e-5 and math.dist(old,offset)>1e-4:
                    raise ValueError('Source casing terminal and selected moving-head travel conflict at '+cid)
                target['end_offsets'][end]=offset
            for target in (connections[cid],physical_connections[cid]):
                target.setdefault('parameters',{})['moving_head_fit']=dict(fit)
        checks=engineering[spec['record']].get('checks',[])
        grades={match[1] for q in checks if (match:=re.search(r'casing, HSS[^ ]+ (ASTM A500 Grade [A-Z])',q.get('limit_state','')))}
        if len(grades)>1:raise ValueError('Source has conflicting casing materials for '+mid)
        if grades:
            material=material_for({'id':mid,'selected_material':grades.pop()},'casing',None,catalog,[spec['record']])
            member['material_id']=physical_members[mid]['material_id']=material
    if groups:physical['materials']=list(catalog.values())
    return len(groups)


def fixed_plates(parts, roles, axis, normal):
    fixed=[]
    for p in parts:
        par=p.get('parameters',{})
        if p['id'] not in roles and not par.get('free_edge_bar'):
            continue
        faces=p['faces'];ys=[q[1] for f in faces for q in f];y0,y1=min(ys),max(ys)
        footprints=[]
        for f in faces:
            if max(abs(q[1]-y0) for q in f)>1e-6:continue
            poly=Polygon([(dot(q,axis),dot(q,normal)) for q in f])
            if poly.is_valid and poly.area>1e-7:footprints.append(poly)
        if not footprints:raise ValueError('Missing stationary pin plate footprint '+p['id'])
        fixed.append((p['id'],y0,y1,unary_union(footprints)))
    return fixed


def obstacles(plates,start,end,clearance=.03125):
    windows=[]
    for _,y0,y1,footprint in plates:
        found=footprint.intersection(box(start-clearance,-10000,end+clearance,10000))
        pieces=list(found.geoms) if hasattr(found,'geoms') else [found]
        for cut in pieces:
            if cut.is_empty:continue
            _,d0,_,d1=cut.bounds
            windows.append(box(y0-clearance,d0-clearance,y1+clearance,d1+clearance))
    return unary_union(windows)


def rectangular_layers(layers, at):
    """Closed exterior of successive measured orthogonal ply sections, with an optional taper."""
    from shapely.geometry import Point
    ys=set();ds=set()
    for s0,s1,section,sy,sd in layers:
        if s1<=s0 or section.is_empty:raise ValueError('Empty machined moving-core section')
        polys=list(section.geoms) if section.geom_type=='MultiPolygon' else [section]
        for p in polys:
            for ring in [p.exterior,*p.interiors]:
                for y,d in ring.coords:ys.add(round(y,8));ds.add(round(d,8))
    ys,ds=sorted(ys),sorted(ds); occupied=set()
    for k,(_,_,section,_,_) in enumerate(layers):
        for i,(a,b) in enumerate(zip(ys,ys[1:])):
            for j,(u,w) in enumerate(zip(ds,ds[1:])):
                if section.contains(Point((a+b)/2,(u+w)/2)):occupied.add((i,j,k))
    faces=[]
    directions=((-1,0,0,(0,4,7,3)),(1,0,0,(1,2,6,5)),(0,-1,0,(0,1,5,4)),
                (0,1,0,(3,7,6,2)),(0,0,-1,(0,3,2,1)),(0,0,1,(4,5,6,7)))
    for i,j,k in sorted(occupied):
        s0,s1,_,sy,sd=layers[k]
        ring=[(ys[i],ds[j]),(ys[i+1],ds[j]),(ys[i+1],ds[j+1]),(ys[i],ds[j+1])]
        corners=[at(s0,d,y) for y,d in ring]+[at(s1,d*sd,y*sy) for y,d in ring]
        for di,dj,dk,face in directions:
            if (i+di,j+dj,k+dk) not in occupied:faces.append([corners[n] for n in face])
    if not faces:raise ValueError('No moving stock remains after machining')
    return faces


def moving_head(a, brace, sourced, rows, profile, axis, normal, at, end, eye_half):
    core=brace['supplier_core'];front=sourced['front_in'];back=front+sourced['thickness_in']
    gap=sourced['casing_gap_in'];terminal=back+gap;travel=core['reported_elongation_in']
    if gap+1e-7<travel:raise ValueError('Head/casing clearance is less than the HR design travel')
    dims=profile['dimensions'];hy=dims['b']/2-dims['t'];hd=dims['h']/2-dims['t']
    fixed_ids={r['id'] for r in rows if r['connected_to']!='brace_end'}
    fixed=fixed_plates(a.parts,fixed_ids,axis,normal)
    shell=box(-dims['b']/2,-dims['h']/2,dims['b']/2,dims['h']/2).difference(box(-hy,-hd,hy,hd))
    # The pin fixes the moving tongues to the gusset locally. The separate
    # casing may approach this joint by the full reported axial elongation.
    claimed=obstacles(fixed,terminal-travel,terminal+24+travel,.005)
    if shell.intersection(claimed).area>1e-7:
        raise ValueError('Stationary gusset reaches casing wall within the required travel')
    tongues=[r for r in rows if r['connected_to']=='brace_end']
    grip=max(r['finish'] for r in rows)-min(r['start'] for r in rows)
    stock=box(-grip/2-.5,-eye_half-1.25,grip/2+.5,eye_half+1.25)
    head=stock.difference(obstacles(fixed,front,back))
    if head.geom_type!='Polygon':raise ValueError('The fitted clevis head is disconnected')
    transfers=[]
    for r in tongues:
        leaf=box(r['start'],-eye_half,r['finish'],eye_half)
        contact=leaf.intersection(head).area
        if contact+1e-6<leaf.area:raise ValueError('Moving head does not engage the full clevis leaf '+r['id'])
        transfers.append(dict(ply=r['id'],face_area_in2=contact))
        a.interfaces.append(dict(id='CLEVIS-HEAD-'+r['id'],basis='A',kind='integral_moving_head',
            connects=[r['id'],'END-CAP'],description='Continuous machined supplier tongue-to-head bearing section'))
    part=a.part('END-CAP','Integral moving clevis head with finite pockets around the stationary gussets',
                rectangular_layers([(front,back,head,1.,1.)],at),'A','plate',selected_material=tongues[0]['material'])
    cy=min(hy-.25,max(grip/2+.125,core['end_thickness_in']/2+.5))
    cd=min(hd-.25,max(eye_half,core['depth_in']/2+.75))
    carrier=box(-cy,-cd,cy,cd);core_tip=box(-core['end_thickness_in']/2,-core['depth_in']/2,
                                         core['end_thickness_in']/2,core['depth_in']/2)
    if not carrier.covers(core_tip):raise ValueError('Core transition falls outside the casing opening')
    stations=[back]
    for _,y0,y1,foot in fixed:
        if max(y0,-cy)>min(y1,cy):continue
        strip=foot.intersection(box(back,-cd-.0625,terminal,cd+.0625))
        if not strip.is_empty:stations.append(strip.bounds[2]+.0625)
    merge=max(stations)
    if merge>=terminal-.0625:raise ValueError('Stationary pin steel reaches the actual axial-core joint')
    stations=sorted(set([round(s,8) for s in stations if s>back+.0001]+[back,merge]))
    stations=[s for i,s in enumerate(stations) if not i or s-stations[i-1]>.00001]
    layers=[]
    for lo,hi in zip(stations,stations[1:]):
        section=carrier.difference(obstacles(fixed,lo,hi))
        if section.area<core['area_in2']-1e-6:raise ValueError('Machined supplier projection is smaller than its selected yielding core')
        layers.append((lo,hi,section,1.,1.))
    layers.append((stations[-1],terminal,carrier,core['end_thickness_in']/(2*cy),core['depth_in']/(2*cd)))
    first=layers[0][2];contact=first.intersection(head).area
    if contact+1e-6<core['area_in2']:raise ValueError('Clevis head misses its moving axial-core projection')
    moving_head_projection(a,axis,mul(axis,back),gap,core)
    proj=next(q for q in a.parts if q['id']=='CORE-END')
    proj['faces']=rectangular_layers(layers,at);proj['bounds']=bounds(proj['faces'])
    for k in ('polygon','normal','thickness'):proj.pop(k,None)
    proj['description']='Machined core fork from moving head to the finite axial-core end, inside the clear casing opening'
    proj['parameters'].update(terminal_face_area_in2=core_tip.area,minimum_carrier_area_in2=min([core_tip.area,*[l[2].area for l in layers]]))
    part['parameters']=dict(source_role='brb_moving_head',required_stroke_in=travel,actual_head_to_casing_gap_in=gap,
                head_front_station_in=front,head_back_station_in=back,casing_face_station_in=terminal,
                gusset_nose_station_in=end,head_section_area_in2=head.area,head_to_core_fork_contact_in2=contact,
                minimum_core_extension_section_in2=proj['parameters']['minimum_carrier_area_in2'],
                stationary_plate_to_swept_casing_overlap_in2=shell.intersection(claimed).area,actual_tongue_contacts=transfers)
    return terminal
