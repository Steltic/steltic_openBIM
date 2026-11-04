import pytest
from steltic_openbim.review_cfs import intersections
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs_wall_bindings import bind
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def test_reentrant_boundary_keeps_both_floor_sides_without_filling_the_notch():
    poly=[[0,0],[72.5,0],[72.5,20],[97.5,20],[97.5,0],[170,0],[170,64],[0,64]]
    assert intersections(poly,1,72.5)==[(0,64)]
    assert intersections(poly,1,97.5)==[(0,64)]
    assert intersections(poly,1,80)==[(20,64)]
    assert intersections(poly,0,0)==[(0,72.5),(97.5,170)]


@pytest.mark.parametrize('case,cid',[
    ('cfs13','JOIST-1-16.0-0-2:1'),('cfs13','ORD-0-240.0-4-0-0-T-0'),
    ('cfs13','Y0-L4-B1-TT'),('cfs13','ROOF-0-120-SEAT0'),('cfs4','J-4-108-0-0:1')])
def test_real_return_wall_and_cut_track_receivers_have_actual_fastener_contact(case,cid):
    p=evidence(case)['package'];s=scenario(case)
    m=build_model(p,dict(design_scenario=dict(id=case,source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    c=next(v for v in m['connections'] if v['id']==cid);m['connections']=[c];bind(m)
    assert 'physical_floor_stack' in c['parameters']
    result=build_scene(m,p,c);parts={v['id']:v for v in result['parts']}
    assert result['fasteners']
    for f in result['fasteners']:
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(case,cid,f['id'],name,q)
    # These actual receivers must not regress to the generic full-floor stack.
    assert not set(parts).intersection({'UPPER','LOWER','JOIST0','JOIST1'})
