"""Engineering drawing set for a natively declared cold-formed steel (CFS) building.

Used only for CFS packages whose physical model was recorded by the CFS engine's native
builder (``design_context.physical_design``).  Hot-rolled (HR) packages never reach this module.

Every value on a sheet is read from the package: geometry from ``physical`` (located studs,
tracks, joists, rods, panels, assembly templates), schedule values from ``design_records``
(the same calculation records the design report prints).  Nothing is inferred, re-designed or
filled from a recipe.  ``generate`` also writes ``cfs_drawing_model.json`` -- the register of
what was drawn (sheets, schedule cells, dimensions, member counts) that the delivery
verification reads back against the PDF, the IFC and the report.
"""
from collections import Counter, OrderedDict, defaultdict
import hashlib
import json
import math
from pathlib import Path

from .drawing_workflow import fingerprint, write_json
from . import bim_assemblies

W, H = 2383.94, 1683.78                      # A1 landscape, points
INK = '#1d2b33'; GREY = '#6c7a80'; LIGHT = '#c9d1d3'; ACCENT = '#a2461f'; BLUE = '#2f6480'; FILL = '#f3e3d9'
MARGIN = 36.0; TITLE_H = 104.0
SCALES = (1, 2, 4, 5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500)


def ascii_text(v):
    return (str(v).replace('–', '-').replace('—', '-').replace('′', "'").replace('″', '"').replace('×', 'x')
            .replace('φ', 'phi').replace('Ω', 'Omega').replace('≤', '<=').replace('≥', '>=').replace('°', ' deg')
            .encode('ascii', 'replace').decode())


