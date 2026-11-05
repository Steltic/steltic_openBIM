"""Located source collector bars, with explicit fictional lap/cover proposals.

This fixture does not design reinforcement. Source counts, diameter and grade
remain separate from adopted bar stock lengths, laps, cover and development.
The separate diaphragm record remains unmapped until its complete reinforcement
and deck attachment system has been represented.
"""
import copy
import math
import re
from .review_receiver_geometry import extract, horizontal_frame
from .pilots.model import sub


def stock_runs(start, end, stock, lap):
    if not 0 < lap < stock or end <= start:
        raise ValueError('Invalid collector stock/lap geometry')
    result = []
    while start < end - 1e-8:
        stop = min(end, start + stock)
        result.append((start, stop))
        if stop == end:
            break
        start = stop - lap
    return result


def openings_on_line(b, panel, along, station, start, end, radius):
    """Never run a selected collector through an accepted floor opening."""
    by_id = {o['id']: o for o in b.openings}
    for ident in panel.get('openings', []):
        opening = by_id[ident]
        if opening.get('plane') != 'xy':
            raise ValueError('Floor opening without its plan geometry: ' + ident)
        lo = [opening['x_ft'] * 12, opening['y_ft'] * 12]
        hi = [lo[0] + opening['width_ft'] * 12,
              lo[1] + opening['height_ft'] * 12]
        if lo[1-along]-radius < station < hi[1-along]+radius and max(start, lo[along]-radius) < min(end, hi[along]+radius):
            return ident
    return None


