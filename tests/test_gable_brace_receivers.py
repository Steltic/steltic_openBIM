import math
import copy
from shapely.geometry import Point,Polygon
from test_rod_actual_receivers import case,contact
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons


def test_gable_brace_lengths_and_both_physical_end_receivers(case):
    m,p=case;cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_gable_brace')]
    assert len(cs)==648
    for c in cs:
        a=build_scene(m,p,c);parts={v['id']:v for v in a['parts']}
        assert parts['BRACE']['member']['source_member_index']==0
        assert parts['HOST']['member']['source_member_index']==1
        for f in a['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name)
        for w in a['welds']:
            delta=[b-a for a,b in zip(w['a'],w['b'])];axis=max(range(3),key=lambda i:abs(delta[i]));other=[i for i in range(3) if i!=axis]
            for fraction in (.05,.5,.95):
                q=[a+(b-a)*fraction for a,b in zip(w['a'],w['b'])]
                for name in w['connects']:
                    distance=min((Polygon(poly).distance(Point([q[i] for i in other])) for poly in section_polygons(parts[name],axis,q[axis])),default=1e6)
                    assert distance<1e-5,(c['id'],w['id'],name,distance)
    members=[x for x in m['members'] if x['kind']=='flange_brace']
    assert {round(math.dist(*x['axis']),1) for x in members}=={37.8,41.8}


def test_gable_supplier_clips_touch_real_web_and_primary_flange(case):
    m,p=case;cs=[c for c in m['connections'] if c.get('parameters',{}).get('actual_gable_secondary')]
    assert len(cs)>300
    failures=[]
    for c in cs:
        a=build_scene(m,p,c);parts={v['id']:v for v in a['parts']}
        for f in a['fasteners']:
            for q in f['points']:
                for name in f['connects']:
                    if not contact(parts[name],f,q):failures.append((c['id'],'fastener',name))
        for w in a['welds']:
            delta=[b-a for a,b in zip(w['a'],w['b'])];axis=max(range(3),key=lambda i:abs(delta[i]));other=[i for i in range(3) if i!=axis]
            q=[(a+b)/2 for a,b in zip(w['a'],w['b'])]
            for name in w['connects']:
                distance=min((Polygon(poly).distance(Point([q[i] for i in other])) for poly in section_polygons(parts[name],axis,q[axis])),default=1e6)
                if distance>=1e-5:failures.append((c['id'],w['id'],name,distance))
    assert not failures,failures[:20]


def test_roof_seat_variants_retain_actual_girder_end_geometry(case):
    from steltic_openbim.connection_details import prepare
    m,p=case;m=copy.deepcopy(m);prepare(m,p)
    templates={a['id']:a for a in m['connection_assemblies']}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_roof_seat':continue
        expected=build_scene(m,p,c);actual=templates[c['assembly_id']]
        def receivers(scene):
            return {v['id']:(v['member']['profile_id'],v['member']['axis'],v['member']['local_y']) for v in scene['parts'] if v['kind']=='member'}
        assert receivers(actual)==receivers(expected),c['id']
