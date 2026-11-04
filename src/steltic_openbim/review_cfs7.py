"""Source room/corridor framing and finishes for the staggered-bar example.

Sizes, spans, spacing and layer thicknesses come from the saved selection.
Mechanical-zone coordinates and the reconciliation of nominal analysis levels
with the steel bearing surfaces are accepted fictional coordination inputs.
The source force/capacity records are neither changed nor rechecked here.
"""
from .review_cfs import frange,section


def finish(roof=False):
    return 19/32 if roof else 23/32+1.5


def depth(roof=False):
    return 10+finish(roof)


def wall_ranges(b,axis,pos,ranges):
    """A north-bar grid must not create an extra south-bar bearing wall."""
    if axis==0:
        return [(0,240)] if abs(pos-58*12)<.001 else ranges
    result=[]
    for line in b.cfg['lines_y']:
        if abs(line['pos']*12-pos)>.001:continue
        interval=(58,116) if line['name'].startswith('YN') else (0,58)
        if interval not in result:result.append(interval)
    return sorted(result) or ranges


def ordinary_sections(b):
    for m in b.members:
        if m['kind']!='stud' or not m['id'].startswith('ORD-'):continue
        axis=int(m['id'].split('-')[1]);x,y=m['axis'][0][:2];k=m['level']
        if axis==0 and any(abs(y-v*12)<.001 for v in (26,32,84,90)):
            rid,pid='stud-corridor','600S162-68'
        elif axis==0 and (abs(y)<.001 or abs(y-116*12)<.001 or abs(y-58*12)<.001 and (x<90*12 or x>150*12)):
            rid,pid='stud-ext-long','600S162-'+('43' if k<=2 else '33')
        elif axis==1:
            end=(y>=58*12 and any(abs(x-v*12)<.001 for v in (0,150)) or
                 y<=58*12 and any(abs(x-v*12)<.001 for v in (90,240)))
            rid,pid=('stud-end-walls','600S162-68') if end else ('stud-cross-walls','600S200-68' if k<=2 else '600S162-68')
        else:
            # The unbraced parts of XM have no separate ordinary-stud source.
            # Preserve their authored selection instead of claiming coverage.
            continue
        record=b.record('studs',rid)
        if not record:raise ValueError('Missing CFS7 stud selection '+rid)
        old=m['profile_id'];m['profile_id']=b.profile(pid)
        m['design_record_ids']=list(dict.fromkeys(m['design_record_ids']+[record]));b.used_records.add(record)
        m['physical_fit_basis']='S: source ordinary-stud tier on its actual wall line. A: non-braced set-out; source connection requirements remain applicable.'
        if old!=pid:b.changes.append(dict(kind='cfs7_source_ordinary_stud',member_id=m['id'],previous_profile_id=old,profile_id=pid,source_record_ids=[record]))


def roof_selection(lo,hi,station):
    """Apply a zone's selected uniform-span check to every intersected joist."""
    # Source specifies 40 x 30 ft in the north bar, without its location.
    x0,x1,y0,y1=50*12,90*12,70*12,100*12
    drift=17.1*12
    if lo<x1 and hi>x0 and y0<=station<=y1:return 'joist-roof-mech'
    if lo<x1+drift and hi>x0-drift and y0-drift<=station<=y1+drift:return 'joist-roof-unit-drift'
    return 'joist-roof'


