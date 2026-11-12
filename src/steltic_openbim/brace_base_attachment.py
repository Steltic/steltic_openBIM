"""Resolve an embedded-column gusset to its collar or selected cap clearance."""
import re
from .assembly_templates import NUMBER,number
from .grade_steel import selection


def value(text,pattern):
    hit=re.search(pattern+r'\s*\(?\s*'+NUMBER,text,re.I)
    return number(hit[1]) if hit else None


def locate_grade_interfaces(package,model):
    """Retain a stated diaphragm transfer when the physical column passes through grade."""
    decision=next((r for r in model.get('assumptions',[]) if
        'grade slab and foundation walls receive' in r.get('answer','').lower()),None)
    members={m['id']:m for m in model['members']}
    located_bases={(mid,tuple(c['point'])):c for c in model['connections'] if c.get('detail_ref',{}).get('id') in
                   ('review_base','hr_column_base') for mid in c['member_ids']}
    records={r['id']:r['data'] for r in package.get('design_records',[])}
    for c in model['connections']:
        if c.get('parameters',{}).get('joint')!='base' or c['detail_ref']['id'] not in ('review_brace','review_brb'):continue
        rail=selection(records,c)
        if rail:
            c['parameters']['grade_rail']=rail
            continue
        bound=[members[mid] for mid in c['member_ids']]
        columns=[m for m in bound if m['kind']=='column']
        if len(columns)!=1 or any(m['kind'] not in ('brace','column') for m in bound):continue
        column=columns[0];datum=c['point'][2]
        ends=[q[2]+off[2] for q,off in zip(column['axis'],column['end_offsets'])]
        if not min(ends)+1e-4<datum<max(ends)-1e-4:continue
        base=located_bases.get((column['id'],tuple(c['point'])))
        if base:
            from types import SimpleNamespace
            from .review_base_selection import embedment
            base_source=' '.join(records.get(r,{}).get('components','') for r in base['design_record_ids'])
            if embedment(base_source) is None:continue
            detail=SimpleNamespace(package=package,c=c,ms=bound)
            cap=cap_plate(detail)
            if cap:
                if cap['record_id'] not in c['design_record_ids']:c['design_record_ids'].append(cap['record_id'])
                continue
            if base_attachment(detail,column['profile_id']):continue
            if c.get('parameters',{}).get('grade_attachment'):continue
            note=('The selected column sole lies below this brace workpoint. A source connection '
                  'is needed between the gusset and the foundation or the continuing column at this elevation.')
            extra={'base_connection_id':base['id'],'base_source_record_ids':base['design_record_ids']}
            code='embedded_column_grade_attachment_required'
        elif decision:
            note=('The accepted grade diaphragm and foundation walls receive the base shear. '
                  'The steel-to-diaphragm attachment is unspecified at this continuing column.')
            extra={'decision_id':decision['id']};code='grade_diaphragm_attachment_required'
        else:continue
        c['parameters']['grade_diaphragm_interface']=note
        finding=dict(code=code,connection_id=c['id'],column_id=column['id'],point_in=c['point'],
                     column_elevations_in=ends,design_record_ids=c['design_record_ids'],detail=note,**extra)
        rows=package['provenance'].setdefault('openbim_translation_findings',[])
        if finding not in rows:rows.append(finding)


def base_attachment(ctx,column):
    records={r['id']:r['data'] for r in ctx.package['design_records']}
    for rid in ctx.c['design_record_ids']:
        text=records.get(rid,{}).get('components','')
        # A slotted brace record may state its actual base welds after the
        # slot/reinforcement clauses and before a separate ordinary corner row.
        column_fillet=re.search(r'base gusset[^;]*?welded to the column flange \('+NUMBER+
            r' in, column-edge fillets '+NUMBER+r' in both faces',text,re.I)
        bottom_fillet=re.search(r'top of the base plate \('+NUMBER+
            r' in from the flange face, base-edge fillets '+NUMBER+r' in both faces',text,re.I)
        if column_fillet and bottom_fillet:
            from .base_plate_extensions import base_edge_layout
            checked_length=base_edge_layout(records[rid])
            return dict(kind='base',record_id=rid,column_kind='fillet',
                column_length=number(column_fillet[1]),column_fillet=number(column_fillet[2]),
                horizontal_length=checked_length or number(bottom_fillet[1]),horizontal_fillet=number(bottom_fillet[2]),
                workpoint_station=value(text,r'brace end'),bearing_at_workpoint=checked_length is not None,faces=2)
        if not re.match(r'base (?:corner )?gusset\b',text,re.I):continue
        tongue=re.search(r'welded to the base plate \('+NUMBER+r' in\) and the column flange \('+NUMBER+r' in\)',text,re.I)
        both=re.search(NUMBER+r' in E\d+ fillets both sides',text,re.I)
        if tongue and both:
            return dict(kind='base',record_id=rid,column_kind='fillet',column_length=number(tongue[2]),
                        horizontal_length=number(tongue[1]),column_fillet=number(both[1]),
                        horizontal_fillet=number(both[1]),faces=2)
        variants=list(re.finditer(r'\bat (BOX\d+[.\d]*X[.\d/]+):',text,re.I))
        scoped=text[:variants[0].start()] if variants else text
        for i,variant in enumerate(variants):
            if variant[1].upper()==column.upper():
                scoped=text[variant.end():variants[i+1].start() if i+1<len(variants) else len(text)]
                break
        else:
            primary=re.search(r'CJP-welded to the\s*\(?([.\d]+)\s+in\)? box wall',scoped,re.I)
            if primary and not column.startswith('BOX'+format(float(primary[1]),'g')+'X'):continue
        vertical=value(scoped,r'column[- ]edge(?: weld length)?')
        horizontal=value(scoped,r'(?:bottom|base(?:-plate)?)[- ]edge(?: weld length)?')
        if vertical is None or horizontal is None:continue
        column_clause=scoped.split('column edge',1)[-1].split('bottom edge',1)[0].split('base edge',1)[0]
        size=re.search(NUMBER+r'[- ]in (?:E\d+\s+)?fillets? both',scoped,re.I)
        result=dict(record_id=rid,column_length=vertical,horizontal_length=horizontal,
                    column_kind='CJP' if 'CJP' in column_clause else 'fillet',
                    fillet=number(size[1]) if size else None)
        if re.search(r'clear of the cap face \(no foundation interface\)',scoped,re.I):
            return dict(result,kind='free',clearance=horizontal)
        if 'collar plate' not in scoped.lower():return dict(result,kind='base')
        ct=value(scoped,r'welded to a PL');gap=value(scoped,r'centre gap\s*\(')
        length=value(scoped,r'\bLw\s*=')
        if any(v is None for v in (ct,gap,length)):
            raise ValueError('Embedded collar source selection is incomplete: '+rid)
        segment=next((r for r in records.values() if r.get('id')=='conn-column-base-segment-'+column),{})
        steel=re.search(r'\b\d+ PL '+NUMBER+r' x '+NUMBER+r' in',segment.get('components',''),re.I)
        reinforcement=number(steel[1]) if steel else 0.
        return dict(result,kind='collar',thickness=ct,gap=gap,wall_weld_length=length,
                    reinforcement=reinforcement,reinforcement_width=number(steel[2]) if steel else 0.)
    return None


