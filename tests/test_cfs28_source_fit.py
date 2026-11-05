"""Saved agricultural-building conditions must survive physical export."""
import math
from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs_occurrences import axis
from steltic_openbim.pilots.model import add,sub,mul,unit,dot,cross
from test_cfs27_source_fit import contact


@pytest.fixture(scope='module')
def actual():
    package=evidence('cfs28')['package'];before=fingerprint(package)
    model=build_model(package,dict(design_scenario=dict(id='cfs28',answers_sha256=fingerprint(scenario('cfs28')['answers']))))
    assert fingerprint(package)==before
    return model,package


def test_source_open_front_and_individual_braced_bays(actual):
    m,p=actual;counts=Counter(v['kind'] for v in m['members'])
    assert counts['column']==22 and counts['rafter']==22
    assert counts['open_front_strut']==10
    struts=[v for v in m['members'] if v['kind']=='open_front_strut']
    assert {round(v['axis'][0][1],5) for v in struts}=={round(i*211.2,5) for i in range(10)}
    assert all(v['profile_id']=='2X600S300-54' and v['axis'][0][2]==171 for v in struts)
    straps={prefix:[v for v in m['members'] if v['id'].startswith(prefix)] for prefix in ('AG-SOUTH-X-','AG-ROOF-X-','AG-END-X-','AG-OPEN-X-')}
    assert [len(v) for v in straps.values()]==[8,96,8,4]
    for prefix in ('AG-SOUTH-X-','AG-ROOF-X-','AG-OPEN-X-'):
        assert all(math.isclose(abs(v['axis'][1][1]-v['axis'][0][1]),211.2,abs_tol=1e-6) for v in straps[prefix])
    assert len(m['panels'])==9
    assert not any(v['id'].startswith('AG-SKIN-W0') for v in m['panels'])
    assert all(v.get('physical_constituent_member_ids') for v in m['panels'])
    assert not any(c['detail_ref']['id'] in ('review_cfs_strap','review_next_secondary','review_screwed_flybrace','review_next_portal_joint','review_next_portal_base') for c in m['connections'])


def test_source_three_pair_joints_and_post_kicker_groups(actual):
    m,p=actual;members={v['id']:v for v in m['members']}
    for purpose,count in (('knee',16),('ridge',12)):
        c=next(v for v in m['connections'] if v['detail_ref']['id']=='review_ag_primary' and v['parameters']['purpose']==purpose)
        scene=build_scene(m,p,c)
        assert len(scene['fasteners'])==6
        assert all(f['count']==count and f['diameter']==.75 for f in scene['fasteners'])
    posts=[c for c in m['connections'] if c['detail_ref']['id']=='review_ag_flybrace' and c['parameters'].get('post')]
    assert len(posts)==10
    assert all(c['parameters']['count']==3 for c in posts)
    assert all(math.isclose(math.dist(*members[c['member_ids'][0]]['axis']),30.9,abs_tol=1e-8) for c in m['connections'] if c['detail_ref']['id']=='review_ag_open_brace' and c['parameters']['purpose']=='brace')
    plates=[v for v in m['members'] if v['kind']=='flange_cross_plate']
    assert len(plates)==132
    assert all(v['source_plate_size_in']==[4,19] for v in plates)
    assert len({tuple(tuple(round(x,5) for x in q) for q in axis(v)) for v in plates})==len(plates)


def test_source_strap_groups_crossings_and_solid_pack_layers(actual):
    m,p=actual
    for c in m['connections']:
        if c['detail_ref']['id']!='review_ag_strap':continue
        par=c['parameters'];scene=build_scene(m,p,c)
        if par['purpose']=='crossing':
            assert len(c['member_ids'])==2 and scene['fasteners'][0]['count']==2
        else:
            expected={'roof':12,'south':33,'end':14,'open':17}[par['kind']]
            groups=[f for f in scene['fasteners'] if f['id'].startswith('STRAP-END')]
            assert len(groups)==len(par['ends'])
            assert all(f['count']==expected for f in groups)
    layered=[c for c in m['connections'] if c['detail_ref']['id']=='review_ag_cladding' and any(c['parameters'].get('strap_layers',[]))]
    assert layered
    for c in layered:
        scene=build_scene(m,p,c)
        for part in scene['parts']:
            if not part['id'].startswith('PACK'):continue
            i=int(part['id'].split('-')[0].removeprefix('PACK'));lo,hi=part['bounds'][2]
            for layer in c['parameters']['strap_layers'][i]:assert hi<=layer['bottom']+1e-7 or lo>=layer['top']-1e-7


def test_finite_source_receivers_in_all_changed_interfaces(actual):
    m,p=actual
    # Every scene is independently built with its actual occurrence. This
    # catches missing receiving plies and finite-end/handed clip errors.
    for c in m['connections']:
        if not (c['detail_ref']['id'].startswith('review_ag_') or c['detail_ref']['id'] in ('review_sbmf_girt','review_single_stitch')):continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
