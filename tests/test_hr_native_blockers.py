"""Fresh native HR jobs: contract-valid data that used to stop delivery.

A slot end written to nine decimals, a connection located by its joint only, and box / cylinder
constituents are all allowed by the physical contract. Each must be delivered and measured.
"""
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from steltic_openbim.base_hardware_clearance import located
from steltic_openbim.constituent_solid_readback import matches_box, matches_cylinder
from steltic_openbim.joint_mesh_readback import Mesh
from steltic_openbim.pilots.geometry import member_faces, part_faces


def mesh(faces):
    points = []; rows = []
    for face in faces:
        row = []
        for p in face:
            key = tuple(round(float(v), 9) for v in p)
            if key not in points: points.append(key)
            row.append(points.index(key))
        rows.append(tuple(row))
    return Mesh(np.asarray(points, dtype=float), tuple(rows))


BOX = dict(type='box', origin=[10., -0.1875, 2.], size=[4.5, .375, 15.], x_axis=[1., 0., 0.], y_axis=[0., 1., 0.])
ROD = dict(type='cylinder', origin=[3., 4., -12.], axis=[0., 0., 1.], radius=.5, length=18.)
SKEW = dict(type='cylinder', origin=[1., 2., 3.], axis=[.6, 0., .8], radius=.4375, length=2.5)


def test_box_and_cylinder_constituents_are_measured_from_the_actual_faces():
    assert matches_box(mesh(part_faces(dict(geometry=BOX), {})), BOX)
    for geometry in (ROD, SKEW):
        assert matches_cylinder(mesh(part_faces(dict(geometry=geometry), {})), geometry)


@pytest.mark.parametrize('declared', [dict(BOX, size=[4.5, .5, 15.]), dict(BOX, origin=[10., -0.1875, 2.25]),
                                      dict(BOX, x_axis=[0., 0., 1.], y_axis=[0., 1., 0.])])
def test_box_with_another_thickness_position_or_orientation_fails(declared):
    assert not matches_box(mesh(part_faces(dict(geometry=BOX), {})), declared)


@pytest.mark.parametrize('declared', [dict(ROD, radius=.4375), dict(ROD, length=17.), dict(ROD, origin=[3., 4.25, -12.]),
                                      dict(ROD, axis=[1., 0., 0.])])
def test_cylinder_with_another_diameter_length_position_or_axis_fails(declared):
    assert not matches_cylinder(mesh(part_faces(dict(geometry=ROD), {})), declared)


def test_a_box_is_not_accepted_as_a_cylinder_or_the_reverse():
    assert not matches_cylinder(mesh(part_faces(dict(geometry=BOX), {})), ROD)
    assert not matches_box(mesh(part_faces(dict(geometry=ROD), {})), BOX)


def test_slot_end_written_to_nine_decimals_is_placed_on_the_member_end_and_leaves_a_square_cut(tmp_path):
    """HR may round a slot end; the derived drawing source carries it on the member end, the original stays as issued."""
    from test_native_hr_completion import ordinary_job
    from steltic_openbim.drawing_workflow import fingerprint
    from steltic_openbim.native_hr_completion import complete_native_hr, slot_end_merges
    source = ordinary_job(); h = source.pop('source_handoff'); h.pop('contract_sha256')
    physical = source['physical']; brace = next(m for m in physical['members'] if m['id'] == 'B')
    brace.update(axis=[[0., 0., 0.], [150., 0., 168.]], end_offsets=[[10.406496395, 0., 11.655275963], [-13.5700713, 0., -15.198479856]])
    physical['joints'][-1]['point'] = brace['axis'][1]
    ends = [[p + o for p, o in zip(point, offset)] for point, offset in zip(brace['axis'], brace['end_offsets'])]
    length = math.dist(*ends); rounded = round(length, 9)
    assert rounded != length and abs(rounded - length) < 1e-9
    brace['slots'] = [dict(section_axis=0, start_in=length - 14.0625, end_in=rounded, width_in=.875, centre_in=0., connection_id='far-end')]
    h['source_bindings']['native_content_sha256'] = fingerprint(source); h['contract_sha256'] = fingerprint(h); source['source_handoff'] = h
    profiles = {p['id']: p for p in physical['profiles']}; ray = (np.asarray(ends[1]) - np.asarray(ends[0])) / length

    def overrun(member):
        points = np.asarray([p for face in member_faces(member, profiles) for p in face])
        return float(((points - np.asarray(ends[0])) @ ray).max() - length)
    assert overrun(brace) > 1e-5                                   # as issued: the sliver skews the end cap
    assert slot_end_merges(physical['members']) == [('B', 0, 'end_in', length)]
    before = fingerprint(source); derived = complete_native_hr(source)
    assert fingerprint(source) == before and derived is not source
    made = next(m for m in derived['physical']['members'] if m['id'] == 'B')
    far = next(s for s in made['slots'] if s.get('connection_id') == 'far-end')
    assert far['end_in'] == math.dist(*[[p + o for p, o in zip(point, offset)] for point, offset in zip(made['axis'], made['end_offsets'])])
    assert far['issued_end_in'] == rounded
    assert slot_end_merges(derived['physical']['members']) == []
    square = dict(brace, slots=[dict(brace['slots'][0], end_in=length)])
    assert abs(overrun(square)) < 1e-9


