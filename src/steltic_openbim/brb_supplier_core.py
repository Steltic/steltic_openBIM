"""Complete a supplier-delegated BRB envelope from its issued core area and yielding length."""
import math
import re

from .pilots.model import add, mul


def source_core(record):
    data=record['data']
    notes=data.get('design_note','')
    area=re.search(r'\bsteel core Asc\s*=\s*(\d+(?:\.\d+)?)\s*in(?:2|\^2)\s*\((ASTM\s+A\d+)',notes,re.I)
    if not area:
        area=re.search(r'\bAsc\s*=\s*(\d+(?:\.\d+)?)\s*in(?:2|\^2)\s*,\s*((?:ASTM\s+)?A\d+)\s+core',notes,re.I)
    if not area:return None
    ratios={float(m[1]) for check in data.get('checks',[]) if
            (m:=re.search(r'yielding length [\d.]+ in\s*\(([\d.]+)\s*Lwp\b',check.get('limit_state',''),re.I))}
    if len(ratios)!=1:
        return None
    strokes=[float(m[1]) for check in data.get('checks',[]) if
             (m:=re.search(r'brace elongation ([\d.]+) in',check.get('limit_state',''),re.I))]
    grade=area[2].upper()
    return dict(record=record['id'],area_in2=float(area[1]),material=grade if grade.startswith('ASTM') else 'ASTM '+grade,
                yielding_length_workpoint_ratio=ratios.pop(),reported_elongation_in=max(strokes,default=0.))


def source_requirements(members, handoff, records):
    """Bind each selected core to its own physical member and original design record."""
    recovered = {r['id']: spec for r in records if r['id'].startswith('members/') and (spec := source_core(r))}
    typed_members=handoff.get('member_selections', {})
    missing=set(typed_members)-{m['id'] for m in members}
    if missing:raise ValueError('HR source member selection has no physical member: '+min(missing))
    result = {}
    for member in members:
        mid = member['id']
        bindings = member.get('design_record_ids', [])
        matches = [recovered[r] for r in bindings if r in recovered]
        if len(matches) > 1:
            raise ValueError('Ambiguous HR core member controls for ' + mid)
        typed = typed_members.get(mid, {})
        fields={}
        for item in typed.get('fields', []):
            if item['role']!='brb_core':continue
            key=item['field'];value=item['value']
            if key in fields and fields[key]!=value:
                raise ValueError('Conflicting selected BRB core '+key+' for '+mid)
            fields[key]=value
        if not fields:
            if matches:
                result[mid] = matches[0]
            continue
        rid = typed['record_id']
        if rid not in bindings:
            raise ValueError('HR core selection is not bound to member ' + mid)
        if 'physical_profile' in typed and typed['physical_profile']!=member.get('source_profile_id',member['profile_id']):
            raise ValueError('HR selected core profile differs from the physical brace: '+mid)
        if 'axis_in' in typed:
            axis=member['axis'];workpoint=math.dist(*axis)
            if any(math.dist(p,q)>1e-4 for p,q in zip(typed['axis_in'],axis)) or abs(typed['workpoint_length_in']-workpoint)>1e-4:
                raise ValueError('HR selected core workline differs from the located physical brace: '+mid)
            expected=workpoint*fields['yielding_length_workpoint_ratio']
            if abs(typed['yielding_core_length_in']-expected)>1e-4:
                raise ValueError('HR selected yielding length disagrees with its located workpoints: '+mid)
        spec = dict(record=rid, area_in2=float(fields['area_in2']), material=fields['material'],
                    yielding_length_workpoint_ratio=float(fields['yielding_length_workpoint_ratio']),
                    reported_elongation_in=float(fields.get('expected_elongation_in',fields.get('reported_elongation_in',0.))))
        if matches:
            original = matches[0]
            if (original['record'] != rid or abs(original['area_in2'] - spec['area_in2']) > 1e-6 or
                    abs(original['yielding_length_workpoint_ratio'] - spec['yielding_length_workpoint_ratio']) > 1e-6 or
                    original['material'].upper().removeprefix('ASTM ') != spec['material'].upper().removeprefix('ASTM ')):
                raise ValueError('Typed HR core disagrees with the bound HR design record for ' + mid)
            spec['reported_elongation_in'] = max(spec['reported_elongation_in'], original['reported_elongation_in'])
        result[mid] = spec
    return result


def prepare(package,model):
    specs=source_requirements(model['members'],package.get('source_handoff',{}),package.get('design_records',[]))
    from .brb_casing import prepare_casings
    prepare_casings(package,model,specs)
    profiles={p['id']:p for p in model['profiles']}
    for m in model['members']:
        spec=specs.get(m['id'])
        if not spec:
            continue
        p=profiles[m['profile_id']]
        if p.get('family')!='rhs':
            raise ValueError('Selected BRB core requires its located hollow supplier casing for '+m['id'])
        if 'core_area_in2' in p and abs(spec['area_in2']-p['core_area_in2'])>1e-5:
            raise ValueError('BRB envelope and selected HR core area differ for '+m['id'])
        d=p['dimensions']
        # Supplier coordination geometry. Preserve room between the core and
        # the represented casing walls, including at the ends of the core.
        inside_width=d['b']-2*d['t']
        inside_depth=d['h']-2*d['t']
        depth=min(2*math.sqrt(spec['area_in2']),inside_depth-.5)
        thickness=spec['area_in2']/depth
        end_thickness=thickness+.25
        if end_thickness>inside_width-.5 or not 0<spec['yielding_length_workpoint_ratio']<1:
            raise ValueError('Selected BRB core cannot fit inside its casing for '+m['id'])
        m['supplier_core']=dict(spec,depth_in=depth,thickness_in=thickness,end_thickness_in=end_thickness,
                                yielding_length_in=math.dist(*m['axis'])*spec['yielding_length_workpoint_ratio'])


