"""Explicit fictional pack-fit corrections, preserving every selected ply.

This is an authored geometry proposal for the registered examples. It is not a
built-up column capacity check or a silent correction of a real project.
"""
import copy,math
from .pilots.geometry import strips
from .bim_contract import _convex_overlap


def separate_plies(profiles,profile,gap=1/64):
    if profile.get('family')!='built_up':return False
    before=copy.deepcopy(profile['components']);placed=[]
    def polygons(component):
        a=math.radians(component['rotation_deg']);c,s=math.cos(a),math.sin(a);x,y=component['offset']
        return [[(x+c*u-s*v,y+s*u+c*v) for u,v in poly] for poly in strips(profiles[component['profile_id']],profiles)]
    def overlap(first,second):
        for p in first:
            for q in second:
                if any(max(v[k] for v in p)<=min(v[k] for v in q)+1e-9 or max(v[k] for v in q)<=min(v[k] for v in p)+1e-9 for k in (0,1)):continue
                if _convex_overlap(p,q)>1e-8:return True
        return False
    # Retain existing locations when they already fit. Move colliding outside
    # plies outwards, in explicit 1/64 in fitting increments, without changing
    # the selected profile, rotation, thickness, ply count or source records.
    for component in sorted(profile['components'],key=lambda p:abs(p['offset'][0])):
        sign=-1 if component['offset'][0]<0 else 1
        for step in range(2049):
            poly=polygons(component)
            if not any(overlap(poly,q) for q in placed):placed.append(poly);break
            component['offset'][0]+=sign*gap
        else:raise ValueError('Cannot separate source plies in '+profile['id'])
    if before==profile['components']:return False
    profile['fit_proposal']=dict(previous_components=before,increment_in=gap,
        basis='Accepted fictional fit: separate overlapping plies outwards; selected section/count retained; capacity not rechecked')
    return True


def apply(builder):
    if not builder.key.startswith('cfs'):return
    changed=[]
    for profile in builder.profiles.values():
        if separate_plies(builder.profiles,profile):changed.append(profile['id'])
    if changed:
        builder.changes.append(dict(kind='separate_overlapping_pack_plies',profile_ids=changed,basis='Accepted fictional physical-fit proposal; no capacity verification'))
        builder.note('PACK-FIT','A: overlapping chord-pack plies in the earlier drawing geometry are separated outwards in 1/64 in increments. Exact source sections, material thicknesses and ply counts remain unchanged. The profile register records every former and adopted ply location. This does not certify the revised built-up arrangement.')
