"""Read the HR-selected flange plate and bolt group of a milled, bolted W-column splice."""
import re
from .assembly_templates import NUMBER, number

_FLANGE = re.compile(
    r'flange plates? PL ' + NUMBER + r' x ' + NUMBER + r' in (?:outside )?each flange with (\d+) x ' + NUMBER +
    r' in\b[^;]*?bolts (?:per|each) side', re.I)
_WEB = re.compile(r'web plates?(?: both sides)? with (\d+)(?: x ' + NUMBER + r' in)?[^;]*?bolts', re.I)
_GRADE = re.compile(r'\b(A325|A490)(?:-([NX]))?\b')


def flange_selection(text):
    """Return the selected flange plate thickness, width, bolts per flange per side, bolt diameter and grade.

    HR writes the count either as "... each flange with N x d in <grade> bolts per side" or as
    "... outside each flange with N x d in <grade> bolts each side". Both state N bolts in each flange
    plate on each side of the splice. Return None when the record does not state the group.
    """
    match = _FLANGE.search(str(text))
    if not match:
        return None
    grade = _GRADE.search(match[0])
    return dict(thickness_in=number(match[1]), width_in=number(match[2]), bolts_per_flange_per_side=int(match[3]),
                diameter_in=number(match[4]), grade=grade[0] if grade else None, source=match[0])


def web_bolts_per_side(text):
    match = _WEB.search(str(text))
    return int(match[1]) if match else None
