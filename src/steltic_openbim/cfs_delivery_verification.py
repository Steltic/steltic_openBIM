"""Independent delivery check for a native CFS drawing set and IFC model.

Run before a CFS delivery is handed off.  It never trusts the generator's own bookkeeping for
an engineering value: every comparison re-reads the delivered artifacts --

* the drawing PDF, through its extracted page text (pypdf);
* the IFC, through its entities, placements, mesh coordinates and property sets (ifcopenshell);
* the design report (``report.html`` of the source job), through its tables;

and compares them with one another and with the calculation records in the source package.
Any difference fails the delivery.  The certificate binds the checked PDF, IFC, report and
package by SHA-256, so a file changed after the check no longer matches its certificate.

This module is used only for CFS packages recorded by the CFS engine's native physical
builder.  HR deliveries keep their own verification (``delivery_verification``).
"""
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .drawing_workflow import fingerprint, write_json
from .validation import inspect_package

INCH = 0.0254
TOL_IN = 0.02            # geometric tolerance on read-back member / panel dimensions (in.)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(text):
    """Comparison key for printed text: case, spacing, punctuation and typographic variants removed."""
    t = html.unescape(str(text))
    for a, b in (('×', 'x'), ('ρ', 'rho'), ('φ', 'phi'), ('Ω', 'omega'), ('≤', '<='), ('≥', '>='), ('–', '-'), ('—', '-'),
                 ('′', "'"), ('″', '"'), ('°', 'deg'), ('&', 'and')):
        t = t.replace(a, b)
    return re.sub(r'[^a-z0-9.]', '', t.lower())


def feet(inches):
    n = round(abs(float(inches)) * 16)
    ft, rem = divmod(n, 192)
    whole, frac = divmod(rem, 16)
    txt = str(whole)
    if frac:
        g = math.gcd(frac, 16)
        txt += ' %d/%d' % (frac // g, 16 // g)
    return ('-' if inches < -1e-9 else '') + "%d'-%s\"" % (ft, txt)


def f0(v):
    return '%.0f' % float(v)


def f1(v):
    return '%.1f' % float(v)


def f2(v):
    return '%.2f' % float(v)


class Check(object):
    def __init__(self, name, what):
        self.name, self.what, self.checked, self.failures = name, what, 0, []

    def expect(self, ok, message):
        self.checked += 1
        if not ok:
            self.failures.append(str(message)[:400])
        return ok

    def result(self):
        return dict(name=self.name, compares=self.what, checked=self.checked, passed=not self.failures and self.checked > 0,
                    failures=self.failures[:25], failure_count=len(self.failures))


# ------------------------------------------------------------------------------------------
# read-back of the three artifacts
# ------------------------------------------------------------------------------------------

def read_pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or '')
    return pages


def read_report(path):
    """Table rows of the design report, as lists of cell text."""
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', t, flags=re.S)
    rows = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', t, flags=re.S):
        cells = [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, flags=re.S)]
        if cells:
            rows.append(cells)
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
    return rows, text


def read_ifc(path):
    """Products of the IFC with their property sets, placement and mesh extents, without a geometry kernel."""
    import ifcopenshell
    f = ifcopenshell.open(str(path))
    unit = 1.0
    for u in f.by_type('IfcSIUnit'):
        if u.UnitType == 'LENGTHUNIT':
            unit = {None: 1.0, 'MILLI': 0.001, 'CENTI': 0.01}.get(u.Prefix, 1.0)
    to_in = unit / INCH
    maps = {}

    def mesh_points(product):
        rep = product.Representation
        if rep is None:
            return None
        for r in rep.Representations:
            for item in r.Items:
                if item.is_a('IfcMappedItem'):
                    src = item.MappingSource
                    if src.id() not in maps:
                        pts = []
                        for it in src.MappedRepresentation.Items:
                            if it.is_a('IfcPolygonalFaceSet') or it.is_a('IfcTriangulatedFaceSet'):
                                pts.extend(it.Coordinates.CoordList)
                        maps[src.id()] = pts
                    return maps[src.id()]
        return None

    def placement(product):
        pl = product.ObjectPlacement.RelativePlacement if product.ObjectPlacement else None
        if pl is None:
            return (0.0, 0.0, 0.0), None, None
        loc = tuple(pl.Location.Coordinates)
        ax = tuple(pl.Axis.DirectionRatios) if getattr(pl, 'Axis', None) else None
        rd = tuple(pl.RefDirection.DirectionRatios) if getattr(pl, 'RefDirection', None) else None
        return loc, ax, rd

    def props(product):
        out = {}
        for rel in getattr(product, 'IsDefinedBy', []) or []:
            if rel.is_a('IfcRelDefinesByProperties') and rel.RelatingPropertyDefinition.is_a('IfcPropertySet'):
                for p in rel.RelatingPropertyDefinition.HasProperties:
                    out[p.Name] = p.NominalValue.wrappedValue if p.NominalValue is not None else None
        return out

    materials = defaultdict(list)
    for rel in f.by_type('IfcRelAssociatesMaterial'):
        m = rel.RelatingMaterial
        names = [m.Name] if m.is_a('IfcMaterial') else [c.Material.Name for c in (m.MaterialConstituents or [])] if m.is_a('IfcMaterialConstituentSet') else []
        for o in rel.RelatedObjects:
            materials[o.id()].extend(names)
    products = {}
    for cls in ('IfcColumn', 'IfcBeam', 'IfcMember', 'IfcWall', 'IfcSlab', 'IfcElementAssembly', 'IfcAnnotation', 'IfcBuildingElementProxy'):
        for o in f.by_type(cls):
            ps = props(o)
            sid = ps.get('SourceId')
            if sid is None:
                continue
            pts = mesh_points(o)
            loc, ax, rd = placement(o)
            if pts and (ax or rd):
                z = ax or (0.0, 0.0, 1.0); x = rd or (1.0, 0.0, 0.0)
                y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
                world = [[(loc[i] + p[0] * x[i] + p[1] * y[i] + p[2] * z[i]) * to_in for i in range(3)] for p in pts]
            elif pts:
                world = [[(loc[i] + p[i]) * to_in for i in range(3)] for p in pts]
            else:
                world = None
            products[(cls if cls != 'IfcBuildingElementProxy' else 'IfcProxy', sid)] = dict(cls=cls, props=ps, points=world, materials=materials.get(o.id(), []),
                                                                                         origin=[v * to_in for v in loc])
    storeys = [(s.Name, float(s.Elevation or 0.0) * to_in) for s in f.by_type('IfcBuildingStorey')]
    grids = {}
    for g in f.by_type('IfcGrid'):
        for fam in ('UAxes', 'VAxes'):
            for a in getattr(g, fam) or []:
                grids[a.AxisTag] = [[c * to_in for c in p.Coordinates] for p in a.AxisCurve.Points]
    return dict(products=products, storeys=storeys, grids=grids, schema=f.schema)


