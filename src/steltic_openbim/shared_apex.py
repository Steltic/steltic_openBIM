"""Place one actual common gusset at a pair of brace ends on the same beam."""
import copy
import math
from collections import defaultdict

from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from .assembly_scene import Assembly,bounds
from .bim_assemblies import transformed
from .connection_cuts import drill_plate
from .drawing_workflow import fingerprint
from .pilots.model import cross,dot,sub


def locate_pairs(package,model):
    physical=package['physical'];groups=defaultdict(list)
    drawing={c['id']:c for c in model['connections']}
    scenes={s['id']:s for s in model['connection_assemblies']}
    for c in physical['connections']:
        inst=c.get('assembly_instance',{});bindings=inst.get('bindings',{})
        if c.get('parameters',{}).get('joint')=='apex' and 'BRACE' in bindings and 'BEAM' in bindings:
            brace_direction=next((m for m in c['member_ids'] if m==bindings['BRACE']),None)
            if not brace_direction:continue
            # Both the top and the underside of this beam can receive a pair.
            # Neither a workpoint nor a beam ID distinguishes the two faces.
            upper=drawing[c['id']].get('parameters',{}).get('upper_end')
            groups[(c['joint_id'],bindings['BEAM'],upper)].append(c)
    pairs=[]
    for group in groups.values():
        if len(group)!=2:continue
        first,second=sorted(group,key=lambda c:c['id'])
        a,b=[c['assembly_instance'] for c in (first,second)]
        if (a['bindings']['BRACE']==b['bindings']['BRACE'] or
                math.dist(a['origin'],b['origin'])>1e-5 or dot(a['x_axis'],b['x_axis'])>-.99999 or
                dot(a['y_axis'],b['y_axis'])>-.99999):
            continue
        silhouettes=[]
        for connection,frame in ((first,a),(second,b)):
            scene=scenes[drawing[connection['id']]['assembly_id']]
            part=next((p for p in scene['parts'] if p['id']=='GUSSET' and p.get('polygon')),None)
            if not part:break
            points=[in_frame(q,frame,a) for q in part['polygon']]
            silhouettes.append(Polygon([(q[0],q[2]) for q in points]))
        if len(silhouettes)!=2 or silhouettes[0].intersection(silhouettes[1]).area<1e-6:continue
        for c in (first,second):
            drawing[c['id']]['parameters']['common_apex_datum']=True
        pairs.append((first['id'],second['id']))
    return pairs


def in_frame(point,source,dest,direction=False):
    world=transformed(point,source,direction)
    v=world if direction else sub(world,dest['origin'])
    return [dot(v,k) for k in (dest['x_axis'],dest['y_axis'],cross(dest['x_axis'],dest['y_axis']))]


def unified_plate(primary,secondary,pi,si):
    t=primary['thickness']
    if abs(t-secondary['thickness'])>1e-6:raise ValueError('two selected gusset thicknesses')
    def planar(plate,source):
        points=[in_frame(q,source,pi) for q in plate['polygon']]
        if any(abs(abs(q[1])-t/2)>1e-5 for q in points):raise ValueError('distinct plate planes')
        poly=Polygon([(q[0],q[2]) for q in points])
        if not poly.is_valid:raise ValueError('an invalid source plate boundary')
        return poly
    one,two=planar(primary,pi),planar(secondary,si)
    if one.intersection(two).area<1e-6:return None
    outline=orient(one.union(two),sign=-1)
    if outline.geom_type!='Polygon' or outline.interiors:raise ValueError('a discontinuous common gusset')
    a=Assembly('Common apex plate',{})
    part=a.polygon('GUSSET',[[x,-t/2,z] for x,z in list(outline.exterior.coords)[:-1]],t,basis=primary['basis'],
                   description=f'Selected {t:g} in common apex gusset spanning both brace attachments')
    for plate,source in ((primary,pi),(secondary,si)):
        for h in plate.get('holes',[]):
            q=in_frame(h['point'],source,pi)
            if any(math.hypot(q[0]-old['point'][0],q[2]-old['point'][2])<1e-5 for old in part.get('holes',[])):continue
            drill_plate(part,[q],[0.,1.,0.],h['diameter_in'],h['basis'])
    return part


