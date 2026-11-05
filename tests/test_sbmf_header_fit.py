import math
import pytest
from shapely.geometry import Polygon
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from steltic_openbim.pilots.geometry import member_faces
from shapely.geometry import Point


def contact(part,fastener,pt):
    # Sample every interval between actual face vertices, not 80 uniform steps:
    # a 0.1242in sheet can be skipped by a 10.2484in through-bolt's coarse grid.
    axis=max(range(3),key=lambda i:abs(fastener['axis'][i]));other=[i for i in range(3) if i!=axis]
    lo,hi=sorted((pt[axis],pt[axis]+fastener['axis'][axis]*fastener['grip']))
    cuts=sorted({lo,hi,*[q[axis] for f in part['faces'] for q in f if lo<q[axis]<hi]})
    query=Point([pt[i] for i in other])
    return any(Polygon(poly).buffer(1e-7).covers(query) for a,b in zip(cuts,cuts[1:])
               for poly in section_polygons(part,axis,(a+b)/2))


@pytest.fixture(scope='module',params=('cfs10','cfs18'))
def actual(request):
    key=request.param;p=evidence(key)['package'];before=fingerprint(p);s=scenario(key)
    model=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(p)==before
    return model,p


def test_every_header_end_uses_real_members_and_all_bolts_contact(actual):
    model,p=actual;count=0
    for c in model['connections']:
        if c['detail_ref']['id']!='review_sbmf_header':continue
        scene=build_scene(model,p,c);parts={a['id']:a for a in scene['parts']}
        assert {v['member']['source_member_index'] for v in parts.values() if v.get('member')}=={0,1,2,3}
        for f in scene['fasteners']:
            assert f['count']==2
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        for y in (-.18,0,.18):
            tab=[Polygon(v) for v in section_polygons(parts['TAB'],1,y)]
            steel=[Polygon(v) for v in section_polygons(parts['SBMF'],1,y)]
            assert sum(a.intersection(b).area for a in tab for b in steel)<1e-7,c['id']
        assert len(scene['welds'])==2
        assert all(w['basis']==('S' if model['pilot']=='cfs10' else 'A') for w in scene['welds'])
        count+=1
    assert count==(32 if model['pilot']=='cfs10' else 64)


def test_cap_is_source_section_and_fasteners_hit_both_real_top_flanges(actual):
    model,p=actual;profiles={v['id']:v for v in model['profiles']};members={v['id']:v for v in model['members']};count=0
    for c in model['connections']:
        if c['detail_ref']['id']!='review_sbmf_cap':continue
        cap,header=[members[mid] for mid in c['member_ids']]
        assert 'T250-97' in cap['profile_id'] or cap['profile_id']=='1200T300-118'
        scene=build_scene(model,p,c);parts={v['id']:v for v in scene['parts']};f=scene['fasteners'][0]
        assert f['count']==2 and f['basis']=='A'
        for q in f['points']:
            for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        top=max(q[2] for face in member_faces(header,profiles) for q in face)
        capweb=cap['axis'][0][2]-profiles[cap['profile_id']]['dimensions']['t']/2
        assert capweb==pytest.approx(top)
        count+=1
    assert count>100


def test_moment_joint_keeps_bolt_contacts_and_discloses_relief_capacity(actual):
    model,p=actual;count=0
    for c in model['connections']:
        if c['detail_ref']['id']!='review_sbmf_joint' or c.get('parameters',{}).get('joint')=='storefront':continue
        scene=build_scene(model,p,c);parts={v['id']:v for v in scene['parts']}
        assert parts['BEAM']['member']['slots']
        assert any('uncut capacity is not assigned' in note for note in scene['notes'])
        for f in scene['fasteners']:
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        count+=1
    assert count==(18 if model['pilot']=='cfs10' else 34)


def test_roof_top_chord_and_panel_datums_are_preserved(actual):
    model,_=actual;key=model['pilot'];base=302 if key=='cfs10' else 300;raise_in=3+(.1242 if key=='cfs10' else .1017)
    bottom=[m for m in model['members'] if m['id'].startswith('ROOF-') and m['kind']=='truss_chord' and m['id'].rsplit('-',1)[1].startswith('B')]
    assert bottom and all(all(q[2]==pytest.approx(base+raise_in) for q in m['axis']) for m in bottom)
    panels=[p for p in model['panels'] if p['id'].startswith('MAIN-ROOF-')]
    assert min(q[2] for p in panels for q in p['vertices'])==(332 if key=='cfs10' else 324)
    changes=[c for c in model['changes'] if c['kind']=='sbmf_header_physical_fit']
    assert changes and all('capacity is not assigned' in c['basis'] for c in changes)
