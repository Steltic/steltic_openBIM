"""Locate integral plate tongues from the brace detail in the column base's frame."""
import re
from .assembly_templates import NUMBER,number
from .pilots.model import dot


def base_edge_layout(record):
    """Read the checked base-edge length at the zero-eccentricity workpoint."""
    if not re.search(r'\bUFM with eb = 0\b',record.get('components',''),re.I):
        return None
    for check in record.get('checks',[]):
        text=check.get('limit_state','')
        match=re.match(r'gusset base edge on the base plate: '+NUMBER+r' in \+ '+NUMBER+r' in edge',text,re.I)
        if match and check.get('units')=='in':
            # The printed weld is rounded. The checked demand includes the edge allowance.
            length=round(float(check['demand'])-number(match[2]),6)
            if length<=0 or abs(length-number(match[1]))>.051:
                raise ValueError('Inconsistent checked gusset base-edge length')
            return length
    return None


def frame_extension(record):
    text=record.get('components','')
    extension=re.search(r'at the ([XY])-frame bases the plate is extended '+NUMBER+
                        r' in on the brace side \(N = '+NUMBER+r' in\)',text,re.I)
    if not extension:return None
    stock=re.search(r'base plate PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',text,re.I)
    if stock is None:raise ValueError('Braced-base extension lacks nominal stock dimensions')
    width,length=number(stock[2]),number(extension[2])
    if abs(number(stock[3])+length-number(extension[3]))>1e-5:
        raise ValueError('Braced-base extension differs from the issued overall length')
    return extension[1].upper(),width,length


def locate(package,model):
    records={r['id']:r['data'] for r in package.get('design_records',[])}
    source={}
    for rid,record in records.items():
        hit=re.search(r'plate extended on the bay side by a '+NUMBER+r' in wide tongue '+NUMBER+r' in long',
                      record.get('components',''),re.I)
        if hit:source[rid]=tuple(map(number,hit.groups()))
    layouts={rid for rid,record in records.items() if base_edge_layout(record) is not None}
    if not source and not layouts:return
    native={c['id']:c for c in package['physical']['connections']}
    bases={(mid,tuple(c['point'])):c for c in model['connections'] if c['detail_ref']['id']=='review_base'
           for mid in c['member_ids']}
    for occurrence in model['connections']:
        chosen=next((rid for rid in occurrence['design_record_ids'] if rid in source or rid in layouts),None)
        if not chosen:continue
        if chosen in layouts and occurrence.get('parameters',{}).get('joint')!='base':continue
        brace=native[occurrence['id']]['assembly_instance']
        base=bases.get((brace['bindings']['COLUMN'],tuple(occurrence['point'])))
        if not base:raise ValueError('Selected bay-side base tongue lacks its column base: '+occurrence['id'])
        if chosen in layouts:
            base['parameters']['bearing_at_workpoint']=True
            native[base['id']].setdefault('parameters',{})['bearing_at_workpoint']=True
            extensions=[(rid,spec) for rid in base['design_record_ids']
                        if (spec:=frame_extension(records.get(rid,{}))) is not None]
            if not extensions:continue
            rid,(axis,width,length)=extensions[0]
            if abs(brace['x_axis']['XY'.index(axis)])<1-1e-5:continue
        else:
            rid=chosen
            width,length=source[chosen]
        plate=native[base['id']]['assembly_instance']
        direction=[dot(brace['x_axis'],plate[axis]) for axis in ('x_axis','y_axis')]
        largest=max(range(2),key=lambda i:abs(direction[i]))
        if abs(abs(direction[largest])-1)>1e-5 or abs(direction[1-largest])>1e-5:
            raise ValueError('Selected rectangular plate tongue is skew to the base stock: '+occurrence['id'])
        sign=1 if direction[largest]>0 else -1
        row=dict(axis=largest,sign=sign,width_in=width,length_in=length,source_record_id=rid,
                 brace_connection_id=occurrence['id'])
        stock=base['parameters'].setdefault('integral_gusset_tongues',[])
        if row not in stock:stock.append(row)
        native[base['id']].setdefault('parameters',{})['integral_gusset_tongues']=stock