def part_at(part,source,dest):
    """Transform the inspected drawing geometry, including cap/section references."""
    take=lambda q:in_frame(q,source,dest)
    vector=lambda q:in_frame(q,source,dest,True)
    result=copy.deepcopy(part)
    result['faces']=[[take(q) for q in face] for face in part['faces']]
    result['bounds']=bounds(result['faces'])
    if 'polygon' in part:result['polygon']=[take(q) for q in part['polygon']]
    if 'normal' in part:result['normal']=vector(part['normal'])
    if 'points' in part:result['points']=[take(q) for q in part['points']]
    if isinstance(part.get('axis'),list) and len(part['axis'])==3:result['axis']=vector(part['axis'])
    if part.get('holes'):result['holes']=[dict(h,point=take(h['point']),axis=vector(h['axis'])) for h in part['holes']]
    if 'member' in part:
        m=result['member'];m['axis']=[take(q) for q in part['member']['axis']];m['local_y']=vector(part['member']['local_y'])
        m['end_offsets']=[vector(q) for q in part['member']['end_offsets']]
    if result.get('geometry'):result['geometry']=dict(type='mesh',faces=result['faces'])
    return result


def shape_key(part,source,dest):
    transform=lambda q:tuple(round(x,5) for x in in_frame(q,source,dest))
    g=part['geometry']
    points=g['points'] if g['type']=='polyline' else [q for face in g.get('faces',[]) for q in face]
    return (part['kind'],part['material_id'],tuple(sorted({transform(q) for q in points})))


def build_pair(c1,c2,t1,t2,s1,s2):
    pi,si=c1['assembly_instance'],c2['assembly_instance']
    originals=[next((p for p in s['parts'] if p['id']=='GUSSET'),None) for s in (s1,s2)]
    if not all(originals):return None
    before=[{p['id']:p for p in t['parts']} for t in (t1,t2)]
    if before[0]['GUSSET']['material_id']!=before[1]['GUSSET']['material_id']:raise ValueError('two selected gusset materials')
    plate=unified_plate(*originals,pi,si)
    if plate is None:return None
    # Only the owning occurrence represents the physical gusset. Identify
    # coincident supports by their actual geometry, material and weld selection.
    names={'GUSSET':'GUSSET'}
    support=lambda p:p['id'].startswith(('ST','WST','WD','WGB','DOUBLER'))
    owner_by_shape={shape_key(p,pi,pi):p for p in t1['parts'] if support(p)}
    for p in t2['parts']:
        if not support(p):continue
        peer=owner_by_shape.get(shape_key(p,si,pi))
        if peer:
            for k in ('size_in','weld_type'):
                if p['parameters'].get(k)!=peer['parameters'].get(k):raise ValueError('two selections for a coincident support weld')
            names[p['id']]=peer['id']
        elif p['id'].startswith('WGB'):
            raise ValueError('two incompatible selected beam weld runs')
    parts=[]
    for p in t1['parts']:
        if p['id']=='GUSSET':
            par=dict(p['parameters'],description=plate['description'],source_role='common_apex_gusset',thickness=plate['thickness'])
            if plate.get('holes'):par['holes']=plate['holes']
            p=dict(p,parameters=par,geometry={'type':'mesh','faces':plate['faces']})
        parts.append(p)
    remote=next(r for r in t2['receivers'] if r['id']=='BRACE')
    other=dict(remote,id='BRACE-OTHER',axis=[in_frame(q,si,pi) for q in remote['axis']],
               local_y=in_frame(remote['local_y'],si,pi,True))
    t1=dict(t1,parts=parts,receivers=[*t1['receivers'],other])
    t2=dict(t2,parts=[p for p in t2['parts'] if p['id'] not in names])
    for t in (t1,t2):
        t.pop('revision',None);t['id']=t['id']+'-apex-'+fingerprint([t['parts'],t['receivers']])[:10]
        t['revision']=fingerprint(t)
    scenes=[]
    for own,partner,own_frame,other_frame in ((s1,s2,pi,si),(s2,s1,si,pi)):
        new_plate=part_at(plate,pi,own_frame)
        replacement=dict(own,parts=[new_plate if p['id']=='GUSSET' else p for p in own['parts']])
        partner_brace=part_at(next(p for p in partner['parts'] if p['id']=='BRACE'),other_frame,own_frame)
        partner_brace.update(id='BRACE-OTHER',description='Other physical brace sharing this apex gusset',representation_role='context_only')
        replacement['parts'].append(partner_brace)
        role_names={'BRACE':'BRACE-OTHER','GUSSET':'GUSSET'}
        for part in partner['parts']:
            if part.get('member') or part['id']=='GUSSET' or part['id'].startswith(('ST','DOUBLER')):continue
            other=part_at(part,other_frame,own_frame);role='OTHER-'+part['id']
            other.update(id=role,representation_role='context_only',shared_joint_context=True)
            role_names[part['id']]=role;replacement['parts'].append(other)
        replacement['welds']=list(own['welds'])
        for weld in partner['welds']:
            if weld['id'].startswith(('WGB','WST','WD')):continue
            replacement['welds'].append(dict(weld,id='OTHER-'+weld['id'],a=in_frame(weld['a'],other_frame,own_frame),
                b=in_frame(weld['b'],other_frame,own_frame,False),connects=[role_names.get(role,role) for role in weld['connects']],
                shared_joint_context=True))
        replacement['bounds']=bounds([f for p in replacement['parts'] for f in p['faces']])
        replacement['notes']=[*own['notes'],'The two brace ends share one located apex gusset and one set of beam attachments.']
        replacement['geometry_sha256']=fingerprint([replacement['parts'],replacement['welds'],own['interfaces']])
        scenes.append(replacement)
    return t1,t2,scenes,names


