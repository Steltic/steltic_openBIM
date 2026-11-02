"""Explicit, source-bound answers for the registered fictional drawing test buildings.

These are opt-in test inputs, not defaults for real projects or new source jobs.
Source engineering evidence is preserved and is never promoted to verified design.
"""
from __future__ import annotations
import copy
from .drawing_workflow import fingerprint, StaleRevision

SCENARIOS = {
    'hr22': {
        'title': 'Six-storey hospital',
        'source_sha256': 'f134698729e8d92a782720f6482a21da48e32ce5f4fbf92e12257df27f8c13fc',
        'grids': {'x': [(str(i+1), i*360) for i in range(7)],
                  'y': [(chr(65+i), i*360) for i in range(5)]},
        'levels': [(0, 'BASE', 0), (1, 'L1 TOS', 192), (2, 'L2 TOS', 360),
                   (3, 'L3 TOS', 528), (4, 'L4 TOS', 696), (5, 'L5 TOS', 864), (6, 'ROOF TOS', 1032)],
        'answers': {
            'HR-OPENINGS': 'Adopt two 8 ft x 18 ft stair openings at X=11/Y=6 ft and X=161/Y=96 ft; two 8 ft square shafts at X=81/Y=36 ft and X=101/Y=36 ft, repeated at all six steel levels. New W18X40 edge trimmers and headers are assumed test members. Openings lie between existing beam lines.',
            'HR-SETOUT': 'Adopt source level elevations as top of steel, with 6-1/4 in composite slab/deck above. Beam ends use the source face offsets; bolt groups are centred on their beam webs. Retain 96 in embedded lateral columns and 2 in grout plus 1-5/8 in gravity base plates. All datums refer to base Z=0.',
            'HR-PENTHOUSE': 'Adopt the source local roof reinforcement at Grids 3-5/B-C: four W27X84 girders and four W18X40 infills. This is a local roof loading zone, with no additional occupied storey. Use the assumed small-beam shear detail for W18X40 connections; do not force the W30X99 five-bolt plate into the smaller web.',
            'HR-BASE-STUDS': 'For this fictional test, supersede the conflicting 12 in stud-zone wording: use 48 headed studs, 7/8 in diameter x 5 in long, in four vertical rows of 12 at 6 in pitch. Row elevations are -90 through -24 in. Preserve the source 96 in embedment, boxed section and end plate; this changed stud distribution has no new capacity verification.',
            'HR-DETAILS': 'Assume L3x3x1/4 bottom-flange kickers at the source brace stations. Adopt 3/8 x 6 x 12 in erection tabs, four 3/4 in bolts at 3 in pitch; retain source CJP moment and lateral-column splice welds. Gravity splice erection plates are 3/4 x 12 x 24 in. Deck attachment uses an assumed 36/4 pattern with sidelaps at 12 in; source shear-stud counts remain unchanged.',
            'HR-SEPARATION': 'Locate the existing wing west of Grid 1. Set its east face 14 in clear of the new outer column flange, using the largest source column flange/depth envelope at that face. The clearance is an assumed test coordination value; no existing-building response is inferred.'},
    },
    'cfs16': {
        'title': 'Portal-frame warehouse',
        'source_sha256': '14b7af0e1a74aa0e5ab8889cc49f593ecefecdd9696bf683197941b03831db6f',
        'grids': {'x': [('A', 0), ('B', 360), ('C', 720)],
                  'y': [(str(i+1), i*150) for i in range(23)]},
        'levels': [(0, 'BASE', 0), (1, 'EAVE WORKPOINT', 240), (2, 'RIDGE WORKPOINT', 312)],
        'answers': {
            'CFS16-DOORS': 'Adopt two 3 ft 6 in x 7 ft personnel doors, one in each long side wall. Each opening starts at Y=131 ft 9 in, within Grids 11-12; wall planes are X=-11 in and X=60 ft 11 in. Assume paired 800S250-97 jambs and HSS6X4X3/16 headers. Interrupt the 6 ft girt at each jamb. Preserve both source 14 ft x 16 ft overhead doors.',
            'CFS16-FRAME-SETOUT': 'Adopt 60 ft between column worklines and 58 ft 10 in nominal clear between the 14 in deep column faces; revise the brief wording of 60 ft clear. Frames are at 12 ft 6 in centres, 22 bays/275 ft total. Retain 6-3/8 in pair centres, 3/8 in web gaps and 1:5 roof slope. Assume 3/8 in assembly gaps with joint-bisector end cuts.',
            'CFS16-BRACKETS': 'Adopt the source knee/apex bolt patterns and 3/8 in plates. Make each bracket the union of its 12 in wide leg plates, with 2 in end/side margins beyond the bolt group; remove no material within that envelope. Base anchors are four 3/4 in rods on a 10 x 12 in rectangle in the 14 x 16 in plate. Base web bolts are a 2 x 2 group at 3 in pitch/gauge per pair; 2 in edge distance.',
            'CFS16-SECONDARY-SETOUT': 'Adopt purlin/girt worklines 11 in outside the frame workline, source 24 in lap extensions and 30 in flange braces. Use a 1/8 in nominal nested-Z separation. Add 30 in knee/apex/post-top kickers to adjacent purlins, increasing door-jamb top kickers to 31-1/2 in to reach their purlins. Retain source regular-kicker fasteners; new end clips use 2 in legs and two 1/4 in screws each leg as test assumptions.',
            'CFS16-END-BRACING': 'Adopt end-wall strap zones X=0-20 ft and X=40-60 ft, clear of the overhead door. Retain side and roof bracing in the first and last bays. Use the source 54-mil outer end-girt zones and 97-mil intermediate zones; the new personnel doors remain outside braced bays.'},
    },
    'cfs8': {
        'title': 'Four-storey T-plan student housing',
        'source_sha256': '1c7a843165fc0df5f442aa561ba5707dec1996f4daa5bb91f9f0ec6248337159',
        'grids': {'x': [(str(i+1), i*168) for i in range(11)] + [('SW', 564), ('SE', 1116), ('W', 492)],
                  'y': [('A', 0), ('B', 168), ('C', 336), ('D', 504), ('E', 672), ('F', 840), ('G', 1008), ('H', 1284), ('J', 1560)]},
        'levels': [(0, 'GROUND FFL', 0), (1, 'FLOOR 2 FFL', 120), (2, 'FLOOR 3 FFL', 236),
                   (3, 'FLOOR 4 FFL', 352), (4, 'ROOF BEARING', 468), (5, 'RIDGE', 537)],
        'answers': {
            'CFS8-OPENINGS': 'Adopt 4 ft square north-wall windows at X=21,49,91,113 ft and stem-wall windows at Y=18 and 62 ft on both sides, with 3 ft sills at each storey. Add a ground entrance at X=68 ft 6 in/Y=0, and a 3 ft x 7 ft west access door at Y=38 ft 6 in on each storey. These avoid all braced bays. Floor openings: two 8 x 18 ft stairs at X=17/Y=94 and X=115/Y=94 ft, plus a 4 ft square shaft at X=66/Y=50 ft, at the three elevated floors. Assume paired headers/trimmers and interrupt affected studs/joists/bridging.',
            'CFS8-CHORDS': 'Retain the source 4, 4-1/4 and 4-3/4 in clear bracket spaces; these spaced packs supersede the generic back-to-back wording. Assume 1/4 in spacer plates at 24 in vertical centres, with four No.14 screws at each spacer. Keep the source chord sections, rods and bracket plate thicknesses. No new pack-capacity check is claimed.',
            'CFS8-FLOOR': 'Adopt FFLs 0, 10 ft, 19 ft 8 in and 29 ft 4 in, with roof bearing at 39 ft. Use 12 in joists plus 3/4 in WSP: bearing planes at 8 ft 11-1/4 in, 18 ft 7-1/4 in and 28 ft 3-1/4 in. Align tracks to those planes; assume squash blocks cut to the 12 in bearing gap and reconcile the source 12.11 in wording. Keep 2-1/2 in nominal joist bearing and 1/8 in fit clearance at interrupted rims. Raise walkway joist axes 4 in to put their top flanges and the outer beam 3/4 in below each FFL; hang their ends at the ledger/edge beam.',
            'CFS8-ROOF-INTERFACE': 'Assume 46 ft Fink trusses at 2 ft centres, with paired 600S162-68 chords and 600S162-54 webs. A four-ply 800S200-97 girder truss spans SW-SE at Grid G and supports the head-roof trusses over the junction. Valley overframing sits above the main head roof, with 2 ft stations and a diminishing triangular envelope; it does not continue full-depth stem trusses through the main roof. Illustrative regular-truss reactions are 2.0 kip down and the source 1.06 kip uplift per heel; girder reactions are assumed 24 kip down/12 kip uplift per end, not analysed values.',
            'CFS8-WALKWAY-EDGE': 'Adopt an HSS8x4x1/4 outer edge beam on Grid W (X=41 ft), on HSS6x6x1/4 posts at Y=0,14,28,42,56,70,84 ft. Provide the three elevated walkway levels, 42 in guards with posts at 4 ft maximum centres, and illustrative 6 x 6 x 2 ft 6 in pads. Beam/post/base sizes are explicit test assumptions; no foundation or guard capacity verification is implied.',
            'CFS8-STUD-SETOUT': 'Adopt head party walls at X=14,28,...126 ft and stem party walls at Y=14,28,...70 ft. Start ordinary studs at the west/south end of each line at 16 in centres; chord packs replace studs within 8 in of the pack centre. Double jambs are placed outside the adopted clear openings; corners and T-intersections use three-stud packs.',
            'CFS8-DETAILS': 'Keep source fastener counts/grades. Assume screw groups on a 1 in grid with 1/2 in edge distance, using as many rows as needed for the source count. Side plates extend 1 in beyond the group; strap gussets extend 2 in beyond their group. Sill anchors use the source count and diameter, equally spaced with 6 in end offsets. Bridging is interrupted at openings and anchored to jamb packs with the source two No.10 screws; additional opening clips and support plates are test details.'},
    },
}


