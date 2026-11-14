"""Portal-frame sheets of the native CFS drawing set (see ``cfs_native_pdf``).

A CFS portal building is drawn from the same package as a wall-framed one: frame members,
purlins, girts and bracing straps from ``physical.members``; schedule values from
``design_records``.  This module only adds what is specific to the building type: the model
extraction (frames, column lines, purlin / girt lines, braced bays), the plans and elevations,
and the schedule layouts.  Nothing is designed or inferred here.
"""
from collections import Counter, OrderedDict, defaultdict
import math

INK = '#1d2b33'; GREY = '#6c7a80'; LIGHT = '#c9d1d3'; ACCENT = '#a2461f'; BLUE = '#2f6480'; FILL = '#f3e3d9'
W, H = 2383.94, 1683.78
MARGIN = 36.0; TITLE_H = 104.0
FRAME_KINDS = ('column', 'rafter', 'hanger_post', 'knee_brace', 'beam', 'post')      # members drawn on the frame elevation


def profile_extents(profile, profiles):
    """(width along local_y, depth along axis x local_y) of a declared profile, from its declared dimensions."""
    fam, d = profile['family'], profile.get('dimensions') or {}
    if fam == 'built_up':
        lo, hi, depth = [], [], 0.0
        for c in profile['components']:
            q = profiles[c['profile_id']]['dimensions']
            flip = abs(float(c['rotation_deg']) % 360.0 - 180.0) < 1e-6
            u = float(c['offset'][0])
            a, b = (-q['t'] / 2.0, q['b'] - q['t'] / 2.0)
            if flip:
                a, b = -b, -a
            lo.append(u + a); hi.append(u + b); depth = max(depth, q['d'])
        return max(hi) - min(lo), depth
    if fam == 'channel':
        return d['b'], d['d']
    if fam == 'z':
        return 2.0 * d['b'] - d['t'], d['d']
    if fam == 'flat':
        return d['width'], d['thickness']
    if fam == 'box_envelope':
        return d['width'], d['depth']
    return d.get('d', 1.0), d.get('d', 1.0)


def ranges(values):
    """[1, 2, 3, 7, 8] -> '1 to 3, 7, 8'."""
    values = sorted(values); out = []; i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1] == values[j] + 1:
            j += 1
        out.append(str(values[i]) if j == i else ('%d, %d' % (values[i], values[j]) if j == i + 1 else '%d to %d' % (values[i], values[j])))
        i = j + 1
    return ', '.join(out)


