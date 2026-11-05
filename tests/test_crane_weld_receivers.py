import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.assembly_scene import section_polygons
from steltic_openbim.assembly_templates import build_scene
from test_crane_roof_bracing import case


def test_crane_and_roof_weld_midpoints_reach_real_parts_with_only_authored_slot_clearance(case):
    model,package=case;seen=set();count=0
    for c in model['connections']:
        par=c.get('parameters',{});kind=par.get('actual_crane_joint')
        if not kind and not par.get('crane_roof_bracing') and not par.get('crane_eave_bracing'):continue
        key=(kind,bool(par.get('crane_roof_bracing')),bool(par.get('crane_eave_bracing')),par.get('sign'),par.get('into'))
        if key in seen:continue
        seen.add(key);scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        for w in scene['welds']:
            vector=[b-a for a,b in zip(w['a'],w['b'])];axis=max(range(3),key=lambda i:abs(vector[i]));other=[i for i in range(3) if i!=axis]
            q=[(a+b)/2 for a,b in zip(w['a'],w['b'])]
            for name in w['connects']:
                polygons=section_polygons(parts[name],axis,q[axis]);query=Point([q[i] for i in other])
                distance=min((Polygon(p).distance(query) for p in polygons),default=1e6)
                # The explicit slots have1/16 in clearance each side of the
                # plate. Source fillet sizes and unverified local fit remain
                # in the record; this is geometry, not weld qualification.
                tolerance=.062501 if name.startswith('KICKER') else .00001
                assert distance<=tolerance,(c['id'],w['id'],name,distance)
                count+=1
    assert count>150
