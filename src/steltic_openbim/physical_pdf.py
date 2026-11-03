"""Dimensioned HR coordination sheets from declared physical occurrences.

The drawing identifiers are assigned here. Member geometry, section sizes and
connection parts come only from the saved source package; no test recipe is used.
"""
from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path

from .design_pdf import feet, inches, INK, BLUE, LIGHT, ASSUMED
from .drawing_pdf import feature_vertices, source_openings
from .drawing_workflow import write_json, fingerprint
from .pilots.geometry import member_faces, part_faces, part_lines
from .source_worklines import physical_view
from .source_workline_pdf import WorklineSheets


def drawing_model(package):
    model = copy.deepcopy(physical_view(package))
    model['title'] = package['building_id']
    members = model['members']
    groups = sorted({(m['kind'], m.get('profile_id') or 'TBD') for m in members})
    marks = {key: f'M{i:03}' for i, key in enumerate(groups, 1)}
    for m in members:
        m['mark'] = m.get('mark') or marks[m['kind'], m.get('profile_id') or 'TBD']
        m['basis'] = 'S'
    columns = [m for m in members if m['kind'] in ('col', 'column')]
    points = [p for m in (columns or members) for p in m['axis']]
    model['grids'] = {}
    for axis, key in enumerate(('x', 'y')):
        values = sorted({round(p[axis], 6) for p in points})
        model['grids'][key] = [(str(i + 1) if key == 'x' else chr(65 + i) if i < 26 else 'Y' + str(i + 1), v)
                              for i, v in enumerate(values)]
    levels = package.get('layout_evidence', {}).get('levels_in') or []
    if not levels:
        levels = [p['vertices'][0][2] for p in model['panels'] if p.get('kind') in ('floor', 'roof')
                  and len({round(v[2], 6) for v in p['vertices']}) == 1]
        levels += [min(p[2] for m in members for p in m['axis'])]
    if len(set(levels)) < 2:
        levels += [m['axis'][0][2] for m in members if abs(m['axis'][0][2] - m['axis'][1][2]) < 1e-5]
    model['levels'] = sorted(set(round(v, 6) for v in levels))
    families = defaultdict(list)
    for connection in model['connections']:
        key = connection.get('detail_ref', {}).get('id') or '|'.join(connection.get('design_record_ids', [])) or connection['id']
        families[key].append(connection)
    model['details'] = []
    for i, (key, occurrences) in enumerate(families.items(), 1):
        ref = f'C{i:03}'
        model['details'].append(dict(reference=ref, family=key, connections=occurrences))
        for c in occurrences:
            c['drawing_reference'] = ref
    return model


class PhysicalSheets(WorklineSheets):
    def start(self, number, title, scale='NTS', refs=()):
        if self.page: self.c.showPage()
        self.page += 1; self.current = number
        self.rows.append(dict(number=number, title=title, page=self.page, scale=scale, query_ids=list(refs)))
        c = self.c; c.setStrokeColor(INK); c.setLineWidth(1); c.rect(34, 34, self.W - 68, self.H - 68)
        self.text(55, self.H - 70, 'STELTIC / OPENBIM', 17, font='Helvetica-Bold')
        self.text(55, self.H - 112, title, 25, font='Helvetica-Bold')
        self.text(self.W - 390, self.H - 69, number, 27, font='Helvetica-Bold')
        self.text(self.W - 390, self.H - 96, 'A1 landscape | ' + scale, 13)
        self.line((34, 122), (self.W - 34, 122))
        self.text(55, 96, self.p['building_id'], 16, font='Helvetica-Bold')
        self.text(55, 71, f"REV {self.s['revision']} | SOURCE DESIGN COORDINATION | {self.s['drawing_status'].upper()}", 12, BLUE)
        self.text(55, 49, 'Dimensions ft-in unless noted | Worklines are not cut lengths | Not a fabrication or construction issue', 11)
        self.text(self.W - 650, 95, 'Source ' + self.s['source_model_sha256'][:24], 11)
        self.text(self.W - 650, 72, 'Dashed amber = proposal / TBD - resolve query', 11, ASSUMED)
        self.text(self.W - 200, 49, f'Sheet {self.page} / {number}', 12)


