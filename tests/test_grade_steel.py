import numpy as np
import pytest
from shapely.geometry import Polygon

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.bim_contract import joint_disposition_findings
from steltic_openbim.connection_cuts import drill_plate
from steltic_openbim.grade_steel import add_nut, add_rail
from test_brb_core_readback import as_mesh


XY = (np.array([1., 0., 0.]), np.array([0., 1., 0.]))


@pytest.mark.parametrize('travel', [0., 2.])
def test_tab_bore_preserves_selected_direction_and_travel(travel):
    assembly = Assembly('Transfer tab', {})
    plate = assembly.box('P1', [-4, -3, 0], [8, 6, .75])
    drill_plate(plate, [[0, 0, 0]], [0, 0, 1], 1.125, 'S', radial_reference=[1, 0, 0], slot_travel=travel)
    mesh = as_mesh(plate['faces'])
    section = mesh.section([0, 0, 1], .375, XY)
    assert mesh.closed and len(section.interiors) == 1
    hole = Polygon(section.interiors[0])
    assert hole.bounds == pytest.approx((-(travel+1.125)/2, -.5625, (travel+1.125)/2, .5625))


def test_nut_is_a_drilled_hex_seated_on_the_washer():
    assembly = Assembly('Heavy rod', {})
    add_nut(assembly, 0, [4, -5, 0], 2.5, 3., dict(nut_across_flats_in=5., nut_height_in=3., nut_material='QT steel'))
    mesh = as_mesh(assembly.parts[0]['faces'])
    section = mesh.section([0, 0, 1], 4., XY)
    assert mesh.closed and len(section.interiors) == 1
    assert mesh.vertices[:, 2].min() == pytest.approx(2.5)
    assert mesh.vertices[:, 2].max() == pytest.approx(5.5)
    assert Polygon(section.interiors[0]).bounds == pytest.approx((2.5, -6.5, 5.5, -3.5))


def test_grade_receiver_webs_and_welds_span_between_both_plates():
    stock = dict(horizontal_length=18., end_margin_in=2., width_in=12., bottom_plate_in=1.5,
                 top_plate_in=3., web_height_in=2., web_thickness_in=1.5, web_gauge_in=5.,
                 record_id='issued-rail', material='A572', weld_material='E70', interface_note='Underside at grade.')
    assembly = Assembly('Grade receiver', {})
    add_rail(assembly, stock, 8.)
    parts = {part['id']: as_mesh(part['faces']) for part in assembly.parts}
    assert parts['GRADE-SOLE'].vertices[:, 2].min() == 0.
    assert parts['BASE'].vertices[:, 2].max() == 6.5
    assert len(assembly.welds) == 4
    for weld in assembly.welds:
        assert (weld['a'][0], weld['b'][0]) == (8., 28.)
        for receiver in weld['connects']:
            for point in np.linspace(weld['a'], weld['b'], 5):
                assert parts[receiver].point_distance(point) < 1e-6


@pytest.mark.parametrize('grade,allowed,waived,valid', [
    (0., ['col'], False, True), (-144., ['col'], False, False), (0., [], False, False),
    (None, ['col'], False, False), (0., ['col'], True, False),
])
def test_grade_boundary_needs_the_issued_column_and_datum(grade, allowed, waived, valid):
    scope = dict(grade_in=grade, clipped_columns=allowed)
    package = dict(require_connection_parts=True, design_records=[dict(id='issue', waived=waived, data=dict(steel_delivery_scope=scope))],
                   physical=dict(members=[dict(id='col', kind='column')], joints=[dict(id='end', point=[0, 0, 0],
                   member_ends=[dict(member_id='col', end='start')])], joint_dispositions=[dict(joint_id='end',
                   kind='scope_boundary', design_record_ids=['issue'])]))
    findings = joint_disposition_findings(package, verified_bonds={})
    assert [f['code'] for f in findings] == ([] if valid else ['joint_scope_boundary'])