def portal_model(package):
    """Frames, column lines, purlin / girt lines and braced bays read from the located members."""
    ph = package['physical']
    profiles = {p['id']: p for p in ph['profiles']}
    frames = defaultdict(list)
    for m in ph['members']:
        if m['kind'] in FRAME_KINDS and m.get('frame') is not None:
            frames[int(m['frame'])].append(m)
    rows = []
    for fi in sorted(frames):
        mem = []
        for m in frames[fi]:
            a, b = sorted(m['axis'], key=lambda p: (p[2], p[0]))
            mem.append(dict(id=m['id'], kind=m['kind'], role=m.get('role') or m['kind'], profile=m['profile_id'], a=[a[0], a[2]], b=[b[0], b[2]], depth=profile_extents(profiles[m['profile_id']], profiles)[1],
                            width=profile_extents(profiles[m['profile_id']], profiles)[0]))
        sig = tuple(sorted((q['kind'], q['profile'], round(q['a'][0], 2), round(q['a'][1], 2), round(q['b'][0], 2), round(q['b'][1], 2)) for q in mem))
        rows.append(dict(frame=fi, y_in=frames[fi][0]['axis'][0][1], members=mem, signature=sig))
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(r['signature'], []).append(r['frame'])
    types = []
    for i, (sig, fis) in enumerate(groups.items(), 1):
        types.append(dict(mark='PF%d' % i, frames=fis, label='Frames %s' % ranges(fis) if len(fis) > 1 else 'Frame %d' % fis[0], members=next(r['members'] for r in rows if r['frame'] == fis[0])))
    col_x = sorted({round(q['a'][0], 3) for r in rows for q in r['members'] if q['kind'] == 'column'})
    ext = [col_x[0], col_x[-1]]

    def nearest(x):
        return min(col_x, key=lambda v: abs(v - x))
    lines = OrderedDict()
    for m in ph['members']:
        if m['kind'] in ('purlin', 'girt'):
            a, b = m['axis']
            key = (m['kind'], round(a[0], 3), round(a[2], 3))
            ln = lines.setdefault(key, dict(kind=m['kind'], x=a[0], z=a[2], profile=m['profile_id'], members=0, y0=min(a[1], b[1]), y1=max(a[1], b[1]),
                                            depth=profile_extents(profiles[m['profile_id']], profiles)[1], column_line=nearest(a[0]) if m['kind'] == 'girt' else None))
            ln['members'] += 1; ln['y0'] = min(ln['y0'], a[1], b[1]); ln['y1'] = max(ln['y1'], a[1], b[1])
    straps = []
    for m in ph['members']:
        if m['kind'] == 'strap' and m.get('plane') in ('wall', 'roof'):
            a, b = m['axis']
            straps.append(dict(id=m['id'], plane=m['plane'], bay=m.get('bay'), a=a, b=b, profile=m['profile_id'], column_line=nearest((a[0] + b[0]) / 2.0) if m['plane'] == 'wall' else None))
    struts = []
    for m in ph['members']:
        if m['kind'] == 'strut':
            a, b = m['axis']
            struts.append(dict(id=m['id'], a=a, b=b, profile=m['profile_id'], column_line=nearest((a[0] + b[0]) / 2.0), z=a[2]))
    bridging = []
    for m in ph['members']:
        if m['kind'] == 'bridging':
            a, b = m['axis']
            bridging.append(dict(id=m['id'], a=a, b=b, profile=m['profile_id'], plane=m.get('plane'), flange=m.get('flange'), column_line=nearest((a[0] + b[0]) / 2.0) if m.get('plane') == 'wall' else None))
    return dict(frames=rows, types=types, column_x=col_x, exterior_x=ext, lines=list(lines.values()), straps=straps, struts=struts, bridging=bridging,
                y=[r['y_in'] for r in rows], top=max(q['b'][1] for r in rows for q in r['members']))


# ------------------------------------------------------------------------------------------
# schedules
# ------------------------------------------------------------------------------------------

def dc_cell(d, num):
    """D/C as the report prints it; a record of existing work outside the design scope has no ratio."""
    if d.get('DC') == 0 and str(d.get('limit_state') or '').startswith('n/a'):
        return 'existing (not in scope)'
    return num(d.get('DC'), 2)