def feet(inches):
    """Feet-inches to the nearest 1/16 in., e.g. 10'-8", 0'-3 1/2"."""
    n = round(abs(float(inches)) * 16)
    ft, rem = divmod(n, 192)
    whole, frac = divmod(rem, 16)
    txt = str(whole)
    if frac:
        g = math.gcd(frac, 16)
        txt += ' %d/%d' % (frac // g, 16 // g)
    return ('-' if inches < -1e-9 else '') + "%d'-%s\"" % (ft, txt)


def num(v, nd=2):
    if v is None or isinstance(v, bool):
        return '-'
    if isinstance(v, (int, float)):
        return ('%.' + str(nd) + 'f') % float(v)          # fixed decimals, exactly as the report prints the value
    return str(v)


# ------------------------------------------------------------------------------------------
# model extraction (package -> what the sheets show)
# ------------------------------------------------------------------------------------------

def is_native_cfs(package):
    pd = (package.get('design_context') or {}).get('physical_design')
    return (package.get('module') == 'CFS' and isinstance(pd, dict) and pd.get('schema') == 'steltic.cfs_physical_design'
            and bool(package['physical'].get('members')) and all(m.get('status') == 'declared' for m in package['physical']['members']))


def record_index(package):
    return {r['id']: r for r in package.get('design_records', [])}


def line_frame(line):
    a, b, pos = line['start_ft'] * 12.0, line['end_ft'] * 12.0, line['pos_ft'] * 12.0
    if line['direction'] == 'X':
        return [a, pos, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], b - a
    return [pos, a, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], b - a


def station(P0, u, p):
    return (p[0] - P0[0]) * u[0] + (p[1] - P0[1]) * u[1]


def wall_type_key(st):
    """Sheathed segment: ('S', material, thickness, faces, edge, field, screw, stud, track); strap-braced bay:
    ('B', material, width, thickness, faces, strap screws, screw, gusset screws, gusset thickness, track)."""
    sh = st.get('sheathing')
    if sh:
        return ('S', sh['material'], round(float(sh['thickness_in']), 4), int(sh['faces']), float(sh['edge_in']), float(sh['field_in']), sh['screw'],
                st['segment_stud']['section'], st['track']['section'])
    sp = st.get('strap')
    if sp:
        return ('B', sp['material'], float(sp['width_in']), round(float(sp['t_in']), 4), int(sp['faces']), int(sp['n_strap']), sp['screw'], int(sp['n_gusset']),
                round(float(sp['gusset']['t_in']), 4), st['track']['section'])
    return None


def drawing_model(package):
    """Everything the sheets print, with its source, as plain data."""
    pd = package['design_context']['physical_design']
    ph = package['physical']
    records = record_index(package)
    levels = sorted(package.get('reference_system', {}).get('levels', []), key=lambda r: r['level'])
    model = dict(building_id=package['building_id'], kind=pd['kind'], levels=levels, wall_lines=OrderedDict(), wall_types=[], floors=[], marks=[],
                 details=[], schedules=OrderedDict())
    # shear wall types, strongest schedule first
    types = {}
    for key, line in pd.get('wall_lines', {}).items():
        for ks, st in line['stories'].items():
            k = wall_type_key(st)
            if k is not None:
                types.setdefault(k, []).append((key, int(ks)))
    order = sorted([k for k in types if k[0] == 'S'], key=lambda k: (-k[3], k[4], -k[2], k[1]))
    tmark = {k: 'SW%d' % i for i, k in enumerate(order, 1)}
    for k in order:
        model['wall_types'].append(dict(mark=tmark[k], sheathing_material=k[1], thickness_in=k[2], faces=k[3], edge_in=k[4], field_in=k[5], screw=k[6],
                                        stud=k[7], track=k[8], used=sorted(set(types[k]))))
    model['strap_types'] = []
    for i, k in enumerate(sorted([k for k in types if k[0] == 'B'], key=lambda k: (-k[4] * k[2] * k[3], k[1])), 1):
        tmark[k] = 'SB%d' % i
        model['strap_types'].append(dict(mark=tmark[k], material=k[1], width_in=k[2], t_in=k[3], faces=k[4], n_strap=k[5], screw=k[6], n_gusset=k[7], gusset_t_in=k[8], track=k[9],
                                         used=sorted(set(types[k]))))
    by_line = defaultdict(list)
    for m in ph['members']:
        if m.get('wall_line'):
            by_line[m['wall_line']].append(m)
    panels = defaultdict(list)
    for p in ph['panels']:
        if p.get('wall_line'):
            panels[p['wall_line']].append(p)
    openings = defaultdict(list)
    for o in ph.get('openings', []):
        if o.get('wall_line'):
            openings[o['wall_line']].append(o)
    for key, line in pd.get('wall_lines', {}).items():
        P0, u, n, L = line_frame(line)
        rows = []
        for m in by_line.get(key, []):
            a, b = m['axis']
            rows.append(dict(id=m['id'], kind=m['kind'], role=m.get('role'), storey=m.get('storey'), profile=m['profile_id'], material=m['material_id'],
                             s0=station(P0, u, a), s1=station(P0, u, b), z0=a[2], z1=b[2], records=m.get('design_record_ids', [])))
        segs = []
        for p in panels.get(key, []):
            ss = [station(P0, u, v) for v in p['vertices']]; zz = [v[2] for v in p['vertices']]
            st = line['stories'][str(p['storey'])]
            segs.append(dict(id=p['id'], storey=p['storey'], face=p.get('face'), segment=p.get('segment'), s0=min(ss), s1=max(ss), z0=min(zz), z1=max(zz),
                             type=tmark[wall_type_key(st)], thickness=p['thickness'], records=p.get('design_record_ids', [])))
        bays = defaultdict(list)
        for m in by_line.get(key, []):
            if m['kind'] == 'strap':
                bays[(m['storey'], m.get('segment'))].append(m)
        for (k_, si), ms in sorted(bays.items()):
            st = line['stories'][str(k_)]
            a_, b_ = st['segments_ft'][si - 1]
            zz = [v[2] for m in ms for v in m['axis']]
            segs.append(dict(id='bay:%s:S%d:G%d' % (key, k_, si), storey=k_, face='+', segment=si, s0=a_ * 12.0 - line['start_ft'] * 12.0, s1=b_ * 12.0 - line['start_ft'] * 12.0, z0=min(zz), z1=max(zz),
                             type=tmark[wall_type_key(st)], strap=True, straps=sorted(m['id'] for m in ms), records=sorted({r for m in ms for r in m.get('design_record_ids', [])}),
                             diagonals=[(station(P0, u, m['axis'][0]), m['axis'][0][2], station(P0, u, m['axis'][1]), m['axis'][1][2]) for m in ms if m.get('face') == '+']))
        ops = []
        for o in openings.get(key, []):
            ss = [station(P0, u, v) for v in o['vertices']]; zz = [v[2] for v in o['vertices']]
            ops.append(dict(id=o['id'], storey=o.get('storey'), kind=o.get('kind'), s0=min(ss), s1=max(ss), z0=min(zz), z1=max(zz)))
        model['wall_lines'][key] = dict(key=key, label=key.split(':', 1)[1], direction=line['direction'], pos_in=line['pos_ft'] * 12.0, start_in=line['start_ft'] * 12.0,
                                        length_in=L, analysis_line=line.get('analysis_line'), grid=line.get('grid', True), members=rows, panels=segs, openings=ops,
                                        stories={int(k): v for k, v in line['stories'].items()})
    for fl in pd.get('floors', []):
        lvl = fl['level']
        joists = [m for m in ph['members'] if m['kind'] == 'joist' and m.get('level') == lvl]
        model['floors'].append(dict(level=lvl, kind=fl.get('kind', 'floor'), zones=fl['zones'], sheathing=fl['sheathing'],
                                    joists=[dict(id=m['id'], zone=m.get('zone'), axis=m['axis'], profile=m['profile_id']) for m in joists]))
    # member marks: one mark per (kind, role, section, material)
    groups = defaultdict(list)
    for m in ph['members']:
        groups[(m['kind'], m.get('role') or m['kind'], m['profile_id'], m['material_id'])].append(m)
    prefix = {'stud': 'S', 'bottom_track': 'T', 'top_track': 'T', 'joist': 'J', 'header': 'H', 'tie_rod': 'R', 'strap': 'B'}
    counters = Counter()
    for key in sorted(groups):
        pf = prefix.get(key[0], 'M'); counters[pf] += 1
        ms = groups[key]
        lengths = [math.dist(*m['axis']) for m in ms]
        model['marks'].append(dict(mark='%s%d' % (pf, counters[pf]), kind=key[0], role=key[1], section=key[2], material=key[3], count=len(ms),
                                   length_min_in=round(min(lengths), 4), length_max_in=round(max(lengths), 4), total_length_ft=round(sum(lengths) / 12.0, 1)))
    # connection families: one detail per assembly template family
    templates = bim_assemblies.index(ph)
    fam = OrderedDict()
    for c in ph['connections']:
        inst = c.get('assembly_instance')
        name = c.get('family') or (inst['template_id'].rsplit('-', 1)[0] if inst else 'connection')
        f = fam.setdefault(name, dict(family=name, connections=0, templates=Counter(), representative=None, records=set(), delegated=0))
        f['connections'] += 1
        f['records'].update(c.get('design_record_ids', []))
        if c.get('scope') == 'delegated':
            f['delegated'] += 1
        if inst:
            f['templates'][inst['template_id']] += 1
            if f['representative'] is None:
                f['representative'] = c['id']
    for i, f in enumerate(fam.values(), 1):
        parts = Counter()
        for tid, n in f['templates'].items():
            for p in templates[tid]['parts']:
                parts[p['kind']] += n
        model['details'].append(dict(reference='D%02d' % i, family=f['family'], occurrences=f['connections'], templates=len(f['templates']), representative=f['representative'],
                                     records=sorted(f['records']), part_counts=dict(sorted(parts.items())), delegated=f['delegated']))
    model['schedules'] = schedules(package, model, records)
    return model


def _rec(records, rid):
    return (records.get(rid) or {}).get('data') or {}


def schedules(package, model, records):
    """Schedule rows exactly as printed; each row names its design record."""
    out = OrderedDict()
    pd = package['design_context']['physical_design']
    tmark = {}
    for t in model['wall_types'] + model['strap_types']:
        for key, k in t['used']:
            tmark[(key, k)] = t['mark']
    rows = []
    for t in model['wall_types']:
        rows.append(dict(record=None, cells=[t['mark'], '%s, %s' % (_spec(pd, t['sheathing_material']), frac_in(t['thickness_in'])), 'both faces' if t['faces'] == 2 else 'one face',
                                           '%s at %s in. o.c. edges, %s in. o.c. field' % (t['screw'], num(t['edge_in'], 0), num(t['field_in'], 0)), t['stud'], t['track']]))
    if rows:
        out['wall_types'] = dict(title='Shear wall types', headers=['Type', 'Sheathing', 'Faces', 'Sheathing screws', 'Segment studs', 'Track'], widths=[110, 560, 170, 620, 230, 230], rows=rows)
    rows = []
    for t in model['strap_types']:
        rows.append(dict(record=None, cells=[t['mark'], '%s in. x %s in. flat strap, %s' % (num(t['width_in'], 0), num(t['t_in'], 4), _spec(pd, t['material'])), 'both faces' if t['faces'] == 2 else 'one face',
                                           '%d %s screws to a %s in. gusset plate each strap end' % (t['n_strap'], t['screw'], num(t['gusset_t_in'], 4)), '%d %s screws gusset to chord studs and track' % (t['n_gusset'], t['screw']), t['track']]))
    if rows:
        out['strap_types'] = dict(title='Strap-braced bay types (X-bracing, tension-only)', headers=['Type', 'Strap (each diagonal)', 'Faces', 'Strap end connection', 'Gusset connection', 'Track'],
                                  widths=[110, 640, 170, 560, 520, 230], rows=rows)
    rows = []
    for key, wl in model['wall_lines'].items():
        if not wl['analysis_line']:
            continue
        d, name = wl['analysis_line'].split(':')
        for k in sorted(wl['stories']):
            st = wl['stories'][k]
            sel_ = st.get('sheathing') or st.get('strap')
            if not sel_:
                continue
            rid = sel_['record']; w = _rec(records, rid)
            segs = st.get('segments_ft', [])
            rows.append(dict(record=rid, cells=[key.split(':', 1)[1], str(k), tmark[(key, k)], '%d x %s' % (len(segs), feet((segs[0][1] - segs[0][0]) * 12.0)) if segs else '-',
                                              num(w.get('v_design_plf'), 0), num(w.get('vn_plf'), 0), num(w.get('capacity'), 0), num(w.get('DC'), 2)]))
    out['wall_lines'] = dict(title='Shear wall schedule (by wall line and storey)', headers=['Wall line', 'Storey', 'Type', 'Segments / braced bays', 'v design (lb/ft)', 'vn (lb/ft)', 'phi vn (lb/ft)', 'D/C'],
                             widths=[200, 120, 120, 300, 240, 220, 240, 150], rows=rows)
    rows = []
    seen = set()
    for key, wl in model['wall_lines'].items():
        st = wl['stories'].get(1) or {}
        if not st.get('rod') or wl['analysis_line'] in seen:
            continue
        seen.add(wl['analysis_line'])
        rid = st['rod']['record']; h = _rec(records, rid)
        ch = _rec(records, st['chord']['record'])
        rows.append(dict(record=rid, cells=[wl['analysis_line'].split(':')[1], '%s in. dia. %s' % (frac_dia(st['rod']['d_in']), _spec(pd, st['rod']['material'])), num(h.get('T_design_kip'), 1),
                                          num(h.get('capacity'), 1), num(h.get('DC'), 2), '%d x %s' % (st['chord']['n'], st['chord']['section']), num(ch.get('P_design_kip'), 1), num(ch.get('capacity'), 1), num(ch.get('DC'), 2)]))
    out['holddowns'] = dict(title='Tie-down rod and chord stud schedule', headers=['Wall line', 'Tie-down rod (each end of every segment)', 'T design (kip)', 'phi Rn (kip)', 'D/C', 'Chord studs', 'P design (kip)', 'phi Pn (kip)', 'D/C'],
                            widths=[150, 600, 190, 180, 120, 300, 200, 190, 120], rows=rows)
    rows = []; seen = set()
    for key, wl in model['wall_lines'].items():
        st = wl['stories'].get(1) or {}
        if not st.get('anchor') or wl['analysis_line'] in seen:
            continue
        seen.add(wl['analysis_line'])
        rid = st['anchor']['record']; a = _rec(records, rid)
        rows.append(dict(record=rid, cells=[wl['analysis_line'].split(':')[1], '%s in. dia. %s at %s in. o.c.' % (frac_dia(st['anchor']['d_in']), _spec(pd, st['anchor']['material']), num(st['anchor']['spacing_in'], 0)),
                                          num(a.get('v_design_plf'), 0), num(a.get('v_capacity_plf'), 0), num(a.get('T_design_kip'), 1), num(a.get('DC'), 2)]))
    out['anchorage'] = dict(title='Base anchorage schedule (wall segments, storey 1)', headers=['Wall line', 'Bottom-track anchors', 'v design (lb/ft)', 'phi v (lb/ft)', 'Rod T design (kip)', 'D/C'],
                            widths=[150, 760, 240, 220, 260, 130], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'studs':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('section') or '-', d.get('bracing_assumption') or '-', num(d.get('P_design_kip'), 1) if d.get('P_design_kip') is not None else '-', num(d.get('DC'), 2)]))
    out['studs'] = dict(title='Stud and chord schedule', headers=['Record', 'Section and spacing', 'Bracing basis', 'P design (kip)', 'D/C'], widths=[220, 760, 860, 190, 110], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] in ('framing', 'gravity_framing'):
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('member') or '-', d.get('section') or '-', num(d.get('span_ft'), 1), d.get('limit_state') or '-', num(d.get('DC'), 2)]))
    out['framing'] = dict(title='Floor and roof framing schedule', headers=['Record', 'Member', 'Section', 'Span (ft)', 'Governing limit state', 'D/C'], widths=[220, 420, 760, 140, 480, 110], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'collectors':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('line'), d.get('selection') or '-', num(d.get('F_design_kip'), 1), num(d.get('capacity'), 1), num(d.get('DC'), 2)]))
    out['collectors'] = dict(title='Collector schedule', headers=['Wall line', 'Collector', 'F design (kip)', 'Capacity (kip)', 'D/C'], widths=[150, 1250, 220, 220, 110], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'diaphragms':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('selection') or '-', num(d.get('Fpx_kip'), 1), num(d.get('v_design_plf'), 0), num(d.get('capacity'), 0), num(d.get('DC'), 2)]))
    out['diaphragms'] = dict(title='Diaphragm schedule', headers=['Record', 'Sheathing and fastening', 'Fpx (kip)', 'v design (lb/ft)', 'phi vn (lb/ft)', 'D/C'], widths=[240, 1120, 160, 220, 220, 110], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'connections':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('type') or '-', d.get('components') or '-', num(d.get('demand'), 2), num(d.get('capacity'), 2), num(d.get('DC'), 2)]))
    out['connections'] = dict(title='Connection schedule', headers=['Record', 'Connection', 'Components', 'Demand', 'Capacity', 'D/C'], widths=[270, 470, 980, 140, 140, 110], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'materials':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('item') or '-', d.get('spec') or '-', d.get('strength') or '-', d.get('used') or '-']))
    out['materials'] = dict(title='Materials', headers=['Item', 'Specification', 'Strength', 'Used for'], widths=[470, 560, 560, 560], rows=rows)
    return out


