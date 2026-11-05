from collections import Counter,defaultdict
import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons
from steltic_openbim.review_cfs_occurrences import axis
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_every_sag_fastener_crosses_all_its_finite_receiver_plies(actual):
    m,p=actual;counts=Counter()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_sag':continue
        purpose=c['parameters']['purpose'];counts[purpose]+=1
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            assert f['basis']=='A'
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        if purpose in ('foot','cap'):
            assert len(scene['welds'])==2
            z=.25 if purpose=='foot' else -.25
            # The angle cut and terminal plate have an actual common face;
            # no floating weld/plate surrogate is allowed at either end.
            faces={label:[Polygon(poly) for poly in section_polygons(parts[label],2,z+eps)]
                for label,eps in [('SAG',1e-6 if purpose=='foot' else -1e-6),('PLATE',-1e-6 if purpose=='foot' else 1e-6)]}
            a=parts['SAG']['member']['axis'][0 if purpose=='foot' else 1]
            query=Point(a[:2])
            assert all(any(poly.buffer(1e-6).covers(query) for poly in polys) for polys in faces.values()),c['id']
    assert counts=={'girt':120,'foot':40,'cap':40}


def test_each_three_girt_line_has_midspan_restraint_and_two_real_terminals(actual):
    m,_=actual;members={v['id']:v for v in m['members']};rows=defaultdict(list);ends=defaultdict(set)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_sag':continue
        sag=members[c['member_ids'][0]];par=c['parameters']
        if par['purpose']=='girt':
            girt=members[c['member_ids'][1]];rows[sag['id']].append(girt)
            along=par['along'];lo,hi=axis(girt)
            assert c['point'][along]==pytest.approx((lo[along]+hi[along])/2)
            assert c['point'][along]-lo[along]<=75 and hi[along]-c['point'][along]<=75
            assert axis(sag)[0][2]<c['point'][2]<axis(sag)[1][2]
            assert girt['midspan_restraint_member_id']==sag['id']
        elif par['purpose']=='cap':
            assert members[c['member_ids'][1]]['kind'] in ('girder','moment_beam')
            ends[sag['id']].add('cap')
        else:ends[sag['id']].add('foot')
    assert len(rows)==40 and all(len(v)==3 for v in rows.values())
    assert all(v=={'foot','cap'} for v in ends.values())
    for values in rows.values():assert sorted(g['axis'][0][2] for g in values)==[72,144,216]
