"""Resolve an embedded-column gusset to its collar or selected cap clearance."""
import re
from .assembly_templates import NUMBER,number


def value(text,pattern):
    hit=re.search(pattern+r'\s*\(?\s*'+NUMBER,text,re.I)
    return number(hit[1]) if hit else None


def locate_grade_interfaces(package,model):
    """Retain a stated diaphragm transfer when the physical column passes through grade."""
    decision=next((r for r in model.get('assumptions',[]) if
        'grade slab and foundation walls receive' in r.get('answer','').lower()),None)
    if not decision:return
    members={m['id']:m for m in model['members']}
    located_bases={(mid,tuple(c['point'])) for c in model['connections'] if c.get('detail_ref',{}).get('id') in
                   ('review_base','hr_column_base') for mid in c['member_ids']}
    for c in model['connections']:
        if c.get('parameters',{}).get('joint')!='base' or c['detail_ref']['id'] not in ('review_brace','review_brb'):continue
        bound=[members[mid] for mid in c['member_ids']]
        columns=[m for m in bound if m['kind']=='column']
        if len(columns)!=1 or any(m['kind'] not in ('brace','column') for m in bound):continue
        column=columns[0];datum=c['point'][2]
        ends=[q[2]+off[2] for q,off in zip(column['axis'],column['end_offsets'])]
        if not min(ends)+1e-4<datum<max(ends)-1e-4 or (column['id'],tuple(c['point'])) in located_bases:continue
        note=('The accepted grade diaphragm and foundation walls receive the base shear. '
              'The steel-to-diaphragm attachment is unspecified at this continuing column.')
        c['parameters']['grade_diaphragm_interface']=note
        finding=dict(code='grade_diaphragm_attachment_required',connection_id=c['id'],column_id=column['id'],
                     point_in=c['point'],column_elevations_in=ends,decision_id=decision['id'],
                     design_record_ids=c['design_record_ids'],detail=note)
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
            return dict(kind='base',record_id=rid,column_kind='fillet',
                column_length=number(column_fillet[1]),column_fillet=number(column_fillet[2]),
                horizontal_length=number(bottom_fillet[1]),horizontal_fillet=number(bottom_fillet[2]),
                workpoint_station=value(text,r'brace end'),faces=2)
        if not re.match(r'base (?:corner )?gusset\b',text,re.I):continue
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