def portal_schedules(package, model, records, num):
    out = OrderedDict()
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'members':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('section') or '-', d.get('selection') or '-', d.get('bracing_assumption') or '-', d.get('limit_state') or '-', dc_cell(d, num)]))
    out['frame_members'] = dict(title='Portal frame member schedule', headers=['Record', 'Section', 'Make-up', 'Bracing of the flanges', 'Governing limit state', 'D/C'], widths=[170, 250, 760, 600, 480, 100], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'connections':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('components') or d.get('selection') or '-', d.get('limit_state') or '-', num(d.get('demand'), 1), num(d.get('capacity'), 2), dc_cell(d, num)]))
    out['connections'] = dict(title='Frame connection schedule', headers=['Record', 'Components', 'Governing limit state', 'Moment (kip-in.)', 'Governing capacity', 'D/C'], widths=[190, 1040, 560, 200, 220, 100], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'anchorage':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('id'), d.get('selection') or '-', num(d.get('V_design_kip'), 2), num(d.get('T_design_kip'), 2), num(d.get('C_design_kip'), 2), d.get('limit_state') or '-', dc_cell(d, num)]))
    out['anchorage'] = dict(title='Column base and anchorage schedule (reactions per column base)', headers=['Record', 'Base', 'V (kip)', 'T uplift (kip)', 'C (kip)', 'Governing limit state', 'D/C'],
                            widths=[190, 980, 150, 170, 150, 560, 100], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'schedules':
            for q in r['data'].get('rows') or []:
                rows.append(dict(record=r['id'], cells=[q.get('id'), q.get('member') or '-', q.get('section') or '-', q.get('limit_state') or '-', num(q.get('DC'), 2)]))
            if not r['data'].get('rows'):                # a schedule with no designed rows (existing work): its scope statement
                rows.append(dict(record=r['id'], cells=[r['data'].get('id'), str(r['data'].get('schedule') or '-'), r['data'].get('selection') or '-', r['data'].get('limit_state') or '-', dc_cell(r['data'], num)]))
    out['secondary'] = dict(title='Purlin, girt, flange brace and bracing strap schedule', headers=['Row', 'Member', 'Section and connection', 'Governing limit state', 'D/C'], widths=[240, 480, 940, 600, 100], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'drift_table':
            d = r['data']
            if d.get('value_in') is not None and d.get('limit_in') is not None:
                rows.append(dict(record=r['id'], cells=[str(d.get('check')).replace('_', ' '), d.get('criterion') or '-', num(d.get('value_in'), 3), num(d.get('limit_in'), 3), num(d.get('DC'), 2)]))
    if rows:
        out['serviceability'] = dict(title='Serviceability schedule', headers=['Check', 'Criterion', 'Deflection (in.)', 'Limit (in.)', 'Ratio'], widths=[300, 1300, 220, 220, 120], rows=rows)
    rows = []
    for r in package.get('design_records', []):
        if r['table'] == 'materials':
            d = r['data']
            rows.append(dict(record=r['id'], cells=[d.get('item') or '-', d.get('spec') or '-', d.get('strength') or '-', d.get('used') or '-']))
    out['materials'] = dict(title='Materials', headers=['Item', 'Specification', 'Strength', 'Used for'], widths=[470, 560, 560, 560], rows=rows)
    return out


NOTES = ['These drawings are produced directly from the physical model and calculation records of the completed design; every schedule value is the value printed in the design report for the same record.',
         'Dimensions are to frame lines, column lines and member worklines (section centroids). Member lengths are design worklines, not shop cut lengths. Do not scale.',
         'Cold-formed steel members are designated per SFIA (e.g. 1200S250-118: 12 in. web, 2-1/2 in. flange, 118 mil; Z for zee purlins and girts). A built-up frame member "n x section" is n channels in back-to-back pairs placed side by side.',
         'Every frame of a frame type (PF mark) is identical; the frame elevation gives the frame lines it applies to.',
         'Bracing straps are tension-only X-bracing in the bays marked on the plans and side-wall elevations. Roof and wall cladding is not relied on as a diaphragm unless the design basis states otherwise.',
         'Foundations, concrete anchorage, end-wall and door framing and items marked as delegated are by others for the demands tabulated in the schedules.',
         'Design coordination issue: not for construction or fabrication. All design output must be independently checked and sealed by a licensed professional engineer.']


# ------------------------------------------------------------------------------------------
# sheets
# ------------------------------------------------------------------------------------------

def _grid(sh, tr, pm, feet, xlo, xhi):
    """Frame lines (numbered) and column lines (lettered) on a plan whose horizontal axis is the building length."""
    for r in pm['frames']:
        a, b = tr(r['y_in'], xlo), tr(r['y_in'], xhi)
        sh.line((a[0], a[1] - 30), (b[0], b[1] + 46), GREY, 0.35, [9, 4])
        sh.bubble(b[0], b[1] + 62, str(r['frame']), 13)
    y0, y1 = pm['y'][0], pm['y'][-1]
    for i, x in enumerate(pm['column_x']):
        a, b = tr(y0, x), tr(y1, x)
        sh.line((a[0] - 60, a[1]), (b[0] + 30, b[1]), GREY, 0.35, [9, 4])
        sh.bubble(a[0] - 76, a[1], chr(65 + i), 13)


def _plan_dims(sh, tr, pm, xlo, xhi):
    ys = pm['y']
    for a, b in zip(ys, ys[1:]):
        sh.dim(tr(a, xlo), tr(b, xlo), b - a, offset=(0, -52), kind='frame_spacing', size=8)
    sh.dim(tr(ys[0], xlo), tr(ys[-1], xlo), ys[-1] - ys[0], offset=(0, -90), kind='building_length')
    cx = pm['column_x']
    for a, b in zip(cx, cx[1:]):
        sh.dim(tr(ys[-1], a), tr(ys[-1], b), b - a, offset=(70, 0), kind='span')
    if len(cx) > 2:
        sh.dim(tr(ys[-1], cx[0]), tr(ys[-1], cx[-1]), cx[-1] - cx[0], offset=(112, 0), kind='building_width')


def _plan_box():
    return (MARGIN + 230, MARGIN + TITLE_H + 330, W - 2 * MARGIN - 470, H - 2 * MARGIN - TITLE_H - 520)


def draw_base_plan(sh, package, model, number, feet):
    pm = model['portal']
    xlo, xhi = pm['column_x'][0], pm['column_x'][-1]
    tr, den = sh.view(_plan_box(), ((pm['y'][0], pm['y'][-1]), (xlo, xhi)))
    sh.rows[-1]['scale'] = '1:%d' % den
    k = 72.0 / den
    _grid(sh, tr, pm, feet, xlo, xhi)
    n = 0
    for r in pm['frames']:
        for q in r['members']:
            if q['kind'] == 'column':
                c = tr(r['y_in'], q['a'][0]); w, d = max(5.0, q['width'] * k), max(5.0, q['depth'] * k)
                sh.poly([(c[0] - w / 2, c[1] - d / 2), (c[0] + w / 2, c[1] - d / 2), (c[0] + w / 2, c[1] + d / 2), (c[0] - w / 2, c[1] + d / 2)], INK, 0.9, fill=FILL)
                n += 1
    bays = defaultdict(set)
    for s in pm['straps']:
        if s['plane'] == 'wall':
            bays[(s['column_line'], min(s['a'][1], s['b'][1]), max(s['a'][1], s['b'][1]))].add(s['id'])
    for (x, y0, y1), ids in sorted(bays.items()):
        off = -14 if x <= (xlo + xhi) / 2.0 else 14
        a, b = tr(y0, x), tr(y1, x)
        sh.line((a[0], a[1] + off), (b[0], b[1] + off), ACCENT, 2.4)
        sh.text((a[0] + b[0]) / 2.0, a[1] + off + (-13 if off < 0 else 6), 'XB', 10, ACCENT, 'Helvetica-Bold', 'middle')
    _plan_dims(sh, tr, pm, xlo, xhi)
    x = MARGIN + 60; y = MARGIN + TITLE_H + 150
    sh.text(x, y, 'COLUMN BASE AND BRACING PLAN', 13, font='Helvetica-Bold'); y -= 20
    txt = '%d column bases on %d frame lines and %d column lines.' % (n, len(pm['frames']), len(pm['column_x']))
    sh.text(x, y, txt, 11); y -= 16
    sh.cells.append(dict(sheet=number, schedule='plan_counts', record=None, text=txt, cells=['column bases', str(n), str(len(pm['frames'])), str(len(pm['column_x']))]))
    walls = Counter((s['column_line'], s['profile']) for s in pm['straps'] if s['plane'] == 'wall')
    for (cl, prof), cnt in sorted(walls.items()):
        nb = len({k_ for k_ in bays if k_[0] == cl})
        txt = 'XB on column line %s: %d braced bays, %d straps %s (X pattern, tension only).' % (chr(65 + pm['column_x'].index(cl)), nb, cnt, prof)
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='strap_counts', record=None, text=txt, cells=['wall', chr(65 + pm['column_x'].index(cl)), prof, str(nb), str(cnt)]))
    for st in pm['struts']:
        sh.line(tr(st['a'][1], st['a'][0]), tr(st['b'][1], st['b'][0]), BLUE, 1.2)
    for (cl, prof, z), cnt in sorted(Counter((st['column_line'], st['profile'], round(st['z'], 2)) for st in pm['struts']).items()):
        txt = 'Struts (blue) on column line %s at %s above the base: %d x %s.' % (chr(65 + pm['column_x'].index(cl)), feet(z), cnt, prof)
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='strut_counts', record=None, text=txt, cells=[chr(65 + pm['column_x'].index(cl)), prof, str(cnt)]))
    sh.text(x, y, 'Column bases: see the base detail and the anchorage schedule. Foundations by others.', 11, GREY)