def consolidate(package,model,pairs):
    if not pairs:return
    native=package['physical'];conns={c['id']:c for c in native['connections']}
    draw={c['id']:c for c in model['connections']};sheets={s['id']:s for s in model['connection_assemblies']}
    templates={t['id']:t for t in native['assemblies']}
    cache={};updated={};built={}
    for first,second in pairs:
        c1,c2=conns[first],conns[second]
        i1,i2=c1['assembly_instance'],c2['assembly_instance']
        key=(i1['template_id'],i2['template_id'],draw[first]['assembly_id'],draw[second]['assembly_id'])
        if key not in cache:
            try:cache[key]=build_pair(c1,c2,templates[key[0]],templates[key[1]],sheets[key[2]],sheets[key[3]])
            except ValueError as err:cache[key]=str(err)
        result=cache[key]
        if isinstance(result,str):
            package.setdefault('provenance',{}).setdefault('openbim_translation_findings',[]).append(
                dict(code='shared_gusset_selection_conflict',connections=[first,second],detail=result))
            continue
        if result is None:continue
        t1,t2,scenes,names=result
        for c,inst,t,scene in zip((c1,c2),(i1,i2),(t1,t2),scenes):
            inst.update(template_id=t['id'],revision=t['revision']);built[t['id']]=t;updated[c['id']]=scene
        other=i2['bindings']['BRACE'];i1['bindings']['BRACE-OTHER']=other
        if other not in c1['member_ids']:c1['member_ids'].append(other)
        c1['parameters']['shared_brace_ends']=[dict(role='BRACE-OTHER',connection_id=second,member_id=other)]
        c2['parameters']['shared_constituents']=[dict(role=role,owner_connection_id=first,owner_part_id=target,
            owner_template_id=t1['id'],owner_template_revision=t1['revision'],point_in=i1['origin'],
            owner_weld_roles=[v for v in names.values() if v.startswith('WGB')] if role=='GUSSET' else [])
            for role,target in names.items()]
    all_templates=dict(templates,**built)
    used={c['assembly_instance']['template_id'] for c in conns.values() if c.get('assembly_instance')}
    native['assemblies']=[t for tid,t in all_templates.items() if tid in used]
    # Preserve every approved sheet. Add a variant only if one old sheet
    # originally combined distinct physical conditions.
    next_number=max((int(s['sheet'][1:]) for s in sheets.values() if s['sheet'][1:].isdigit()),default=0)
    register=[]
    for original in sheets.values():
        variants=defaultdict(list)
        for cid in original['occurrences']:
            scene=updated.get(cid,original);variants[scene['geometry_sha256']].append(cid)
        for i,ids in enumerate(variants.values()):
            s=dict(updated.get(ids[0],original),occurrences=ids,occurrence_count=len(ids))
            if i:
                next_number+=1;s.update(id=f'CD{next_number:03}',sheet=f'C{next_number:03}',reference=f'1/C{next_number:03}')
            for cid in ids:
                if cid in draw:draw[cid].update(assembly_id=s['id'],drawing_ref=s['reference'])
                if cid in conns:
                    c=conns[cid];c.update(assembly_id=s['id'],drawing_ref=s['reference'])
                    c['detail_ref']=dict(c['detail_ref'],source_drawing=s['reference'])
            register.append(s)
    model['connection_assemblies']=register