def _spec(pd, mid):
    return (pd.get('materials', {}).get(mid) or {}).get('specification') or mid


def frac_in(t):
    table = {0.4375: '7/16 in.', 0.46875: '15/32 in.', 0.375: '3/8 in.', 0.5: '1/2 in.', 0.625: '5/8 in.', 0.75: '3/4 in.', 0.59375: '19/32 in.', 0.71875: '23/32 in.'}
    return table.get(round(float(t), 5), '%.4g in.' % t)


def frac_dia(d):
    whole = int(d); f = round(d - whole, 4)
    names = {0.0: '', 0.125: '1/8', 0.25: '1/4', 0.375: '3/8', 0.5: '1/2', 0.625: '5/8', 0.75: '3/4', 0.875: '7/8'}
    s = names.get(f, '%g' % f)
    return ('%d-%s' % (whole, s)) if whole and s else (str(whole) if whole else s)


# ------------------------------------------------------------------------------------------
# sheet canvas
# ------------------------------------------------------------------------------------------

class Sheets(object):
    def __init__(self, package, state, dest):
        from reportlab.pdfgen.canvas import Canvas
        self.c = Canvas(str(Path(dest) / 'drawings.pdf'), pagesize=(W, H), pageCompression=1, invariant=1)
        self.c.setTitle(ascii_text(package['building_id']) + ' - cold-formed steel structural drawings')
        self.c.setAuthor('Steltic openBIM')
        self.p, self.s = package, state
        self.page = 0
        self.rows, self.dimensions, self.cells = [], [], []
        self.total = None

    def text(self, x, y, t, size=10, color=INK, font='Helvetica', anchor='start'):
        t = ascii_text(t)
        self.c.setFillColor(color); self.c.setFont(font, size)
        if anchor == 'middle':
            self.c.drawCentredString(x, y, t)
        elif anchor == 'end':
            self.c.drawRightString(x, y, t)
        else:
            self.c.drawString(x, y, t)

    def line(self, a, b, color=INK, width=0.6, dash=None):
        self.c.setStrokeColor(color); self.c.setLineWidth(width); self.c.setDash(dash or [])
        self.c.line(a[0], a[1], b[0], b[1])
        self.c.setDash([])

    def poly(self, pts, color=INK, width=0.6, fill=None, dash=None):
        self.c.setStrokeColor(color); self.c.setLineWidth(width); self.c.setDash(dash or [])
        p = self.c.beginPath(); p.moveTo(*pts[0])
        for q in pts[1:]:
            p.lineTo(*q)
        p.close()
        if fill:
            self.c.setFillColor(fill)
        self.c.drawPath(p, stroke=1, fill=1 if fill else 0)
        self.c.setDash([])

    def lines(self, t, width, size=10, font='Helvetica'):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        out, cur = [], ''
        for word in ascii_text(t).split():
            while stringWidth(word, font, size) > width and len(word) > 1:      # break an over-long token
                cut = len(word)
                while cut > 1 and stringWidth(word[:cut], font, size) > width:
                    cut -= 1
                if cur:
                    out.append(cur); cur = ''
                out.append(word[:cut]); word = word[cut:]
            trial = (cur + ' ' + word).strip()
            if cur and stringWidth(trial, font, size) > width:
                out.append(cur); cur = word
            else:
                cur = trial
        if cur:
            out.append(cur)
        return out or ['']

    def wrap(self, x, y, t, width, size=10, leading=None, color=INK, font='Helvetica'):
        leading = leading or size * 1.35
        for ln in self.lines(t, width, size, font):
            self.text(x, y, ln, size, color, font); y -= leading
        return y

    def close(self):
        """Print the scale of the sheet being finished (known only after its views are laid out)."""
        if self.page:
            self.text(W - 605, MARGIN + 12, 'Scale ' + self.rows[-1]['scale'] + (' at A1' if self.rows[-1]['scale'] != 'NTS' else ''), 10, GREY)

    def start(self, number, title, scale='NTS'):
        if self.page:
            self.close(); self.c.showPage()
        self.page += 1; self.number = number
        self.rows.append(dict(number=number, title=title, page=self.page, scale=scale))
        c = self.c
        c.setStrokeColor(INK); c.setLineWidth(1.4); c.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN)
        c.setLineWidth(0.9); c.line(MARGIN, MARGIN + TITLE_H, W - MARGIN, MARGIN + TITLE_H)
        for x in (W - 1160, W - 620, W - 250):
            c.line(x, MARGIN, x, MARGIN + TITLE_H)
        self.text(MARGIN + 18, MARGIN + 68, 'STELTIC / OPENBIM', 15, font='Helvetica-Bold')
        self.text(MARGIN + 18, MARGIN + 44, 'Cold-formed steel structural design drawings', 12)
        self.text(MARGIN + 18, MARGIN + 20, 'DESIGN COORDINATION ISSUE - NOT FOR CONSTRUCTION. To be checked and sealed by a licensed engineer.', 11, ACCENT, 'Helvetica-Bold')
        self.text(W - 1145, MARGIN + 74, 'PROJECT', 9, GREY)
        self.text(W - 1145, MARGIN + 46, self.p['building_id'], 20, font='Helvetica-Bold')
        self.text(W - 1145, MARGIN + 20, 'Revision %s | source %s' % (self.s['revision'], self.s['source_model_sha256'][:16]), 10, GREY)
        self.text(W - 605, MARGIN + 74, 'SHEET TITLE', 9, GREY)
        y = MARGIN + 50
        for ln in self.lines(title, 340, 14, 'Helvetica-Bold')[:2]:
            self.text(W - 605, y, ln, 14, font='Helvetica-Bold'); y -= 19
        self.text(W - 235, MARGIN + 74, 'SHEET', 9, GREY)
        self.text(W - 235, MARGIN + 36, number, 32, font='Helvetica-Bold')
        self.text(W - 235, MARGIN + 12, 'Page %d' % self.page, 10, GREY)

    # ---- views ----
    def view(self, box, bounds, title=None):
        """box = (x, y, w, h) on paper; bounds = ((a0, a1), (b0, b1)) in model inches. Returns (transform, scale denominator)."""
        x, y, w, h = box
        da, db = max(1.0, bounds[0][1] - bounds[0][0]), max(1.0, bounds[1][1] - bounds[1][0])
        need = max(da * 72.0 / w, db * 72.0 / h)
        den = next((s for s in SCALES if s >= need), math.ceil(need / 100.0) * 100)
        k = 72.0 / den
        ox = x + (w - da * k) / 2.0; oy = y + (h - db * k) / 2.0

        def tr(a, b):
            return (ox + (a - bounds[0][0]) * k, oy + (b - bounds[1][0]) * k)
        if title:
            self.text(x, y + h + 14, title + '   (1:%d)' % den, 12, font='Helvetica-Bold')
        return tr, den

    def dim(self, a, b, value_in, offset=(0, -18), label=None, kind='dimension', size=9):
        """Dimension between paper points a and b (already transformed); value_in is the model distance."""
        ox, oy = offset
        p, q = (a[0] + ox, a[1] + oy), (b[0] + ox, b[1] + oy)
        self.line(a, p, GREY, 0.3); self.line(b, q, GREY, 0.3)
        self.line(p, q, GREY, 0.5)
        for e in (p, q):
            self.line((e[0] - 3, e[1] - 3), (e[0] + 3, e[1] + 3), INK, 0.8)
        label = label or feet(value_in)
        mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
        if abs(p[0] - q[0]) >= abs(p[1] - q[1]):
            self.text(mx, my + 3, label, size, anchor='middle')
        else:
            self.c.saveState(); self.c.translate(mx - 3, my); self.c.rotate(90); self.text(0, 0, label, size, anchor='middle'); self.c.restoreState()
        self.dimensions.append(dict(sheet=self.number, kind=kind, value_in=round(float(value_in), 4), label=label))

    def bubble(self, x, y, label, r=15):
        self.c.setStrokeColor(INK); self.c.setLineWidth(0.8); self.c.setFillColor('#ffffff'); self.c.circle(x, y, r, stroke=1, fill=1)
        self.text(x, y - 4, label, 10 if len(label) < 4 else 8, font='Helvetica-Bold', anchor='middle')

    def table(self, number, sched, key):
        """Paginated schedule (continuation sheets take a letter suffix); every printed cell is registered for the read-back."""
        headers, widths, rows = sched['headers'], sched['widths'], sched['rows']
        scale = (W - 2 * MARGIN - 60) / float(sum(widths))
        widths = [w * scale for w in widths]
        page = 0; y = 0
        for ri, row in enumerate(rows or [dict(record=None, cells=['-'] * len(headers))]):
            cells = [self.lines(c, w - 14, 11) for c, w in zip(row['cells'], widths)]
            hgt = max(len(c) for c in cells) * 14.5 + 10
            if page == 0 or y - hgt < MARGIN + TITLE_H + 20:
                page += 1
                self.start(number if page == 1 else number + chr(96 + page), sched['title'] + (' (continued, %d)' % page if page > 1 else ''))
                y = H - MARGIN - 50; x = MARGIN + 30
                for hd, w in zip(headers, widths):
                    self.text(x, y, hd, 11.5, font='Helvetica-Bold'); x += w
                y -= 12; self.line((MARGIN + 26, y), (W - MARGIN - 26, y), INK, 0.9); y -= 18
            x = MARGIN + 30
            for c, w in zip(cells, widths):
                for i, ln in enumerate(c):
                    self.text(x, y - i * 14.5, ln, 11)
                x += w
            self.cells.append(dict(sheet=self.number, schedule=key, record=row.get('record'), cells=[ascii_text(c) for c in row['cells']]))
            y -= hgt; self.line((MARGIN + 26, y + 8), (W - MARGIN - 26, y + 8), LIGHT, 0.4)
        return page


