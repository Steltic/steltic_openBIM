import re
from steltic_openbim.design_pdf import compact_references


def test_long_schedule_ranges_preserve_gaps_detail_numbers_and_sheet_series():
    original={f'1/C{i:03}' for i in range(10,113)}-{'1/C011','1/C046'}
    original.update({'2/C010','2/C011','1/S501','1/S503','supplier detail'})
    label=compact_references(reversed(sorted(original)))
    restored=set()
    for token in label.split(', '):
        match=re.fullmatch(r'([^/]+)/([A-Z]+)(\d+)(?:-\2(\d+))?',token)
        if not match:restored.add(token);continue
        restored.update(f'{match[1]}/{match[2]}{i:03}' for i in range(int(match[3]),int(match[4] or match[3])+1))
    assert restored==original
    assert len(label)<130