def floors(b,outline,levels):
    ordinary_sections(b)
    records={r['id']:r for r in b.raw['framing']}
    b.material_selections=getattr(b,'material_selections',[])+[
        dict(id='cfs7-source-wood-panel',specification='Structural I wood structural panel',basis='S',
             source_configuration_field='cfg.diaphragm_material',source_selection_text=b.cfg['diaphragm_material']),
        dict(id='cfs7-source-gypsum',specification='Nonstructural gypsum floor underlayment',basis='S',
             source_configuration_field='cfg.diaphragm_material',source_selection_text=b.cfg['diaphragm_material'])]
    last=len(levels)-1
    for k,z in enumerate(levels[1:],1):
        roof=k==last;cover=finish(roof);wood=19/32 if roof else 23/32
        # A structural layer and a nonstructural finish remain distinct. Their
        # host reservations are completed after the floor openings are located.
        b.panel(f'FLOOR-{k}','roof' if roof else 'floor',[[12*x,12*y,z-(0 if roof else 1.5)] for x,y in outline],wood,k,'S',
                floor_stack_id=f'CFS7-FLOOR-{k}',finished_floor_z_in=z,material_description='Structural I wood structural panel',
                material_id='cfs7-source-wood-panel',
                reference_line='top surface of structural sheathing',thickness_direction='negative_global_z',
                pending_source_requirements='Blocked panel edges, source 6 in edge screws, and steel-to-steel bearing-wall holdbacks must be located before complete source acceptance.')
        if not roof:
            b.panel(f'GYPSUM-{k}','finish',[[12*x,12*y,z] for x,y in outline],1.5,k,'S',floor_stack_id=f'CFS7-FLOOR-{k}',
                    material_description='Nonstructural gypsum floor underlayment',structural=False,
                    material_id='cfs7-source-gypsum',
                    reference_line='finished floor top surface',thickness_direction='negative_global_z',
                    pending_source_requirements='Same bearing-wall holdbacks and stair reservations as the structural sheathing.')
        def joist(label,rid,axis,station,lo,hi):
            row=records[rid];pid=b.profile(section(row['section']));d=b.depth(pid)
            if abs(d-10)>.001:raise ValueError('CFS7 floor datum requires the actual selected 10 in joist')
            refs=[name for name in ('framing/'+rid,'gravity_framing/'+rid) if name in b.records]
            def point(u):return [u,station,z-cover-d/2] if axis==0 else [station,u,z-cover-d/2]
            m=b.member(label,pid,'joist',point(lo),point(hi),k,'S',records=refs)
            m['physical_fit_basis']='S: selected span/section and 16 in maximum spacing. A: local set-out and the explicitly recorded mechanical-zone position; source analysis unchanged.'
            b.ends(m,'review_cfs_joist',refs,parameters=dict(spacing=16,floor_depth=depth(roof)))
        for bar,y0,y1,x0 in (('S',0,58,90),('N',58,116,0)):
            corridor=(26 if bar=='S' else 84,32 if bar=='S' else 90)
            stations=list(frange(y0*12,y1*12+.01,16))
            if bar=='N' and (not stations or abs(stations[-1]-y1*12)>.001):stations.append(y1*12)
            for station in stations:
                # The south grid ends 8 in before the common boundary; its
                # rim/blocking closes that edge. The north grid starts there.
                if not roof and corridor[0]*12<station<corridor[1]*12:continue
                for bay in range(12):
                    lo=(x0+bay*12.5)*12;hi=lo+150
                    rid=roof_selection(lo,hi,station) if roof and bar=='N' else 'joist-roof' if roof else 'joist-typ'
                    joist(f'JOIST-{k}-{bar}-{station:g}-{bay}',rid,0,station,lo,hi)
            if not roof:
                for x in frange(x0*12,(x0+150)*12+.01,16):
                    joist(f'CORRIDOR-{k}-{bar}-{x:g}','joist-corridor',1,x,corridor[0]*12,corridor[1]*12)
    for m in b.members:
        if m['kind'] not in ('top_track','bottom_track','ordinary_track','tier_track') or abs(m['local_y'][2])<.999:continue
        half=b.profiles[m['profile_id']]['dimensions']['t']/2
        for off in m['end_offsets']:off[2]+=half*m['local_y'][2]
    b.note('SOURCE-FLOOR-SCHEDULE','S: room/roof joists span 12.5 ft on their own bar grid; floor corridor joists span 6 ft north-south. Source ordinary-stud tiers, 23/32 in floor sheathing, 1.5 in nonstructural gypsum and 19/32 in roof sheathing are retained. A: physical bearing datums reconcile these actual layers with the nominal 12 in analysis floor allowance; the saved analysis and capacity checks are unchanged. Panel-edge blocking, holdbacks, stiffeners and collector details remain separately required.')
    b.note('MECHANICAL-ZONE','S: 40 x 30 ft north-bar equipment zone and 17.1 ft unit drift extent. A: locate the zone at X=50-90 ft, Y=70-100 ft; apply each selected source uniform-span joist check to the whole intersected span. This accepted fictional location is not a new load analysis or equipment support design.')
    b.changes.append(dict(kind='cfs7_physical_floor_datums',source_nominal_analysis_depth_in=12,physical_floor_depth_in=depth(),physical_roof_depth_in=depth(True),
                          mechanical_zone_ft=[50,70,90,100],basis='S selected member/layer dimensions; A local physical set-out. Full physical and capacity acceptance remain separately gated.'))
