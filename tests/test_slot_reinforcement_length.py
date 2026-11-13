from steltic_openbim.review_hr_brace_ends import stated_reinforcement
from steltic_openbim.saved_assemblies import material_for
import pytest


def test_full_statement_gives_the_plate_length():
    text = ('HSS5X5X1/2 slotted for a 0.75 in A572 Gr 50 gusset; slot reinforced with two PL 0.5 x 2.5 in '
            '(2 PL 1/2 x 2.5 x 12 in A572 Gr 50 slot reinforcement, centred on the slot end)')
    match = stated_reinforcement(text)
    assert (match[1], match[2], match[3]) == ('1/2', '2.5', '12')


def test_single_statement_is_kept():
    assert stated_reinforcement('slot reinforced with two PL 0.5 x 4 in reinforcing plates')[3] is None
    assert stated_reinforcement('2 PL 3/8 x 5 x 17 in')[3] == '17'
    assert stated_reinforcement('no reinforcement needed') is None


def schedule():
    rows = [('gold-material-3', 'Plates and bars', 'ASTM A572 Grade 50'),
            ('gold-material-5', 'Notch toughness, plates (AISC 341-22 A3.3)', 'plates 2 in and thicker need CVN toughness'),
            ('gold-material-8', 'Welds', 'E70XX')]
    return {i: dict(id=i, source_item=item, specification=spec) for i, item, spec in rows}


def test_new_plate_takes_the_schedule_plate_grade():
    part = dict(id='ST00', kind='plate')
    assert material_for(part, 'plate', None, schedule(), ['connections/x']) == 'gold-material-3'


def test_two_plate_grades_stay_unresolved():
    materials = schedule()
    materials['gold-material-9'] = dict(id='gold-material-9', source_item='Plates over 4 in', specification='ASTM A588')
    with pytest.raises(ValueError):
        material_for(dict(id='ST00', kind='plate'), 'plate', None, materials, ['connections/x'])
