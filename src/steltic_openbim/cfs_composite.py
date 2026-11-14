"""Deliver one drawing set and one IFC model for a composite CFS project, with a composite self-check.

    python -m steltic_openbim.cfs_composite --job-root PROJECT --jobs-dir JOBS --output DELIVERY

A composite project (Steltic CFS ``steel_engine/cfs_composite.py``) is several structurally separate
structures -- each a complete CFS job with its own READY physical package and report -- bound by
``PROJECT/design/composite.json`` (parts, plan set-out, interface between the parts).  This command

1. delivers every part with the ordinary CFS delivery and its ten-check certificate (``parts/<id>/``);
2. writes ``drawings.pdf``: a project sheet (composition, key plan, clear gaps, sheet index) followed by
   every sheet of every part, each stamped with its part and its page in the project set;
3. writes ``model.ifc``: one IfcProject holding every part at its set-out, every product tagged with its part;
4. checks the result and writes ``delivery_certificate.json``.

The composite checks do not repeat the part checks; they prove that binding the parts changed nothing and
that the set-out and the interface in the report are the ones in the drawings and the model:

* every part certificate passed, for the very files the project report was built from;
* the project report contains every part report in full, and the composition table and interface record;
* every part sheet is in the project set unchanged, and the sheet index lists it;
* every part product is in the project model once, same class, properties and materials, moved by exactly
  the part origin; nothing else was added;
* the clear gaps measured between the parts in the model equal the gaps stated in the report and are not
  less than the separation the interface record requires.

CFS only.  The HR delivery never comes here.
"""
import argparse
import io
import json
import math
from pathlib import Path

from .drawing_workflow import write_json
from .cfs_delivery_verification import Check, norm, read_ifc, read_pdf, read_report, sha, INCH

SCHEMA = 'steltic.cfs_composite'
TOL_SETOUT_IN = 0.01
TOL_GAP_IN = 0.26           # stated gaps are whole or half inches; the model must agree to a quarter


def corners(member, profiles):
    """World corners (in the part's own system) of the bounding prism of one member."""
    from . import cfs_native_portal as portal
    a, b = member['axis']
    ux = [b[i] - a[i] for i in range(3)]
    ln = math.sqrt(sum(v * v for v in ux)) or 1.0
    ux = [v / ln for v in ux]
    ly = member['local_y']
    lz = [ux[1] * ly[2] - ux[2] * ly[1], ux[2] * ly[0] - ux[0] * ly[2], ux[0] * ly[1] - ux[1] * ly[0]]
    prof = profiles[member['profile_id']]
    d = prof.get('dimensions') or {}
    fam = prof['family']
    if fam in ('built_up', 'z', 'rhs'):
        wy, wz = portal.profile_extents(prof, profiles)
        y0, y1, z0, z1 = -wy / 2.0, wy / 2.0, -wz / 2.0, wz / 2.0
    elif fam == 'channel':
        y0, y1, z0, z1 = -d.get('t', 0.0) / 2.0, d['b'] - d.get('t', 0.0) / 2.0, -d['d'] / 2.0, d['d'] / 2.0
    elif 'width' in d:
        hz = d.get('thickness', d.get('depth', 0.0)) / 2.0
        y0, y1, z0, z1 = -d['width'] / 2.0, d['width'] / 2.0, -hz, hz
    else:
        r = max([float(v) for v in d.values() if isinstance(v, (int, float))] or [0.0]) / 2.0
        y0, y1, z0, z1 = -r, r, -r, r
    return [[e[q] + yy * ly[q] + zz * lz[q] for q in range(3)] for e in (a, b) for yy in (y0, y1) for zz in (z0, z1)]


def boxes(package, origin, kinds=None, within=None):
    """Axis-aligned boxes [(lo, hi)] of the members of a part, in the project system. within: {'x'|'y'|'z': [lo, hi]} keeps the members whose centre lies in the range."""
    ph = package['physical']
    profiles = {p['id']: p for p in ph['profiles']} if isinstance(ph['profiles'], list) else ph['profiles']
    out = []
    for m in ph['members']:
        if kinds and m['kind'] not in kinds:
            continue
        cs = corners(m, profiles)
        lo, hi = [min(c[i] for c in cs) + origin[i] for i in range(3)], [max(c[i] for c in cs) + origin[i] for i in range(3)]
        if within and not all(r[0] <= (lo['xyz'.index(k)] + hi['xyz'.index(k)]) / 2.0 <= r[1] for k, r in within.items()):
            continue
        out.append((lo, hi))
    return out


