"""Name drawing grid lines as the HR design names them.

HR numbers its regular grid 1, 2, ... along X and A, B, ... along Y. A column that stands off that grid (a chamfer
column, for example) must not take the next number or letter, or every later line is renamed and a record written
for "Grid C" lands on another line. Off-grid column lines take the name of the preceding source line with a
fractional suffix: 1.5 lies halfway between Grids 1 and 2.
"""


def source_lines(config, axis):
    explicit, count, spacing = (('XS', 'NX', 'SX'), ('YS', 'NY', 'SY'))[axis]
    values = config.get(explicit)
    if isinstance(values, (list, tuple)) and values:
        try:
            return sorted(float(v) for v in values)
        except (TypeError, ValueError):
            return None
    try:
        return [index * float(config[spacing]) for index in range(int(config[count]) + 1)]
    except (KeyError, TypeError, ValueError):
        return None


def _name(index, axis):
    return str(index + 1) if axis == 0 else chr(65 + index) if index < 26 else 'Y' + str(index + 1)


def labelled(values, config, axis, tolerance=1e-3):
    """Return [(label, coordinate)] for the column lines of one plan axis."""
    source = source_lines(config or {}, axis)
    on_grid = lambda v: any(abs(v - s) <= tolerance for s in source)
    if not source or not all(any(abs(v - s) <= tolerance for v in values) for s in source) or all(on_grid(v) for v in values):
        # No usable source grid, a source line without a column, or nothing off grid: keep the sequential names.
        return [(_name(index, axis), value) for index, value in enumerate(values)]
    result = []
    for value in values:
        if on_grid(value):
            index = min(range(len(source)), key=lambda k: abs(source[k] - value))
            result.append((_name(index, axis), value)); continue
        before = [k for k, s in enumerate(source) if s < value]
        if not before:
            result.append((_name(0, axis) + '-' + format(abs(source[0] - value), 'g'), value)); continue
        index = before[-1]
        span = (source[index + 1] - source[index]) if index + 1 < len(source) else None
        fraction = (value - source[index]) / span if span else None
        suffix = format(round(fraction, 2), 'g').lstrip('0') if fraction is not None and 0 < fraction < 1 else '+' + format(value - source[index], 'g')
        result.append((_name(index, axis) + suffix, value))
    return result