def draw_roof_plan(sh, package, model, number, feet):
    pm = model['portal']
    xlo, xhi = pm['column_x'][0], pm['column_x'][-1]
    tr, den = sh.view(_plan_box(), ((pm['y'][0], pm['y'][-1]), (xlo, xhi)))
    sh.rows[-1]['scale'] = '1:%d' % den
    _grid(sh, tr, pm, feet, xlo, xhi)
    for ln in pm['lines']:
        if ln['kind'] == 'purlin':
            sh.line(tr(ln['y0'], ln['x']), tr(ln['y1'], ln['x']), BLUE, 0.45)
    nraf = 0
    for r in pm['frames']:
        for q in r['members']:
            if q['kind'] == 'rafter':
                sh.line(tr(r['y_in'], q['a'][0]), tr(r['y_in'], q['b'][0]), INK, 1.5); nraf += 1
    for s in pm['straps']:
        if s['plane'] == 'roof':
            sh.line(tr(s['a'][1], s['a'][0]), tr(s['b'][1], s['b'][0]), ACCENT, 1.1)
    _plan_dims(sh, tr, pm, xlo, xhi)
    x = MARGIN + 60; y = MARGIN + TITLE_H + 150
    sh.text(x, y, 'ROOF FRAMING PLAN', 13, font='Helvetica-Bold'); y -= 20
    txt = '%d rafters on %d frame lines.' % (nraf, len(pm['frames']))
    sh.text(x, y, txt, 11); y -= 16
    sh.cells.append(dict(sheet=number, schedule='plan_counts', record=None, text=txt, cells=['rafters', str(nraf), str(len(pm['frames']))]))
    pur = [ln for ln in pm['lines'] if ln['kind'] == 'purlin']
    for prof in sorted({ln['profile'] for ln in pur}):
        sel = [ln for ln in pur if ln['profile'] == prof]
        txt = 'Purlins (blue): %s, %d lines, %d members.' % (prof, len(sel), sum(ln['members'] for ln in sel))
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='line_counts', record=None, text=txt, cells=['purlin', prof, str(len(sel)), str(sum(ln['members'] for ln in sel))]))
    roof = Counter(s['profile'] for s in pm['straps'] if s['plane'] == 'roof')
    for prof, cnt in sorted(roof.items()):
        nb = len({s['bay'] for s in pm['straps'] if s['plane'] == 'roof' and s['profile'] == prof})
        txt = 'Roof-plane bracing (accent): %d braced bays, %d straps %s (X pattern, tension only).' % (nb, cnt, prof)
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='strap_counts', record=None, text=txt, cells=['roof', '-', prof, str(nb), str(cnt)]))
    roofb = [b for b in pm['bridging'] if b['plane'] == 'roof']
    for b in roofb:
        if b['flange'] == 'outer':
            sh.line(tr(b['a'][1], b['a'][0]), tr(b['b'][1], b['b'][0]), GREY, 0.5, [4, 3])
    for prof, cnt in sorted(Counter(b['profile'] for b in roofb).items()):
        txt = 'Purlin brace lines (grey dashed, one strap on each flange): %d straps %s.' % (cnt, prof)
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='bridging_counts', record=None, text=txt, cells=['roof', '-', prof, str(cnt)]))
    pd = package['design_context']['physical_design']
    if pd.get('purlins'):
        lap = float(pd['purlins'].get('lap_ft') or 0.0)
        sh.text(x, y, 'Purlin set-out along the slope is on the frame elevation. ' + ('Purlins are lapped %s each side of every interior frame.' % feet(lap * 12.0) if lap else 'Purlins are simple spans between frames.'), 11, GREY)


