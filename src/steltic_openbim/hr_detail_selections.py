"""Resolve retained HR connection selections by role and occurrence."""
import re
from .assembly_templates import NUMBER, number


class SelectionConflict(ValueError):
    def __init__(self,connection_id,key,sources):
        self.connection_id=connection_id
        self.key=key
        self.sources=sources
        super().__init__(f'Competing selected {key[0]}.{key[1]} at {connection_id}')

    def record(self,package,connection_id):
        rows=package.setdefault('provenance',{}).setdefault('openbim_translation_findings',[])
        finding=dict(code='unresolved_selected_component',connection_id=connection_id,
                     role=self.key[0],field=self.key[1],sources=self.sources,
                     disposition='Retained prior geometry pending source applicability resolution')
        if finding not in rows:
            rows.append(finding)


class SelectedFields(dict):
    def __init__(self, connection_id):
        super().__init__()
        self.connection_id = connection_id
        self.conflicts = set()
        self.sources = {}

    def get(self, key, default=None):
        if key in self.conflicts:
            raise SelectionConflict(self.connection_id,key,self.sources[key])
        return super().get(key, default)

    def signature(self):
        return (tuple(sorted((k,str(v)) for k,v in self.items())),
                tuple(sorted((k,tuple((x['record_id'],x['field_index'],str(x['value'])) for x in self.sources[k]))
                             for k in self.conflicts)))


def selected_fields(package, connection):
    """Read only the source fields selected for this particular occurrence."""
    handoff = package.get('source_handoff', {})
    occurrence = handoff.get('occurrences', {}).get(connection['id'], {})
    values = SelectedFields(connection['id'])
    overrides = {(row['record_id'], row['field_index']): row['value']
                 for row in occurrence.get('overrides', [])}
    for application in occurrence.get('applications', []):
        record = handoff['records'][application['record_id']]
        for index in application.get('selected', []):
            field = record['fields'][index]
            key = (field['role'], field['field'])
            value = overrides.get((application['record_id'], index), field['value'])
            values.sources.setdefault(key,[]).append({'record_id':application['record_id'],
                'field_index':index,'pointer':field.get('source',{}).get('pointer'),'value':value})
            if key in values and values[key] != value:
                # Different connected records can describe neighboring hardware.
                # Consumers must explicitly address the controlling record.
                values.conflicts.add(key)
            else:
                values[key] = value
    return values


def beam_family(components):
    text = components.strip().lower()
    if re.match(r'pin(?:-hinge\b|\s+[\d./-]+\s+in\s+dia)', text):
        return 'review_pin_beam'
    if re.search(r'\b(?:single[- ]plate|shear (?:tab|plate)|single shear plate)\b', text):
        return 'review_beam'
    return None


def selected_shear_text(ctx):
    """Use the selected component group inside a multi-detail source record."""
    from .review_assemblies import source_text
    handoff=ctx.package['source_handoff']
    ids=list(dict.fromkeys(r['record_id'] for r in ctx.selected.sources[('shear_plate','thickness_in')]))
    originals={r['id']:r['data'] for r in ctx.package['design_records']}
    applications={a['record_id']:a for a in handoff['occurrences'][ctx.c['id']]['applications']}
    texts=[]
    for rid in ids:
        app=applications[rid];record=handoff['records'][rid]
        group=app.get('beam_end_group',{}).get('selected')
        if group:
            rows=[f for f in record['fields'] if f.get('applicability',{}).get('beam_group')
                  and f['role'] in ('bolt','shear_plate') and f['source']['pointer'].endswith('/components')]
            matches=[f['source']['span'] for f in rows if f['applicability']['beam_group']==group]
            if matches:
                lo=min(span[0] for span in matches);last=max(span[1] for span in matches)
                components=originals[rid]['components']
                hi=min((f['source']['span'][0] for f in rows if f['source']['span'][0]>=last and
                        f['applicability']['beam_group']!=group),default=len(components))
                texts.append(components[lo:hi])
                continue
        texts.append(source_text(ctx.package,dict(ctx.c,design_record_ids=[rid])))
    return '\n'.join(texts)


