"""Select the stated paired-plate variant for the actual column face."""
import re
from .assembly_templates import NUMBER

PAIR = r'(?:two plates PL|two plates,.*?each: plate) '+NUMBER+r' x '+NUMBER+r' in'


def paired(text, *, weak=False, column=None):
    line=next((line for line in text.splitlines() if re.search(PAIR,line,re.I)),None)
    if line is None:return text,None
    if 'web-side ends on the ' in line:
        common=line.split('; fit-up:',1)[-1] if '; fit-up:' in line else ''
        if weak:
            match=re.search(r'web-side ends on the '+re.escape(column or '')+r'\b.*?(?=; web-side ends on the |; fit-up:|$)',line,re.I)
            if match is None:raise ValueError('No source paired-plate web-side selection for '+str(column))
            line=match[0]+'; fit-up: '+common
        else:line=line.split('; web-side ends on the ',1)[0]+'; fit-up: '+common
    return line,re.search(PAIR,line,re.I)
