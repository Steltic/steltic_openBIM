"""Source mezzanine selections and finite interfaces remain explicit."""
import math
from collections import Counter
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_cfs27_source_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs29')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs29',answers_sha256=fingerprint(scenario('cfs29')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_source_grid_and_collector_halves(actual):
    m,p=actual;posts=[v for v in m['members'] if v['kind'] in ('column','chord')]
    assert len(posts)==18 and len({tuple(v['axis'][0]) for v in posts})==18
    assert {tuple(v['axis'][0][:2]) for v in posts}=={(x,y) for x in range(0,721,144) for y in (0,192,384)}
    walls={v['line']:v for v in m['wall_layouts']}
    assert walls['Y0']['runs']==[dict(start_in=192,end_in=384,position_in=0)]
    assert walls['Y60']['runs']==[dict(start_in=0,end_in=192,position_in=720)]
    for c in m['connections']:
        if c['parameters']['purpose']=='collector' and c['parameters']['along']==1:
            assert c['point'][1]==192
            assert c['member_ids'][1] in ('MZ-JOIST-0-0','MZ-JOIST-720-192')


def test_source_deck_welds_and_source_bolt_groups(actual):
    m,p=actual;floor=next(v for v in m['panels'] if v['id']=='MEZZ29-FLOOR')
    assert floor['thickness_in']==1.125 and len(floor['physical_constituent_member_ids'])==60
    assert sum(v['kind']=='joist' for v in m['members'])==92
    seams=[v for v in m['connections'] if v['parameters']['purpose']=='box_seams']
    assert len(seams)==33
    for c in seams:
        s=build_scene(m,p,c)
        if c['parameters']['post']:
            lengths=Counter(round(math.dist(w['a'],w['b']),5) for w in s['welds'])
            assert lengths[8]==4 and lengths[1.5]>=18
        else:assert len(s['welds'])==2
    c=next(v for v in m['connections'] if v['parameters']['purpose']=='beam_end')
    s=build_scene(m,p,c)
    assert len(s['fasteners'])==4
    assert all(f['count']==2 and f['diameter']==.75 for f in s['fasteners'])


def test_shared_guard_caps_and_unspliced_braces(actual):
    m,p=actual;members={v['id']:v for v in m['members']}
    caps=[v for v in m['members'] if v['kind']=='guard_cap']
    guards=[v for v in m['members'] if v['kind']=='guard_post']
    assert len(caps)==len(guards)==61
    assert len({tuple(v['axis'][0]) for v in caps})==len(caps)
    for c in m['connections']:
        if c['parameters']['purpose']=='rail_post':assert members[c['member_ids'][2]]['kind']=='guard_cap'
        if c['parameters']['purpose']=='strap_end':
            s=build_scene(m,p,c)
            assert s['fasteners'][0]['count']==10 and s['fasteners'][0]['diameter']==.19
    assert sum(v['kind']=='strap' for v in m['members'])==32


def test_every_fastener_contacts_each_actual_receiver(actual):
    m,p=actual
    for c in m['connections']:
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        for f in s['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