def apply(b):
    if b.key != 'cfs4':
        return
    floors = [p for p in b.panels if p['kind'] == 'floor']
    if len(floors) != 3 or any(p['thickness_in'] != 4 for p in floors):
        raise ValueError('CFS4 source collector scope requires its three 4 in deck/fill floors')
    diameter = .625
    profile = b.custom('REBAR-5', 'round', dict(d=diameter),
                       basis='S: source #5 reinforcing-bar nominal diameter; ribs omitted')
    b.material_selections = getattr(b, 'material_selections', [])
    b.material_selections.append(dict(id='CFS4-REBAR-GR60', basis='S',
        specification='Source Gr 60 reinforcing steel; product standard is not inferred'))
    b.material_selections.extend([
        dict(id='CFS4-LWC',basis='S',specification="Source lightweight concrete,110 pcf,f'c=3000 psi",
             source_selection_text=b.records['diaphragms/diaphragm-floors']['data']['selection']),
        dict(id='CFS4-DECK',basis='S',specification='Source ASTM A653 SS Gr33,20 ga composite steel deck,1.5 in nominal profile depth',
             source_configuration_field='cfg.materials / Floor deck and fill')])
    source_openings={o['id']:o for o in b.openings}
    for panel in floors:
        before=copy.deepcopy(panel)
        panel.update(thickness_in=2.5,material_id='CFS4-LWC',basis='S thickness/material; A footprint/openings',
            floor_stack_id='CFS4-FLOOR-'+str(panel['level']),reference_line='top surface of concrete topping',
            thickness_direction='negative_global_z')
        deck=b.panel('DECK-'+str(panel['level']),'deck',[[q[0],q[1],q[2]-2.5] for q in panel['vertices']],1.5,
            panel['level'],'S nominal depth/material; A footprint/openings',material_id='CFS4-DECK',
            floor_stack_id=panel['floor_stack_id'],reference_line='top of deck ribs',thickness_direction='negative_global_z',
            openings=[],sheet_gauge=20,
            representation='Source profile-depth envelope; rib geometry and deck attachments remain supplier/engineer requirements')
        for oid in panel.get('openings',[]):
            opening=source_openings[oid]
            if opening.get('plane')!='xy' or abs(opening['z_ft']*12-panel['vertices'][0][2])>.001:
                raise ValueError('Floor-stack opening needs its actual top-surface datum: '+oid)
            opening['host_id']=panel['id']
            lower=copy.deepcopy(opening)
            lower.update(id=oid+':DECK',host_id=deck['id'],z_ft=opening['z_ft']-2.5/12,
                parent_opening_id=oid,floor_stack_id=panel['floor_stack_id'],
                representation='Same accepted through-floor void at the explicitly lower deck datum')
            b.openings.append(lower);deck['openings'].append(lower['id'])
        b.changes.append(dict(kind='source_deck_fill_layers',host_panel_id=panel['id'],deck_panel_id=deck['id'],
            previous_panel=before,basis='Separate source2.5 in concrete topping from1.5 in deck depth below the retained finished-floor datum; no new deck capacity or rib selection.'))
    b.endpoint_links = getattr(b, 'endpoint_links', [])
    selected = [r for r in b.records.values() if r['table'] == 'collectors']
    for record in selected:
        data = record['data'];rid = record['id']
        match = re.fullmatch(r'(\d+) #5 collector bars in the topping along the line \(continuous, lap-spliced\)', data['member'])
        if not match or '#5 Gr 60 bars in the 2.5 in. topping' not in data['selection']:
            raise ValueError('Unrecognized concrete collector selection: ' + rid)
        count = int(match[1]);along = 'XY'.index(data['direction'])
        line = next(v for v in b.cfg['lines_x' if along == 0 else 'lines_y'] if v['name'] == data['line'])
        station = line['pos'] * 12
        for panel in floors:
            level = panel['level'];z = panel['vertices'][0][2]
            low = [min(q[i] for q in panel['vertices']) for i in (0, 1)]
            high = [max(q[i] for q in panel['vertices']) for i in (0, 1)]
            for index in range(count):
                if abs(station-low[1-along]) < .001:
                    offset = 2 + 2*index
                elif abs(station-high[1-along]) < .001:
                    offset = -2 - 2*index
                else:
                    offset = (index-(count-1)/2)*2
                runs = stock_runs(low[along]+3, high[along]-3, 240, 25)
                # Do not partially bind a source bar if its path crosses a void.
                for piece, (start, end) in enumerate(runs):
                    cross = station+offset+(-1 if piece % 2 == 0 else 1)*diameter/2
                    opening = openings_on_line(b, panel, along, cross, start, end, diameter/2)
                    if opening:
                        raise ValueError(f'{rid} crosses {opening}; an explicit collector route is required')
                made = []
                for piece, (start, end) in enumerate(runs):
                    cross = station+offset+(-1 if piece % 2 == 0 else 1)*diameter/2
                    height = z-1.25-along*diameter
                    a = [start, cross, height] if along == 0 else [cross, start, height]
                    d = [end, cross, height] if along == 0 else [cross, end, height]
                    mid = f'COLLECTOR-{data["line"]}-L{level}-B{index+1}-P{piece+1}'
                    m = b.member(mid, profile, 'diaphragm_collector_bar', a, d, level,
                        records=[rid], host_panel_id=panel['id'], source_bar_index=index+1,
                        source_bar_count=count, source_line=data['line'],
                        geometry_basis='S count, diameter and grade; A stock lengths, lap stations, lateral placement and vertical layers')
                    m['material_id'] = 'CFS4-REBAR-GR60';made.append(m)
                    point = [(x+y)/2 for x,y in zip(a,d)]
                    cid = mid+':BOND'
                    b.connection(cid, 'review_collector_bond', point, [m], [rid],
                        parameters=dict(host_panel_id=panel['id'], slab_top_in=z, topping_in=2.5),
                        title='SOURCE COLLECTOR BAR / A BOND AND COVER FIT')
                    for end_name in ('start','end'):
                        b.endpoint_links.append(dict(member_id=mid, end=end_name, connection_id=cid,
                            basis='This physical bar end is embedded in its actual host topping. Bond is represented along the bar; anchorage capacity is unverified.'))
                for left,right in zip(made,made[1:]):
                    start = right['axis'][0][along];end = left['axis'][1][along]
                    point = [(x+y)/2 for x,y in zip(left['axis'][1],right['axis'][0])]
                    b.connection(left['id']+':LAP', 'review_collector_lap', point, [left,right], [rid],
                        parameters=dict(host_panel_id=panel['id'], slab_top_in=z, topping_in=2.5,
                                        lap_in=end-start), title='SOURCE COLLECTOR / A CONTACT LAP')
            b.changes.append(dict(kind='source_concrete_collector', record_id=rid, host_panel_id=panel['id'],
                line=data['line'], source_bar_count=count, diameter_in=diameter,
                basis='S: source count, #5 diameter and Gr 60. A: 20 ft maximum pieces, 25 in contact laps, 2 in bar-line spacing, 3 in end margins and two vertical layers. No development, cover or capacity verification. Source deck-to-blocking screw schedule remains a separate component requirement.'))
    b.note('CONCRETE-COLLECTORS',
        'S: each floor collector line retains its specific 2, 3 or 4 #5 Gr 60 bars. Those specific checks supersede the generic #4 collector wording in the diaphragm summary, which remains preserved as source evidence. '
        'A: 20 ft maximum straight pieces and 25 in contact laps (40 nominal diameters), alternate touching bars, 2 in lateral spacing and 3 in end margins; X/Y centres lie 1.25/1.875 in below the topping top. '
        'These are fictional set-out proposals. Concrete cover, development, lap classification, congestion and capacity require engineering verification. No reinforcing-bar weld is proposed. '
        'WWR, perimeter chord continuity and deck-to-blocking screws remain separate requirements; this addition does not establish diaphragm or whole-building completeness.')


