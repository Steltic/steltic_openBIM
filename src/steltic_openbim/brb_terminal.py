"""Smooth, integral end transitions cut from the same steel heat as the HR yielding core."""
import math


def shaped_sections(spec,length):
    from .brb_supplier_core import rectangular_ring
    source=spec['terminal'];gauge=spec['yielding_length_in'];d=spec['depth_in'];thin=spec['thickness_in']
    thick=thin*source['end_area_ratio'];change=source['minimum_transition_length_in']
    reserve=(length-gauge)/2
    if reserve+1e-5<change:raise ValueError('Casing cannot contain both selected core transitions and the complete yielding segment')
    stations=[(0.,thick)]
    if reserve-change>1e-6:stations.append((reserve-change,thick))
    # Sixteen chords resolve the smooth cosine milling profile. Its derivatives
    # vanish at the constant-area ends, reducing the sharp shoulder of a linear taper.
    for i in range(1,17):
        fraction=i/16.
        thickness=thin+(thick-thin)*(1.+math.cos(math.pi*fraction))/2.
        stations.append((reserve-change+change*fraction,thickness))
    mirror=[(length-s,t) for s,t in reversed(stations)]
    return [[s,rectangular_ring(t,d)] for s,t in stations+mirror]