def extent(points, direction):
    vals = [sum(p[i] * direction[i] for i in range(3)) for p in points]
    return max(vals) - min(vals)


def unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


# ------------------------------------------------------------------------------------------
# the checks
# ------------------------------------------------------------------------------------------

def section_envelope(profile, profiles):
    """(overall width along local_y, depth) of a zee or of a built-up pack of channels, from the declared dimensions and placements."""
    d = profile.get('dimensions') or {}
    if profile['family'] == 'z':
        return 2.0 * d['b'] - d['t'], d['d']
    lo, hi, depth = [], [], 0.0
    for comp in profile['components']:
        q = profiles[comp['profile_id']]['dimensions']
        turned = abs(float(comp['rotation_deg']) % 360.0 - 180.0) < 1e-6
        a, b = (-q['b'] + q['t'] / 2.0, q['t'] / 2.0) if turned else (-q['t'] / 2.0, q['b'] - q['t'] / 2.0)
        lo.append(comp['offset'][0] + a); hi.append(comp['offset'][0] + b); depth = max(depth, q['d'])
    return max(hi) - min(lo), depth


def report_row(rows, rid):
    for r in rows:
        if r and r[0] == rid:
            return r
    return None


def expected_report_tokens(record):
    """What the design report must print for a calculation record (its own formatting rules)."""
    d = record['data']; t = record['table']
    out = []
    if d.get('DC') is not None and not d.get('waived'):
        out.append(('D/C', f2(d['DC'])))
    if t == 'wall_lines':
        for k in ('sheathing', 'fastener_schedule'):
            if d.get(k):
                out.append((k, d[k]))
        if isinstance(d.get('capacity'), (int, float)):
            out.append(('capacity', f0(d['capacity'])))
    elif t == 'holddowns':
        if d.get('selection'):
            out.append(('selection', d['selection']))
        if isinstance(d.get('capacity'), (int, float)):
            out.append(('capacity', f1(d['capacity'])))
        if d.get('T_design_kip') is not None:
            out.append(('T design', f1(d['T_design_kip'])))
    elif t in ('anchorage', 'collectors'):
        if d.get('selection'):
            out.append(('selection', d['selection']))
    elif t in ('studs', 'members'):
        if d.get('section'):
            out.append(('section', d['section']))
    return out