def rectangular_ring(t,d):
    return [[-t/2,-d/2],[t/2,-d/2],[t/2,d/2],[-t/2,d/2]]


def core_at_end(m,point,display_length):
    from .hr_boxed_plies import cropped_plies
    plies=[p for p in m.get('section_plies',[]) if p['id']=='YIELDING-CORE' or p.get('constituent_id')=='MORTAR-INFILL']
    if not plies:return []
    length=plies[0]['sections'][-1][0]
    end=min(range(2),key=lambda i:math.dist(point,m['axis'][i]))
    span=min(display_length,length)
    cropped=cropped_plies(plies,0.,span) if not end else cropped_plies(plies,length-span,length)
    if end:
        for p in cropped:
            p['sections']=[[span-x,ring] for x,ring in reversed(p['sections'])]
    return cropped


def show_core(ctx,m,part):
    from .pilots.geometry import member_faces
    from .assembly_scene import bounds
    if m.get('section_plies'):
        local=part['member']
        local['section_plies']=core_at_end(m,ctx.c['point'],math.dist(*local['axis']))
        part['faces']=member_faces(local,ctx.p);part['bounds']=bounds(part['faces'])
    casing=m.get('brb_casing',{})
    if casing:
        label='; casing '+(casing.get('section') or 'supplier envelope')+', '+casing['material']
        if casing.get('infill_material'):label+='; '+casing['infill_material']+' around separated moving core'
        if label not in part['description']:part['description']+=label


def moving_head_projection(assembly,axis,back,gap,spec):
    normal=[-axis[2],0.,axis[0]]
    points=[add(back,add(mul(normal,z),[0.,y,0.])) for y,z in rectangular_ring(spec['end_thickness_in'],spec['depth_in'])]
    projection=assembly.polygon('CORE-END',points,gap,normal=axis,description='Moving core projection through the clear supplier casing opening')
    projection.update(selected_material=spec['material'],parameters={'source_role':'brb_core_extension'})
    assembly.interfaces.extend([
        dict(id='MOVING-HEAD-TO-CORE',kind='supplier_interface',connects=['CORE-END','END-CAP'],basis='A',
             description='Supplier moving clevis head and core projection share their terminal steel faces'),
        dict(id='CORE-CONTINUATION',kind='brb_core_continuation',connects=['BRACE','CORE-END'],basis='A',
             description='Moving core projection continues into the axial steel core within the separate restraining casing')])


def write_cores(package,model):
    from .saved_assemblies import material_for
    from .brb_casing import infill_plies
    physical=package['physical']
    members={m['id']:m for m in physical['members']}
    catalog={r['id']:r for r in physical['materials']}
    profiles={r['id']:r for r in model['profiles']}
    for m in model['members']:
        spec=m.get('supplier_core')
        if not spec:
            continue
        length=math.dist(*[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])])
        t=spec['thickness_in'];d=spec['depth_in']
        reserve=(length-spec['yielding_length_in'])/2
        # In a provisional short envelope show its actual available length. The
        # independent reader compares this with the original job's required length.
        taper=min(max(reserve,0.),max(1.,d/2))
        full=rectangular_ring(spec['end_thickness_in'],d)
        yield_ring=rectangular_ring(t,d)
        if taper>1e-6:
            sections=[[0.,full],[reserve-taper,full],[reserve,yield_ring],
                      [length-reserve,yield_ring],[length-reserve+taper,full],[length,full]]
            sections=[v for i,v in enumerate(sections) if not i or v[0]-sections[i-1][0]>1e-7]
        else:
            sections=[[0.,yield_ring],[length,yield_ring]]
        material=material_for(dict(id='YIELDING-CORE',selected_material=spec['material']),'plate',None,catalog,[spec['record']])
        ply=dict(id='YIELDING-CORE',material_id=material,source_record_ids=[spec['record']],sections=sections,
                 basis='S: core material, yielding area and length from HR. A: rectangular core, end shapes and positions within the supplier casing.')
        fill=infill_plies(m,profiles[m['profile_id']],ply,length,catalog)
        for target in (m,members[m['id']]):
            target['supplier_core']=dict(spec)
            target['section_plies']=[v for v in target.get('section_plies',[]) if v['id']!='YIELDING-CORE' and
                                    v.get('constituent_id')!='MORTAR-INFILL']+[ply,*fill]
    physical['materials']=list(catalog.values())


def extension(assembly,axis,start,finish,depth,thickness,spec):
    """An exposed splice tongue, followed by a solid transition into the internal core."""
    normal=[-axis[2],0,axis[0]]
    narrow=spec['depth_in'];thick=spec['end_thickness_in']
    width=max(depth,narrow*thick/thickness)
    def ring(at,t,w):
        return [add(mul(axis,at),add([0.,y,0.],mul(normal,z))) for y,z in rectangular_ring(t,w)]
    shoulder=start+(finish-start)/2
    first=ring(start,thickness,width)
    last=ring(finish,thick,narrow)
    rings=[first,ring(shoulder,thickness,width),last]
    faces=[list(reversed(first)),last]
    for a,b in zip(rings,rings[1:]):
        faces.extend([[a[i],a[(i+1)%4],b[(i+1)%4],b[i]] for i in range(4)])
    p=assembly.part('CORE-END','Supplier core projection and transition to the axial core inside the clear casing',faces,
                    'A','plate',selected_material=spec['material'])
    p['parameters']={'source_role':'brb_core_extension','core_area_in2':spec['area_in2']}
    return shoulder
