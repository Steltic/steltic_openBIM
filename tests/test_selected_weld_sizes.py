"""Welds that HR sizes in a connection record are drawn at that size."""
from functools import lru_cache
import pytest
from steltic_openbim.review_cases import evidence, scenario, build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.connection_details import prepare
from steltic_openbim.selected_weld_sizes import (cap_plate_thickness, cap_perimeter_fillet, continuity_web_fillet,
                                                 column_to_base_weld)


def selected(case, identity):
    return next(r['components'] for r in evidence(case)['calc']['connections'] if r['id'] == identity)


@lru_cache(maxsize=4)
def scenes(case):
    package = evidence(case)['package']; chosen = scenario(case)
    model = build_model(package, {'revision': 1, 'design_scenario': {'id': case, 'source_sha256': chosen['source_sha256'],
                                                                        'answers_sha256': fingerprint(chosen['answers'])}})
    return list(prepare(model, package))


def test_source_wording_is_read():
    cap = selected('hr21', 'conn-gravity_col-W14X90')
    assert cap_plate_thickness(cap) == .75 and cap_perimeter_fillet(cap) == .25
    assert continuity_web_fillet(selected('hr16', 'conn-roof-W21X57')) == .4375
    assert column_to_base_weld(selected('hr35', 'conn-base-lateral_col-W10X39')) == ('fillet', .3125)


def test_a_lug_cjp_does_not_select_the_column_weld():
    text = selected('hr21', 'conn-base-lateral_col-W14X90')
    assert 'CJP-welded to the base plate' in text       # the shear lug
    assert column_to_base_weld(text) is None


def test_hr21_cap_weld_and_plate_follow_the_record():
    caps = [s for s in scenes('hr21') if any(w['id'] == 'WC' for w in s['welds']) and 'CAP' in {p['id'] for p in s['parts']}]
    assert caps
    for scene in caps:
        weld = next(w for w in scene['welds'] if w['id'] == 'WC')
        assert weld['size'] == .25 and weld['basis'] == 'S'
        cap = next(p for p in scene['parts'] if p['id'] == 'CAP')
        assert 'PL 0.75 in' in cap['description']


def test_hr35_column_base_weld_is_the_selected_fillet():
    found = 0
    for scene in scenes('hr35'):
        if 'connections/conn-base-lateral_col-W10X39' not in scene['source_record_ids']:
            continue
        weld = next((w for w in scene['welds'] if w['id'] == 'W1'), None)
        if weld is None:
            continue
        assert weld['kind'] == 'fillet' and weld['size'] == .3125
        found += 1
    assert found


def test_hr16_continuity_plate_web_fillets_are_the_selected_size():
    records = {'connections/' + r['id']: r['components'] for r in evidence('hr16')['calc']['connections']}
    checked = 0
    for scene in scenes('hr16'):
        welds = [w for w in scene['welds'] if w['id'].startswith('WC') and w['id'][2:].isdigit()]
        if not welds:
            continue
        stated = {continuity_web_fillet(records[i]) for i in scene['source_record_ids'] if i in records} - {None}
        if len(stated) != 1:
            continue
        assert {w['size'] for w in welds} == stated, scene['title']
        assert all(w['basis'] == 'S' for w in welds)
        checked += 1
    assert checked