def draw_frame(sh, package, model, number, ftype, feet, num):
    pm = model['portal']
    xlo, xhi = pm['column_x'][0], pm['column_x'][-1]
    top = pm['top']
    box = (MARGIN + 330, MARGIN + TITLE_H + 250, W - 2 * MARGIN - 1100, H - 2 * MARGIN - TITLE_H - 400)
    tr, den = sh.view(box, ((xlo, xhi), (0.0, top)))
    sh.rows[-1]['scale'] = '1:%d' % den
    for l in model['levels']:
        a, b = tr(xlo, l['elevation_in']), tr(xhi, l['elevation_in'])
        sh.line((a[0] - 250, a[1]), (b[0] + 60, b[1]), GREY, 0.4, [10, 4])
        sh.text(a[0] - 250, a[1] + 5, '%s  %s' % (l['name'], feet(l['elevation_in'])), 10.5, font='Helvetica-Bold')
    for q in ftype['members']:
        a, b = q['a'], q['b']
        L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        n = [-(b[1] - a[1]) / L * q['depth'] / 2.0, (b[0] - a[0]) / L * q['depth'] / 2.0]
        sh.poly([tr(a[0] + n[0], a[1] + n[1]), tr(b[0] + n[0], b[1] + n[1]), tr(b[0] - n[0], b[1] - n[1]), tr(a[0] - n[0], a[1] - n[1])], INK, 1.0, fill=FILL)
        sh.line(tr(*a), tr(*b), GREY, 0.3, [12, 3, 2, 3])
    k = 72.0 / den
    for ln in pm['lines']:
        c = tr(ln['x'], ln['z']); h = max(3.0, ln['depth'] * k / 2.0)
        sh.poly([(c[0] - h, c[1] - h), (c[0] + h, c[1] - h), (c[0] + h, c[1] + h), (c[0] - h, c[1] + h)], BLUE, 0.7)
    cx = pm['column_x']
    for a, b in zip(cx, cx[1:]):
        sh.dim(tr(a, 0.0), tr(b, 0.0), b - a, offset=(0, -46), kind='span')
    if len(cx) > 2:
        sh.dim(tr(cx[0], 0.0), tr(cx[-1], 0.0), cx[-1] - cx[0], offset=(0, -84), kind='building_width')
    lv = model['levels']
    for i, (a, b) in enumerate(zip(lv, lv[1:])):
        sh.dim(tr(xhi, a['elevation_in']), tr(xhi, b['elevation_in']), b['elevation_in'] - a['elevation_in'], offset=(96, 0), kind='level_height')
    sh.dim(tr(xhi, 0.0), tr(xhi, top), top, offset=(150, 0), kind='overall_height')
    # joints: detail references by family
    refs = {d['family']: d['reference'] for d in model['details']}
    ends = defaultdict(list)
    for q in ftype['members']:
        ends[(round(q['a'][0], 2), round(q['a'][1], 2))].append(q['kind']); ends[(round(q['b'][0], 2), round(q['b'][1], 2))].append(q['kind'])
    for (x_, z_), kinds in sorted(ends.items()):
        fam = 'column base' if (kinds == ['column'] and z_ < 1.0) else (('valley bracket' if (kinds.count('rafter') == 2 and 'valley bracket' in refs) else 'knee bracket') if ('column' in kinds and 'rafter' in kinds)
                                                                    else ('apex bracket' if kinds.count('rafter') == 2 else None))
        if fam and fam in refs:
            c = tr(x_, z_)
            sh.c.setFillColor('#ffffff'); sh.c.rect(c[0] + 16, c[1] + 12, 44, 17, stroke=0, fill=1)
            sh.text(c[0] + 38, c[1] + 16, refs[fam], 11, ACCENT, 'Helvetica-Bold', 'middle')
    # set-out of purlins along each rafter and girts up each exterior column
    x = W - MARGIN - 700; y = H - MARGIN - 60
    sh.text(x, y, '%s  -  %s' % (ftype['mark'], ftype['label'].upper()), 15, font='Helvetica-Bold'); y -= 26
    counts = Counter((q['role'], q['profile']) for q in ftype['members'])
    for (role, prof), cnt in sorted(counts.items()):
        txt = '%d x %s per frame: %s (%d in the %d frames)' % (cnt, role, prof, cnt * len(ftype['frames']), len(ftype['frames']))
        y = sh.wrap(x, y, txt, 660, 11) - 3
        sh.cells.append(dict(sheet=number, schedule='frame_counts', record=None, text=txt, cells=[ftype['mark'], role, prof, str(cnt), str(len(ftype['frames'])), str(cnt * len(ftype['frames']))]))
    y -= 8
    records = {r['id']: r for r in package.get('design_records', [])}
    for r in package.get('design_records', []):
        if r['table'] == 'members':
            d = r['data']
            sh.text(x, y, r['id'], 11, BLUE, 'Helvetica-Bold'); y -= 16
            y = sh.wrap(x, y, d.get('selection') or d.get('section') or '-', 660, 10.5) - 3
            y = sh.wrap(x, y, 'Bracing: %s' % (d.get('bracing_assumption') or '-'), 660, 10.5) - 8
    pur = sorted([ln for ln in pm['lines'] if ln['kind'] == 'purlin'], key=lambda l: l['x'])
    gir = sorted([ln for ln in pm['lines'] if ln['kind'] == 'girt'], key=lambda l: (l['column_line'], l['z']))
    if pur:
        sp = sorted({round(math.hypot(b['x'] - a['x'], b['z'] - a['z']), 2) for a, b in zip(pur, pur[1:]) if (b['z'] - a['z']) * (pur[1]['z'] - pur[0]['z']) > 0})
        txt = 'Purlins (blue squares): %d lines, %s; spacing along the slope %s.' % (len(pur), ', '.join(sorted({l['profile'] for l in pur})), ' / '.join(feet(v) for v in sp[:3]))
        y = sh.wrap(x, y, txt, 660, 10.5) - 3
    if gir:
        zs = sorted({round(l['z'], 2) for l in gir})
        txt = 'Girts (blue squares): %d lines, %s; heights above the base %s.' % (len(gir), ', '.join(sorted({l['profile'] for l in gir})), ', '.join(feet(v) for v in zs[:8]))
        y = sh.wrap(x, y, txt, 660, 10.5) - 3
    sh.wrap(x, y - 8, 'Detail references (accent) are the knee, apex and base assemblies of the typical details. Chain lines are the analysed member worklines.', 660, 10, color=GREY)