# ------------------------------------------------------------------------------------------
# sheets
# ------------------------------------------------------------------------------------------

def draw_cover(sh, package, model, register):
    ctx = package.get('design_context', {})
    sh.start('G-001', 'General notes, design basis and drawing list')
    x, y = MARGIN + 40, H - MARGIN - 60
    sh.text(x, y, package['building_id'], 34, font='Helvetica-Bold'); y -= 34
    sh.text(x, y, 'Cold-formed steel structure: structural design drawings generated from the completed Steltic CFS design', 15, GREY); y -= 44
    sh.text(x, y, 'DESIGN BASIS', 14, font='Helvetica-Bold'); y -= 24
    elf = ctx.get('elf') or {}
    wb = ctx.get('wind_basis') or {}
    basis = [('Design standards', ctx.get('code')), ('Seismic force-resisting system', str(ctx.get('system') or '').replace('_', ' ')),
             ('Seismic weight W / base shear V', '%s kip / %s kip (Cs = %s)' % (num(elf.get('W_kip'), 1), num(elf.get('V_kip'), 1), num(elf.get('Cs'), 4)) if elf else None),
             ('Redundancy factor', num(ctx.get('rho'), 2) if ctx.get('rho') is not None else None),
             ('Basic wind speed / exposure', '%s mph / %s (qh = %s psf)' % (num(wb.get('V_mph'), 0), wb.get('exposure'), num(wb.get('qh_psf'), 2)) if wb else None),
             ('Designed by', '%(model)s (%(provider)s) with %(harness)s, %(date)s' % ctx['design_agent'] if isinstance(ctx.get('design_agent'), dict) else None)]
    for k, v in basis:
        if v:
            sh.text(x, y, k, 11.5, GREY); y2 = sh.wrap(x + 330, y, v, 760, 11.5); y = min(y - 19, y2 - 4)
    sh.cells.append(dict(sheet='G-001', schedule='design_basis', record=None, cells=[ascii_text(v) for k, v in basis if v]))
    y -= 18
    sh.text(x, y, 'GENERAL NOTES', 14, font='Helvetica-Bold'); y -= 24
    notes = ['These drawings are produced directly from the physical model and calculation records of the completed design; every schedule value is the value printed in the design report for the same record.',
             'Dimensions are to wall-line worklines (wall studs are centred on the line) and floor datums. Member lengths are design worklines, not shop cut lengths. Do not scale.',
             'Cold-formed steel members are designated per SFIA (e.g. 600S162-54: 6 in. web, 1-5/8 in. flange, 54 mil). Material grades are given in the materials schedule.',
             'Shear wall types (SW marks) give the sheathing, the number of sheathed faces, and the screw schedule; the wall elevations show where each type applies.',
             'Tie-down rods are continuous from the foundation to the top storey shown, with a coupler, bearing plate and take-up device at each floor.',
             'Foundations, concrete anchorage and items marked as delegated are by others for the demands tabulated in the schedules.',
             'Design coordination issue: not for construction or fabrication. All design output must be independently checked and sealed by a licensed professional engineer.']
    for i, t in enumerate(notes, 1):
        sh.text(x, y, '%d.' % i, 11.5); y = sh.wrap(x + 26, y, t, 1060, 11.5) - 5
    x2 = W / 2.0 + 80; y = H - MARGIN - 60
    sh.text(x2, y, 'DRAWING LIST', 14, font='Helvetica-Bold'); y -= 26
    col = 0
    for number, title in register:
        if y < MARGIN + TITLE_H + 30:
            col += 1; y = H - MARGIN - 86
        sh.text(x2 + col * 520, y, number, 11, font='Helvetica-Bold'); sh.text(x2 + col * 520 + 78, y, title[:74], 11); y -= 16.5


