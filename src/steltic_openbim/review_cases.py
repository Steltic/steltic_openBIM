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
    from .review_cfs26_primary import prepare as canopy_primary_prepare
    canopy_primary_prepare(b)
    from .review_sbmf_floor import prepare as prepare_sbmf_floor
    prepare_sbmf_floor(b)
    from .review_sbmf_wall_chords import prepare as prepare_sbmf_wall_chords
    prepare_sbmf_wall_chords(b)
    from .review_sbmf_mezzanine import prepare as prepare_sbmf_mezzanine
    prepare_sbmf_mezzanine(b)
    from .review_sbmf_collectors import prepare as prepare_sbmf_collectors
    prepare_sbmf_collectors(b)
    from .review_sbmf_restraints import prepare as prepare_sbmf_restraints
    prepare_sbmf_restraints(b)
    from .review_parallel_wall_framing import apply as parallel_wall_framing
    parallel_wall_framing(b)
    from .review_crane_receivers import apply as crane_receivers
    crane_receivers(b)
    from .review_crane_roof_bracing import apply as crane_roof_bracing
    crane_roof_bracing(b)
    from .review_crane_eave_bracing import apply as crane_eave_bracing
    crane_eave_bracing(b)
    from .review_rod_receivers import apply as rod_receivers
    rod_receivers(b)
    from .review_gable_bracing import apply as gable_bracing
    gable_bracing(b)
    from .review_wall_line_joists import apply as wall_line_joists
    wall_line_joists(b,adopt_roof_wall_joists=True)
    from .review_supplements import floor_openings
    floor_openings(b)
    from .review_cfs_complements import apply
    apply(b)
    from .review_hr_strut_bracing import apply as strut_bracing
    strut_bracing(b)
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
    from .review_endwall_posts import apply as endwall_posts
    endwall_posts(b)
    from .review_selected_details import apply as selected_details
    selected_details(b)
    from .review_profile_fit import apply as profile_fit
    profile_fit(b)
    from .review_cfs6_headers import apply as cfs6_headers
    cfs6_headers(b)
    from .review_cfs6_floor_panels import apply as cfs6_floor_panels
    cfs6_floor_panels(b)
    from .review_cfs_strut_ends import apply as cfs_strut_ends
    cfs_strut_ends(b)
    from .review_cfs_endwall_girts import apply as cfs_endwall_girts
    cfs_endwall_girts(b)
    from .review_cfs_endwall_heads import apply as cfs_endwall_heads
    cfs_endwall_heads(b)
    from .review_cfs_kickers import apply as cfs_kickers
    cfs_kickers(b)
    from .review_cfs_cross_plates import apply as cfs_cross_plates
    cfs_cross_plates(b)
    from .review_cfs_door_headers import apply as cfs_door_headers
    cfs_door_headers(b)
    from .review_supplements import track_bearing_datums
    track_bearing_datums(b)
    from .review_double_top_tracks import apply as double_top_tracks
    double_top_tracks(b)
    from .review_cfs6_floor_framing import apply as cfs6_floor_framing
    cfs6_floor_framing(b)
    from .review_cfs_frame_straps import apply as frame_straps
    frame_straps(b)
    from .review_wall_straps import apply as wall_straps
    wall_straps(b)
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
    from .review_track_splices import apply as track_splices
    track_splices(b)
    from .review_cfs6_chord_floors import apply as chord_floor_packs
    chord_floor_packs(b)
    from .review_cfs6_floor_framing import bearing_receivers as floor_bearing_receivers
    floor_bearing_receivers(b,b.levels)
    from .review_edge_chords import apply as edge_chord_corners
    edge_chord_corners(b)
    from .review_cfs_source_bindings import apply as cfs_source_bindings
    cfs_source_bindings(b)
    from .review_concrete_collectors import apply as concrete_collectors
    concrete_collectors(b)
    from .review_concrete_chords import apply as concrete_chords
    concrete_chords(b)
    from .review_concrete_mesh import apply as concrete_mesh
    concrete_mesh(b)
    from .review_concrete_deck import apply as concrete_deck
    concrete_deck(b)
    from .review_source_conflicts import apply as source_conflicts
    source_conflicts(b)
    from .review_plate_boundaries import apply as plate_boundaries
    plate_boundaries(b)
    from .review_hr9_selections import splice_scope
    splice_scope(b)
    from .review_cfs6_roof_distribution import apply as roof_distribution
    roof_distribution(b)
    from .review_cfs6_bridging import apply as actual_crc
    actual_crc(b)
    if key=='cfs6':
        from .review_floor_openings import bind as floor_opening_receivers
        floor_opening_receivers(dict(pilot=b.key,members=b.members,profiles=list(b.profiles.values()),
            connections=b.connections,changes=b.changes,connection_endpoint_links=b.endpoint_links))
    from .review_cfs6_wallface_blocking import apply as wallface_blocking
    wallface_blocking(b)
    from .review_cfs6_diaphragms import apply as source_diaphragms
    source_diaphragms(b)
    from .review_cfs6_endpoint_links import apply as cfs6_endpoint_links
    cfs6_endpoint_links(b)
    from .review_cfs5_floors import apply as cfs5_floors
    cfs5_floors(b)
    from .review_cfs5_parapets import apply as cfs5_parapets
    cfs5_parapets(b)
    from .review_cfs5_diaphragms import apply as cfs5_diaphragms
    cfs5_diaphragms(b)
    from .review_cfs5_roof_restraint import apply as cfs5_roof_restraint
    cfs5_roof_restraint(b)
    from .review_cfs5_collectors import apply as cfs5_collectors
    cfs5_collectors(b)
    from .review_sbmf_headers import apply as sbmf_headers
    sbmf_headers(b)
    from .review_sbmf_roof_seats import apply as sbmf_roof_seats
    sbmf_roof_seats(b)
    from .review_sbmf_restraints import apply as sbmf_restraints
    sbmf_restraints(b)
    from .review_sbmf_girts import apply as sbmf_girts
    sbmf_girts(b)
    from .review_sbmf_post_heads import apply as sbmf_post_heads
    sbmf_post_heads(b)
    from .review_sbmf_tiers import apply as sbmf_tiers
    sbmf_tiers(b)
    from .review_sbmf_source import apply as sbmf_source
    sbmf_source(b)
    from .review_sbmf_hold_downs import apply as sbmf_hold_downs
    sbmf_hold_downs(b)
    from .review_sbmf_wall_chords import apply as sbmf_wall_chords
    sbmf_wall_chords(b)
    from .review_sbmf_mezzanine import apply as sbmf_mezzanine
    sbmf_mezzanine(b)
    from .review_sbmf_collectors import apply as sbmf_collectors
    sbmf_collectors(b)
    from .review_sbmf_bearing import apply as sbmf_bearing
    sbmf_bearing(b)
    from .review_sbmf_deck import apply as sbmf_deck
    sbmf_deck(b)
    from .review_sbmf_floor import apply as sbmf_floor
    sbmf_floor(b)
    from .review_sbmf_diaphragms import apply as sbmf_diaphragms
    sbmf_diaphragms(b)
    from .review_sbmf_stud_heads import apply as sbmf_stud_heads
    sbmf_stud_heads(b)
    from .review_sbmf_sag_angles import apply as sbmf_sag_angles
    sbmf_sag_angles(b)
    from .review_cfs25_secondary import apply as cfs25_secondary
    cfs25_secondary(b)
    from .review_cfs25_existing import apply as cfs25_existing
    cfs25_existing(b)
    from .review_cfs26_primary import apply as canopy_primary
    canopy_primary(b)
    from .review_cfs26_purlins import apply as canopy_purlins
    canopy_purlins(b)
    from .review_cfs25_cladding import apply as cfs25_cladding
    cfs25_cladding(b)
    from .review_cfs6_floor_panels import bind_bearing_clearances
    bind_bearing_clearances(b)
    return b.finish()
