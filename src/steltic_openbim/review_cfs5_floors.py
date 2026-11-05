"""Exact CFS5 source floor layers and evidence-checked gravity aliases."""
import copy
from .review_cfs_source_bindings import attach


def apply(b):
    if b.key!='cfs5':return
    selection=b.cfg['diaphragm_material']
    if '23/32' not in selection or '1-1/2' not in selection or '19/32' not in selection:
        raise ValueError('CFS5 source floor selection changed')
    b.material_selections=getattr(b,'material_selections',[])+[
        dict(id='CFS5-WSP-FLOOR',basis='S',specification='23/32 in Structural I wood structural panel'),
        dict(id='CFS5-WSP-ROOF',basis='S',specification='19/32 in Structural I wood structural panel'),
        dict(id='CFS5-GYPSUM',basis='S',specification='1.5 in nonstructural gypsum underlayment')]
    originals={o['id']:o for o in b.openings}
    for panel in list(b.panels):
        if panel['kind'] not in ('floor','roof'):continue
        before=copy.deepcopy(panel);top=panel['vertices'][0][2];roof=panel['kind']=='roof'
        panel.update(thickness_in=19/32 if roof else 23/32,thickness_direction='negative_global_z',
            material_id='CFS5-WSP-ROOF' if roof else 'CFS5-WSP-FLOOR',
            basis='S thickness and Structural I material; A accepted footprint')
        if not roof:
            panel['vertices']=[[q[0],q[1],top-1.5] for q in panel['vertices']]
            finish=b.panel('FINISH-'+str(panel['level']),'floor_finish',copy.deepcopy(before['vertices']),1.5,
                panel['level'],'S',material_id='CFS5-GYPSUM',thickness_direction='negative_global_z',openings=[])
            for oid in panel.get('openings',[]):
                lower=originals[oid];lower.update(host_id=panel['id'],z_ft=(top-1.5)/12)
                upper=copy.deepcopy(lower);upper.update(id=oid+'-FINISH',host_id=finish['id'],z_ft=top/12,parent_opening_id=oid)
                b.openings.append(upper);finish['openings'].append(upper['id'])
        b.changes.append(dict(kind='source_cfs5_floor_layers',previous_panel=before,subfloor_panel_id=panel['id'],
            basis='S exact layer thicknesses and material. A bearing-wall top lowered7/32in below the former rounded floor fit, retaining all finish levels and selected steel sections. Roof wall top retained with its explicit bearing pack. No new strength check.'))
    # The gravity table duplicates the same saved member checks; its first
    # basis paragraph also summarizes the other three gravity load cases.
    for suffix in ('joist-typ','joist-corridor'):
        source=b.records['framing/'+suffix]['data'];alias=b.records['gravity_framing/'+suffix]['data']
        if {k:v for k,v in source.items() if k!='basis'}!={k:v for k,v in alias.items() if k!='basis'}:
            raise ValueError('CFS5 gravity alias differs from its saved framing check')
        if source['basis'] not in alias['basis']:raise ValueError('CFS5 gravity alias lost the specific load case')
        for member in b.members:
            if 'framing/'+suffix not in member['design_record_ids']:continue
            attach(b,member,'gravity_framing/'+suffix,
                'Same immutable source check and selected physical joist; all numeric/design fields equal. The first gravity row additionally describes the other gravity load cases, without replacing their separate checks.')
    b.note('EXACT-FLOOR-LAYERS','S:23/32in Structural I floor WSP plus1.5in nonstructural gypsum;19/32in Structural I roof WSP. A: retain finish levels and lower floor bearing-wall tops7/32in from the former rounded fit to accommodate the source layers and10in joists. Roof wall tops retain their existing datum and explicit bearing packs. Blocked-edge and collector attachments are separately represented; no source capacity is invented.')