def plan_bounds(model):
    xs, ys = [], []
    for wl in model['wall_lines'].values():
        if wl['direction'] == 'X':
            xs += [wl['start_in'], wl['start_in'] + wl['length_in']]; ys.append(wl['pos_in'])
        else:
            ys += [wl['start_in'], wl['start_in'] + wl['length_in']]; xs.append(wl['pos_in'])
    return (min(xs), max(xs)), (min(ys), max(ys))


def draw_plan(sh, package, model, number, title, storey, floor=None):
    pd = package['design_context']['physical_design']
    bx, by = plan_bounds(model)
    box = (MARGIN + 190, MARGIN + TITLE_H + 150, W - 2 * MARGIN - 820, H - 2 * MARGIN - TITLE_H - 300)
    tr, den = sh.view(box, (bx, by))
    sh.rows[-1]['scale'] = '1:%d' % den
    # joists first (light)
    if floor:
        for j in floor['joists']:
            a, b = j['axis']; sh.line(tr(a[0], a[1]), tr(b[0], b[1]), LIGHT, 0.25)
        labelled = set()
        biggest = {}
        for zn in floor['zones']:                   # one label per distinct joist selection, on its largest zone
            lb = '%s at %s in. o.c.' % (zn['joist'].get('section') or zn['joist']['designation'], num(zn['joist']['spacing_in'], 0))
            ar = (zn['x_ft'][1] - zn['x_ft'][0]) * (zn['y_ft'][1] - zn['y_ft'][0])
            if ar > biggest.get(lb, (0, None))[0]:
                biggest[lb] = (ar, zn['id'])
        for zn in floor['zones']:
            cx, cy = sum(zn['x_ft']) * 6.0, sum(zn['y_ft']) * 6.0
            p = tr(cx, cy)
            lbl = '%s at %s in. o.c.' % (zn['joist'].get('section') or zn['joist']['designation'], num(zn['joist']['spacing_in'], 0))
            half = 0.32 * (zn['y_ft'][1] - zn['y_ft'][0] if zn['span'] == 'Y' else zn['x_ft'][1] - zn['x_ft'][0]) * 12.0
            a = tr(cx, cy - half) if zn['span'] == 'Y' else tr(cx - half, cy); b = tr(cx, cy + half) if zn['span'] == 'Y' else tr(cx + half, cy)
            sh.line(a, b, BLUE, 1.0)
            for e, o in ((a, b), (b, a)):
                ang = math.atan2(o[1] - e[1], o[0] - e[0])
                for da in (0.45, -0.45):
                    sh.line(e, (e[0] + 9 * math.cos(ang + da), e[1] + 9 * math.sin(ang + da)), BLUE, 1.0)
            if biggest[lbl][1] != zn['id']:
                continue
            sh.c.setFillColor('#ffffff'); sh.c.rect(p[0] + 8, p[1] - 6, 6.2 * len(lbl) + 8, 15, stroke=0, fill=1)
            sh.text(p[0] + 12, p[1] - 2, lbl, 10.5, BLUE, 'Helvetica-Bold')
            sh.cells.append(dict(sheet=number, schedule='joist_zone', record=None, cells=[lbl]))
    lines_x = sorted([w for w in model['wall_lines'].values() if w['direction'] == 'X'], key=lambda w: w['pos_in'])
    lines_y = sorted([w for w in model['wall_lines'].values() if w['direction'] == 'Y'], key=lambda w: w['pos_in'])
    for wl in model['wall_lines'].values():
        if storey not in wl['stories']:
            continue
        s0, L, pos = wl['start_in'], wl['length_in'], wl['pos_in']
        P = (lambda s: tr(s0 + s, pos)) if wl['direction'] == 'X' else (lambda s: tr(pos, s0 + s))
        sh.line(P(0), P(L), INK, 1.5)
        for pn in wl['panels']:
            if pn['storey'] == storey and pn.get('face') == '+':
                a, b = P(pn['s0']), P(pn['s1'])
                wdt = 4.2
                if wl['direction'] == 'X':
                    sh.poly([(a[0], a[1] - wdt), (b[0], b[1] - wdt), (b[0], b[1] + wdt), (a[0], a[1] + wdt)], ACCENT, 0.6, fill=ACCENT)
                    sh.text((a[0] + b[0]) / 2.0, a[1] + 8, pn['type'], 8.5, ACCENT, 'Helvetica-Bold', 'middle')
                else:
                    sh.poly([(a[0] - wdt, a[1]), (b[0] - wdt, b[1]), (b[0] + wdt, b[1]), (a[0] + wdt, a[1])], ACCENT, 0.6, fill=ACCENT)
                    sh.text(a[0] + 8, (a[1] + b[1]) / 2.0 - 3, pn['type'], 8.5, ACCENT, 'Helvetica-Bold')
        for m in wl['members']:
            if m['kind'] == 'tie_rod' and m['storey'] == storey:
                p = P(m['s0']); sh.c.setStrokeColor(INK); sh.c.setFillColor('#ffffff'); sh.c.setLineWidth(0.7); sh.c.circle(p[0], p[1], 2.6, stroke=1, fill=1)
        for o in wl['openings']:
            if o['storey'] == storey:
                a, b = P(o['s0']), P(o['s1'])
                sh.line(a, b, '#ffffff', 2.4); sh.line(a, b, BLUE, 0.8, [3, 2])
    # chain dimensions, then grid bubbles on top
    ys = sorted({w['pos_in'] for w in lines_x if w['grid']}); xs = sorted({w['pos_in'] for w in lines_y if w['grid']})
    for a, b in zip(ys, ys[1:]):
        sh.dim(tr(bx[0], a), tr(bx[0], b), b - a, offset=(-125, 0), kind='wall_line_spacing')
    if len(ys) > 1:
        sh.dim(tr(bx[0], ys[0]), tr(bx[0], ys[-1]), ys[-1] - ys[0], offset=(-158, 0), kind='overall')
    for a, b in zip(xs, xs[1:]):
        sh.dim(tr(a, by[1]), tr(b, by[1]), b - a, offset=(0, 125), kind='wall_line_spacing')
    if len(xs) > 1:
        sh.dim(tr(xs[0], by[1]), tr(xs[-1], by[1]), xs[-1] - xs[0], offset=(0, 158), kind='overall')
    for wl in lines_x:
        if wl['grid']:
            p = tr(bx[0], wl['pos_in']); sh.bubble(p[0] - 70, p[1], wl['label'].split('/')[0])
    for wl in lines_y:
        if wl['grid']:
            p = tr(wl['pos_in'], by[1]); sh.bubble(p[0], p[1] + 70, wl['label'].split('/')[0])
    # legend / notes
    x = W - MARGIN - 590; y = H - MARGIN - 60
    sh.text(x, y, 'LEGEND', 13, font='Helvetica-Bold'); y -= 26
    sh.line((x, y + 4), (x + 60, y + 4), INK, 1.5); sh.text(x + 76, y, 'Stud wall on its wall line (storey %d)' % storey, 11); y -= 22
    sh.poly([(x, y), (x + 60, y), (x + 60, y + 8), (x, y + 8)], ACCENT, 0.6, fill=ACCENT); sh.text(x + 76, y, ('Sheathed shear-wall segment and type' if model['wall_types'] else 'Strap-braced bay and type') if not (model['wall_types'] and model['strap_types']) else 'Shear-wall segment or strap-braced bay and type', 11); y -= 22
    sh.c.setStrokeColor(INK); sh.c.setFillColor('#ffffff'); sh.c.circle(x + 30, y + 4, 2.6, stroke=1, fill=1); sh.text(x + 76, y, 'Tie-down rod', 11); y -= 22
    sh.line((x, y + 4), (x + 60, y + 4), BLUE, 0.8, [3, 2]); sh.text(x + 76, y, 'Wall opening (header over)', 11); y -= 22
    if floor:
        sh.line((x, y + 4), (x + 60, y + 4), LIGHT, 0.6); sh.text(x + 76, y, 'Joist (every joist drawn); arrow = span direction', 11); y -= 22
    y -= 14
    sh.text(x, y, 'SHEAR WALL TYPES' if model['wall_types'] else 'BRACED BAY TYPES', 13, font='Helvetica-Bold'); y -= 24
    for t in model['strap_types']:
        y = sh.wrap(x, y, '%s: %s in. x %s in. strap, %s; %d %s screws each strap end' % (t['mark'], num(t['width_in'], 0), num(t['t_in'], 4), 'both faces' if t['faces'] == 2 else 'one face',
                                                                                         t['n_strap'], t['screw']), 560, 10.5) - 5
    for t in model['wall_types']:
        y = sh.wrap(x, y, '%s: %s, %s; %s at %s in. edges / %s in. field; studs %s' % (t['mark'], _spec(pd, t['sheathing_material']), 'both faces' if t['faces'] == 2 else 'one face',
                                                                                         t['screw'], num(t['edge_in'], 0), num(t['field_in'], 0), t['stud']), 560, 10.5) - 5
    y -= 10
    sh.text(x, y, 'NOTES', 13, font='Helvetica-Bold'); y -= 24
    lv = {l['level']: l for l in model['levels']}
    notes = ['Walls shown are the storey %d walls, standing on %s (elevation %s).' % (storey, lv[storey - 1]['name'], feet(lv[storey - 1]['elevation_in'])),
             'See the wall elevations (S-2xx) for stud, chord and opening set-out, and the schedules (S-3xx) for sections and capacities.']
    if floor:
        notes.insert(1, '%s framing at %s (elevation %s): %s sheathing (%s) on the joists shown.' % ('Roof' if floor['kind'] == 'roof' else 'Floor', lv[floor['level']]['name'], feet(lv[floor['level']]['elevation_in']),
                                                                                              frac_in(floor['sheathing']['thickness_in']), _spec(pd, floor['sheathing']['material'])))
    for t in notes:
        y = sh.wrap(x, y, t, 560, 10.5) - 5


