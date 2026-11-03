"""Recover a clearly identified coordination view from captured HR occurrences.

The source package is immutable. This view never promotes analysis axes into
fabrication geometry, copies prototype connections to nodes, or imports a
fictional review recipe into an ordinary job.
"""
from bisect import bisect_left
from collections import Counter
import copy
import math

from .bim_contract import mapping_geometry_findings


KINDS = {'col':'column', 'column':'column', 'beam':'beam', 'girder':'girder',
         'brace':'brace', 'brb':'brace', 'infill':'infill', 'joist':'joist', 'rafter':'rafter'}


def required(package):
    if package.get('module') != 'HR' or not package['analysis']['elements']: return False
    if mapping_geometry_findings(package): return True
    represented={aid for m in package['physical']['members'] for aid in m.get('analysis_ids',[])}
    represented.update(s['analysis_id'] for m in package['physical']['members'] for s in m.get('analysis_segments',[]))
    represented.update(row['analysis_id'] for row in package['physical'].get('analysis_only',[]))
    if any(e['id'] not in represented and str(e.get('kind','')).lower() in KINDS
           for e in package['analysis']['elements']):return True
    return any(m.get('status') == 'candidate' and m.get('geometry_basis') == 'analysis_axis'
               for m in package['physical']['members'])


def physical_view(package):
    """Retain numeric storey aliases and group HR elevations without moving geometry."""
    physical=copy.deepcopy(package['physical'])
    for collection in ('members','panels','joints','connections','openings'):
        for entity in physical.get(collection,[]):
            value=entity.get('storey')
            if entity.get('level') is None and type(value) in (int,float) and math.isfinite(value) and int(value)==value:
                entity['level']=int(value)
                entity['level_basis']='Source-declared numeric storey field'
                entity['level_source_field']='storey'
    levels=sorted(set(package.get('layout_evidence',{}).get('levels_in') or []))
    if package.get('module')!='HR' or len(levels)<2:return physical
    for collection,key in (('members','axis'),('panels','vertices')):
        for entity in physical[collection]:
            if entity.get('level') is not None:continue
            z=max(p[2] for p in entity[key])
            entity['level']=max(1,min(len(levels)-1,bisect_left(levels,z-1e-5)))
            entity['level_basis']='Derived from source level elevations for coordination'
    return physical


def build(package):
    nodes = {n['id']: n for n in package['analysis']['nodes']}
    excluded = {e['analysis_id'] for e in package['physical'].get('analysis_only', [])}
    levels = sorted(set(package.get('layout_evidence', {}).get('levels_in') or []))
    eligible = []
    for element in package['analysis']['elements']:
        ids = element['node_ids']; kind = str(element.get('kind','')).lower()
        if element['id'] in excluded or kind not in KINDS or len(ids) != 2: continue
        if str(element.get('profile_id','')).startswith('RZ-'): continue
        axis = [nodes[n]['point'] for n in ids]
        if math.dist(*axis) < 1e-6: continue
        eligible.append((element, axis))
    if not levels:
        levels = sorted({p[2] for e,axis in eligible if KINDS[e['kind'].lower()] == 'column' for p in axis})
    if not levels: levels = sorted({p[2] for _,axis in eligible for p in axis})
    members = []
    for element, axis in eligible:
        top = max(p[2] for p in axis)
        level = max(1, min(max(1,len(levels)-1), bisect_left(levels,top-1e-5)))
        members.append(dict(id=element['id'],kind=KINDS[element['kind'].lower()],axis=copy.deepcopy(axis),
            level=level,profile_id=element.get('profile_id'),analysis_ids=[element['id']],
            status='candidate',basis='S',geometry_basis='captured_analysis_workline',
            source_schedule=copy.deepcopy(element.get('source_schedule')),source_node_ids=element['node_ids']))
    if not members: raise ValueError('No supported captured HR line occurrences are available for recovery')
    marks = {key:f'M{i:03}' for i,key in enumerate(sorted({(m['kind'],m.get('profile_id') or 'TBD') for m in members}),1)}
    for m in members: m['mark'] = marks[m['kind'],m.get('profile_id') or 'TBD']
    joints = {}
    for m in members:
        for end, p in zip(('start','end'),m['axis']):
            key = tuple(round(v,6) for v in p)
            joints.setdefault(key, []).append(dict(member_id=m['id'],end=end))
    joint_rows = [dict(id=f'J{i:04}',point=list(p),member_ends=ends)
                  for i,(p,ends) in enumerate(sorted(joints.items()),1)]
    columns = [m for m in members if m['kind']=='column']
    grids = {axis:sorted({p[i] for m in columns for p in m['axis']}) for i,axis in enumerate(('x','y'))}
    records = [copy.deepcopy(r) for r in package['design_records'] if r['table']=='connections']
    return dict(schema='steltic.source_workline_view',building_id=package['building_id'],members=members,
        levels=[dict(level=i,elevation_in=z) for i,z in enumerate(levels)],grids=grids,joints=joint_rows,
        source_connection_records=records,
        counts=dict(analysis_elements=len(package['analysis']['elements']),drawn_occurrences=len(members),
                    excluded_or_unsupported=len(package['analysis']['elements'])-len(members),levels=len(levels)-1,
                    source_connection_records=len(records),member_kinds=dict(Counter(m['kind'] for m in members))),
        basis='Actual captured analysis occurrences and section assignments. Physical datums, cuts, assemblies and connection part placement remain TBD; no structural analysis or design change.',
        suppressed_declarations={k:len(package['physical'].get(k,[])) for k in ('members','panels','connections')},
        suppressed_basis='Original declarations are retained in source.json. Their unverified locations are not presented as complete building geometry.')