from .review_cases import CASES as REVIEW_CASES, scenario as review_scenario
SCENARIOS.update({key:review_scenario(key) for key in REVIEW_CASES})


def available_scenario(package):
    digest=fingerprint(package)
    return next((key for key,value in SCENARIOS.items() if value['source_sha256']==digest),None)


def scenario_features(pilot):
    if pilot in REVIEW_CASES:
        # Fully resolved features are constructed together with their real framing.
        # They are published from design_model.json, never copied from another pilot.
        return []
    result=[]
    def add(kind,plane,x,y,z,w,h,level,query):
        result.append(dict(id=f'O{len(result)+1:02}',kind=kind,plane=plane,x_ft=x,y_ft=y,z_ft=z,
            width_ft=w,height_ft=h,level=level,query_id=query,confirmed=True,
            geometry_role='assumed_test_opening',basis='A - user-authorized fictional test input'))
    if pilot=='hr22':
        for level,z in enumerate((16,30,44,58,72,86),1):
            for kind,x,y,w,h in [('stair',11,6,8,18),('stair',161,96,8,18),('shaft',81,36,8,8),('shaft',101,36,8,8)]:
                add(kind,'xy',x,y,z,w,h,level,'HR-OPENINGS')
    elif pilot=='cfs16':
        for x in (-11/12,60+11/12): add('personnel door','yz',x,131.75,0,3.5,7,1,'CFS16-DOORS')
    else:
        for level,z in enumerate((0,10,236/12,352/12),1):
            for x in (21,49,91,113): add('window','xz',x,130,z+3,4,4,level,'CFS8-OPENINGS')
            for x in (47,93):
                for y in (18,62): add('window','yz',x,y,z+3,4,4,level,'CFS8-OPENINGS')
            add('walkway door','yz',47,38.5,z,3,7,level,'CFS8-OPENINGS')
        add('entrance door','xz',68.5,0,0,3,7,1,'CFS8-OPENINGS')
        for level,z in enumerate((10,236/12,352/12),1):
            for kind,x,y,w,h in [('stair',17,94,8,18),('stair',115,94,8,18),('service shaft',66,50,4,4)]:
                add(kind,'xy',x,y,z,w,h,level,'CFS8-OPENINGS')
    return result


