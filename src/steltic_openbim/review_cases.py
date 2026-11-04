"""Opt-in fictional review cases; exact source hashes prevent use on other jobs."""
import copy,json,zipfile
from functools import lru_cache
from pathlib import Path

DATA=Path(__file__).with_name('review_data')
CASES={c['id']:c for c in json.loads((DATA/'cases.json').read_text(encoding='utf-8'))} if (DATA/'cases.json').is_file() else {}

@lru_cache(maxsize=64)
def evidence(key):
    if key not in CASES:raise ValueError('Unknown review case '+key)
    with zipfile.ZipFile(DATA/'inputs.zip') as z:
        return {name:json.loads(z.read(key+'/'+name+'.json')) for name in ('package','configuration','calc','viewer')}

@lru_cache(maxsize=1)
def catalog():
    with zipfile.ZipFile(DATA/'inputs.zip') as z:return json.loads(z.read('catalog.json'))

def scenario(key):
    c=CASES[key]
    return dict(title=c.get('drawing_title',c['source_building'].replace('_',' ')),source_sha256=c['source_sha256'],answers={
        key.upper()+'-GEOMETRY':'Adopt the source physical grids, member sections and level-specific footprint. Reconstruct analysis-only systems as physical walls/trusses using the source configuration and design schedules. Exact adopted member/plate geometry is retained in the drawing model; additions are marked A.',
        key.upper()+'-OPENINGS':'For this fictional test, retain all located source openings and use the explicitly dimensioned opening schedule for supplementary access/windows/services. Locate supplementary openings clear of source braced segments, preserve irregular footprints, and frame every cut member end.',
        key.upper()+'-CONNECTIONS':'Develop each source connection as an assembled design detail. Retain source grades, counts, plate thicknesses and special conditions; adopt and label A all missing fit, set-out, receiving support and local fastener geometry. Workline dimensions are design dimensions, not fabrication cut lengths.',
        key.upper()+'-DELEGATED':'Show the designed scope and its interfaces completely. Supplier or existing-building items use explicitly labelled fictional geometry; original delegated verification and capacity requirements remain visible. No new structural analysis or verified supplier/foundation design is inferred.'})

def build_model(package,state):
    from .drawing_workflow import fingerprint
    key=state['design_scenario']['id'];spec=scenario(key)
    if fingerprint(package)!=spec['source_sha256'] or state['design_scenario']['answers_sha256']!=fingerprint(spec['answers']):raise ValueError('Review scenario or source changed')
    from .review_model import CaseModel
    b=CaseModel(key,package,state,evidence(key))
    if CASES[key]['module']=='HR':
        from .review_hr import build
    else:
        from .review_cfs import build
    build(b)
    from .review_supplements import floor_openings
    floor_openings(b)
    from .review_cfs_complements import apply
    apply(b)
    if key in ('cfs2','cfs4','cfs6','cfs9','cfs10','cfs12'):
        from .review_next_cfs_walls import connections
        connections(b)
    if key in ('cfs1','cfs5','cfs15'):
        from .review_final_cfs import connections
        connections(b)
    from .review_design_bindings import apply as design_bindings
    design_bindings(b)
    from .review_cfs_rods import apply as rod_joints
    rod_joints(b)
    from .review_physical_pieces import apply as physical_pieces
    physical_pieces(b)
    from .review_selected_details import apply as selected_details
    selected_details(b)
    from .review_profile_fit import apply as profile_fit
    profile_fit(b)
    from .review_cfs_frame_straps import apply as frame_straps
    frame_straps(b)
    from .review_crossings import apply as brace_crossings
    brace_crossings(b)
    from .review_releases import apply as physical_releases
    physical_releases(b)
    from .review_column_local_checks import apply as local_checks
    local_checks(b)
    from .review_rbs import apply as physical_rbs
    physical_rbs(b)
    from .review_track_corners import apply as track_corners
    track_corners(b)
    return b.finish()