def draw_side(sh, package, model, number, cl, feet):
    """Side-wall elevation on an exterior column line: columns, girts and wall bracing."""
    pm = model['portal']
    ys = pm['y']
    cols = [(r['y_in'], q) for r in pm['frames'] for q in r['members'] if q['kind'] == 'column' and abs(q['a'][0] - cl) < 0.01]
    eave = max(q['b'][1] for _y, q in cols)
    box = (MARGIN + 230, MARGIN + TITLE_H + 330, W - 2 * MARGIN - 470, H - 2 * MARGIN - TITLE_H - 620)
    tr, den = sh.view(box, ((ys[0], ys[-1]), (0.0, eave)))
    sh.rows[-1]['scale'] = '1:%d' % den
    for l in model['levels']:
        if l['elevation_in'] <= eave + 1e-6:
            a, b = tr(ys[0], l['elevation_in']), tr(ys[-1], l['elevation_in'])
            sh.line((a[0] - 150, a[1]), (b[0] + 40, b[1]), GREY, 0.4, [10, 4])
            sh.text(a[0] - 150, a[1] + 5, '%s  %s' % (l['name'], feet(l['elevation_in'])), 10.5, font='Helvetica-Bold')
    gir = [ln for ln in pm['lines'] if ln['kind'] == 'girt' and abs(ln['column_line'] - cl) < 0.01]
    for ln in gir:
        sh.line(tr(ln['y0'], ln['z']), tr(ln['y1'], ln['z']), BLUE, 0.7)
    for y_, q in cols:
        sh.line(tr(y_, q['a'][1]), tr(y_, q['b'][1]), INK, 1.8)
        fr = next(r['frame'] for r in pm['frames'] if r['y_in'] == y_)
        c = tr(y_, eave); sh.bubble(c[0], c[1] + 40, str(fr), 13)
    st = [s for s in pm['straps'] if s['plane'] == 'wall' and abs(s['column_line'] - cl) < 0.01]
    for s in st:
        sh.line(tr(s['a'][1], s['a'][2]), tr(s['b'][1], s['b'][2]), ACCENT, 1.3)
    doors = [d for d in (package['design_context']['physical_design'].get('doors') or []) if pm['column_x'][int(d['line']) - 1] == cl]
    for d in doors:
        mid = (ys[int(d['bay']) - 1] + ys[int(d['bay'])]) / 2.0; hw = float(d['width_ft']) * 6.0; hh = float(d['height_ft']) * 12.0
        sh.poly([tr(mid - hw, 0.0), tr(mid + hw, 0.0), tr(mid + hw, hh), tr(mid - hw, hh)], GREY, 0.8, dash=[6, 3])
        c = tr(mid, hh / 2.0); sh.text(c[0], c[1], 'DOOR', 9, GREY, 'Helvetica-Bold', 'middle')
    for a, b in zip(ys, ys[1:]):
        sh.dim(tr(a, 0.0), tr(b, 0.0), b - a, offset=(0, -46), kind='frame_spacing', size=8)
    sh.dim(tr(ys[0], 0.0), tr(ys[-1], 0.0), ys[-1] - ys[0], offset=(0, -84), kind='building_length')
    sh.dim(tr(ys[-1], 0.0), tr(ys[-1], eave), eave, offset=(70, 0), kind='eave_height')
    x = MARGIN + 60; y = MARGIN + TITLE_H + 150
    label = chr(65 + pm['column_x'].index(cl))
    sh.text(x, y, 'SIDE WALL ON COLUMN LINE %s' % label, 13, font='Helvetica-Bold'); y -= 20
    txt = '%d columns.' % len(cols)
    sh.text(x, y, txt, 11); y -= 16
    sh.cells.append(dict(sheet=number, schedule='side_counts', record=None, text=txt, cells=[label, 'columns', '-', str(len(cols))]))
    for prof in sorted({ln['profile'] for ln in gir}):
        sel = [ln for ln in gir if ln['profile'] == prof]
        txt = 'Girts (blue): %s, %d lines, %d members; heights above the base %s.' % (prof, len(sel), sum(ln['members'] for ln in sel), ', '.join(feet(v) for v in sorted({round(l['z'], 2) for l in sel})))
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='line_counts', record=None, text=txt, cells=['girt:' + label, prof, str(len(sel)), str(sum(ln['members'] for ln in sel))]))
    for prof, cnt in sorted(Counter(s['profile'] for s in st).items()):
        txt = 'Wall bracing (accent): %d straps %s in %d braced bays.' % (cnt, prof, len({s['bay'] for s in st if s['profile'] == prof}))
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='side_counts', record=None, text=txt, cells=[label, 'straps', prof, str(cnt)]))
    wallb = [b for b in pm['bridging'] if b['plane'] == 'wall' and abs(b['column_line'] - cl) < 0.01]
    for b in wallb:
        if b['flange'] == 'outer':
            sh.line(tr(b['a'][1], b['a'][2]), tr(b['b'][1], b['b'][2]), GREY, 0.5, [4, 3])
    for prof, cnt in sorted(Counter(b['profile'] for b in wallb).items()):
        txt = 'Girt brace lines (grey dashed, one strap on each flange): %d straps %s.' % (cnt, prof)
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='bridging_counts', record=None, text=txt, cells=['wall', label, prof, str(cnt)]))
    if doors:
        sizes = sorted({(float(d['width_ft']), float(d['height_ft'])) for d in doors})
        txt = 'Door openings (dashed): %d, %s, in bays %s; door framing by the building supplier, girts below the door head stop at the door bays.' % (
            len(doors), ' and '.join('%s x %s' % (feet(w * 12.0), feet(h * 12.0)) for w, h in sizes), ', '.join(str(d['bay']) for d in sorted(doors, key=lambda d: d['bay'])))
        sh.text(x, y, txt, 11); y -= 16
        sh.cells.append(dict(sheet=number, schedule='door_counts', record=None, text=txt, cells=[label, str(len(doors))]))
    if not gir and not st:
        sh.text(x, y, 'No girts or wall bracing on this line (open side).', 11, GREY)


def sheet_plan(model):
    """Sheet register entries specific to a portal building: (number, title, what)."""
    pm = model['portal']
    plan = [('S-100', 'Column base and bracing plan', ('portal_base',)), ('S-101', 'Roof framing plan', ('portal_roof',))]
    for i, t in enumerate(pm['types'], 1):
        plan.append(('S-%d' % (200 + i), 'Portal frame elevation %s: %s' % (t['mark'], t['label']), ('portal_frame', t)))
    for i, cl in enumerate(pm['exterior_x'], 1):
        plan.append(('S-%d' % (250 + i), 'Side wall elevation: column line %s' % chr(65 + pm['column_x'].index(cl)), ('portal_side', cl)))
    return plan