def plot(sh, number, title, members, axes=(0, 1), features=(), z=None):
    if not members: return
    points = [p for m in members for p in m['axis']]
    bounds = [(min(p[i] for p in points), max(p[i] for p in points)) for i in axes]
    need = max(max(12, b - a) * 72 / space for (a, b), space in zip(bounds, (sh.W - 900, sh.H - 560)))
    scale = next((s for s in (10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000) if s >= need), math.ceil(need / 100) * 100)
    sh.start(number, title, '1:' + str(scale))
    tr, _ = sh.grid_view(bounds, axes, scale, origin=(215, 330))
    groups = defaultdict(list)
    for m in members:
        a, b = [tr(p) for p in m['axis']]
        sh.line(a, b, BLUE if 'brace' in m['kind'] else INK, 1.1 if m['kind'] in ('col', 'column') else .6)
        if math.dist(a, b) < 2:
            sh.c.setStrokeColor(INK); sh.c.rect(a[0] - 3, a[1] - 3, 6, 6)
        groups[m['mark']].append((m, a, b))
    occupied = []
    for f in features:
        pp = [tr(p) for p in feature_vertices(f)]; color = BLUE if f['confirmed'] else ASSUMED
        for a, b in zip(pp, pp[1:] + pp[:1]): sh.line(a, b, color, 1.1, None if f['confirmed'] else [5, 3])
        mid = tuple(sum(p[i] for p in pp) / len(pp) for i in (0, 1)); occupied.append(mid)
        sh.label(*mid, f['id'] + (' / source or confirmed' if f['confirmed'] else ' / TBD'), 10, color)
    sh.representative_marks(groups, 24, occupied)
    ids = {m['id'] for m in members}; joints = {j['id']: j for j in sh.m['joints']}
    used = set()
    for c in sh.m['connections']:
        j = joints.get(c.get('joint_id')); ref = c['drawing_reference']
        if not j or ref in used or len(used) >= 7: continue
        linked = set(c.get('member_ids', [])) | {e['member_id'] for e in j.get('member_ends', [])}
        if not linked & ids: continue
        if z is not None:
            # Physical end offsets can place the actual joint below the floor
            # workline. Its declared member-end mapping establishes the plan.
            on_plane=abs(j['point'][2]-z)<1e-5
            for end in j.get('member_ends', []):
                m=sh.lookup.get(end['member_id'])
                if m and m['id'] in ids:
                    on_plane |= abs(m['axis'][0 if end['end']=='start' else 1][2]-z)<1e-5
            if not on_plane: continue
        p = tr(j['point'])
        if not (205 <= p[0] <= sh.W - 600 and 315 <= p[1] <= sh.H - 215): continue
        if any(abs(p[0] - a) < 180 and abs(p[1] - b) < 70 for a, b in occupied): continue
        sh.callout(p, ref + ' (typ)', 22, 26); occupied.append(p); used.add(ref)
    if axes[1] == 2:
        for a, b in zip(sh.m['levels'], sh.m['levels'][1:]):
            p = [0, 0, a]; q = [0, 0, b]; p[axes[0]] = q[axes[0]] = bounds[0][0]
            sh.dim(tr(p), tr(q), 78, value=b-a, ref='Source level interval')
        for elevation in sh.m['levels']:
            p = [0, 0, elevation]; p[axes[0]] = bounds[0][1]
            x, y = tr(p); sh.label(x + 40, y + 4, feet(elevation), 10)
    notes = ['Framing follows the source-declared member worklines. Physical offsets, profiles and parts are retained in the return IFC.',
             'Grid labels are drawing identifiers assigned to source column coordinates. Dimensions are source workline distances.',
             'M marks identify section groups unless source marks are supplied. Full occurrence IDs and axes: member_index.json.',
             'C references point to source connection families. All occurrence mappings are retained in connection_index.json. Unlocated or unspecified parts remain TBD.']
    y = sh.panel_notes(notes, x=sh.W-570, y=sh.H-180, width=480)-10
    sh.text(sh.W-570, y, 'MEMBER MARKS IN VIEW', 14, font='Helvetica-Bold'); y -= 28
    for mark, rows in sorted(groups.items()):
        if y < 250:
            sh.text(sh.W-570, y, 'Further marks: M-series member schedule.', 11); break
        m = rows[0][0]; y = sh.wrap(sh.W-570, y, f"{mark}: {m.get('profile_id') or 'TBD'} / {m['kind']} / {len(rows)}", 480, 11, 15)-8
    sh.views[-1]['member_ids'] = [m['id'] for m in members]


