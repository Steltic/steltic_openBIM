"""Complete source-selected brace interfaces for an ordinary, located HR job."""
import copy
import math

from shapely.geometry import LineString, Polygon

from .assembly_scene import Assembly
from .bim_assemblies import index, parts, transformed
from .drawing_workflow import fingerprint
from .hr_brace_fit import slot_for_gusset
from .hr_detail_selections import selected_fields, SelectionConflict
from .pilots.geometry import strips
from .pilots.model import add, sub, mul, dot, cross, unit
from .review_assemblies import hull
from .saved_assemblies import native_parts
from .stmf_fit import local


def actual_ends(member):
    return [add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]


def cross_section(member,profiles,frame,origin):
    ray=unit(sub(*reversed(member['axis'])))
    y=member['local_y'];z=cross(ray,y)
    return [Polygon([local(add(origin,add(mul(y,u),mul(z,v))),frame,True)[:2] for u,v in ring])
            for ring in strips(profiles[member['profile_id']],profiles)]


def support_face(member,profiles,frame,thickness):
    ends=actual_ends(member);z=cross(frame['x_axis'],frame['y_axis'])
    on_axis=add(ends[0],mul(z,dot(sub(frame['origin'],ends[0]),z)))
    sections=cross_section(member,profiles,frame,on_axis)
    if not sections:raise ValueError('Receiving profile has no numeric section')
    # Include all section corners inside the actual plate thickness. A web,
    # flange or hollow section must expose one real face along this weld.
    stations={-thickness/2,0.,thickness/2}
    stations.update(y for p in sections for _,y in p.exterior.coords if abs(y)<thickness/2)
    extremes=[]
    for y in stations:
        line=LineString([(-1e6,y),(1e6,y)])
        cuts=[poly.intersection(line) for poly in sections if poly.intersects(line)]
        if not cuts:raise ValueError('The gusset plane does not meet solid receiving steel')
        extremes.append(max(cut.bounds[2] for cut in cuts))
    if max(extremes)-min(extremes)>1e-4:
        raise ValueError('The receiving face changes across the selected gusset thickness')
    return max(extremes),sorted(local(p,frame,True)[2] for p in ends)