def adopt_scenario(package,state,body):
    if body.get('revision')!=state['revision'] or body.get('source_model_sha256')!=state['source_model_sha256']:
        raise StaleRevision('Refresh before adopting the fictional test answers')
    if body.get('confirm_fictional') is not True:
        raise ValueError('Explicitly confirm that this is a fictional test building')
    pilot=available_scenario(package)
    if pilot is None or body.get('pilot',pilot)!=pilot:
        raise ValueError('These authored answers are bound to a registered fictional test package')
    author=str(body.get('author','')).strip()
    if not author or len(author)>160: raise ValueError('Provide the author of the adopted test assumptions')
    result=copy.deepcopy(state); scenario=SCENARIOS[pilot]
    if {r['id'] for r in result['requests']}!=set(scenario['answers']):
        raise ValueError('The information-request set differs from the reviewed test scenario')
    for request in result['requests']:
        request.update(confirmed=True,status='resolved_for_test',resolution=scenario['answers'][request['id']],
            resolution_basis='user_authorized_fictional_assumption',confirmed_by=author)
    result['features']=scenario_features(pilot)
    for feature in result['features']: feature['confirmed_by']=author
    result['design_scenario']={'id':pilot,'version':1,'source_sha256':fingerprint(package),
        'answers_sha256':fingerprint(scenario['answers']),'author':author,'fictional':True}
    result['revision']+=1;result['drawing_status']='design_test'
    result['policy']['new_capacity_verification']=False
    result['events'].append(dict(revision=result['revision'],action='adopt_fictional_design_answers',author=author,
        note='User-authorized assumed answers for this registered fictional building; source design remains immutable.'))
    return result