def detail(sh, row):
    cs = row['connections']; source = next((c for c in cs if c.get('parts')), cs[0])
    kinds = sorted({p.get('kind', 'part').replace('_', ' ') for c in cs for p in c.get('parts', [])})
    sh.start(row['reference'], 'Connection / ' + (', '.join(kinds).capitalize() if kinds else 'Source specification'))
    joints = {j['id']: j for j in sh.m['joints']}; joint = joints.get(source.get('joint_id'), {})
    center = joint.get('point', source.get('point', [0, 0, 0]))
    parts = [(face, True) for p in source.get('parts', []) for face in part_faces(p, sh.profiles)]
    lines = [line for p in source.get('parts', []) for line in part_lines(p)]
    faces = list(parts)
    linked = (set(source.get('member_ids', [])) | {e['member_id'] for e in joint.get('member_ends', [])}
              | {e['member_id'] for e in joint.get('attachments', [])})
    crop = [(v-36, v+36) for v in center]
    for m in sh.m['members']:
        if m['id'] in linked:
            faces += [(f, False) for f in member_faces(m, sh.profiles, crop)]
    if parts or lines:
        views = [('PLAN X-Y', (0, 1), (80, 910, 660, 480)), ('ELEVATION X-Z', (0, 2), (790, 910, 660, 480)),
                 ('ELEVATION Y-Z', (1, 2), (80, 260, 660, 500)), ('ASSEMBLY / ISOMETRIC', None, (790, 260, 660, 500))]
        for label, axes, (x, y, w, h) in views:
            def raw(p):
                q = [p[i]-center[i] for i in range(3)]
                return [q[axes[0]], q[axes[1]]] if axes else [q[0]*.8-q[1]*.6, q[2]*.9-q[0]*.26-q[1]*.35]
            allp = [raw(p) for f, _ in faces for p in f] + [raw(p) for line in lines for p in line]
            bounds = [(min(p[i] for p in allp), max(p[i] for p in allp)) for i in (0, 1)]
            scale = min((w-110)/max(1, bounds[0][1]-bounds[0][0]), (h-100)/max(1, bounds[1][1]-bounds[1][0]))
            def tr(p):
                q = raw(p)
                return x+w/2+(q[0]-sum(bounds[0])/2)*scale, y+h/2+(q[1]-sum(bounds[1])/2)*scale
            sh.text(x, y+h+22, label + ' / NTS', 14, font='Helvetica-Bold')
            for f, ispart in sorted(faces, key=lambda r:r[1]):
                pp = [tr(p) for p in f]
                for a, b in zip(pp, pp[1:]+pp[:1]): sh.line(a, b, BLUE if ispart else LIGHT, .8 if ispart else .35)
            for line in lines:
                pp = [tr(p) for p in line]
                for a, b in zip(pp, pp[1:]): sh.line(a, b, ASSUMED, 1.4, [5, 3])
            if axes and parts:
                pp = [p for f, _ in parts for p in f]
                low = [min(p[i] for p in pp) for i in range(3)]; high = [max(p[i] for p in pp) for i in range(3)]
                a = list(low); b = list(low); b[axes[0]] = high[axes[0]]
                value=high[axes[0]]-low[axes[0]]
                sh.dim(tr(a), tr(b), -30, value=value, label=inches(value), ref='Source connection-part envelope', size=11)
                b=list(low); b[axes[1]]=high[axes[1]]; value=high[axes[1]]-low[axes[1]]
                sh.dim(tr(a), tr(b), 35, value=value, label=inches(value), ref='Source connection-part envelope', size=11)
            sh.views.append(dict(sheet=sh.current, kind='source_connection_assembly' if parts else 'source_connection_reference', axes=list(axes) if axes else None,
                                 connection_id=source['id'], part_ids=[p['id'] for p in source['parts']], contextual_member_ids=sorted(linked)))
    else:
        sh.text(85, sh.H-250, 'No located part geometry supplied for this family.', 22, ASSUMED)
        sh.wrap(85, sh.H-300, 'Connection specification retained below. Part set-out and assembly views: TBD - resolve query. No geometry has been invented.', 1250, 18, 28)
    x = sh.W-830; y = sh.H-185
    notes = [f"{len(cs)} source occurrences; representative {source['id']}.",
             'Blue: supplied connection parts. Grey: connected members cropped around the source joint.',
             'Dimensions identify the supplied part envelope, not hole centres or fabrication cut sizes. Only explicitly supplied parts are shown.',
             'Design records: ' + ', '.join(source.get('design_record_ids', []))]
    if lines: notes.insert(1, 'Amber dashed lines: source reference locations only. Physical plate/weld set-out: TBD - resolve query. No solid geometry inferred from detail notes.')
    y = sh.panel_notes(notes, x=x, y=y, width=735)-10
    counts = Counter(p.get('kind', 'part') for p in source.get('parts', []))
    y = sh.wrap(x, y, 'REPRESENTATIVE PARTS: ' + (', '.join(f'{n} {k}' for k,n in counts.items()) or 'TBD'), 735, 13, 19)-28
    records = {r['id']: r for r in sh.p['design_records']}
    for ref in source.get('design_record_ids', []):
        record = records.get(ref, {}).get('data', {})
        for key in ('type', 'components', 'design_basis', 'limit_state', 'demand', 'capacity', 'dc'):
            if key not in record: continue
            value = record[key]; value = json.dumps(value, ensure_ascii=True) if isinstance(value, (dict, list)) else str(value)
            lines = sh.lines(key.replace('_',' ').upper()+': '+value, 735, 12)
            if y-len(lines)*17 < 190:
                sh.text(x, y, 'Full source specification: source_records.json.', 12); return
            y = sh.wrap(x, y, key.replace('_',' ').upper()+': '+value, 735, 12, 17)-18