def clear_gap(a_boxes, b_boxes, axis, projected=False):
    """Smallest clear distance along a plan axis between any box of a and the envelope of b, over the boxes of a that face b
    (projected: over every box of a, as when a plane of framing such as an end frame faces the other part)."""
    i = 0 if axis == 'x' else 1
    j = 1 - i
    blo = [min(b[0][k] for b in b_boxes) for k in range(3)]
    bhi = [max(b[1][k] for b in b_boxes) for k in range(3)]
    best = None
    for lo, hi in a_boxes:
        if not projected and (hi[j] < blo[j] or lo[j] > bhi[j] or hi[2] < blo[2] or lo[2] > bhi[2]):
            continue                                  # does not face the other part
        if hi[i] <= blo[i]:
            g = blo[i] - hi[i]
        elif lo[i] >= bhi[i]:
            g = lo[i] - bhi[i]
        else:
            g = -min(hi[i] - blo[i], bhi[i] - lo[i])   # overlap: the parts clash
        best = g if best is None else min(best, g)
    return best


def gaps_measured(manifest, packages):
    origin = {p['id']: p['origin_in'] for p in manifest['parts']}
    out = []
    for g in (manifest.get('interface') or {}).get('clear_gaps') or []:
        a, b = g['a'], g['b']
        val = clear_gap(boxes(packages[a['part']], origin[a['part']], a.get('kinds'), a.get('within')), boxes(packages[b['part']], origin[b['part']], b.get('kinds'), b.get('within')), g['axis'], bool(g.get('projected')))
        out.append(dict(g, measured_in=None if val is None else round(val, 3)))
    return out


# ------------------------------------------------------------------------------------------
# drawings
# ------------------------------------------------------------------------------------------

def stamp_page(width, height, text):
    from reportlab.pdfgen.canvas import Canvas
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(width, height), pageCompression=1, invariant=1)
    c.setFont('Helvetica-Bold', 11); c.setFillColor('#2f6480')
    c.drawString(44.0, height - 30.0, text)
    c.save()
    return buf.getvalue()