def verify(directory, job_root, *, report_name='report.html'):
    """Check a rendered CFS delivery directory against its source job. Writes delivery_certificate.json."""
    directory, job_root = Path(directory), Path(job_root)
    package = json.loads((directory / 'source.json').read_text(encoding='utf-8'))
    state = json.loads((directory / 'state.json').read_text(encoding='utf-8'))
    manifest = json.loads((directory / 'drawing_manifest.json').read_text(encoding='utf-8'))
    dmodel = json.loads((directory / 'cfs_drawing_model.json').read_text(encoding='utf-8'))
    ifc_manifest = json.loads((directory / 'ifc_manifest.json').read_text(encoding='utf-8'))
    pdf_path, ifc_path, report_path = directory / 'drawings.pdf', directory / 'model.ifc', job_root / report_name
    checks = []
    ph = package['physical']
    pd = package['design_context']['physical_design']
    records = {r['id']: r for r in package['design_records']}

    # ---- A. the delivery is bound to one unchanged source ----
    c = Check('source_binding', 'package readiness, fingerprints of package / drawings / IFC, and the job files the package was exported from')
    verdict = inspect_package(package, job_root)
    c.expect(verdict['status'] == 'ready', 'Source package is not ready: ' + json.dumps(verdict['findings'][:3])[:300])
    fp = fingerprint(package)
    c.expect(state.get('source_model_sha256') == fp, 'state.json refers to a different source package')
    c.expect(manifest.get('source_model_sha256') == fp, 'drawing manifest refers to a different source package')
    c.expect(dmodel.get('source_model_sha256') == fp, 'drawing register refers to a different source package')
    c.expect(ifc_manifest.get('source_sha256') == fp, 'IFC manifest refers to a different source package')
    c.expect(manifest.get('pdf_sha256') == sha(pdf_path), 'drawings.pdf differs from the drawing manifest')
    c.expect(ifc_manifest.get('sha256') == sha(ifc_path), 'model.ifc differs from the IFC manifest')
    calc = job_root / 'design' / package['provenance']['package_file']
    c.expect(calc.is_file() and package['provenance']['source_files'].get('design/' + package['provenance']['package_file']) == sha(calc),
             'calculation package of the job differs from the one the physical package was exported from')
    if calc.is_file():
        on_disk = json.loads(calc.read_text(encoding='utf-8'))
        for rid, r in records.items():
            rows = on_disk.get(r['table'])
            idx = int(r['source_pointer'].rsplit('/', 1)[1])
            c.expect(isinstance(rows, list) and idx < len(rows) and rows[idx] == r['data'], 'design record %s differs from the job calculation package' % rid)
    checks.append(c)

    # ---- B. report <-> calculation records ----
    rows, report_text = read_report(report_path)
    c = Check('report_matches_design_records', 'every schedule record: the value printed in report.html against the calculation record carried by the package')
    report_dc = {}
    for rid, r in records.items():
        if r['table'] == 'schedules' and not r.get('waived'):
            # a secondary-framing schedule is printed row by row (purlin zones, girt zones, flange braces, straps)
            for q in r['data'].get('rows') or []:
                row = report_row(rows, q.get('id'))
                if c.expect(row is not None, 'report has no schedule row for %s of %s' % (q.get('id'), rid)) and q.get('DC') is not None:
                    c.expect(f2(q['DC']) in row, 'report row %s: D/C %s not printed' % (q.get('id'), f2(q['DC'])))
                    if q.get('section'):
                        c.expect(norm(q['section']) in norm(' | '.join(row)), 'report row %s does not print its section' % q.get('id'))
            continue
        if r['table'] not in ('wall_lines', 'holddowns', 'anchorage', 'studs', 'collectors', 'connections', 'members') or r.get('waived'):
            continue
        row = report_row(rows, r['data'].get('id'))
        if not c.expect(row is not None, 'report has no schedule row for %s' % rid):
            continue
        joined = norm(' | '.join(row))
        for label, token in expected_report_tokens(r):
            if label in ('D/C', 'capacity', 'T design'):
                ok = token in row
            else:
                ok = norm(token) in joined
            c.expect(ok, 'report row %s: %s "%s" not printed (row: %s)' % (rid, label, str(token)[:80], ' | '.join(row)[:160]))
        if r['data'].get('DC') is not None:
            report_dc[rid] = f2(r['data']['DC'])
    ctx = package['design_context']
    for key, fmt, label in (('W_kip', f1, 'seismic weight'), ('V_kip', f1, 'base shear')):
        v = (ctx.get('elf') or {}).get(key)
        if v is not None:
            c.expect((fmt(v) + ' kip') in report_text, 'report does not print the %s %s kip of the package' % (label, fmt(v)))
    c.expect(package['building_id'] in report_text, 'report is for a different building')
    checks.append(c)

    # ---- C. drawing PDF read-back ----
    pages = read_pdf(pdf_path)
    npages = [norm(p) for p in pages]
    c = Check('pdf_sheet_register', 'sheet numbers and titles read from each PDF page against the drawing register')
    c.expect(len(pages) == len(dmodel['sheets']), 'PDF has %d pages, register has %d sheets' % (len(pages), len(dmodel['sheets'])))
    page_of = {}
    for s in dmodel['sheets']:
        i = s['page'] - 1
        if i < len(pages):
            c.expect(norm(s['number']) in npages[i] and norm(s['title'])[:60] in npages[i], 'page %d does not carry sheet %s "%s"' % (s['page'], s['number'], s['title']))
            c.expect(norm(package['building_id']) in npages[i], 'page %d does not name the building' % s['page'])
        page_of[s['number']] = i
    checks.append(c)

    c = Check('pdf_schedules_match_design_records', 'every schedule row read from the PDF against the calculation record it names, and against the report value')
    printed = defaultdict(list)
    for cell in dmodel['cells']:
        i = page_of.get(cell['sheet'])
        txt = npages[i] if i is not None and i < len(npages) else ''
        for v in ([cell['text']] if cell.get('text') else cell['cells']):
            c.expect(norm(v) in txt, 'sheet %s: "%s" is registered but not readable on the page' % (cell['sheet'], str(v)[:90]))
        if cell.get('record'):
            printed[cell['record']].append(cell)
    # independent expectation, straight from the records
    for rid, r in records.items():
        d = r['data']
        if r.get('waived'):
            continue
        if r['table'] == 'schedules':
            cells = printed.get(rid)
            if not c.expect(bool(cells), 'no drawing schedule row names record %s' % rid):
                continue
            by_row = {cell['cells'][0]: cell['cells'] for cell in cells}
            for q in d.get('rows') or []:
                got = by_row.get(str(q.get('id')))
                if not c.expect(got is not None, 'drawing schedule has no row %s of %s' % (q.get('id'), rid)):
                    continue
                if q.get('DC') is not None:
                    c.expect(f2(q['DC']) == got[-1], 'drawing schedule row %s prints D/C %s, record %s' % (q.get('id'), got[-1], f2(q['DC'])))
                    row = report_row(rows, q.get('id'))
                    c.expect(row is not None and got[-1] in row, 'D/C of %s differs between drawing and report' % q.get('id'))
                if q.get('section'):
                    c.expect(any(norm(q['section']) == norm(v) for v in got), 'drawing schedule row %s does not print its section' % q.get('id'))
            continue
        if r['table'] in ('wall_lines', 'holddowns', 'anchorage', 'studs', 'collectors', 'connections', 'diaphragms', 'framing', 'members'):
            cells = printed.get(rid)
            if r['table'] == 'anchorage' and not cells and pd.get('kind') != 'portal':
                continue                               # anchorage rows are printed once per analysis line, keyed by that record
            if not c.expect(bool(cells), 'no drawing schedule row names record %s' % rid):
                continue
            flat = [v for cell in cells for v in cell['cells']]
            if d.get('DC') is not None:
                c.expect(f2(d['DC']) in flat, 'drawing schedule row for %s does not print D/C %s (prints %s)' % (rid, f2(d['DC']), flat[-3:]))
                if rid in report_dc:
                    c.expect(report_dc[rid] in flat, 'D/C of %s differs between drawing and report' % rid)
            cap = d.get('capacity')
            if isinstance(cap, (int, float)) and r['table'] in ('wall_lines', 'holddowns', 'diaphragms'):
                want = f0(cap) if r['table'] in ('wall_lines', 'diaphragms') else f1(cap)
                c.expect(want in flat, 'drawing schedule row for %s does not print capacity %s' % (rid, want))
            for key in ('section', 'selection', 'components'):
                if d.get(key) and (r['table'] in ('studs', 'collectors', 'connections', 'framing', 'diaphragms', 'members') or (r['table'] == 'anchorage' and pd.get('kind') == 'portal' and key == 'selection')):
                    c.expect(any(norm(d[key]) == norm(v) for v in flat), 'drawing schedule row for %s does not print its %s' % (rid, key))
        elif r['table'] == 'materials':
            cells = printed.get(rid)
            if c.expect(bool(cells), 'materials schedule omits %s' % rid):
                flat = [norm(v) for cell in cells for v in cell['cells']]
                c.expect(norm(d.get('spec', '')) in flat, 'materials schedule row %s does not print the specification' % rid)
    checks.append(c)

    c = Check('pdf_dimensions_match_model', 'level elevations, storey heights, wall-line spacings and segment set-out read from the PDF against the package geometry')
    levels = sorted(package['reference_system']['levels'], key=lambda r: r['level'])
    elev_pages = [page_of[s['number']] for s in dmodel['sheets'] if s['title'].startswith('Wall elevation')]
    for i in elev_pages:
        for lv in levels:
            c.expect(norm(lv['name'] + feet(lv['elevation_in'])) in npages[i], 'elevation page %d does not show %s at %s' % (i + 1, lv['name'], feet(lv['elevation_in'])))
        for a, b in zip(levels, levels[1:]):
            c.expect(norm(feet(b['elevation_in'] - a['elevation_in'])) in npages[i], 'elevation page %d omits the storey height %s' % (i + 1, feet(b['elevation_in'] - a['elevation_in'])))
    plan_pages = [page_of[s['number']] for s in dmodel['sheets'] if 'plan' in s['title'].lower() and s['number'].startswith('S-1')]
    if pd.get('kind') == 'portal':
        # independent set-out from the located frame members: frame lines along the building, column lines across it
        fy = sorted({round(m['axis'][0][1], 4) for m in ph['members'] if m['kind'] in ('column', 'rafter')})
        cx = sorted({round(m['axis'][0][0], 4) for m in ph['members'] if m['kind'] == 'column'})
        c.expect(len(plan_pages) >= 2, 'portal drawing set needs a base plan and a roof plan')
        side_pages = [page_of[s['number']] for s in dmodel['sheets'] if s['title'].startswith('Side wall elevation')]
        frame_pages = [page_of[s['number']] for s in dmodel['sheets'] if s['title'].startswith('Portal frame elevation')]
        c.expect(bool(frame_pages), 'portal drawing set has no frame elevation')
        c.expect(len(side_pages) == 2, 'portal drawing set needs the two side-wall elevations')
        for i in plan_pages + side_pages:
            for a, b in zip(fy, fy[1:]):
                c.expect(norm(feet(b - a)) in npages[i], 'page %d omits the frame spacing %s' % (i + 1, feet(b - a)))
            c.expect(norm(feet(fy[-1] - fy[0])) in npages[i], 'page %d omits the building length %s' % (i + 1, feet(fy[-1] - fy[0])))
        for i in plan_pages + frame_pages:
            for a, b in zip(cx, cx[1:]):
                c.expect(norm(feet(b - a)) in npages[i], 'page %d omits the span %s between column lines' % (i + 1, feet(b - a)))
        top = max(p_[2] for m in ph['members'] if m['kind'] in ('column', 'rafter') for p_ in m['axis'])
        for i in frame_pages:
            for lv in levels:
                c.expect(norm(lv['name'] + feet(lv['elevation_in'])) in npages[i], 'frame elevation page %d does not show %s at %s' % (i + 1, lv['name'], feet(lv['elevation_in'])))
            c.expect(norm(feet(top)) in npages[i], 'frame elevation page %d omits the overall height %s' % (i + 1, feet(top)))
        types = (dmodel.get('portal') or {}).get('frame_types', [])
        c.expect(sorted(f for t in types for f in t['frames']) == sorted({int(m['frame']) for m in ph['members'] if m.get('frame') is not None}), 'frame elevations do not cover every frame of the model exactly once')
        for s_ in dmodel['dimensions']:
            c.expect(norm(s_['label']) in npages[page_of[s_['sheet']]], 'sheet %s: dimension %s is registered but not readable' % (s_['sheet'], s_['label']))
    grid_lines = [w for w in pd.get('wall_lines', {}).values() if w.get('grid', True)]
    for direction in ('X', 'Y'):
        pos = sorted({w['pos_ft'] * 12.0 for w in grid_lines if w['direction'] == direction})
        for a, b in zip(pos, pos[1:]):
            for i in plan_pages:
                c.expect(norm(feet(b - a)) in npages[i], 'plan page %d omits the %s wall-line spacing %s' % (i + 1, direction, feet(b - a)))
    by_title = {s['title']: page_of[s['number']] for s in dmodel['sheets']}
    for key, line in pd.get('wall_lines', {}).items():
        i = by_title.get('Wall elevation: line %s' % key.split(':', 1)[1])
        if not c.expect(i is not None, 'no elevation sheet for wall line %s' % key):
            continue
        L = (line['end_ft'] - line['start_ft']) * 12.0
        c.expect(norm(feet(L)) in npages[i], 'elevation of %s omits the wall length %s' % (key, feet(L)))
        st = line['stories'][min(line['stories'], key=int)]
        for a, b in st.get('segments_ft', []):
            c.expect(norm(feet((b - a) * 12.0)) in npages[i], 'elevation of %s omits the segment length %s' % (key, feet((b - a) * 12.0)))
    checks.append(c)

    # ---- D. IFC read-back ----
    ifc = read_ifc(ifc_path)
    prods = ifc['products']
    profiles = {p['id']: p for p in ph['profiles']}
    materials = {m['id']: m for m in ph['materials']}
    c = Check('ifc_members_match_model', 'every member: IFC product, section label, material, and the length / depth / flange width measured from its IFC mesh')
    by_sid = defaultdict(list)
    for (cls, sid), p in prods.items():
        by_sid[sid].append(p)
    member_cls = ('IfcColumn', 'IfcBeam', 'IfcMember')
    count = 0
    for m in ph['members']:
        hits = [p for p in by_sid.get(m['id'], []) if p['cls'] in member_cls]
        if not c.expect(len(hits) == 1, 'member %s has %d IFC products' % (m['id'], len(hits))):
            continue
        p = hits[0]; count += 1
        c.expect(p['props'].get('Section') == m['profile_id'], 'member %s: IFC section %s, design %s' % (m['id'], p['props'].get('Section'), m['profile_id']))
        spec = materials[m['material_id']]['specification']
        c.expect(spec in p['materials'], 'member %s: IFC material %s, design %s' % (m['id'], p['materials'], spec))
        if not c.expect(bool(p['points']), 'member %s has no IFC body geometry' % m['id']):
            continue
        ax = unit([b - a for a, b in zip(*m['axis'])]); ly = unit(m['local_y']); lz = cross(ax, ly)
        length = math.dist(*m['axis'])
        d = profiles[m['profile_id']]['dimensions']
        c.expect(abs(extent(p['points'], ax) - length) <= TOL_IN, 'member %s: IFC length %.3f in., design %.3f in.' % (m['id'], extent(p['points'], ax), length))
        fam = profiles[m['profile_id']]['family']
        if fam in ('built_up', 'z'):
            wy, wz = section_envelope(profiles[m['profile_id']], profiles)
            c.expect(abs(extent(p['points'], lz) - wz) <= TOL_IN, 'member %s: IFC depth %.3f in., design %.3f in.' % (m['id'], extent(p['points'], lz), wz))
            c.expect(abs(extent(p['points'], ly) - wy) <= TOL_IN, 'member %s: IFC overall width %.3f in., design %.3f in.' % (m['id'], extent(p['points'], ly), wy))
            d = dict(d=wz, b=wy)
        elif 'b' in d:
            c.expect(abs(extent(p['points'], lz) - d['d']) <= TOL_IN, 'member %s: IFC depth %.3f in., design %.3f in.' % (m['id'], extent(p['points'], lz), d['d']))
            c.expect(abs(extent(p['points'], ly) - d['b']) <= TOL_IN, 'member %s: IFC flange width %.3f in., design %.3f in.' % (m['id'], extent(p['points'], ly), d['b']))
        elif 'width' in d:                      # flat strap (width x thickness) or truss envelope (width x depth)
            other = d.get('thickness', d.get('depth'))
            c.expect(abs(extent(p['points'], ly) - d['width']) <= TOL_IN, 'member %s: IFC width %.3f in., design %.3f in.' % (m['id'], extent(p['points'], ly), d['width']))
            c.expect(abs(extent(p['points'], lz) - other) <= TOL_IN, 'member %s: IFC thickness/depth %.3f in., design %.3f in.' % (m['id'], extent(p['points'], lz), other))
        else:
            c.expect(abs(extent(p['points'], lz) - d['d']) <= 0.05 * d['d'] + TOL_IN, 'member %s: IFC diameter %.3f in., design %.3f in.' % (m['id'], extent(p['points'], lz), d['d']))
        mid = [sum(q[i] for q in p['points']) / len(p['points']) for i in range(3)]
        centre = [(a + b) / 2.0 for a, b in zip(*m['axis'])]
        off = [mid[i] - centre[i] for i in range(3)]
        along = sum(off[i] * ax[i] for i in range(3))
        c.expect(abs(along) <= 0.5 and math.sqrt(max(0.0, sum(v * v for v in off) - along * along)) <= max(d.get('d', 1.0), d.get('b', 1.0)),
                 'member %s: IFC body is not on its design workline' % m['id'])
    extra = [sid for (cls, sid), p in prods.items() if cls in member_cls and sid not in {m['id'] for m in ph['members']}]
    c.expect(not extra, 'IFC has member products that are not in the design model: %s' % extra[:5])
    checks.append(c)

    c = Check('ifc_panels_levels_grids_match_model', 'sheathing panels (thickness, extents), storeys, grids and openings in the IFC against the package')
    for pn in ph['panels']:
        hits = [p for p in by_sid.get(pn['id'], []) if p['cls'] in ('IfcWall', 'IfcSlab', 'IfcBuildingElementProxy')]
        if not c.expect(len(hits) == 1 and bool(hits[0]['points']), 'panel %s is not one IFC product with geometry' % pn['id']):
            continue
        p = hits[0]
        c.expect(abs(float(p['props'].get('ThicknessIn') or 0.0) - pn['thickness']) < 1e-6, 'panel %s: IFC thickness property differs' % pn['id'])
        for i in range(3):
            lo, hi = min(v[i] for v in pn['vertices']), max(v[i] for v in pn['vertices'])
            got_lo, got_hi = min(q[i] for q in p['points']), max(q[i] for q in p['points'])
            c.expect(abs(got_lo - lo) <= pn['thickness'] + TOL_IN and abs(got_hi - hi) <= pn['thickness'] + TOL_IN, 'panel %s: IFC extent differs on axis %d' % (pn['id'], i))
        c.expect(materials[pn['material_id']]['specification'] in p['materials'], 'panel %s: IFC material differs' % pn['id'])
    got = {name: z for name, z in ifc['storeys']}
    for lv in levels:
        c.expect(lv['name'] in got and abs(got[lv['name']] - lv['elevation_in']) <= 1e-3, 'IFC storey %s elevation differs from the design level' % lv['name'])
    for g in package['reference_system'].get('grids', []):
        pts = ifc['grids'].get(g['label'])
        c.expect(pts is not None and all(math.dist(a, b) <= 1e-3 for a, b in zip(pts, g['points_in'])), 'IFC grid %s differs from wall line %s' % (g['label'], g['id']))
    for o in ph.get('openings', []):
        hits = [p for p in by_sid.get(o['id'], []) if p['cls'] == 'IfcAnnotation']
        c.expect(len(hits) == 1, 'opening %s is not in the IFC' % o['id'])
    checks.append(c)

    c = Check('ifc_connections_match_model', 'every located connection assembly: IFC product, template, placement at its joint, and its design records')
    joints = {j['id']: j for j in ph['joints']}
    n_inst = 0
    for cn in ph['connections']:
        inst = cn.get('assembly_instance')
        if not inst:
            continue
        n_inst += 1
        hits = [p for p in by_sid.get(cn['id'], []) if p['cls'] == 'IfcElementAssembly']
        if not c.expect(len(hits) == 1, 'connection %s has %d IFC assemblies' % (cn['id'], len(hits))):
            continue
        p = hits[0]
        c.expect(p['props'].get('AssemblyTemplate') == inst['template_id'], 'connection %s: IFC template differs' % cn['id'])
        c.expect(p['props'].get('JointId') == cn['joint_id'], 'connection %s: IFC joint differs' % cn['id'])
        try:
            recs = [r_['id'] for r_ in json.loads(p['props'].get('DesignRecords') or '[]')]
        except ValueError:
            recs = None
        c.expect(recs is not None and set(recs) == set(cn.get('design_record_ids', [])), 'connection %s: IFC design records differ' % cn['id'])
    c.expect(n_inst == sum(1 for (cls, sid) in prods if cls == 'IfcElementAssembly'), 'IFC assembly count differs from the located connections of the design')
    checks.append(c)

    # ---- E. IFC <-> report through the records carried in the IFC ----
    c = Check('ifc_design_records_match_report', 'D/C and capacity of the calculation records embedded in IFC products against the report rows')
    seen = set()
    for (cls, sid), p in prods.items():
        raw = p['props'].get('DesignRecords')
        if not raw:
            continue
        try:
            recs = json.loads(raw)
        except ValueError:
            c.expect(False, 'IFC product %s carries unreadable design records' % sid); continue
        for r_ in recs:
            rid = r_['id']
            if rid in seen:
                continue
            seen.add(rid)
            src = records.get(rid)
            if not c.expect(src is not None and src['data'] == r_['data'], 'IFC product %s carries a design record %s that differs from the package' % (sid, rid)):
                continue
            if rid in report_dc:
                row = report_row(rows, r_['data'].get('id'))
                c.expect(row is not None and f2(r_['data']['DC']) in row, 'record %s: D/C in the IFC differs from the report' % rid)
    linked = {rid for coll in ('members', 'panels', 'connections', 'openings') for e in ph.get(coll, []) for rid in e.get('design_record_ids', [])}
    c.expect(linked <= seen | {rid for rid in linked if records[rid]['table'] == 'materials'}, 'design records linked in the model but absent from the IFC: %s' % sorted(linked - seen)[:5])
    checks.append(c)

    # ---- F. drawings <-> IFC ----
    c = Check('drawings_match_ifc', 'member schedule counts, wall elevation counts, wall / braced-bay types and detail occurrence counts printed on the drawings against the selections and the products counted in the IFC')
    ifc_groups = Counter()
    ifc_line = Counter()
    ifc_family = Counter()
    for (cls, sid), p in prods.items():
        if cls in member_cls:
            try:
                src = json.loads(p['props'].get('SourceEntity') or '{}')
            except ValueError:
                src = {}
            ifc_groups[(src.get('role') or src.get('kind'), p['props'].get('Section'), src.get('material_id'))] += 1
            if src.get('wall_line') and src.get('kind') == 'stud':
                ifc_line[(src['wall_line'], str(src.get('storey')), src.get('role'), p['props'].get('Section'))] += 1
        elif cls == 'IfcElementAssembly':
            try:
                src = json.loads(p['props'].get('SourceEntity') or '{}')
            except ValueError:
                src = {}
            ifc_family[src.get('family')] += 1
    for cell in dmodel['cells']:
        v = cell['cells']
        if cell['schedule'] == 'members':
            n = ifc_groups.get((v[1], v[2], v[3]))
            c.expect(n is not None and str(n) == v[4], 'member schedule %s %s: drawing count %s, IFC count %s' % (v[1], v[2], v[4], n))
        elif cell['schedule'] == 'elevation_counts':
            n = ifc_line.get((v[0], v[1], v[2], v[3]))
            c.expect(n is not None and str(n) == v[4], 'wall %s storey %s %s %s: drawing count %s, IFC count %s' % (v[0], v[1], v[2], v[3], v[4], n))
    c.expect(sum(int(cell['cells'][4]) for cell in dmodel['cells'] if cell['schedule'] == 'members') == sum(ifc_groups.values()), 'member schedule total differs from the IFC member count')
    delegated = Counter(cn.get('family') for cn in ph['connections'] if cn.get('scope') == 'delegated')
    for det in dmodel['details']:
        c.expect(det['occurrences'] - det['delegated'] == ifc_family.get(det['family'], 0), 'detail %s (%s): drawing lists %d located occurrences, IFC has %d assemblies'
                 % (det['reference'], det['family'], det['occurrences'] - det['delegated'], ifc_family.get(det['family'], 0)))
    if pd.get('kind') == 'portal':
        src_of = {}
        for (cls, sid), p in prods.items():
            if cls in member_cls:
                try:
                    src_of[sid] = json.loads(p['props'].get('SourceEntity') or '{}')
                except ValueError:
                    src_of[sid] = {}
        types = {t['mark']: t for t in (dmodel.get('portal') or {}).get('frame_types', [])}
        cx = sorted({round(m['axis'][0][0], 4) for m in ph['members'] if m['kind'] == 'column'})

        def line_of(sid):
            pts = prods[next(k for k in prods if k[1] == sid and k[0] in member_cls)]['points']
            xm = sum(q[0] for q in pts) / len(pts)
            return chr(65 + cx.index(min(cx, key=lambda v: abs(v - xm))))
        seen_kinds = set()
        for cell in dmodel['cells']:
            v = cell['cells']
            if cell['schedule'] == 'frame_counts':
                t = types.get(v[0])
                if not c.expect(t is not None, 'frame count row names an unknown frame type %s' % v[0]):
                    continue
                n = sum(1 for sid, src in src_of.items() if src.get('frame') in t['frames'] and (src.get('role') or src.get('kind')) == v[1] and prods[next(k for k in prods if k[1] == sid and k[0] in member_cls)]['props'].get('Section') == v[2])
                c.expect(str(n) == v[5] and int(v[3]) * int(v[4]) == n, 'frame type %s: drawing lists %s x %s %s, IFC has %d' % (v[0], v[5], v[1], v[2], n))
            elif cell['schedule'] == 'line_counts':
                kind = v[0].split(':')[0]; seen_kinds.add(kind)
                ids = [sid for sid, src in src_of.items() if src.get('kind') == kind and prods[next(k for k in prods if k[1] == sid and k[0] in member_cls)]['props'].get('Section') == v[1]
                       and (':' not in v[0] or line_of(sid) == v[0].split(':')[1])]
                nlines = len({(src_of[sid].get('host_line'), src_of[sid].get('line')) for sid in ids})
                c.expect(str(len(ids)) == v[3] and str(nlines) == v[2], '%s %s: drawing lists %s lines / %s members, IFC has %d / %d' % (v[0], v[1], v[2], v[3], nlines, len(ids)))
            elif cell['schedule'] == 'strut_counts':
                ids = [sid for sid, src in src_of.items() if src.get('kind') == 'strut' and prods[next(k for k in prods if k[1] == sid and k[0] in member_cls)]['props'].get('Section') == v[1] and line_of(sid) == v[0]]
                c.expect(str(len(ids)) == v[2], 'struts on line %s: drawing lists %s x %s, IFC has %d' % (v[0], v[2], v[1], len(ids)))
            elif cell['schedule'] == 'strap_counts':
                ids = [sid for sid, src in src_of.items() if src.get('kind') == 'strap' and src.get('plane') == v[0] and prods[next(k for k in prods if k[1] == sid and k[0] in member_cls)]['props'].get('Section') == v[2]
                       and (v[1] == '-' or line_of(sid) == v[1])]
                c.expect(str(len(ids)) == v[4] and str(len({src_of[sid].get('bay') for sid in ids})) == v[3], '%s bracing %s: drawing lists %s straps in %s bays, IFC has %d in %d' % (v[0], v[2], v[4], v[3], len(ids), len({src_of[sid].get('bay') for sid in ids})))
        for kind in ('purlin', 'girt'):
            if any(src.get('kind') == kind for src in src_of.values()):
                c.expect(kind in seen_kinds, 'the drawings give no line count for the %ss of the model' % kind)
        # scheduled strap size against the strap measured in the IFC, and the selected frame make-up against the IFC section
        if any(src.get('kind') == 'strut' for src in src_of.values()):
            c.expect(any(cell['schedule'] == 'strut_counts' for cell in dmodel['cells']), 'the drawings give no count for the struts of the model')
        for where in ('wall', 'roof'):
            entries = (pd.get('bracing') or {}).get(where)
            entries = entries if isinstance(entries, list) else ([entries] if entries else [])
            if not entries:
                continue
            ids = [sid for sid, src in src_of.items() if src.get('kind') == 'strap' and src.get('plane') == where]
            want = 0
            for sel_ in entries:
                row_id = sel_.get('row') or 'strap-' + where
                mine = [sid for sid in ids if src_of[sid].get('schedule_row') == row_id]
                nlines = len(sel_['lines']) if sel_.get('lines') else len({src_of[sid].get('host_line') for sid in mine})
                want += 2 * len(sel_['bays']) * nlines * int(sel_.get('panels', 1))
                c.expect(len(mine) == 2 * len(sel_['bays']) * nlines * int(sel_.get('panels', 1)), '%s bracing %s: %d straps in the IFC, X-bracing in the selected bays needs %d' % (where, row_id, len(mine), 2 * len(sel_['bays']) * nlines * int(sel_.get('panels', 1))))
                for sid in mine[:4]:
                    m = next(q for q in ph['members'] if q['id'] == sid)
                    pts = prods[next(k for k in prods if k[1] == sid and k[0] in member_cls)]['points']
                    axm = unit([b_ - a_ for a_, b_ in zip(*m['axis'])]); lym = unit(m['local_y'])
                    c.expect(abs(extent(pts, lym) - sel_['width_in']) <= TOL_IN and abs(extent(pts, cross(axm, lym)) - sel_['t_in']) <= TOL_IN, 'strap %s: selected %g x %.4f in., IFC %.3f x %.4f in.' % (sid, sel_['width_in'], sel_['t_in'], extent(pts, lym), extent(pts, cross(axm, lym))))
                rec = records.get(sel_['record'])
                row = next((q for q in (rec or {}).get('data', {}).get('rows', []) if q.get('id') == row_id), None)
                c.expect(row is not None and abs(row['width_in'] - sel_['width_in']) < 1e-9 and row['n_screws'] == sel_['n_screws'], '%s bracing: the modelled strap differs from the scheduled strap row %s' % (where, row_id))
            c.expect(len(ids) == want, '%s bracing: %d straps in the IFC, %d selected' % (where, len(ids), want))
        for key, kind in (('column', 'column'), ('rafter', 'rafter')):
            sel_ = pd['frame'][key]
            want = ('%dx%s' % (sel_['n'], sel_['section'])) if int(sel_['n']) > 1 else sel_['section']
            got = {prods[k]['props'].get('Section') for k in prods if k[0] in member_cls and src_of.get(k[1], {}).get('kind') == kind}
            c.expect(got == {want}, '%s make-up: selected %s, IFC sections %s' % (key, want, sorted(got)))
            rec = records.get(sel_['record'])
            c.expect(rec is not None and rec['data'].get('section') == want, '%s make-up differs from its calculation record' % key)
    # wall types: the type scheduled on the drawings for each wall line and storey against the selection and the IFC products
    tsel = {}
    for t in list(dmodel.get('wall_types', [])) + list(dmodel.get('strap_types', [])):
        for key, k in t['used']:
            tsel[(key, int(k))] = t
    for key, line in pd.get('wall_lines', {}).items():
        normal = [0.0, 1.0, 0.0] if line['direction'] == 'X' else [1.0, 0.0, 0.0]
        for ks, st in line['stories'].items():
            nseg = len(st.get('segments_ft', []))
            sp, sh_ = st.get('strap'), st.get('sheathing')
            if not nseg or not (sp or sh_):
                continue
            t = tsel.get((key, int(ks)))
            if not c.expect(t is not None, 'wall %s storey %s has no wall type on the drawings' % (key, ks)):
                continue
            if sp:
                c.expect(abs(t.get('width_in', -1) - sp['width_in']) < 1e-6 and abs(t.get('t_in', -1) - round(float(sp['t_in']), 4)) < 1e-6 and t.get('faces') == sp['faces']
                         and t.get('n_strap') == sp['n_strap'] and t.get('n_gusset') == sp['n_gusset'] and t.get('screw') == sp['screw'],
                         'wall %s storey %s: drawing strap type %s differs from the selected strap' % (key, ks, t.get('mark')))
                straps = [p for (cls, sid), p in prods.items() if cls in member_cls and sid.startswith('B:%s:S%s:' % (key, ks))]
                c.expect(len(straps) == 2 * sp['faces'] * nseg, 'wall %s storey %s: %d straps selected (X each face of %d bays), IFC has %d' % (key, ks, 2 * sp['faces'] * nseg, nseg, len(straps)))
                for p in straps[:4]:
                    c.expect(abs(extent(p['points'], normal) - sp['t_in']) <= TOL_IN, 'strap on %s storey %s: scheduled thickness %.4f in., IFC %.4f in.' % (key, ks, sp['t_in'], extent(p['points'], normal)))
                ends = [p for (cls, sid), p in prods.items() if cls == 'IfcElementAssembly' and sid.startswith('C:B:%s:S%s:' % (key, ks))]
                c.expect(len(ends) == 2 * len(straps), 'wall %s storey %s: %d strap end connections expected, IFC has %d' % (key, ks, 2 * len(straps), len(ends)))
            else:
                c.expect(abs(t.get('thickness_in', -1) - round(float(sh_['thickness_in']), 4)) < 1e-6 and t.get('faces') == sh_['faces'] and abs(t.get('edge_in', -1) - sh_['edge_in']) < 1e-6
                         and t.get('screw') == sh_['screw'] and t.get('sheathing_material') == sh_['material'],
                         'wall %s storey %s: drawing wall type %s differs from the selected sheathing' % (key, ks, t.get('mark')))
                pans = [p for (cls, sid), p in prods.items() if cls != 'IfcElementAssembly' and sid.startswith('P:%s:S%s:G' % (key, ks))]
                c.expect(len(pans) == sh_['faces'] * nseg, 'wall %s storey %s: %d sheathing panels selected, IFC has %d' % (key, ks, sh_['faces'] * nseg, len(pans)))
    # rod diameters and sheathing thickness: schedule text against measured IFC geometry
    for key, line in pd.get('wall_lines', {}).items():
        for ks, st in line['stories'].items():
            if st.get('rod'):
                rods = [p for (cls, sid), p in prods.items() if cls == 'IfcMember' and sid.startswith('R:%s:' % key) and sid.endswith(':S%s' % ks)]
                for p in rods[:2]:
                    w = min(extent(p['points'], [1, 0, 0]), extent(p['points'], [0, 1, 0]))
                    c.expect(abs(w - st['rod']['d_in']) <= 0.05 * st['rod']['d_in'] + TOL_IN, 'rod on %s storey %s: scheduled %.3f in., IFC %.3f in.' % (key, ks, st['rod']['d_in'], w))
    checks.append(c)

    results = [k.result() for k in checks]
    certificate = dict(schema='steltic.cfs_delivery_certificate', version=1, building_id=package['building_id'], passed=all(r['passed'] for r in results),
                       checks=results, source_model_sha256=fp, pdf_sha256=sha(pdf_path), ifc_sha256=sha(ifc_path), report_sha256=sha(report_path),
                       calculation_package_sha256=sha(calc) if calc.is_file() else None,
                       counts=dict(sheets=len(pages), members=len(ph['members']), panels=len(ph['panels']), connections=len(ph['connections']), design_records=len(records)),
                       tolerances=dict(geometry_in=TOL_IN, printed_values='identical strings at the printed resolution'),
                       scope='Agreement of the delivered drawings, IFC and report with one another and with the calculation records. Not a structural design check.')
    write_json(directory / 'delivery_certificate.json', certificate)
    return certificate