def draw_elevation(sh, package, model, wl, number):
    L = wl['length_in']
    zs = [l['elevation_in'] for l in model['levels']]
    box = (MARGIN + 200, MARGIN + TITLE_H + 190, W - 2 * MARGIN - 420, H - 2 * MARGIN - TITLE_H - 330)
    tr, den = sh.view(box, ((0.0, L), (zs[0], zs[-1])))
    sh.rows[-1]['scale'] = '1:%d' % den
    for l in model['levels']:
        a, b = tr(0, l['elevation_in']), tr(L, l['elevation_in'])
        sh.line((a[0] - 150, a[1]), (b[0] + 40, b[1]), GREY, 0.4, [10, 4])
        sh.text(a[0] - 150, a[1] + 5, '%s  %s' % (l['name'], feet(l['elevation_in'])), 10.5, font='Helvetica-Bold')
    for a, b in zip(model['levels'], model['levels'][1:]):
        sh.dim(tr(L, a['elevation_in']), tr(L, b['elevation_in']), b['elevation_in'] - a['elevation_in'], offset=(70, 0), kind='storey_height')
    faces = defaultdict(set)
    for pn in wl['panels']:
        faces[(pn['storey'], round(pn['s0'], 3))].add(pn.get('face'))
    for pn in wl['panels']:
        if pn.get('face') != '+':
            continue
        q = [tr(pn['s0'], pn['z0']), tr(pn['s1'], pn['z0']), tr(pn['s1'], pn['z1']), tr(pn['s0'], pn['z1'])]
        if pn.get('strap'):
            for x0, z0, x1, z1 in pn['diagonals']:
                sh.line(tr(x0, z0), tr(x1, z1), ACCENT, 1.6)
        else:
            sh.poly(q, ACCENT, 0.9, fill=FILL)
        cx, cy = (q[0][0] + q[1][0]) / 2.0, (q[0][1] + q[2][1]) / 2.0 + (14 if pn.get('strap') else 0)
        sh.c.setFillColor('#ffffff'); sh.c.rect(cx - 24, cy - 8, 48, 18, stroke=0, fill=1)
        sh.text(cx, cy - 3, pn['type'], 11.5, ACCENT, 'Helvetica-Bold', 'middle')
    counts = Counter()
    for m in wl['members']:
        if m['kind'] == 'stud':
            heavy = m['role'] in ('chord stud', 'jamb stud')
            sh.line(tr(m['s0'], m['z0']), tr(m['s1'], m['z1']), INK, 0.9 if heavy else 0.3)
            counts[(m['storey'], m['role'], m['profile'])] += 1
        elif m['kind'] in ('bottom_track', 'top_track'):
            sh.line(tr(m['s0'], m['z0']), tr(m['s1'], m['z1']), INK, 1.1)
        elif m['kind'] == 'header':
            sh.line(tr(m['s0'], m['z0']), tr(m['s1'], m['z1']), BLUE, 2.2)
        elif m['kind'] == 'tie_rod':
            sh.line(tr(m['s0'], m['z0']), tr(m['s1'], m['z1']), ACCENT, 1.1, [5, 3])
    for o in wl['openings']:
        q = [tr(o['s0'], o['z0']), tr(o['s1'], o['z0']), tr(o['s1'], o['z1']), tr(o['s0'], o['z1'])]
        sh.poly(q, BLUE, 0.7); sh.line(q[0], q[2], BLUE, 0.3); sh.line(q[1], q[3], BLUE, 0.3)
    # set-out of the sheathed segments along the base (storey 1 or lowest storey with segments)
    base = sorted({(round(pn['s0'], 4), round(pn['s1'], 4)) for pn in wl['panels'] if pn['storey'] == min([p['storey'] for p in wl['panels']] or [1])})
    cuts = sorted({0.0, L} | {v for ab in base for v in ab})
    for a, b in zip(cuts, cuts[1:]):
        if b - a > 0.5:
            sh.dim(tr(a, zs[0]), tr(b, zs[0]), b - a, offset=(0, -42), kind='segment_setout', size=8.5)
    sh.dim(tr(0, zs[0]), tr(L, zs[0]), L, offset=(0, -78), kind='wall_length')
    ops = sorted({(round(o['s0'], 4), round(o['s1'], 4)) for o in wl['openings']})
    if ops:
        oc = sorted({0.0, L} | {v for ab in ops for v in ab})
        for a, b in zip(oc, oc[1:]):
            if b - a > 0.5:
                sh.dim(tr(a, zs[-1]), tr(b, zs[-1]), b - a, offset=(0, 36), kind='opening_setout', size=8.5)
    # framing table for this line
    x = MARGIN + 60; y = MARGIN + TITLE_H + 92
    sh.text(x, y, 'FRAMING ON THIS LINE (count by storey)', 11.5, font='Helvetica-Bold'); y -= 17
    col = 0
    for (k, role, prof), n in sorted(counts.items()):
        txt = 'Storey %d: %d x %s (%s)' % (k, n, prof, role)
        sh.text(x + col * 430, y, txt, 10); col += 1
        sh.cells.append(dict(sheet=number, schedule='elevation_counts', record=None, text=txt, cells=[wl['key'], str(k), role, prof, str(n)]))
        if col == 5:
            col = 0; y -= 14
    st1 = wl['stories'].get(min(wl['stories']))
    x = W - MARGIN - 190; y = H - MARGIN - 60
    sh.text(x - 360, y, 'WALL LINE %s' % wl['label'], 15, font='Helvetica-Bold')
    info = ['%s-direction line at %s = %s' % (wl['direction'], 'y' if wl['direction'] == 'X' else 'x', feet(wl['pos_in'])), 'Track: %s' % st1['track']['section']]
    if st1.get('rod'):
        info.append('Tie-down rods (dashed): %s in. dia.' % frac_dia(st1['rod']['d_in']))
    if st1.get('chord'):
        info.append('Chord pack each segment end: %d x %s' % (st1['chord']['n'], st1['chord']['section']))
    yy = y - 20
    for t in info:
        sh.text(x - 360, yy, t, 10.5); yy -= 15