def cover_page(manifest, parts, gaps, packages, sheet_rows, total):
    from reportlab.pdfgen.canvas import Canvas
    from .cfs_native_pdf import W, H, INK, GREY, LIGHT, ACCENT, BLUE, FILL, MARGIN, TITLE_H, ascii_text, feet
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(W, H), pageCompression=1, invariant=1)
    c.setTitle(ascii_text(manifest['name']) + ' - cold-formed steel structural drawings')
    c.setAuthor('Steltic openBIM')

    def text(x, y, t, size=10, color=INK, font='Helvetica'):
        c.setFillColor(color); c.setFont(font, size); c.drawString(x, y, ascii_text(t))

    def wrap(x, y, t, width, size=10, color=INK, lead=1.35):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        cur = ''
        for word in ascii_text(t).split():
            if stringWidth((cur + ' ' + word).strip(), 'Helvetica', size) > width and cur:
                text(x, y, cur, size, color); y -= size * lead; cur = word
            else:
                cur = (cur + ' ' + word).strip()
        if cur:
            text(x, y, cur, size, color); y -= size * lead
        return y
    c.setStrokeColor(INK); c.setLineWidth(1.0); c.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN)
    c.line(MARGIN, MARGIN + TITLE_H, W - MARGIN, MARGIN + TITLE_H)
    text(MARGIN + 18, MARGIN + 66, 'STELTIC / OPENBIM', 13, INK, 'Helvetica-Bold')
    text(MARGIN + 18, MARGIN + 44, 'Cold-formed steel structural design drawings', 10, GREY)
    text(MARGIN + 18, MARGIN + 22, 'DESIGN COORDINATION ISSUE - NOT FOR CONSTRUCTION. To be checked and sealed by a licensed engineer.', 9, ACCENT, 'Helvetica-Bold')
    text(W - 1150, MARGIN + 74, 'PROJECT', 7, GREY); text(W - 1150, MARGIN + 48, manifest['name'], 18, INK, 'Helvetica-Bold')
    text(W - 600, MARGIN + 74, 'SHEET TITLE', 7, GREY); text(W - 600, MARGIN + 50, 'Project composition, key plan and sheet index', 11, INK, 'Helvetica-Bold')
    text(W - 210, MARGIN + 74, 'SHEET', 7, GREY); text(W - 210, MARGIN + 40, 'G-000', 24, INK, 'Helvetica-Bold'); text(W - 210, MARGIN + 18, 'Page 1 of %d' % total, 8, GREY)
    x0, y = MARGIN + 40, H - MARGIN - 50
    text(x0, y, 'PROJECT COMPOSITION', 15, INK, 'Helvetica-Bold'); y -= 24
    y = wrap(x0, y, manifest.get('title') or '', 1050, 11)
    y = wrap(x0, y - 4, 'This set covers %d structurally separate structures. Each part is designed, drawn and checked on its own; its sheets follow this one, stamped with the part letter. '
                        'The parts share the set-out below and no structural member, connection or load path.' % len(parts), 1050, 10, GREY) - 10
    cols = [(0, 'Part'), (50, 'Structure'), (620, 'Design job'), (770, 'Origin of the part in the project system'), (1010, 'Sheets')]
    for dx, t in cols:
        text(x0 + dx, y, t, 9, GREY, 'Helvetica-Bold')
    y -= 6; c.setStrokeColor(LIGHT); c.line(x0, y, x0 + 1080, y); y -= 14
    for p in parts:
        text(x0, y, p['id'], 10, INK, 'Helvetica-Bold'); text(x0 + 50, y, p['title'][:105], 9); text(x0 + 620, y, p['job'], 9)
        text(x0 + 770, y, 'x = %s, y = %s, z = %s' % tuple(feet(v) for v in p['origin_in']), 9); text(x0 + 1010, y, str(p['sheets']), 9); y -= 16
    iface = manifest.get('interface') or {}
    if iface:
        y -= 14; text(x0, y, 'INTERFACE BETWEEN THE PARTS', 13, INK, 'Helvetica-Bold'); y -= 20
        y = wrap(x0, y, iface.get('statement') or '', 1050, 10) - 6
        for dx, t in ((0, 'Clear gap'), (640, 'Axis'), (700, 'Required separation'), (850, 'Gap provided'), (960, 'Measured in the model')):
            text(x0 + dx, y, t, 9, GREY, 'Helvetica-Bold')
        y -= 6; c.line(x0, y, x0 + 1080, y); y -= 14
        for g in gaps:
            text(x0, y, g['label'][:118], 9); text(x0 + 640, y, g['axis'], 9); text(x0 + 700, y, '%.2f in.' % g['required_in'], 9); text(x0 + 850, y, '%.2f in.' % float(g['stated_in']), 9)
            text(x0 + 960, y, '%.2f in.' % g['measured_in'] if g['measured_in'] is not None else 'not facing', 9); y -= 16
    # key plan
    origin = {p['id']: p['origin_in'] for p in manifest['parts']}
    env = {}
    for p in manifest['parts']:
        bs = boxes(packages[p['id']], origin[p['id']])
        env[p['id']] = ([min(b[0][k] for b in bs) for k in range(2)], [max(b[1][k] for b in bs) for k in range(2)])
    lo = [min(e[0][k] for e in env.values()) for k in range(2)]; hi = [max(e[1][k] for e in env.values()) for k in range(2)]
    bx, by, bw, bh = x0, MARGIN + TITLE_H + 60, 1050.0, max(260.0, y - (MARGIN + TITLE_H + 60) - 70)
    sc = min(bw / max(hi[0] - lo[0], 1.0), bh / max(hi[1] - lo[1], 1.0)) * 0.9
    tr = lambda q: (bx + 20 + (q[0] - lo[0]) * sc, by + 10 + (q[1] - lo[1]) * sc)
    text(bx, by + bh + 36, 'KEY PLAN', 13, INK, 'Helvetica-Bold'); text(bx + 110, by + bh + 36, 'part envelopes at the project set-out; x to the right, y up the sheet; 1 : %.0f' % (72.0 / sc), 9, GREY)
    for i, p in enumerate(manifest['parts']):
        (ax, ay), (cx, cy) = tr(env[p['id']][0]), tr(env[p['id']][1])
        c.setStrokeColor(INK if i == 0 else ACCENT); c.setLineWidth(1.2 if i == 0 else 1.0); c.setFillColor(FILL)
        c.rect(ax, ay, cx - ax, cy - ay, stroke=1, fill=0 if i == 0 else 1)
        text(ax + 6, cy - 14 if i else cy + 6, 'PART %s  %s x %s' % (p['id'], feet(env[p['id']][1][0] - env[p['id']][0][0]), feet(env[p['id']][1][1] - env[p['id']][0][1])), 9, INK if i == 0 else ACCENT, 'Helvetica-Bold')
    for p in manifest['parts'][:1]:                      # columns of the first part, as the fixed reference the gaps are measured from
        for blo, bhi in boxes(packages[p['id']], origin[p['id']], ['column']):
            (ax, ay), (cx, cy) = tr(blo), tr(bhi)
            c.setFillColor(BLUE); c.rect(ax, ay, max(cx - ax, 1.2), max(cy - ay, 1.2), stroke=0, fill=1)
    # sheet index
    xi, yi = W / 2.0 + 60, H - MARGIN - 50
    text(xi, yi, 'SHEET INDEX', 15, INK, 'Helvetica-Bold'); yi -= 26
    half = (len(sheet_rows) + 1) // 2
    for k, col in enumerate((sheet_rows[:half], sheet_rows[half:])):
        xx, yy = xi + k * 540, yi
        for dx, t in ((0, 'Page'), (40, 'Part'), (75, 'Sheet'), (130, 'Title')):
            text(xx + dx, yy, t, 8, GREY, 'Helvetica-Bold')
        yy -= 13
        size = 8 if half <= 95 else 6.5
        for r in col:
            text(xx, yy, str(r['page']), size); text(xx + 40, yy, r['part'], size); text(xx + 75, yy, r['number'], size); text(xx + 130, yy, r['title'][:92], size); yy -= size * 1.55
    c.showPage(); c.save()
    return buf.getvalue()