def generate(package, state, dest):
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    model = drawing_model(package); sh = PhysicalSheets(package, state, dest, model)
    sh.c.setTitle(package['building_id'] + ' - dimensioned source design coordination')
    sh.start('G001', 'Drawing basis and source coverage')
    y = sh.H-200
    for text in [f"{len(model['members'])} physical members; {len(model['connections'])} connection occurrences; {len(model['details'])} connection families.",
                 'This set uses the supplied physical export and its completed design records. No fictional review recipe or previous building design is substituted.',
                 'Plans and frame sections show source worklines, grid distances, level intervals, member marks and located connection references. Workline lengths are not fabrication cut lengths.',
                 'Connection sheets show the source-supplied parts in plan, elevation and isometric views. Missing part geometry remains explicitly TBD; a design-detail reference alone does not establish an assembly.',
                 'Opening proposals remain separate from the structural source. Provisional symbols have no dimensions. Confirmed openings retain their source or user resolution.',
                 'G: basis and requests. S: base, floor/roof plans and frame sections. C: connection families. M: section schedule. A: opening schedule. Full occurrence data accompany the PDF.']:
        y = sh.wrap(65, y, text, sh.W-150, 18, 27)-32
    for interface in package['physical'].get('interfaces', []):
        text = 'DECLARED INTERFACE: ' + ' | '.join(str(interface[k]) for k in ('id', 'scope', 'responsible_party', 'representation') if k in interface)
        for line in sh.lines(text, sh.W-150, 16):
            if y < 180:
                sh.start(f'G001-{sh.page}', 'Declared interfaces / continued'); y=sh.H-200
            sh.text(65, y, line, 16); y-=25
        y-=24
    for i, r in enumerate(state['requests'], 2):
        sh.start(f'G{i:03}', 'Information request / ' + r['id']); y = sh.H-200
        for label, value in [('Question', r['question']), ('Proposal', r['proposal']), ('Basis', r['evidence']), ('Status', r.get('resolution') or 'TBD - resolve query; drawings proceed.')]:
            if y<230:
                sh.start(f'G{i:03}-{sh.page}', 'Information request / continued'); y=sh.H-200
            sh.text(65, y, label, 17, font='Helvetica-Bold'); y -= 32
            for line in sh.lines(value,sh.W-150,17):
                if y<180:
                    sh.start(f'G{i:03}-{sh.page}', 'Information request / continued'); y=sh.H-200
                sh.text(65,y,line,17); y-=25
            y-=35
    ms = model['members']; levels = model['levels']; base = levels[0]
    columns = [m for m in ms if m['kind'] in ('col','column')]
    column_ids={m['id'] for m in columns}
    plot(sh, 'S100', 'Base column worklines', [m for m in columns if min(p[2] for p in m['axis']) <= base+1e-5] or ms, z=base)
    features = source_openings(package)+state['features']
    for k, z in enumerate(levels[1:] or levels, 1):
        selected = [m for m in ms if (m['id'] in column_ids and min(p[2] for p in m['axis'])-1e-5 <= z <= max(p[2] for p in m['axis'])+1e-5)
                    or (m['id'] not in column_ids and (abs(max(p[2] for p in m['axis'])-z)<1e-5 or m.get('level')==k))]
        plot(sh, f'S{100+k:03}', f"{'Roof' if z==levels[-1] else 'Level '+str(k)} framing / {feet(z)}", selected,
             features=[f for f in features if f['level']==k and f['plane']=='xy'], z=z)
    section = 200
    for axis in (0,1):
        for label, station in model['grids']['xy'[axis]]:
            selected = [m for m in ms if all(abs(p[axis]-station)<1e-5 for p in m['axis'])]
            if selected:
                section += 1; plot(sh, f'S{section}', f"Frame section / {'XY'[axis]} grid {label}", selected, axes=(1-axis,2))
    for row in model['details']: detail(sh, row)
    groups = Counter((m['mark'], m['kind'], m.get('profile_id') or 'TBD', round(math.dist(*m['axis']),6)) for m in ms)
    sh.table('M', 'Member workline schedule', ['Mark','Kind','Section','Workline length','Count','Basis'], [150,240,280,290,120,sh.W-1210],
             [(mark,kind,profile,feet(length),n,'Source-declared geometry; cut length not asserted') for (mark,kind,profile,length),n in sorted(groups.items())])
    if features:
        rows = []
        for f in features:
            dims = [feet(f[key]*12) if f['confirmed'] else 'TBD' for key in ('x_ft','y_ft','z_ft','width_ft','height_ft')]
            rows.append([f['id'],f['level'],f['kind'],*dims,f['query_id']])
            if f['confirmed']: sh.dimensions.append(dict(kind='confirmed_opening', feature_id=f['id'], values_ft={key:f[key] for key in ('x_ft','y_ft','z_ft','width_ft','height_ft')}))
        sh.table('A','Opening schedule',['ID','Level','Kind','X','Y','Z','Width','Height','Source / request'],[140,90,230,220,220,220,220,220,sh.W-1790],rows)
    sh.c.save()
    write_json(dest/'member_index.json', model['members']); write_json(dest/'connection_index.json', model['connections'])
    write_json(dest/'source_records.json', package['design_records'])
    for d in sh.dimensions: d.setdefault('kind','source_dimension')
    report = dict(schema='steltic.drawing_set', revision=state['revision'], building_id=package['building_id'],
        source_model_sha256=fingerprint(package), decision_state_sha256=fingerprint({k:v for k,v in state.items() if k not in ('sheets','artifacts')}),
        drawing_status=state['drawing_status'], can_generate=True,
        open_requests=sum(not r['confirmed'] for r in state['requests']), representation='source_physical_geometry',
        counts=dict(members=len(ms), connections=len(model['connections']), connection_families=len(model['details'])),
        sheets=sh.rows, dimensions=sh.dimensions, views=sh.views, labels=sh.labels, callouts=sh.callouts,
        pdf_sha256=hashlib.sha256((dest/'drawings.pdf').read_bytes()).hexdigest(),
        artifacts=['drawings.pdf','drawing_manifest.json','information_requests.json','member_index.json','connection_index.json','source_records.json'],
        limits=['Source workline dimensions are not fabrication cut lengths.', 'Unprovided connection parts remain TBD; no fabricated assembly geometry.', 'Unconfirmed opening dimensions are omitted.'])
    write_json(dest/'drawing_manifest.json', report)
    return report
