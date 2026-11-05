import pytest
from shapely.geometry import Point,Polygon,box
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cases import evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs6_diaphragms import apply,floor_regions
from steltic_openbim.review_cfs6_wallface_blocking import apply as blocking
from steltic_openbim.review_cfs6_floor_panels import rectangles
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def fixture():
    source=evidence('cfs6');s=scenario('cfs6')
    b=CaseModel('cfs6',source['package'],dict(design_scenario=dict(id='cfs6',answers_sha256=fingerprint(s['answers']))),source)
    b.endpoint_links=[]
    b.panel('FLOOR-1','floor',[[0,0,118.5],[336,0,118.5],[336,80,118.5],[0,80,118.5]],23/32,1,openings=['HOLD'])
    b.openings=[dict(id='HOLD',kind='wall_bearing_holdback',plane='xy',x_ft=(168-3.3125)/12,y_ft=0,z_ft=118.5/12,width_ft=6.625/12,height_ft=80/12,level=1,host_id='FLOOR-1')]
    for y in (8,24,40,56,72):
        for i,(lo,hi) in enumerate(((0,168),(168,336))):
            b.member(f'J{y}-{i}','1000S250-68','joist',[lo,y,112.78125],[hi,y,112.78125],1,local_y=[0,1,0])
    return b,source['package']


def check_scene(b,package,c):
    model=dict(pilot='cfs6',members=b.members,profiles=list(b.profiles.values()),connections=b.connections,panels=b.panels)
    scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
    assert parts['WSP']['bound_panel_id']=='FLOOR-1'
    for f in scene['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)
    return scene


def test_field_and_edge_screws_land_on_actual_steel_and_inside_clipped_host():
    b,package=fixture();apply(b);polygon=floor_regions(b)[1][1]
    assert b.connections and len(b.panels[0]['design_record_ids'])==4
    for c in b.connections:
        assert c['parameters']['source_pitch_in'] in (6,12)
        for q in c['parameters']['points_relative']:
            assert polygon.buffer(-.39).covers(Point(q[0]+c['point'][0],q[1]+c['point'][1]))
        check_scene(b,package,c)


def test_flat_blocking_runs_along_wall_face_and_has_one_source_screw_per_joist():
    b,package=fixture();blocking(b);apply(b)
    strips=[m for m in b.members if m['kind']=='diaphragm_blocking']
    assert strips and all(m['axis'][0][0]==m['axis'][1][0] for m in strips)
    assert {round(m['axis'][0][0]-168,4) for m in strips if abs(m['axis'][0][0]-168)<10}=={-4.0625,4.0625}
    lookup={m['id']:m for m in b.members}
    for strip in strips:
        attached=[c for c in b.connections if c['detail_ref']['id']=='review_wallface_blocking' and c['member_ids'][0]==strip['id']]
        assert sum(row['receiver_index'] is not None for c in attached for row in c['parameters']['screws'])==5
        stations=[c['point'][1]+row['point_relative'][1] for c in attached for row in c['parameters']['screws']]
        assert max(d-a for a,d in zip(stations,stations[1:]))<=6.00001
        for c in attached:
            scene=check_scene(b,package,c)
            assert len(scene['fasteners'])==len(c['parameters']['screws']) and all(f['diameter']==.19 for f in scene['fasteners'])
            assert all(lookup[mid]['kind']=='joist' for mid in c['member_ids'][1:])
    assert all(r['depth_in']==.0566 for r in b.panels[0]['underside_recesses'])
    # Plain field screws cannot duplicate the local strip's screws or put a
    # full-thickness panel over the explicitly rebated source blocking.
    for c in b.connections:
        if c['detail_ref']['id']!='review_diaphragm_screws':continue
        for p in c['parameters']['points_relative']:
            q=Point(p[0]+c['point'][0],p[1]+c['point'][1])
            assert not any(box(x[0],y[0],x[1],y[1]).contains(q) for x,y in (r['bounds_xy_in'] for r in b.panels[0]['underside_recesses']))


def test_hostless_wood_context_does_not_pass_as_a_real_receiving_panel():
    b,package=fixture();apply(b);c=b.connections[0]
    model=dict(pilot='cfs6',members=b.members,profiles=list(b.profiles.values()),connections=b.connections,panels=[])
    with pytest.raises(ValueError,match='no actual declared host'):build_scene(model,package,c)


def test_holdback_rectangles_stay_within_the_real_l_plan():
    polygon=Polygon([(0,0),(62,0),(62,90),(180,90),(180,152),(0,152)])
    clipped=polygon.intersection(box(-1,89,181,91))
    parts=list(rectangles(clipped))
    assert len(parts)==2
    assert sum((c-a)*(d-b) for a,b,c,d in parts)==pytest.approx(clipped.area)
    assert all(polygon.covers(box(*r)) for r in parts)