def merge_pdf(output, manifest, parts, gaps, packages):
    from pypdf import PdfReader, PdfWriter
    sheet_rows, page = [dict(page=1, part='-', number='G-000', title='Project composition, key plan and sheet index')], 1
    for p in parts:
        dm = json.loads((output / 'parts' / p['id'] / 'drawing_manifest.json').read_text(encoding='utf-8'))
        p['sheets'] = len(dm['sheets'])
        for s in dm['sheets']:
            page += 1
            sheet_rows.append(dict(page=page, part=p['id'], number=s['number'], title=s['title'], part_page=s['page']))
    total = page
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(cover_page(manifest, parts, gaps, packages, sheet_rows, total))).pages[0])
    k = 1
    for p in parts:
        reader = PdfReader(str(output / 'parts' / p['id'] / 'drawings.pdf'))
        for i, pg in enumerate(reader.pages, 1):
            k += 1
            w, h = float(pg.mediabox.width), float(pg.mediabox.height)
            added = writer.add_page(pg)               # attach first: pypdf edits content only on pages that belong to a writer
            added.merge_page(PdfReader(io.BytesIO(stamp_page(w, h, stamp_text(manifest['name'], p, i, len(reader.pages), k, total)))).pages[0])
    writer.add_metadata({'/Title': manifest['name'] + ' - cold-formed steel structural drawings', '/Author': 'Steltic openBIM'})
    with (output / 'drawings.pdf').open('wb') as stream:
        writer.write(stream)
    return sheet_rows


def stamp_text(name, part, i, n, k, total):
    return '%s  |  PART %s: %s  |  part sheet %d of %d  |  project page %d of %d' % (name, part['id'], part['title'], i, n, k, total)


# ------------------------------------------------------------------------------------------
# model
# ------------------------------------------------------------------------------------------