def complete_slotted_end(package,connection,brace,support,point,profiles,catalogue):
    selected=selected_fields(package,connection)
    thickness=selected.get(('gusset','thickness_in'))
    material=selected.get(('gusset','material'))
    size=selected.get(('brace_slot_weld','size_in'))
    length=selected.get(('brace_slot_weld','length_in'))
    count=selected.get(('brace_slot_weld','count'))
    if not thickness or not material or not size or not length or count!=4:
        raise ValueError('Slotted brace needs its selected gusset thickness/grade and four-line weld size/length')
    profile=profiles[brace['profile_id']]
    if profile['family'] not in ('rhs','chs'):
        raise ValueError('The selected slotted connection requires a tubular brace')
    width=selected.get(('slot','width_in'))
    clearance=selected.get(('slot','clearance_in'))
    if width is None:width=thickness+(.0625 if clearance is None else clearance)
    axis=brace['axis'];end=min(range(2),key=lambda i:math.dist(point,axis[i]))
    if math.dist(point,axis[end])>1e-4:
        raise ValueError('A brace end workpoint must coincide with the selected joint')
    v=unit(sub(axis[1-end],axis[end]))
    z=unit(sub(support['axis'][1],support['axis'][0]))
    normal=sub(v,mul(z,dot(v,z)))
    if math.dist(normal,[0.,0.,0.])<1e-7:raise ValueError('Collinear members need a splice attachment selection')
    x=unit(normal);y=cross(z,x)
    frame=dict(origin=point,x_axis=x,y_axis=y)
    world_section=(brace['local_y'],cross(unit(sub(axis[1],axis[0])),brace['local_y']))
    slot_axis=max(range(2),key=lambda i:abs(dot(world_section[i],y)))
    if abs(dot(world_section[slot_axis],y))<1-1e-7:
        raise ValueError('The gusset plane requires an oblique section slot')
    face,limits=support_face(support,profiles,frame,thickness)
    vl=local(v,frame);normal2=[-vl[2],0.,vl[0]]
    extent=max(abs(dot(add(mul(world_section[0],u),mul(world_section[1],w)),transformed(normal2,frame,True)))
               for ring in strips(profile,profiles) for u,w in ring)
    # The material's nearest corner clears the support. The plate and its
    # selected longitudinal welds extend to the actual tube wall.
    station=max(0.,(face+extent*abs(vl[2])+.125)/vl[0])
    original=actual_ends(brace)
    if math.dist(brace['end_offsets'][end],[0.,0.,0.])>1e-7:
        station=dot(sub(original[end],point),v)
    start=mul(vl,station)
    a=Assembly('Slotted brace to '+support['kind'],profiles)
    support_role='COLUMN' if support['kind'] in ('column','post','col') else 'BEAM'
    weld_role='gusset_column_weld' if support_role=='COLUMN' else 'gusset_beam_weld'
    support_length=selected.get((weld_role,'length_in'))
    if support_length is None:support_length=max(length,2*extent)
    if limits[1]-limits[0]<support_length:raise ValueError('Selected support weld exceeds the finite receiving member')
    centre=start[2];lo=min(max(centre-support_length/2,limits[0]),limits[1]-support_length)
    hi=lo+support_length
    fold_ratio=selected.get(('brace_end_clearance','depths'))
    if fold_ratio is not None:
        if fold_ratio<=0:raise ValueError('Invalid selected linear brace-end clearance')
        fold=max(dot(q,vl) for q in ([face,0.,lo],[face,0.,hi]))
        minimum=fold+fold_ratio*thickness
        if station<minimum-1e-6 and math.dist(brace['end_offsets'][end],[0.,0.,0.])>1e-7:
            raise ValueError('Selected finite terminal position violates its linear gusset clearance')
        station=max(station,minimum);start=mul(vl,station)
    remaining=dot(sub(original[1-end],point),v)-station
    if remaining<=length+thickness+.0625:raise ValueError('Selected weld and source member leave insufficient terminal length')
    b=a.member('BRACE',brace['profile_id'],start,add(start,mul(vl,min(remaining,length+thickness+5.))),
               y=local(brace['local_y'],frame))
    host_axis=local(actual_ends(support)[0],frame,True)
    a.member(support_role,support['profile_id'],[host_axis[0],host_axis[1],lo],[host_axis[0],host_axis[1],hi],
             y=local(support['local_y'],frame))
    outline=[(face,lo),(face,hi)]
    for side in (-1,1):
        terminal=add(start,mul(normal2,side*extent))
        finish=add(terminal,mul(vl,length))
        edge=add(finish,mul(vl,thickness))
        outline.extend([(terminal[0],terminal[2]),(edge[0],edge[2])])
        for surface in (-1,1):
            q=[terminal[0],surface*thickness/2,terminal[2]]
            a.weld(f'WB{side}{surface}',q,add(q,mul(vl,length)),['BRACE','GUSSET'],size,
                   description='Selected slot-edge fillet on the physical tubular wall')
    gusset=a.polygon('GUSSET',[[u,-thickness/2,w] for u,w in hull(outline)],thickness,
                     description='Source gusset thickness and material; openBIM perimeter fitted to its receivers')
    gusset['selected_material']=material
    support_size=selected.get((weld_role,'size_in'))
    support_kind=selected.get((weld_role,'kind'))
    if support_size or support_kind in ('CJP','PJP'):
        a.weld('WGC' if support_role=='COLUMN' else 'WGB',[face,-thickness/2,lo],[face,-thickness/2,hi],
               [support_role,'GUSSET'],support_size or 0.,kind=support_kind or 'fillet',
               description='Selected gusset support weld along the actual steel face')
    else:
        a.interfaces.append(dict(id='GUSSET-SUPPORT',kind='contact',connects=[support_role,'GUSSET'],
            basis='Located contact between selected receivers; weld sizing remains in HR design evidence'))
    consumables=[m for m in catalogue.values() if 'weld' in m.get('source_item','').lower()]
    for weld in a.welds:
        weld['selected_material']=(consumables[0]['specification'] if len(consumables)==1 else
                                  'Weld consumable grade unspecified in the HR handoff')
    slot=slot_for_gusset(a,b,gusset,thickness,width)
    if fold_ratio is not None:
        from .brace_linear_clearance import dimension
        restrained=[w['id'] for w in a.welds if support_role in w['connects'] and 'GUSSET' in w['connects']]
        dimension(a,vl,fold_ratio,fold,station,restrained)
        gusset['description']+=f'; linear brace-end clearance {station-fold:.4f} in (selected minimum {fold_ratio:g}t)'
    new_offsets=copy.deepcopy(brace['end_offsets'])
    new_offsets[end]=sub(transformed(start,frame),axis[end])
    new_ends=[add(p,o) for p,o in zip(axis,new_offsets)]
    finite_length=math.dist(*new_ends)
    prior_length=math.dist(*original)
    shift=dot(sub(new_ends[0],original[0]),unit(sub(original[1],original[0])))
    other=[]
    for cut in brace.get('slots',[]):
        if cut.get('connection_id')==connection['id']:continue
        depth=cut['end_in']-cut['start_in']
        lo=0. if abs(cut['start_in'])<1e-6 else finite_length-depth if abs(cut['end_in']-prior_length)<1e-6 else cut['start_in']-shift
        if lo< -1e-7 or lo+depth>finite_length+1e-7:raise ValueError('New cutback conflicts with an existing machining feature')
        other.append(dict(cut,start_in=lo,end_in=lo+depth))
    depth=slot['end_in']
    slot.update(connection_id=connection['id'],section_axis=slot_axis,start_in=finite_length-depth if end else 0.,
                end_in=finite_length if end else depth)
    scene=a.result();scene['source_record_ids']=connection['design_record_ids']
    made=native_parts(scene,{'parts':[]},catalogue)
    receivers=[dict(id=p['id'],kind='member',profile_id=p['profile_id'],axis=p['member']['axis'],
                    local_y=p['member']['local_y']) for p in a.parts if p.get('member')]
    tid='openbim-joint-'+fingerprint([connection['id'],made,receivers])[:16]
    template=dict(id=tid,basis='OpenBIM finite contour and slot fitted to located source selections',
                  parts=made,receivers=receivers,source_record_ids=connection['design_record_ids'],source_interfaces=a.interfaces)
    template['revision']=fingerprint(template)
    frame.update(template_id=tid,revision=template['revision'],bindings={'BRACE':brace['id'],support_role:support['id']})
    return template,frame,new_offsets,other+[slot]