def draw_detail(sh, package, model, det, number):
    ph = package['physical']; templates = bim_assemblies.index(ph)
    conn = next((c for c in ph['connections'] if c['id'] == det['representative']), None)
    sh.start(number, 'Typical detail %s: %s' % (det['reference'], det['family']))
    records = record_index(package)
    x = W - MARGIN - 700; y = H - MARGIN - 60
    sh.text(x, y, det['family'].upper(), 15, font='Helvetica-Bold'); y -= 28
    info = ['%d located occurrences in the model (%d distinct local arrangements).' % (det['occurrences'], det['templates'])]
    if det['delegated']:
        info.append('%d occurrences are delegated interfaces: no hardware is modelled for them.' % det['delegated'])
    if det['part_counts']:
        info.append('Located parts in all occurrences: ' + ', '.join('%d %s' % (n, k.replace('_', ' ')) for k, n in det['part_counts'].items()) + '.')
    for t in info:
        y = sh.wrap(x, y, t, 660, 11.5) - 5
    sh.cells.append(dict(sheet=number, schedule='detail', record=None, cells=[det['reference'], det['family'], str(det['occurrences'])] + ['%d %s' % (n, k.replace('_', ' ')) for k, n in det['part_counts'].items()]))
    y -= 10
    shown = det['records'][:3]
    for rid in shown:
        d = _rec(records, rid)
        sh.text(x, y, rid, 11, BLUE, 'Helvetica-Bold'); y -= 16
        for key in ('type', 'components', 'selection', 'sheathing', 'fastener_schedule', 'design_basis', 'limit_state'):
            if d.get(key):
                y = sh.wrap(x, y, '%s: %s' % (key.replace('_', ' ').capitalize(), d[key]), 660, 10.5) - 3
        if d.get('DC') is not None:
            sh.text(x, y, 'Demand / capacity: %s' % num(d.get('DC'), 2), 10.5); y -= 15
        y -= 8
    if len(det['records']) > len(shown):
        y = sh.wrap(x, y, 'and %d further design records of the same family; every occurrence carries its own record (see the schedules).' % (len(det['records']) - len(shown)), 660, 10.5, color=GREY)
    if conn is None or not conn.get('assembly_instance'):
        sh.wrap(MARGIN + 80, H - 300, 'Delegated interface: geometry and anchorage by the responsible party named in the design; demands are in the anchorage schedule.', 1300, 16, color=ACCENT)
        return
    frame = conn['assembly_instance']
    tpl = templates[frame['template_id']]
    parts = tpl['parts']

    def corners(g):
        if g['type'] == 'cylinder':
            return [g['origin'], [g['origin'][i] + g['axis'][i] * g['length'] for i in range(3)]]
        z = bim_assemblies.cross(g['x_axis'], g['y_axis'])
        return [[g['origin'][m] + i * g['size'][0] * g['x_axis'][m] + j * g['size'][1] * g['y_axis'][m] + k * g['size'][2] * z[m] for m in range(3)]
                for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    pts = [q for p in parts for q in corners(p['geometry'])]
    lo = [min(p[i] for p in pts) for i in range(3)]; hi = [max(p[i] for p in pts) for i in range(3)]
    cropped = hi[0] - lo[0] > 144.0
    if cropped:                                          # long runs: show the first 4 ft of the run
        hi[0] = lo[0] + 48.0
        parts = [p for p in parts if all(lo[0] - 0.01 <= q[0] <= hi[0] + 0.01 for q in corners(p['geometry']))]
    # context: the members this assembly is bound to, and the member ends it serves, in the local frame
    xa, ya = frame['x_axis'], frame['y_axis']; za = bim_assemblies.cross(xa, ya)

    def local(p):
        v = [p[i] - frame['origin'][i] for i in range(3)]
        return [sum(v[i] * a[i] for i in range(3)) for a in (xa, ya, za)]
    members = {m['id']: m for m in ph['members']}
    profiles = {p['id']: p for p in ph['profiles']}
    served = set(v for v in frame.get('bindings', {}).values() if v in members)
    joints = {j['id']: j for j in ph['joints']}
    for d_ in ph.get('joint_dispositions', []):
        if conn['id'] in d_.get('connection_ids', []):
            for e in joints.get(d_['joint_id'], {}).get('member_ends', []):
                served.add(e['member_id'])
    pad3 = [6.0, 4.0, 6.0]
    context = []
    for mid in served:
        m = members[mid]
        a, b = local(m['axis'][0]), local(m['axis'][1])
        d = profiles[m['profile_id']]['dimensions']
        half = max(d.get('d', 0.0), d.get('b', 0.0)) / 2.0 if 'b' in d else d.get('d', 1.0) / 2.0
        if all(min(a[i], b[i]) - half <= hi[i] + pad3[i] and max(a[i], b[i]) + half >= lo[i] - pad3[i] for i in range(3)):
            context.append((m, a, b, d))
        if len(context) >= 60:
            break
    views = [('ELEVATION (local x-z)', (0, 2), (MARGIN + 70, MARGIN + TITLE_H + 560, 1480, 780)),
             ('PLAN (local x-y)', (0, 1), (MARGIN + 70, MARGIN + TITLE_H + 60, 900, 420)),
             ('SECTION (local y-z)', (1, 2), (MARGIN + 1050, MARGIN + TITLE_H + 60, 500, 420))]
    for title, (i, j), bx in views:
        pad = 0.08 * max(hi[i] - lo[i], hi[j] - lo[j], 4.0) + 1.0
        tr, den = sh.view(bx, ((lo[i] - pad, hi[i] + pad), (lo[j] - pad, hi[j] + pad)), title)
        sh.c.saveState(); cp = sh.c.beginPath(); cp.rect(bx[0], bx[1], bx[2], bx[3]); sh.c.clipPath(cp, stroke=0)
        for m, a, b, d in context:
            # member envelope: the profile's depth / flange extents about its workline, as seen in this view
            ly = m['local_y']; lyl = [sum(ly[q] * ax[q] for q in range(3)) for ax in (xa, ya, za)]
            ux = [b[q] - a[q] for q in range(3)]; ln = math.sqrt(sum(v * v for v in ux)) or 1.0; ux = [v / ln for v in ux]
            lz = bim_assemblies.cross(ux, lyl)
            if 'b' in d:
                y0, y1, z0, z1 = (-d.get('t', 0.0) / 2.0, d['b'] - d.get('t', 0.0) / 2.0, -d['d'] / 2.0, d['d'] / 2.0)
            elif 'width' in d:                      # flat strap (width x thickness) or a truss envelope (width x depth)
                hz = d.get('thickness', d.get('depth', 0.0)) / 2.0
                y0, y1, z0, z1 = (-d['width'] / 2.0, d['width'] / 2.0, -hz, hz)
            else:
                y0, y1, z0, z1 = (-d['d'] / 2.0, d['d'] / 2.0, -d['d'] / 2.0, d['d'] / 2.0)
            cs = [[e[q] + yy * lyl[q] + zz * lz[q] for q in range(3)] for e in (a, b) for yy in (y0, y1) for zz in (z0, z1)]
            for q0, q1 in ((0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)):
                sh.line(tr(cs[q0][i], cs[q0][j]), tr(cs[q1][i], cs[q1][j]), GREY, 0.35)
        sh.c.restoreState()
        for p in parts:
            g = p['geometry']
            col = ACCENT if p['kind'] in ('screw', 'anchor_rod', 'bolt') else INK
            if g['type'] == 'cylinder':
                a = g['origin']; b = [a[m] + g['axis'][m] * g['length'] for m in range(3)]
                pa, pb = tr(a[i], a[j]), tr(b[i], b[j])
                rr = max(1.2, g['radius'] * 72.0 / den)
                if math.dist(pa, pb) < 1.0:
                    sh.c.setStrokeColor(col); sh.c.setLineWidth(0.6); sh.c.circle(pa[0], pa[1], rr, stroke=1, fill=0)
                else:
                    sh.line(pa, pb, col, max(0.7, 2 * rr))
            elif g['type'] == 'box':
                z = bim_assemblies.cross(g['x_axis'], g['y_axis'])
                cs = [[g['origin'][m] + a_ * g['size'][0] * g['x_axis'][m] + b_ * g['size'][1] * g['y_axis'][m] + c_ * g['size'][2] * z[m] for m in range(3)]
                      for a_ in (0, 1) for b_ in (0, 1) for c_ in (0, 1)]
                pp = [tr(c_[i], c_[j]) for c_ in cs]
                xs = [q[0] for q in pp]; ys = [q[1] for q in pp]
                sh.poly([(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))], INK, 0.7)
        if title.startswith('ELEVATION') or title.startswith('PLAN'):
            a, b = tr(lo[i], lo[j]), tr(hi[i], lo[j])
            sh.dim(a, b, hi[i] - lo[i], offset=(0, -22), kind='detail_extent', label=feet(hi[i] - lo[i]) if hi[i] - lo[i] >= 24 else '%s in.' % num(hi[i] - lo[i], 2))
    sh.wrap(MARGIN + 70, MARGIN + TITLE_H + 34, 'Basis: ' + tpl['basis'] + '.  Representative occurrence: ' + conn['id'] + ('; the first 4 ft of the run is shown' if cropped else '') + '. Grey outlines are the envelopes of the members this assembly fastens; accent marks are the located fasteners.', 1480, 10.5, color=GREY)


