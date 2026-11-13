"""Read weld sizes that HR states in a connection record, so a drawn weld carries the selected size."""
import re
from .assembly_templates import NUMBER, number

_CAP_PLATE = re.compile(r'cap plate PL ' + NUMBER + r' in\b', re.I)
_CAP_FILLET = re.compile(r'cap plate[^;]*?welded all around with ' + NUMBER + r' in fillets', re.I)
_CONTINUITY_WEB = re.compile(NUMBER + r' in fillets both sides to the column web', re.I)
_COLUMN_BASE_FILLET = re.compile(r'column welded to the base plate with ' + NUMBER + r' in (?:E70(?:XX)? )?fillets', re.I)
_COLUMN_BASE_CJP = re.compile(r'column (?:flanges and web )?(?:is )?(?:CJP[- ]welded|welded)[^;]*?(?:to the (?:base )?plate)[^;]*?CJP|column flanges and web CJP-welded to the base plate', re.I)


def cap_plate_thickness(text):
    match = _CAP_PLATE.search(str(text))
    return number(match[1]) if match else None


def cap_perimeter_fillet(text):
    match = _CAP_FILLET.search(str(text))
    return number(match[1]) if match else None


def continuity_web_fillet(text):
    """The stated fillet between a continuity plate and the column web, or None when HR does not state one."""
    match = _CONTINUITY_WEB.search(str(text))
    return number(match[1]) if match else None


def column_to_base_weld(text):
    """Return ('fillet', size), ('CJP', None) or None for the column-to-base-plate weld itself.

    A CJP named elsewhere in the record (a shear lug, for example) does not select the column weld.
    """
    text = str(text)
    match = _COLUMN_BASE_FILLET.search(text)
    if match:
        return 'fillet', number(match[1])
    if _COLUMN_BASE_CJP.search(text):
        return 'CJP', None
    return None
