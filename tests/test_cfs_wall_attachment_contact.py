"""Every proposed screw must actually cross each named joined sheet."""
import json
import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs_wall_bindings import bind,signature
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons


@pytest.fixture(scope='module')
def scenes():
    p=evidence('cfs1')['package'];m=build_model(p,dict(design_scenario=dict(id='cfs1',answers_sha256=fingerprint(scenario('cfs1')['answers']))))
    bind(m);seen=set();result=[]
    for c in m['connections']:
        if not any(k in c.get('parameters',{}) for k in ('physical_jamb_base','physical_opening_joint')) and not (c['detail_ref']['id']=='cfs_stud_bridging' and 'physical_wall_attachment' in c.get('parameters',{})):continue
        key=json.dumps(signature(c.get('parameters',{})),sort_keys=True)
        if key not in seen:seen.add(key);result.append(build_scene(m,p,c))
    return result


def intersects_grip(part,fastener,pt):
    axis=max(range(3),key=lambda i:abs(fastener['axis'][i]));other=[i for i in range(3) if i!=axis]
    query=Point([pt[i] for i in other])
    for step in range(1,40):
        at=pt[axis]+fastener['axis'][axis]*fastener['grip']*step/40
        if any(Polygon(poly).buffer(1e-7).covers(query) for poly in section_polygons(part,axis,at)):return True
    return False


def test_all_header_jamb_and_bridge_screws_cross_the_actual_named_plies(scenes):
    assert scenes
    for scene in scenes:
        parts={p['id']:p for p in scene['parts']}
        for fastener in scene['fasteners']:
            for pt in fastener['points']:
                for joined in fastener['connects']:
                    assert intersects_grip(parts[joined],fastener,pt),(scene['representative_occurrence'],fastener['id'],joined,pt)


def test_attachment_audit_rejects_a_screw_moved_to_the_channel_void(scenes):
    scene=next(s for s in scenes if any(p['id']=='HEADER' for p in s['parts']));part=next(p for p in scene['parts'] if p['id']=='HEADER')
    f=next(f for f in scene['fasteners'] if f['id']=='H0');point=list(f['points'][0]);point[2]=part['bounds'][2][1]+1
    assert not intersects_grip(part,f,point)