def cap_plate(ctx):
    """Find the separately selected upper gusset plate on the embedded column."""
    records={r['id']:r['data'] for r in ctx.package['design_records']}
    col=next((m['id'] for m in ctx.ms if m['kind']=='column'),None)
    if col is None:return None
    for c in ctx.package.get('physical',{}).get('connections',[]):
        if (col not in c['member_ids'] or c.get('detail_ref',{}).get('legacy_family')!='review_base' or
                max(abs(a-b) for a,b in zip(c['point'],ctx.c['point']))>.001):continue
        for rid in c['design_record_ids']:
            components=records.get(rid,{}).get('components','')
            hit=re.search(r'gusset base plate PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+
                r' in (.*?) at the top of the (?:pile )?cap, CJP-welded to the column[^;]*?on '+NUMBER+
                r' in non-shrink grout',components,re.I)
            if hit:
                return dict(thickness=number(hit[1]),width=number(hit[2]),length=number(hit[3]),
                            material=hit[4].strip(),grout=number(hit[5]),record_id=rid,column_id=col)
    return None


def add_cap_plate(assembly,stock,face):
    w=stock['width'];length=stock['length'];grout=stock['grout'];t=stock['thickness']
    plate=assembly.box('BASE',[face,-w/2,grout],[length,w,t],'S stock, CJP and grout; A flange-normal setout',
                       'Selected upper gusset support plate on the embedded column at the cap face')
    plate['selected_material']=stock['material']
    plate['parameters']={'source_record_id':stock['record_id'],'source_role':'cap_gusset_support_plate'}
    assembly.box('GROUT',[face,-w/2,0],[length,w,grout],'S','Selected non-shrink grout under cap gusset plate',kind='grout')
    assembly.weld('CAP-TO-COLUMN',[face,-w/2,grout+t/2],[face,w/2,grout+t/2],['BASE','COLUMN'],
                  kind='CJP',description='Selected cap gusset support plate to actual column face')


def collar(assembly,spec,face,width,interface):
    """Cut two real interruptions at the source-selected reinforcing plate widths."""
    length=spec['horizontal_length'];half=width/2;gap=spec['gap']/2
    t=spec['thickness'];rt=spec['reinforcement'];rw=spec['reinforcement_width']
    # Only the two reinforcing strips project beyond the column face. The
    # clear central edge stays on the actual wall and takes the selected CJP.
    from shapely.geometry import box
    outline=box(face,-half,face+length,half)
    if rt>0 and rw>0:
        for lo,hi in ((gap,min(half,gap+rw)),(max(-half,-gap-rw),-gap)):
            if hi-lo>1e-7:outline=outline.difference(box(face-rt,lo,face+rt,hi))
    plate=assembly.polygon('COLLAR',[[x,y,interface-t] for x,y in list(outline.exterior.coords)[:-1]],t,normal=[0,0,1],
                           basis='S thickness, wall weld and reinforcement clearance; A free perimeter',
                           description='Horizontal embedded-column collar notched at the actual box wall reinforcing strips')
    plate['parameters']={'source_record_id':spec['record_id'],'reinforcing_clear_gap_in':2*gap}
    weld=spec['wall_weld_length']
    if weld>2*gap+1e-5:raise ValueError('Collar-to-wall weld exceeds the source clear central strip')
    assembly.weld('COLLAR-COLUMN',[face,-weld/2,interface-t/2],[face,weld/2,interface-t/2],
                  ['COLLAR','COLUMN'],kind='CJP',description='Selected collar CJP in clear box-wall centre strip')
    return plate