def test_slot_stations_away_from_the_ends_and_exact_ends_are_left_as_issued():
    from steltic_openbim.native_hr_completion import slot_end_merges
    member = dict(id='M', axis=[[0., 0., 0.], [100., 0., 0.]], end_offsets=[[1., 0., 0.], [-1., 0., 0.]],
                  slots=[dict(start_in=0., end_in=12.), dict(start_in=86., end_in=98.), dict(start_in=40., end_in=40.0000001)])
    assert slot_end_merges([member]) == []
    member['slots'][0]['start_in'] = 4e-8; member['slots'][1]['end_in'] = 98 - 9e-8
    assert slot_end_merges([member]) == [('M', 0, 'start_in', 0.), ('M', 1, 'end_in', 98.)]
    assert slot_end_merges([dict(member, extrusion_end_offsets=member['end_offsets'])]) == []


def test_a_connection_is_located_by_its_joint_when_it_carries_no_point():
    joints = {'J1': dict(id='J1', point=[300., 0., 0.])}
    c = dict(id='C1', joint_id='J1', assembly_instance=dict(origin=[1., 2., 3.], bindings=dict(COLUMN='COL', BRACE='BR')))
    assert located(c, joints) == ((300., 0., 0.), ['COL', 'BR'])
    assert located(dict(c, point=[5., 6., 7.], member_ids=['COL']), joints) == ((5., 6., 7.), ['COL'])
    assert located(dict(id='C2', assembly_instance=dict(origin=[1., 2., 3.], bindings={})), joints)[0] == (1., 2., 3.)
    with pytest.raises(ValueError, match='no located joint'):
        located(dict(id='C3'), joints)


def test_an_unreadable_base_does_not_replace_the_findings_of_the_other_connections(tmp_path, monkeypatch):
    from test_native_hr_completion import ordinary_job
    from steltic_openbim import base_hardware_clearance
    from steltic_openbim.drawing_workflow import DrawingStore
    from steltic_openbim.ifc_assembly_verification import verify_assembly_fit
    from steltic_openbim.ifc_export import export_drawing
    store = DrawingStore(tmp_path / 'jobs'); store.import_package('NewHRBuilding', ordinary_job())
    directory, _ = store.current('NewHRBuilding'); derived = json.loads((directory / 'source.json').read_bytes())
    out = tmp_path / 'model.ifc'; export_drawing(directory, out)
    before = verify_assembly_fit(out, derived['physical'], derived['source_handoff'], derived['design_records'])
    assert 'counts' in before

    def broken(checker):
        raise KeyError('point')
    monkeypatch.setattr(base_hardware_clearance, 'check', broken)
    after = verify_assembly_fit(out, derived['physical'], derived['source_handoff'], derived['design_records'])
    codes = [f.get('code') for f in after['findings']]
    assert not after['passed'] and codes.count('base_hardware_clearance_unverified') == 1
    assert [c for c in codes if c != 'base_hardware_clearance_unverified'] == [f.get('code') for f in before['findings']]
    assert after['counts']['all_assembly_occurrences'] == before['counts']['all_assembly_occurrences']