def first_number(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return number(match[1])
    return None


def pin_selection(ctx):
    text = ctx.text
    diameter = ctx.selected.get(('pin', 'diameter_in'))
    if diameter is None:
        diameter = first_number(text, (
            r'\bpin '+NUMBER+r' in\.? dia',
            r'(?:through a |\b)'+NUMBER+r' in(?:\s+dia\.?)? pin\b',
        ))
    material = ctx.selected.get(('pin', 'material'))
    if material is None:
        match = re.search(r'\bpin\s*(?:[\d./-]+\s*in\.?\s*dia\.?\s*)?\(\s*((?:AISI\s+)?4140\s+Q&T|(?:ASTM\s+)?A572\s+(?:Gr(?:ade)?\.?\s*)?50|(?:ASTM\s+)?A193\s+(?:Gr(?:ade)?\.?\s*)?B7)',text,re.I)
        if match:
            material = match[1]
    if diameter is None or material is None:
        raise ValueError('Missing selected pin diameter or material for '+ctx.c['id'])
    hole = ctx.selected.get(('pin_hole', 'diameter_in'))
    clearance = (float(hole)-float(diameter) if hole is not None else
                 first_number(text, (r'(?:holes?\s+|=\s*)d\s*\+\s*'+NUMBER+r'\s*in',)))
    if clearance is not None and clearance < 0:
        raise ValueError('Selected pin is larger than its hole at '+ctx.c['id'])
    return float(diameter), str(material), clearance


def outer_clevis_weld(ctx):
    selected = ctx.selected.get(('clevis_outer_fillet', 'size_in'))
    if selected is not None:
        return float(selected)
    size = first_number(ctx.text, (
        NUMBER+r'[- ]in\.? (?:E\d+\w* )?fillets? to both flanges on their outer faces',
        r'outer[- ]face(?:s)?[^;]{0,65}?'+NUMBER+r'[- ]in\.? (?:E\d+\w* )?fillet',
        NUMBER+r'[- ]in\.? (?:E\d+\w* )?fillets? (?:along|on) (?:the |their )?outer faces?',
    ))
    return size


def reinforcement_weld(ctx):
    size=ctx.selected.get(('reinforcement_fillet','size_in'))
    if size is not None:
        return float(size)
    return first_number(ctx.text, (
        r'(?:each|reinforc\w+)[^;|]{0,180}?'+NUMBER+r'[- ]in\.? (?:longitudinal )?fillet',
        NUMBER+r'[- ]in\.? longitudinal fillets? \(two lines per plate\)',
    ))


def bolted_brb(ctx):
    text = ctx.text
    selected = ctx.selected
    variant=selected.get(('connection','variant'))
    if variant in ('brb_bolted','brb_bolted_splice','bolted_brb'):
        required={'count':'count','diameter':'diameter_in','material':'material','rows':'rows','pitch':'pitch_in'}
        values={key:selected.get(('bolt',field)) for key,field in required.items()}
        if all(value is not None for value in values.values()):
            return with_bolt_pattern(values,selected)
        if not re.search(r'\bBRB end\b[^;|]*\bbolted between two splice plates\b',text,re.I):
            raise ValueError('Incomplete selected bolted BRB arrangement at '+ctx.c['id'])
    if variant=='brb_pinned':return None
    if not re.search(r'\bBRB end\b[^;|]*\bbolted between two splice plates\b',text,re.I):
        return None
    match = re.search(r'\bwith (\d+)\s*x\s*'+NUMBER+r'\s*in\s+(A(?:325|490)(?:-[NX])?)\s+bolts?\s*\((\d+) rows at '+NUMBER+r'\s*in',text,re.I)
    if not match:
        raise ValueError('Missing selected bolted BRB pattern for '+ctx.c['id'])
    count,diameter,material,rows,pitch = match.groups()
    return with_bolt_pattern(dict(count=int(selected.get(('bolt','count')) or count),
                diameter=float(selected.get(('bolt','diameter_in')) or number(diameter)),
                material=str(selected.get(('bolt','material')) or material),
                rows=int(selected.get(('bolt','rows')) or rows),
                pitch=float(selected.get(('bolt','pitch_in')) or number(pitch))),selected)


def with_bolt_pattern(values,selected):
    pattern={k[1]:selected.get(k) for k in selected if k[0]=='brb_bolt_pattern'}
    if not pattern:return values
    required=('longitudinal_stations','transverse_lines','longitudinal_pitch_in','loaded_end_distance_in',
              'block_shear_path_length_in','transverse_shear_plane_spacing_in')
    if any(k not in pattern for k in required):
        raise ValueError('Incomplete directional HR bolt pattern')
    n,lines=pattern['longitudinal_stations'],pattern['transverse_lines']
    if n!=int(n) or lines!=int(lines) or min(n,lines)<2 or n*lines!=values['count']:
        raise ValueError('Directional HR bolt pattern differs from its selected bolt count')
    pitch=pattern['longitudinal_pitch_in'];edge=pattern['loaded_end_distance_in']
    gauge=pattern['transverse_shear_plane_spacing_in']
    if lines==2:gauge_pitch=gauge
    elif 'transverse_pitch_in' in pattern:gauge_pitch=pattern['transverse_pitch_in']
    else:raise ValueError('HR multi-line bolt pattern requires its transverse spacing')
    if (min(pitch,gauge_pitch)<=values['diameter'] or edge<=0 or
            abs((n-1)*pitch+edge-pattern['block_shear_path_length_in'])>1e-4 or
            abs((lines-1)*gauge_pitch-gauge)>1e-4):
        raise ValueError('Directional HR screw-line spacing or block shear paths disagree')
    return dict(values,pattern=pattern,along_count=int(n),across_count=int(lines),along_pitch=pitch,
                across_pitch=gauge_pitch,loaded_edge=edge)