def complete_native_hr(original):
    """Return a derived physical revision, while keeping all original inputs immutable."""
    if original.get('module')!='HR' or not original.get('source_handoff'):return original
    source=original['source_handoff'];physical=original['physical'];templates=index(physical)
    pending=[]
    for c in physical['connections']:
        fields=selected_fields(original,c)
        variants={v['value'] for v in fields.sources.get(('connection','variant'),[])}
        if not (variants & {'brb_pinned','brb_bolted'} or any(k[0]=='brace_slot_weld' for k in fields)):continue
        placed=parts(c,templates)
        if any('GUSSET' in p['id'].upper() and p.get('geometry') for p in placed):continue
        pending.append(c['id'])
    from .physical_pdf import connection_details
    def bindings_match(physical):
        return all(c.get('drawing_ref')=='1/'+row['reference'] and
                   c.get('detail_ref',{}).get('source_drawing')=='1/'+row['reference']
                   for row in connection_details(physical['connections']) for c in row['connections'])
    if not pending and bindings_match(physical):return original
    body={k:v for k,v in original.items() if k!='source_handoff'}
    if source['source_bindings'].get('native_content_sha256')!=fingerprint(body):
        raise ValueError('Native body differs from the authenticated HR source before geometry completion')
    package=copy.deepcopy(original);physical=package['physical']
    members={m['id']:m for m in physical['members']};joints={j['id']:j for j in physical['joints']}
    catalogue={m['id']:m for m in physical['materials']};profiles={p['id']:p for p in physical['profiles']}
    cs={c['id']:c for c in physical['connections']}
    for cid in pending:
        c=cs[cid];j=joints[c['joint_id']]
        linked=set(c.get('member_ids',[]))|set(c.get('assembly_instance',{}).get('bindings',{}).values())
        if not linked:linked={m['member_id'] for m in j.get('member_ends',[])+j.get('attachments',[])}
        linked.intersection_update(members)
        braces=[members[mid] for mid in linked if members[mid]['kind'] in ('brace','truss_web')]
        supports=[members[mid] for mid in linked if members[mid]['kind'] not in ('brace','truss_web')]
        try:
            if parts(c,templates):raise ValueError('Existing connection constituents need a combined contour and attachment fit')
            if len(braces)!=1:raise ValueError('Located connection must select its attached physical brace')
            variant=selected_fields(package,c).get(('connection','variant'))
            if variant in ('brb_pinned','brb_bolted'):
                from .native_brb import build_brb_end
                t,frame,offsets,slots=build_brb_end(package,c,braces[0],supports,profiles,catalogue,j)
            else:
                if len(supports)!=1:raise ValueError('Slotted gusset requires a distinct located support')
                t,frame,offsets,slots=complete_slotted_end(package,c,braces[0],supports[0],j['point'],profiles,catalogue)
            physical.setdefault('assemblies',[]).append(t)
            c.update(assembly_instance=frame,parts=[],member_ids=sorted(linked))
            braces[0].update(end_offsets=offsets,slots=slots)
        except SelectionConflict as issue:
            issue.record(package,cid)
        except ValueError as error:
            package['provenance'].setdefault('openbim_translation_findings',[]).append(
                dict(code='native_joint_geometry',connection_id=cid,detail=str(error),owner='openBIM'))
    physical['materials']=list(catalogue.values())
    for row in connection_details(physical['connections']):
        for c in row['connections']:
            c['drawing_ref']='1/'+row['reference']
            detail=dict(c.get('detail_ref',{}),source_drawing=c['drawing_ref'])
            detail.setdefault('id',row['family'])
            detail.setdefault('revision',c.get('assembly_instance',{}).get('revision') or fingerprint(c.get('parts',[])))
            c['detail_ref']=detail
    return package