def draw(ctx):
    a = ctx.a;par = ctx.params;origin = ctx.c['point']
    axes = horizontal_frame(sub(ctx.ms[0]['axis'][1],ctx.ms[0]['axis'][0]))
    lap = ctx.family == 'review_collector_lap'
    label=par.get('reinforcement_label','Source collector bar')
    radius=ctx.p[ctx.ms[0]['profile_id']]['dimensions']['d']/2
    extent = par.get('context_extent_in',par['lap_in']/2+12 if lap else math.dist(*ctx.ms[0]['axis'])/2+.01)
    for j,m in enumerate(ctx.ms):
        extract(ctx,m,'BAR'+str(j),axes,extent)
        if not lap:
            # The sheet is a local view, while its development interface binds
            # the complete actual bar. Native entry must expand this receiver
            # to the independently declared bar and verify its entire host fit.
            a.parts[-1]['native_receiver_extent']='whole_member'
    parts = [p for p in a.parts if p['kind']=='member']
    xmin=min(p['bounds'][0][0] for p in parts);xmax=max(p['bounds'][0][1] for p in parts)
    ymin=min(p['bounds'][1][0] for p in parts)-2;ymax=max(p['bounds'][1][1] for p in parts)+2
    top=par['slab_top_in']-origin[2]
    a.box('TOPPING',[xmin,ymin,top-par['topping_in']],
          [xmax-xmin,ymax-ymin,par['topping_in']], 'S thickness; A local view extent',
          'Actual host '+par['host_panel_id']+'; 2.5 in lightweight-concrete topping',kind='concrete')
    a.parts[-1]['representation_role']='context_only'
    a.parts[-1]['show_in_section']=True
    a.parts[-1]['source_panel_parameter']='host_panel_id'
    a.interfaces.append(dict(id='BOND',kind='reinforcement_bond_lap' if lap else 'reinforcement_bond_development',
        connects=[p['id'] for p in parts]+['TOPPING'],basis='A',
        description='Physical contact lap in the host topping; development/capacity unverified' if lap else
                    label+' embedded in the host topping; development/capacity unverified',
        **({'length_in':par['lap_in']} if lap else {})))
    interface=a.interfaces.pop()
    groups=[parts] if lap else [[p] for p in parts]
    for i,group in enumerate(groups):
        ident='BOND' if len(groups)==1 else 'BOND'+str(i)
        item=copy.deepcopy(interface);item.update(id=ident,connects=[p['id'] for p in group]+['TOPPING'])
        item['native_bond']=dict(id=ident,kind=item['kind'],host_receiver='TOPPING',
            bar_receivers=[p['id'] for p in group],basis='Accepted fictional bond geometry; no development or capacity check',
            engineering_status='not_verified',**({'length_in':par['lap_in']} if lap else {}))
        a.interfaces.append(item)
    a.front_axes=(0,1);a.section_axis=0;a.section_at=0
    if lap:a.dim([-par['lap_in']/2,0,0],[par['lap_in']/2,0,0],'Contact lap; unverified',basis='A')
    else:a.dim([xmin,0,0],[xmax,0,0],'Local view extent' if par.get('context_extent_in') else 'Bar-piece length',basis='A')
    if par.get('mesh_spacing_in'):
        spacing=par['mesh_spacing_in']
        a.dim([-spacing,-spacing,0],[0,-spacing,0],'Wire spacing',basis='S',offset=-35)
    a.dim([0,ymin,top-par['topping_in']],[0,ymin,top],'Topping',view='section',basis='S',offset=-35)
    bar_top=max(p['bounds'][2][1] for p in parts)
    a.dim([0,ymax,bar_top],[0,ymax,top],'Top cover; unverified',view='section',basis='A',offset=35)
    a.notes.extend([par.get('reinforcement_note','S: source collector bar count, #5 nominal diameter and Gr 60. A: stock lengths, lap stations, cover and layering. No new reinforcement capacity check.'),
        'Concrete is host context. The floor model retains its deck/fill boundary and openings. No reinforcing-bar weld; the bond interface does not assert a verified development length.'])