def request_items(package):
    model=build(package);n=model['counts']['drawn_occurrences'];levels=model['counts']['levels']
    conflicts=[r['id'] for r in model['source_connection_records']
               if 'simple' in str(r['data'].get('type','')).lower() and 'RBS' in str(r['data'].get('components','')).upper()]
    connection_basis='Representative references are not an occurrence-by-occurrence connection layout.'
    if conflicts:connection_basis+=' These source records also describe simple connections while retaining RBS component notes; reconcile the intended specification: '+', '.join(conflicts)+'.'
    return [
        dict(id='MODEL-OCCURRENCES',title='Confirm physical member set-out and occurrence mappings',kind='missing',entity_ids=[],
             basis='Grouped declarations cannot establish every member location.',
             proposed=f'Use all {n:,} captured member worklines across {levels} levels for coordination. Source sections and axes are retained; physical datums, cutbacks and unmodelled secondary framing remain TBD - resolve query.'),
        dict(id='MODEL-CONNECTIONS',title='Locate and supply the connection assemblies',kind='missing',entity_ids=[],
             basis=connection_basis,
             proposed='Retain every source connection schedule and show actual model joints as coordination locations. Part geometry, applicable detail, fasteners, weld placement and splice positions remain TBD - resolve query. Do not repeat a base-point example throughout the building.'),
        dict(id='MODEL-FLOORS',title='Confirm floor, roof and secondary framing geometry',kind='missing',entity_ids=[],
             basis='The supplied panel declarations do not establish all floor and roof assemblies.',
             proposed='Draw source framing at every captured level. Retain slab/deck specifications as source notes; panel extents, thickness applicability and unmodelled infill positions remain TBD - resolve query.'),
        dict(id='MODEL-OPENINGS',title='Confirm stair and service-opening layout',kind='delegated',entity_ids=[],
             basis='No verified opening layout accompanies the recovered building occurrences.',
             proposed='Show two illustrative stair zones and one service-shaft zone within each level footprint. Their positions and sizes are TBD - resolve query, without dimensions. These overlays do not cut or redesign framing.')]


def opening_features(package):
    model=build(package);features=[]
    for item in model['levels'][1:]:
        level=item['level'];pts=[p for m in model['members'] if m['level']==level for p in m['axis']]
        if not pts: continue
        x0,x1=min(p[0] for p in pts)/12,max(p[0] for p in pts)/12
        y0,y1=min(p[1] for p in pts)/12,max(p[1] for p in pts)/12
        dx,dy=x1-x0,y1-y0
        if min(dx,dy)<10: continue
        for i,(kind,u,v,w,h) in enumerate([('stair zone',.15,.15,min(12,dx*.12),min(18,dy*.18)),
                                          ('stair zone',.75,.70,min(12,dx*.12),min(18,dy*.18)),
                                          ('service shaft',.46,.46,min(8,dx*.08),min(8,dy*.08))],1):
            features.append(dict(id=f'WL{level:02}-{i}',query_id='MODEL-OPENINGS',kind=kind,plane='xy',
                x_ft=x0+dx*u,y_ft=y0+dy*v,z_ft=item['elevation_in']/12,width_ft=w,height_ft=h,level=level,
                confirmed=False,geometry_role='illustrative_proposal'))
    return features
