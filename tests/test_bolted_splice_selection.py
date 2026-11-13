"""A bolted column splice is drawn with the flange bolt group HR selected, in either source wording."""
from functools import lru_cache
import pytest
from steltic_openbim.review_cases import evidence, scenario, build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.connection_details import prepare
from steltic_openbim.bolted_splice_selection import flange_selection, web_bolts_per_side


def selected(case, identity):
    return next(r['components'] for r in evidence(case)['calc']['connections'] if r['id'] == identity)


@pytest.mark.parametrize('case,identity,count,diameter,grade,width', [
    ('hr18', 'conn-lateral_col-W14X109', 8, .875, 'A325-N', 14.6),   # "... each flange with 8 x ... bolts per side"
    ('hr18', 'conn-gravity_col-W14X48', 2, .875, 'A325-N', 8.0),
    ('hr1', 'conn-gravity_col-W14X48', 2, .875, 'A325-N', 8.0),
    ('hr30', 'conn-gravity_col-W14X61', 2, 1.0, 'A490-X', 10.0),      # "... outside each flange with 2 x ... bolts each side"
])
def test_source_flange_bolt_group_is_read_in_both_wordings(case, identity, count, diameter, grade, width):
    chosen = flange_selection(selected(case, identity))
    assert chosen['bolts_per_flange_per_side'] == count
    assert chosen['diameter_in'] == diameter and chosen['grade'] == grade and chosen['width_in'] == width
    assert web_bolts_per_side(selected(case, identity)) == 2


def test_record_without_a_bolted_flange_group_is_not_guessed():
    assert flange_selection('CJP groove-welded flanges and web; erection plates with 4 x 7/8 in A325 bolts') is None


@lru_cache(maxsize=4)
def splice_scenes(case):
    package = evidence(case)['package']; chosen = scenario(case)
    model = build_model(package, {'revision': 1, 'design_scenario': {'id': case, 'source_sha256': chosen['source_sha256'],
                                                                        'answers_sha256': fingerprint(chosen['answers'])}})
    return [scene for scene in prepare(model, package) if scene['family'] == 'review_splice']


@pytest.mark.parametrize('case', ['hr18', 'hr1', 'hr30'])
def test_every_bolted_splice_scene_carries_its_own_record_count_and_diameter(case):
    records = {'connections/' + r['id']: r['components'] for r in evidence(case)['calc']['connections']}
    checked = 0
    for scene in splice_scenes(case):
        flange_groups = [g for g in scene['fasteners'] if g['id'][:1] == 'F' and g['id'][1:].isdigit() and len(g['id']) == 3]
        if not flange_groups:
            continue
        chosen = [flange_selection(records[i]) for i in scene['source_record_ids'] if i in records]
        chosen = [c for c in chosen if c]
        stated = {(c['bolts_per_flange_per_side'], c['diameter_in']) for c in chosen}
        assert len(stated) == 1, scene['title']   # records sharing one detail must not disagree
        count, diameter = next(iter(stated))
        for group in flange_groups:
            assert len(group['points']) == count, (scene['title'], group['id'])
            assert group['diameter'] == diameter
        checked += 1
    assert checked
