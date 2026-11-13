"""Drawing grid names follow the HR design's own grid names when a column stands off the regular grid."""
from steltic_openbim.source_grid_labels import labelled, source_lines
from steltic_openbim.review_cases import evidence


def test_regular_grid_keeps_sequential_names():
    assert labelled([0, 336, 672], {'NX': 2, 'SX': 336.0}, 0) == [('1', 0), ('2', 336), ('3', 672)]
    assert labelled([0, 336, 672], {'NY': 2, 'SY': 336.0}, 1) == [('A', 0), ('B', 336), ('C', 672)]


def test_off_grid_column_line_does_not_rename_later_lines():
    config = evidence('hr12')['configuration']          # X Grids 1-6 and Y Grids A-F at 28 ft; chamfer column at 14 ft
    assert source_lines(config, 0) == [0.0, 336.0, 672.0, 1008.0, 1344.0, 1680.0]
    x = labelled([0, 168, 336, 672, 1008, 1344, 1680], config, 0)
    y = labelled([0, 168, 336, 672, 1008, 1344, 1680], config, 1)
    assert [name for name, _ in x] == ['1', '1.5', '2', '3', '4', '5', '6']
    assert [name for name, _ in y] == ['A', 'A.5', 'B', 'C', 'D', 'E', 'F']
    assert dict(y)['C'] == 672 and dict(x)['4'] == 1008


def test_without_a_usable_source_grid_names_stay_sequential():
    assert labelled([0, 100, 250], {}, 0) == [('1', 0), ('2', 100), ('3', 250)]
    # a source line with no column on it: do not guess
    assert labelled([0, 100, 672], {'NX': 2, 'SX': 336.0}, 0) == [('1', 0), ('2', 100), ('3', 672)]