def add(assembly,bx,by,z,thickness,tongues):
    from shapely.geometry import box
    from shapely.ops import unary_union
    footprint=box(-bx/2,-by/2,bx/2,by/2)
    pieces=[footprint]
    for row in tongues:
        width,length=row['width_in'],row['length_in']
        axis,sign=row['axis'],row['sign']
        half=(bx,by)[axis]/2
        if width<=0 or width>(by,bx)[axis] or length<=0:
            raise ValueError('Invalid integral base plate tongue dimensions')
        lo,hi=sorted((sign*half,sign*(half+length)))
        pieces.append(box(lo,-width/2,hi,width/2) if axis==0 else box(-width/2,lo,width/2,hi))
    outline=unary_union(pieces)
    part=assembly.polygon('P1',[[x,y,z] for x,y in list(outline.exterior.coords)[:-1]],
                          thickness,normal=[0,0,1],basis='S',description='Base plate with integral bay-side gusset tongue')
    part['parameters']={'source_role':'base_plate','nominal_stock_in':[bx,by,thickness],
                        'integral_gusset_tongues':[{k:v for k,v in row.items() if k!='brace_connection_id'}
                                                  for row in tongues]}
    return part


def share_supports(package,model):
    """One physical sole serves the column base and the separate brace detail."""
    from .bim_assemblies import fingerprint
    physical=package['physical'];templates={t['id']:t for t in physical['assemblies']}
    bases={}
    for c in physical['connections']:
        if c.get('detail_ref',{}).get('legacy_family') not in ('review_base','review_wall_base'):continue
        for mid in c['member_ids']:bases[mid,c['joint_id']]=c
    drawing_scenes={s['id']:s for s in model['connection_assemblies']}
    reduced={};referenced_sheets=set()
    for c in physical['connections']:
        inst=c.get('assembly_instance',{})
        if c.get('parameters',{}).get('joint')!='base' or 'COLUMN' not in inst.get('bindings',{}):continue
        tid=inst['template_id'];original=templates[tid]
        part=next((p for p in original['parts'] if p['id']=='BASE' and
                   p.get('parameters',{}).get('referenced_part_id')=='P1'),None)
        if not part:continue
        mid=inst['bindings']['COLUMN'];owner=bases.get((mid,c['joint_id']))
        if not owner:raise ValueError('Located brace sole has no owning column base: '+c['id'])
        oi=owner['assembly_instance'];ot=templates[oi['template_id']]
        if 'P1' not in {p['id'] for p in ot['parts']}:raise ValueError('Column-base template lacks P1: '+owner['id'])
        if tid not in reduced:
            new=dict(original,id=tid+'-sole-ref',parts=[p for p in original['parts'] if p['id']!='BASE'])
            new.pop('revision',None);new['revision']=fingerprint(new);reduced[tid]=new
        new=reduced[tid];inst.update(template_id=new['id'],revision=new['revision'])
        c['parameters'].setdefault('shared_constituents',[]).append(dict(role='BASE',owner_part_id='P1',
            sharing_kind='column_base_support',column_id=mid,owner_connection_id=owner['id'],
            owner_template_id=ot['id'],owner_template_revision=ot['revision'],point_in=oi['origin']))
        scene=drawing_scenes[c['assembly_id']]
        for p in scene['parts']:
            if p['id']=='BASE':p['representation_role']='context_only'
        referenced_sheets.add(scene['id'])
    for sid in referenced_sheets:
        scene=drawing_scenes[sid];scene['geometry_sha256']=fingerprint([scene['parts'],scene['welds'],scene['interfaces']])
    for c in physical['connections']:
        if c.get('assembly_id') in referenced_sheets:
            c['detail_ref']['revision']=drawing_scenes[c['assembly_id']]['geometry_sha256']
    templates.update({t['id']:t for t in reduced.values()})
    used={c['assembly_instance']['template_id'] for c in physical['connections'] if c.get('assembly_instance')}
    physical['assemblies']=[t for tid,t in templates.items() if tid in used]
