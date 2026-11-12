"""The original gold records exercise different source notation, not mock NLP."""
import pytest
from steltic_openbim.review_cases import evidence
from steltic_openbim.review_base_selection import embedment,rods,flange_rows,lug_arms


def selected(case,identity):
    return next(r['components'] for r in evidence(case)['calc']['connections'] if r['id']==identity)


@pytest.mark.parametrize('case,profile,count,dia,grade',[
    ('hr8','W14X398',6,3.75,'A193'),('hr8','W14X311',4,3.75,'A193'),
    ('hr5','W14X120',4,.75,'F1554'),('hr7a','W14X90',4,1.5,'F1554')])
def test_exposed_base_with_embedded_lug_retains_selected_anchor_rods(case,profile,count,dia,grade):
    role='gravity_col' if case in ('hr5','hr7a') else 'lateral_col'
    text=selected(case,f'conn-base-{role}-{profile}')
    assert embedment(text) is None
    n,d,spec=rods(text);assert (n,d)==(count,dia);assert grade in spec
    rows,cols,pitch,gap,spacing=flange_rows(text)
    assert 2*rows*cols==count and gap>0 and spacing>0


def test_embedded_column_and_two_distinct_lug_arms_are_not_conflated():
    assert embedment(selected('hr24','conn-base-lateral_col-W14X665'))==78
    assert embedment(selected('hr24','conn-base-lateral_col-W14X730'))==90
    assert lug_arms(selected('hr8','conn-base-lateral_col-W14X398'))==((3.75,12,6),(3.75,16,6))
    assert lug_arms(selected('hr8','conn-base-gravity_col-W14X132'))==((1.25,14,6),(1,12,6))


@pytest.mark.parametrize('case,profile,length',[
    ('hr10','BOX24X4',120),('hr10','BOX30X4',126),
    ('hr15','BOX34X4',42),('hr15','BOX58X4',72),
    ('hr23','BOX34X4',84),('hr23','BOX58X4',120),
    ('hr26','BOX28X4',108),('hr29','BOX34X4',120)])
def test_source_box_before_embedded_verb_retains_real_shaft_embedment(case,profile,length):
    assert embedment(selected(case,'conn-base-lateral_col-'+profile))==length


def test_hr6_anchor_reinforcement_is_not_embedded_column_reinforcement():
    text=selected('hr6','conn-base-lateral_col-W14X193')
    assert embedment(text) is None
    assert rods(text)[:2]==(4,3)
    assert lug_arms(text)==((6.25,24,12),(2.25,8,12))


def test_braced_base_uses_checked_weld_precision_and_one_sided_stock():
    from steltic_openbim.base_plate_extensions import base_edge_layout,frame_extension
    records={row['id']:row for row in evidence('hr30')['calc']['connections']}
    base=records['conn-base-lateral_col-W14X159']
    assert frame_extension(base)==('Y',30,6.5)
    assert lug_arms(base['components'])==((3.25,20,7),(1.5,12,7))
    assert base_edge_layout(records['conn-brace-base-Y-HSS5X5X3/8'])==pytest.approx(14.33)
    assert base_edge_layout(records['conn-brace-base-X-HSS4-1/2X4-1/2X3/8'])==pytest.approx(7.)
