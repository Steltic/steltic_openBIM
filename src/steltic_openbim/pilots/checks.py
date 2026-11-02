"""Independent source/layout regression checks; never a capacity certification."""
from collections import Counter
import math
from .model import add,stable_hash
from ..bim_contract import validate


def inspect(p,source,key):
    checks=[]; ph=p['physical']; members=ph['members']; kinds=Counter(m['kind'] for m in members)
    def check(name,ok,detail):
        checks.append({'name':name,'passed':bool(ok),'detail':detail})
    findings=validate(p)
    check('contract_geometry',not any(f['severity']=='error' for f in findings),'Finite geometry, units, axes, profiles, references, support attachments and analysis interval coverage')
    check('design_preservation',p['design_records']==source['design_records'] and p['design_context']==source['design_context'],'All original design values and context retained verbatim as JSON values')
    check('no_analysis',p['provenance']['analysis_executed'] is False,'Only source replay and geometric composition; no solve or capacity design')
    check('source_record_coverage',not p['review']['unmapped_drawing_records'],'Every drawing-related source record assigned to an occurrence or declared interface')
    check('readiness_honesty',p['readiness']['status']=='needs_input' and any(f['code']=='coordination_required' for f in findings),'Open questions prevent drawing-ready status even if a stored ready flag is changed')
    geometry=[]
    for m in members:
        ends=[add(a,b) for a,b in zip(m['axis'],m['end_offsets'])]
        geometry.append((m['profile_id'],tuple(m['local_y']),tuple(tuple(round(v,6) for v in q) for q in ends)))
    check('duplicate_solids',len(set(geometry))==len(geometry),'No exact duplicate member placement/profile/orientation')
    if key=='hr22':
        splices=[j for j in ph['joints'] if j['id'].startswith('SPLICE-')]
        check('column_splices',kinds['column']==105 and len(splices)==70 and {j['point'][2] for j in splices}=={408,744},'35 columns; physical splices at floors 2/4 +48 in, not at analysis story boundaries')
        check('framing_counts',kinds['moment_beam']==96 and kinds['girder']==252 and kinds['infill']==288,'6 levels × 58 grid beams +48 infills; 16 moment beams per level')
        check('penthouse_local_schedule',sum(m['profile_id']=='W27X84' for m in members)==4 and sum(m['profile_id']=='W18X40' for m in members)==4,'Four girders and four infills in the recorded Grids 3–5/B–C zone; placement is a visible proposal')
        check('embedded_bases',sum(m['end_offsets'][0][2]==-96 for m in members)==20,'20 fixed SMF bases extend 96 in below the foundation workline')
    elif key=='cfs16':
        frames={m.get('frame') for m in members if m.get('frame')}
        check('portal_extent',frames==set(range(1,24)) and kinds['column']==46 and kinds['rafter']==46,'All 23 frames, no viewer cap; 46 columns and 46 rafters')
        check('secondary_counts',kinds['purlin']==286 and kinds['purlin_nested']==12 and kinds['girt']==132 and kinds['eave_strut']==44,'13 purlin lines ×22 spans; 12 nested end-bay reinforcements; 2 walls ×3 girt rows ×22 spans')
        check('door_dimensions',len(ph['openings'])==2 and all(o['vertices'][1][0]-o['vertices'][0][0]==168 and o['vertices'][2][2]==192 for o in ph['openings']),'Both source 14 ×16 ft doors at jamb X=23 and37 ft')
        crossing=[m['id'] for m in members if m['kind']=='endwall_girt' and m['axis'][0][2]<192 and min(m['axis'][0][0],m['axis'][1][0])<444 and max(m['axis'][0][0],m['axis'][1][0])>276]
        check('door_clearance',not crossing,'No low girt crosses either overhead-door opening')
        bolts=sum(part['kind']=='bolt' for c in ph['connections'] for part in c.get('parts',[]))
        check('portal_bolt_patterns',bolts==3036,'46 knees ×48 bolts +23 apex joints ×36 bolts; based on per-leg/per-pair source patterns')
    elif key=='cfs8':
        from .cfs8 import NATURAL
        panels=[q for q in ph['panels'] if q['kind']=='strap_wall_zone']
        check('braced_bays',len(panels)==88 and kinds['strap']==352 and kinds['chord']==176 and kinds['hold_down_rod']==176,'22 bays ×4 stories; four physical strap diagonals, two chord packs and two rod segments per bay')
        positioned=True
        for q in panels:
            _,d,line,_,_=q['id'].split('-'); index=1 if d=='X' else 0
            positioned &= all(abs(v[index]-NATURAL[line]*12)<1e-6 for v in q['vertices'])
        check('true_wall_positions',positioned,'HS=84 ft, SW=47 ft and SE=93 ft; fitted analysis positions are not used as set-out')
        roofs=[q for q in ph['panels'] if q['kind']=='roof']; area=0
        for r in roofs:
            v=r['vertices']; area+=abs(sum(v[i][0]*v[(i+1)%len(v)][1]-v[(i+1)%len(v)][0]*v[i][1] for i in range(len(v))))/2/144
        check('roof_union',len(roofs)==5 and abs(area-10304)<1e-6,'Five nonoverlapping roof planes project to the 10,304 sq ft T footprint; valley junction is a delegated zone')
        check('track_opening_direction',all(m['local_y'][2]==1 for m in members if m['kind']=='bottom_track') and all(m['local_y'][2]==-1 for m in members if m['kind']=='top_track' or (m['kind']=='collector' and m['id'].startswith('DRAG-'))),'Bottom tracks open upward; top tracks/drag tracks open into the studs below')
        check('floor_joist_spans',kinds['joist']==1728 and kinds['bearing_stiffener']==3456,'3 floors ×16 bays ×36 joists; two bearing stiffeners per floor joist')
        check('rim_and_bridging',kinds['rim_track']>24 and kinds['bridging_anchor']>0,'Perimeter rim pieces interrupted at source chord/squash-pack footprints; bridging anchors at 8 ft maximum')
    return {'building_id':p['building_id'],'checks':checks,'passed':all(r['passed'] for r in checks),'counts':dict(kinds),
        'source_package_sha256':stable_hash(source),'model_sha256':stable_hash(p),'limits':['No structural capacity certification','No general collision-free or fabrication-readiness claim','Proposed set-out and source conflicts remain open']}