def generate(package, state, dest):
    if not is_native_cfs(package):
        raise ValueError('The native CFS drawing set needs a CFS package with a recorded physical design')
    dest = Path(dest); dest.mkdir(parents=True, exist_ok=True)
    model = drawing_model(package)
    # sheet register first (the cover lists it)
    plan = [('G-001', 'General notes, design basis and drawing list', None)]
    nst = max(max(w['stories']) for w in model['wall_lines'].values())
    floors = {f['level']: f for f in model['floors']}
    plan.append(('S-100', 'Foundation and storey 1 wall plan', ('plan', 1, None)))
    for k in range(1, nst + 1):
        fl = floors.get(k)
        nm = (('Roof' if fl and fl['kind'] == 'roof' else 'Level %d floor' % (k + 1)) + ' framing plan on storey %d walls' % k)
        plan.append(('S-%d' % (100 + k), nm, ('plan', k, fl)))
    for i, wl in enumerate(model['wall_lines'].values(), 1):
        plan.append(('S-%d' % (200 + i), 'Wall elevation: line %s' % wl['label'], ('elevation', wl)))
    sched_numbers = []
    n = 300
    for key, sc in model['schedules'].items():
        est = 1
        n += 1
        sched_numbers.append((key, n))
        plan.append(('S-%d' % n, sc['title'], ('schedule', key, n)))
    for i, det in enumerate(model['details'], 1):
        plan.append(('S-%d' % (400 + i), 'Typical detail %s: %s' % (det['reference'], det['family']), ('detail', det)))
    plan.append(('S-501', 'Member schedule', ('members',)))
    sh = Sheets(package, state, dest)
    draw_cover(sh, package, model, [(a, b) for a, b, _ in plan])
    for number, title, what in plan[1:]:
        if what[0] == 'plan':
            sh.start(number, title); draw_plan(sh, package, model, number, title, what[1], what[2])
        elif what[0] == 'elevation':
            sh.start(number, title); draw_elevation(sh, package, model, what[1], number)
        elif what[0] == 'schedule':
            sh.table(number, model['schedules'][what[1]], what[1])
        elif what[0] == 'detail':
            draw_detail(sh, package, model, what[1], number)
        elif what[0] == 'members':
            rows = [dict(record=None, cells=[m['mark'], m['role'], m['section'], m['material'], str(m['count']), feet(m['length_min_in']), feet(m['length_max_in']), num(m['total_length_ft'], 1)]) for m in model['marks']]
            sh.table(number, dict(title='Member schedule', headers=['Mark', 'Member', 'Section', 'Material', 'Count', 'Shortest', 'Longest', 'Total length (ft)'], widths=[120, 360, 300, 240, 140, 200, 200, 240], rows=rows), 'members')
    sh.close(); sh.c.save()
    pdf = dest / 'drawings.pdf'
    model_out = dict(schema='steltic.cfs_drawing_model', version=1, building_id=package['building_id'], source_model_sha256=fingerprint(package),
                     levels=model['levels'], wall_types=model['wall_types'], strap_types=model['strap_types'], marks=model['marks'], details=model['details'],
                     wall_lines=[dict(key=w['key'], label=w['label'], direction=w['direction'], pos_in=w['pos_in'], start_in=w['start_in'], length_in=w['length_in'], grid=w['grid']) for w in model['wall_lines'].values()],
                     sheets=sh.rows, cells=sh.cells, dimensions=sh.dimensions)
    write_json(dest / 'cfs_drawing_model.json', model_out)
    report = dict(schema='steltic.drawing_set', revision=state['revision'], building_id=package['building_id'], source_model_sha256=fingerprint(package),
                  decision_state_sha256=fingerprint({k: v for k, v in state.items() if k not in ('sheets', 'artifacts')}),
                  drawing_status=state['drawing_status'], can_generate=True, open_requests=0, representation='cfs_native_physical_geometry',
                  counts=dict(members=len(package['physical']['members']), connections=len(package['physical']['connections']), sheets=len(sh.rows)),
                  sheets=sh.rows, dimensions=sh.dimensions, model_sha256=fingerprint(model_out),
                  pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                  artifacts=['drawings.pdf', 'drawing_manifest.json', 'cfs_drawing_model.json'],
                  limits=['Design coordination drawings: worklines and selected components, not shop details.', 'Not for construction; to be checked and sealed by a licensed engineer.'])
    write_json(dest / 'drawing_manifest.json', report)
    return report