def merge_ifc(output, manifest, parts):
    import ifcopenshell
    import ifcopenshell.guid
    import ifcopenshell.util.element
    base = None
    remapped = {}
    for p in parts:
        f = ifcopenshell.open(str(output / 'parts' / p['id'] / 'model.ifc'))
        unit = 1.0
        for u in f.by_type('IfcSIUnit'):
            if u.UnitType == 'LENGTHUNIT':
                unit = {None: 1.0, 'MILLI': 0.001, 'CENTI': 0.01}.get(u.Prefix, 1.0)
        off = [float(v) * INCH / unit for v in p['origin_in']]
        if any(abs(v) > 1e-12 for v in off):
            for pl in f.by_type('IfcLocalPlacement'):
                if pl.PlacementRelTo is not None:
                    raise ValueError('part %s: relative placements are not expected in a CFS model' % p['id'])
                rp = pl.RelativePlacement
                loc = [float(v) + off[i] for i, v in enumerate(rp.Location.Coordinates)]
                pl.RelativePlacement = f.create_entity('IfcAxis2Placement3D', f.create_entity('IfcCartesianPoint', loc), rp.Axis, rp.RefDirection)
            for g in f.by_type('IfcGrid'):                           # grid axis curves are drawn in absolute coordinates
                seen = set()
                for fam in ('UAxes', 'VAxes', 'WAxes'):
                    for a in getattr(g, fam) or []:
                        for pt in a.AxisCurve.Points:
                            if pt.id() not in seen:
                                seen.add(pt.id()); cs = list(pt.Coordinates); pt.Coordinates = [float(v) + off[i] for i, v in enumerate(cs)]
        products = [o for o in f.by_type('IfcProduct') if not o.is_a('IfcSpatialStructureElement')]
        tag = f.create_entity('IfcPropertySet', ifcopenshell.guid.new(), None, 'Steltic_Composite', None,
                              [f.create_entity('IfcPropertySingleValue', 'CompositePart', None, f.create_entity('IfcLabel', p['id']), None),
                               f.create_entity('IfcPropertySingleValue', 'CompositePartJob', None, f.create_entity('IfcLabel', p['job']), None)])
        f.create_entity('IfcRelDefinesByProperties', ifcopenshell.guid.new(), None, None, None, products, tag)
        for b in f.by_type('IfcBuilding'):
            b.Name = 'Part %s: %s' % (p['id'], p['title'])
            b.Description = p['job']
        if base is None:
            base = f
            base.by_type('IfcProject')[0].Name = manifest['name']
            used = {e.GlobalId for e in base.by_type('IfcRoot')}
            continue
        proj_b = f.by_type('IfcProject')[0]
        bld_b = f.by_type('IfcBuilding')[0]
        for rel in list(proj_b.IsDefinedBy or []):                    # part-level property sets stay with the part's building
            rel.RelatedObjects = [bld_b if o == proj_b else o for o in rel.RelatedObjects]
        for e in f.by_type('IfcRoot'):
            if e.GlobalId in used:
                new = ifcopenshell.guid.new()
                remapped.setdefault(p['id'], {})[e.GlobalId] = new
                e.GlobalId = new
            used.add(e.GlobalId)
        project = base.by_type('IfcProject')[0]
        ctx = {(c.is_a(), c.ContextType, getattr(c, 'ContextIdentifier', None)): c for c in base.by_type('IfcRepresentationContext')}
        before = {t: len(base.by_type(t)) for t in ('IfcProject', 'IfcUnitAssignment')}
        for e in list(f.by_type('IfcRelationship')) + [o for o in f.by_type('IfcProduct')]:
            base.add(e)
        for copy in [q for q in base.by_type('IfcProject') if q != project]:
            for inv in base.get_inverse(copy):
                ifcopenshell.util.element.replace_attribute(inv, copy, project)
            ua = copy.UnitsInContext
            base.remove(copy)
            if ua is not None and not base.get_inverse(ua):
                base.remove(ua)
        for c in [c for c in base.by_type('IfcRepresentationContext')]:
            keep = ctx.get((c.is_a(), c.ContextType, getattr(c, 'ContextIdentifier', None)))
            if keep is not None and keep != c:
                for inv in base.get_inverse(c):
                    ifcopenshell.util.element.replace_attribute(inv, c, keep)
                base.remove(c)
        if len(base.by_type('IfcProject')) != before['IfcProject']:
            raise ValueError('merging part %s left more than one IfcProject' % p['id'])
    base.write(str(output / 'model.ifc'))
    return remapped


# ------------------------------------------------------------------------------------------
# the composite checks
# ------------------------------------------------------------------------------------------

