import math
from collections import Counter,defaultdict
import pytest
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.pilots.geometry import strips
from steltic_openbim.pilots.model import add,sub,mul,unit,cross,dot


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_all_inclined_support_sidelap_and_ridge_screws_cross_real_finite_steel(actual):
    m,_=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']};shapes={};counts=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_deck':continue
        for f in c['parameters']['fasteners']:
            counts[c['parameters']['purpose']]+=1;start=add(c['point'],f['point_relative']);end=add(start,mul(f['axis'],f['grip']))
            for index in f['receivers']:
                member=members[c['member_ids'][index]];a,d=[add(q,o) for q,o in zip(member['axis'],member['end_offsets'])]
                x=unit(sub(d,a));y=member['local_y'];z=cross(x,y);length=math.dist(a,d)
                first,last=[dot(sub(q,a),x) for q in (start,end)]
                assert -.00001<=min(first,last) and max(first,last)<=length+.00001,(c['id'],member['id'])
                pid=member['profile_id']
                if pid not in shapes:shapes[pid]=unary_union([Polygon(p) for p in strips(profiles[pid],profiles)])
                ray=LineString([[dot(sub(q,a),v) for v in (y,z)] for q in (start,end)])
                assert ray.intersection(shapes[pid]).length>.01,(c['id'],member['id'],f)
    frames={v['axis'][0][0] for v in m['members'] if v['id'].startswith('ROOF-') and v['kind']=='truss_chord'}
    assert counts=={'support':len(frames)*52,'sidelap':3200,'ridge':400}


def test_each_sheet_retains_36_4_pattern_and_sidelaps_have_12in_pitch(actual):
    m,_=actual;members={v['id']:v for v in m['members']};support=defaultdict(Counter);laps=defaultdict(list)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_deck':continue
        par=c['parameters']
        if par['purpose']=='support':
            frame=members[c['member_ids'][0]]['axis'][0][0]
            for f in par['fasteners']:
                assert f['diameter']==.216 and f['basis']=='S'
                for index in f['receivers'][1:]:support[c['member_ids'][index]][frame]+=1
        elif par['purpose']=='sidelap':
            for f in par['fasteners']:
                assert f['diameter']==.19 and f['basis']=='S'
                laps[tuple(c['member_ids'])].append(c['point'][0]+f['point_relative'][0])
    assert len(support)==18 and len(laps)==16
    for sheet,values in support.items():
        expected=2 if sheet.endswith('-8') else 4
        assert set(values.values())=={expected}
    for xs in laps.values():
        xs.sort();assert len(xs)==200
        assert xs[0]==6 and xs[-1]==2394
        assert all(b-a==pytest.approx(12) for a,b in zip(xs,xs[1:]))


def test_deck_is_thin_folded_sheet_geometry_on_corrected_roof_bearing_plane(actual):
    m,_=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    for panel in [p for p in m['panels'] if p['id'].startswith('MAIN-ROOF-')]:
        assert len(panel['physical_constituent_member_ids'])==9
        assert panel['source_depth_normal_in']==1.5
        assert panel['vertices'][0][2]==pytest.approx((324 if panel['id'].endswith('0') else 336.5)+3*math.sqrt(1+1/24**2))
        for mid in panel['physical_constituent_member_ids']:
            profile=profiles[members[mid]['profile_id']]
            assert profile['fabrication_form'].startswith('single folded sheet')
            shape=unary_union([Polygon(p) for p in strips(profile,profiles)])
            assert shape.area/(shape.bounds[2]-shape.bounds[0])<.06
            assert shape.bounds[1]>=-1e-7 and shape.bounds[3]==pytest.approx(1.5)