def verify(output, composite_root, jobs_dir):
    output, composite_root, jobs_dir = Path(output), Path(composite_root), Path(jobs_dir)
    manifest = json.loads((composite_root / 'design' / 'composite.json').read_text(encoding='utf-8'))
    dman = json.loads((output / 'composite_manifest.json').read_text(encoding='utf-8'))
    parts = manifest['parts']
    packages = {p['id']: json.loads((output / 'parts' / p['id'] / 'source.json').read_text(encoding='utf-8')) for p in parts}
    checks = []

    c = Check('parts_certified', 'every part delivered with a passing ten-check certificate, for the files the project report was built from')
    certs = {}
    for p in parts:
        d = output / 'parts' / p['id']
        cert = json.loads((d / 'delivery_certificate.json').read_text(encoding='utf-8')) if (d / 'delivery_certificate.json').is_file() else {}
        certs[p['id']] = cert
        c.expect(cert.get('passed') is True and len(cert.get('checks') or []) >= 10 and all(k.get('passed') for k in cert.get('checks') or []), 'part %s: delivery certificate did not pass' % p['id'])
        c.expect(cert.get('building_id') == p['job'], 'part %s: certificate is for %r' % (p['id'], cert.get('building_id')))
        c.expect(cert.get('pdf_sha256') == sha(d / 'drawings.pdf') and cert.get('ifc_sha256') == sha(d / 'model.ifc'), 'part %s: drawings or model changed after its certificate' % p['id'])
        job = jobs_dir / p['job']
        c.expect(sha(job / 'report.html') == p['report_sha256'] == cert.get('report_sha256'), 'part %s: report differs from the one bound into the project' % p['id'])
        c.expect(sha(job / 'design' / 'calc_package_cfs.json') == p['calc_sha256'] == cert.get('calculation_package_sha256'), 'part %s: calculation package differs from the one bound into the project' % p['id'])
        c.expect(sha(job / 'design' / 'bim_package.json') == p['bim_sha256'], 'part %s: physical package differs from the one bound into the project' % p['id'])
    c.expect(sha(composite_root / 'report.html') == manifest.get('report_sha256'), 'project report changed after the composite manifest was written')
    checks.append(c)

    c = Check('report_contains_parts', 'the project report against every part report, the composition table and the interface record')
    _rows, text = read_report(composite_root / 'report.html')
    text_n = norm(text)
    rows_n = [[norm(x) for x in r] for r in _rows]
    for p in parts:
        ptext = body_text(jobs_dir / p['job'] / 'report.html')
        c.expect(norm(ptext) in text_n, 'part %s: its report text is not contained unchanged in the project report' % p['id'])
        c.expect(any(r and r[0] == norm(p['id']) and norm(p['job']) in r and norm('x = %g in., y = %g in., z = %g in.' % tuple(p['origin_in'])) in r for r in rows_n),
                 'part %s: composition table row (job, origin) not found in the project report' % p['id'])
    for g in (manifest.get('interface') or {}).get('clear_gaps') or []:
        c.expect(any(r and r[0] == norm(g['label']) and norm('%.2f' % g['required_in']) in r and norm('%.2f' % float(g['stated_in'])) in r for r in rows_n),
                 'clear gap %r: required / provided values not found in the project report' % g['label'])
    checks.append(c)

    c = Check('drawings_contain_parts', 'the project drawing set against every part drawing set and the sheet index')
    pages = read_pdf(output / 'drawings.pdf')
    total = 1 + sum(len(json.loads((output / 'parts' / p['id'] / 'drawing_manifest.json').read_text(encoding='utf-8'))['sheets']) for p in parts)
    c.expect(len(pages) == total, 'project set has %d pages, expected %d' % (len(pages), total))
    cover = norm(pages[0]) if pages else ''
    k = 1
    for p in parts:
        ppages = read_pdf(output / 'parts' / p['id'] / 'drawings.pdf')
        dm = json.loads((output / 'parts' / p['id'] / 'drawing_manifest.json').read_text(encoding='utf-8'))
        c.expect(len(ppages) == len(dm['sheets']), 'part %s: page count differs from its drawing manifest' % p['id'])
        for i, (pt, s) in enumerate(zip(ppages, dm['sheets']), 1):
            k += 1
            if not c.expect(k <= len(pages), 'part %s sheet %s is missing from the project set' % (p['id'], s['number'])):
                continue
            got = norm(pages[k - 1])
            c.expect(norm(pt) in got or all(norm(line) in got for line in pt.split('\n') if line.strip()), 'part %s sheet %s: page %d of the project set does not carry the sheet unchanged' % (p['id'], s['number'], k))
            c.expect(norm(stamp_text(manifest['name'], p, i, len(ppages), k, total)) in got, 'part %s sheet %s: part stamp missing on project page %d' % (p['id'], s['number'], k))
            c.expect(norm('%d %s %s %s' % (k, p['id'], s['number'], s['title'][:92])) in cover, 'sheet index does not list page %d (%s %s)' % (k, p['id'], s['number']))
        c.expect(norm(p['job']) in cover and norm('x = %s, y = %s, z = %s' % tuple(_feet(v) for v in p['origin_in'])) in cover, 'part %s: job or origin missing on the project sheet' % p['id'])
    checks.append(c)

    c = Check('model_contains_parts', 'every product of every part in the project IFC: class, properties, materials and position moved by the part origin')
    merged = read_ifc(output / 'model.ifc', part_key=True)
    seen = set()
    import ifcopenshell
    mf = ifcopenshell.open(str(output / 'model.ifc'))
    c.expect(len(mf.by_type('IfcProject')) == 1 and mf.by_type('IfcProject')[0].Name == manifest['name'], 'project IFC must hold exactly one IfcProject named %s' % manifest['name'])
    c.expect(len(mf.by_type('IfcBuilding')) == len(parts), 'project IFC has %d buildings for %d parts' % (len(mf.by_type('IfcBuilding')), len(parts)))
    gids = [e.GlobalId for e in mf.by_type('IfcRoot')]
    c.expect(len(gids) == len(set(gids)), 'project IFC has duplicate GlobalIds')
    for p in parts:
        part = read_ifc(output / 'parts' / p['id'] / 'model.ifc')
        o = p['origin_in']
        for (cls, sid), q in part['products'].items():
            m = merged['products'].get((cls, p['id'], sid))
            if not c.expect(m is not None, 'part %s: %s %s is not in the project IFC' % (p['id'], cls, sid)):
                continue
            seen.add((cls, p['id'], sid))
            mp = {k_: v for k_, v in m['props'].items() if k_ not in ('CompositePart', 'CompositePartJob')}
            c.expect(m['cls'] == q['cls'] and mp == q['props'] and sorted(m['materials']) == sorted(q['materials']), 'part %s: %s %s changed class, properties or materials in the project IFC' % (p['id'], cls, sid))
            c.expect(m['props'].get('CompositePartJob') == p['job'], 'part %s: %s %s is not tagged with its part job' % (p['id'], cls, sid))
            c.expect(all(abs(m['origin'][i] - q['origin'][i] - o[i]) <= TOL_SETOUT_IN for i in range(3)), 'part %s: %s %s is not moved by the part origin' % (p['id'], cls, sid))
            if q['points'] is not None:
                ok = m['points'] is not None and len(m['points']) == len(q['points'])
                if ok:
                    for a, b in ((m['points'][0], q['points'][0]), (m['points'][-1], q['points'][-1]), ([min(v[i] for v in m['points']) for i in range(3)], [min(v[i] for v in q['points']) for i in range(3)]),
                                 ([max(v[i] for v in m['points']) for i in range(3)], [max(v[i] for v in q['points']) for i in range(3)])):
                        ok = ok and all(abs(a[i] - b[i] - o[i]) <= TOL_SETOUT_IN for i in range(3))
                c.expect(ok, 'part %s: %s %s geometry differs from the part model moved by the part origin' % (p['id'], cls, sid))
        for name, elev in part['storeys']:
            c.expect(any(n == name and abs(e - elev - o[2]) <= TOL_SETOUT_IN for n, e in merged['storeys']), 'part %s: storey %s is not in the project IFC' % (p['id'], name))
    extra = [k_ for k_ in merged['products'] if k_ not in seen]
    c.expect(not extra, 'project IFC has products that belong to no part: %s' % extra[:5])
    checks.append(c)

    c = Check('interface_matches_model', 'clear gaps between the parts measured in the model against the gaps stated in the report and the separation the interface record requires')
    gaps = gaps_measured(manifest, packages)
    iface = manifest.get('interface') or {}
    c.expect(bool(gaps) or not iface, 'the interface declares no clear gap to check')
    for g in gaps:
        if not c.expect(g['measured_in'] is not None, 'clear gap %r: the two parts do not face each other on axis %s' % (g['label'], g['axis'])):
            continue
        c.expect(g['measured_in'] >= 0.0, 'clear gap %r: the parts overlap by %.2f in.' % (g['label'], -g['measured_in']))
        c.expect(abs(g['measured_in'] - float(g['stated_in'])) <= TOL_GAP_IN, 'clear gap %r: %.2f in. in the model, %.2f in. stated in the report' % (g['label'], g['measured_in'], float(g['stated_in'])))
        c.expect(g['measured_in'] + 1e-6 >= g['required_in'], 'clear gap %r: %.2f in. in the model is less than the %.2f in. required' % (g['label'], g['measured_in'], g['required_in']))
        c.expect(norm('%.2f in.' % g['measured_in']) in cover and norm('%.2f in.' % g['required_in']) in cover, 'clear gap %r: values missing on the project sheet' % g['label'])
    rec = manifest.get('interface_record')
    if iface.get('record'):
        src = json.loads((jobs_dir / next(p['job'] for p in parts if p['id'] == iface['record']['part']) / 'design' / 'calc_package_cfs.json').read_text(encoding='utf-8'))
        c.expect(src.get(iface['record']['key']) == rec, 'interface record in the manifest differs from the part calculation package')
    if not iface:
        c.expect(True, '')
    checks.append(c)

    results = [k_.result() for k_ in checks]
    certificate = dict(schema='steltic.cfs_composite_certificate', version=1, building_id=manifest['name'], passed=all(r['passed'] for r in results), checks=results,
                       parts=[dict(id=p['id'], job=p['job'], passed=bool(certs[p['id']].get('passed')), checks=[dict(name=k_['name'], checked=k_['checked'], passed=k_['passed'], failure_count=k_['failure_count']) for k_ in certs[p['id']].get('checks') or []],
                                   counts=certs[p['id']].get('counts')) for p in parts],
                       pdf_sha256=sha(output / 'drawings.pdf'), ifc_sha256=sha(output / 'model.ifc'), report_sha256=sha(composite_root / 'report.html'),
                       counts=dict(parts=len(parts), sheets=total, members=sum((certs[p['id']].get('counts') or {}).get('members', 0) for p in parts),
                                   panels=sum((certs[p['id']].get('counts') or {}).get('panels', 0) for p in parts), connections=sum((certs[p['id']].get('counts') or {}).get('connections', 0) for p in parts),
                                   design_records=sum((certs[p['id']].get('counts') or {}).get('design_records', 0) for p in parts)),
                       guid_remaps=dman.get('guid_remaps', {}), tolerances=dict(set_out_in=TOL_SETOUT_IN, clear_gap_in=TOL_GAP_IN),
                       scope='Agreement of the project drawings, IFC and report with the certified parts and with one another at the declared set-out. Not a structural design check.')
    write_json(output / 'delivery_certificate.json', certificate)
    return certificate


def body_text(path):
    """Text of the body of a report (tags, scripts and styles removed)."""
    import html
    import re
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    t = t[t.index('<body'):] if '<body' in t else t
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', t, flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))


def _feet(v):
    from .cfs_native_pdf import feet
    return feet(v)


def deliver(composite_root, output, jobs_dir=None, *, check=True):
    from . import cfs_delivery
    composite_root, output = Path(composite_root), Path(output)
    jobs_dir = Path(jobs_dir) if jobs_dir else composite_root.parent
    manifest = json.loads((composite_root / 'design' / 'composite.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != SCHEMA or manifest.get('version') != 1:
        raise ValueError('design/composite.json is not a %s version 1 manifest' % SCHEMA)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'parts').mkdir()
    parts = [dict(p) for p in manifest['parts']]
    for p in parts:
        res = cfs_delivery.deliver(jobs_dir / p['job'], output / 'parts' / p['id'])
        p['passed'] = bool(res.get('passed'))
    packages = {p['id']: json.loads((output / 'parts' / p['id'] / 'source.json').read_text(encoding='utf-8')) for p in parts}
    gaps = gaps_measured(manifest, packages)
    sheet_rows = merge_pdf(output, manifest, parts, gaps, packages)
    remapped = merge_ifc(output, manifest, parts)
    write_json(output / 'composite_manifest.json', dict(schema='steltic.openbim_cfs_composite_delivery', building_id=manifest['name'], parts=[dict(id=p['id'], job=p['job'], origin_in=p['origin_in'], sheets=p['sheets'], passed=p['passed']) for p in parts],
                                                        sheets=sheet_rows, clear_gaps=gaps, guid_remaps=remapped, pdf_sha256=sha(output / 'drawings.pdf'), ifc_sha256=sha(output / 'model.ifc')))
    result = dict(schema='steltic.openbim_cfs_composite_delivery', building_id=manifest['name'], sheets=len(sheet_rows), parts=[p['id'] for p in parts])
    if check:
        cert = verify(output, composite_root, jobs_dir)
        result['passed'] = cert['passed']
        result['checks'] = [dict(name=k['name'], checked=k['checked'], passed=k['passed'], failure_count=k['failure_count']) for k in cert['checks']]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--job-root', required=True, type=Path, help='Composite project folder (holds design/composite.json and report.html)')
    parser.add_argument('--jobs-dir', type=Path, help='Folder holding the part jobs (default: parent of the project folder)')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = deliver(args.job_root, args.output, args.jobs_dir)
    except (OSError, ValueError) as ex:
        parser.exit(1, str(ex) + '\n')
    print(json.dumps(result))
    if not result.get('passed'):
        parser.exit(2, 'CFS composite delivery verification failed. Inspect delivery_certificate.json.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
