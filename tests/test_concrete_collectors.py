import math
from collections import defaultdict
from types import SimpleNamespace

import pytest

from steltic_openbim.review_concrete_collectors import stock_runs, openings_on_line


def test_stock_pieces_preserve_full_run_and_each_explicit_lap():
    pieces = stock_runs(2, 1678, 240, 25)
    assert pieces[0][0] == 2 and pieces[-1][1] == 1678
    assert all(b-a <= 240 for a,b in pieces)
    assert all(left[1]-right[0] == 25 for left,right in zip(pieces,pieces[1:]))
    with pytest.raises(ValueError):stock_runs(0,120,25,25)


def test_collector_path_cannot_silently_cross_a_floor_opening():
    b=SimpleNamespace(openings=[dict(id='VOID',plane='xy',x_ft=6,y_ft=6,width_ft=8,height_ft=18)])
    panel=dict(openings=['VOID'])
    assert openings_on_line(b,panel,0,80,2,1000,.3125)=='VOID'
    assert openings_on_line(b,panel,1,80,2,1000,.3125)=='VOID'
    assert openings_on_line(b,panel,0,2,2,1000,.3125) is None


@pytest.fixture(scope='module')
def actual():
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    p=evidence('cfs4')['package'];s=scenario('cfs4')
    m=build_model(p,dict(design_scenario=dict(id='cfs4',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    return m,p


def test_actual_collectors_preserve_all_source_counts_and_floor_scope(actual):
    m,p=actual
    records={r['id']:r for r in p['design_records'] if r['table']=='collectors'}
    bars=[v for v in m['members'] if v['kind']=='diaphragm_collector_bar']
    assert bars and len(records)==10
    assert set(records)<=set(m['record_coverage']['used'])
    assert 'diaphragms/diaphragm-floors' not in m['record_coverage']['used']
    panels={v['id']:v for v in m['panels']}
    groups=defaultdict(list)
    for bar in bars:
        assert bar['level'] in (1,2,3)
        assert bar['profile_id']=='REBAR-5' and bar['material_id']=='CFS4-REBAR-GR60'
        assert len(bar['design_record_ids'])==1
        panel=panels[bar['host_panel_id']];top=panel['vertices'][0][2]
        assert panel['kind']=='floor'
        assert top-2.5 < bar['axis'][0][2]-.3125 < bar['axis'][0][2]+.3125 < top
        groups[bar['design_record_ids'][0],bar['level']].append(bar)
    assert len(groups)==30
    for (rid,level),parts in groups.items():
        count=int(records[rid]['data']['member'].split()[0])
        assert {m['source_bar_index'] for m in parts}==set(range(1,count+1))
        assert all(m['source_bar_count']==count for m in parts)
    assert all('No development, cover or capacity verification' in c['basis']
               for c in m['changes'] if c['kind']=='source_concrete_collector')


def test_every_actual_lap_has_touching_parallel_bars_and_real_source_receivers(actual):
    from steltic_openbim.assembly_templates import build_scene
    m,p=actual;members={v['id']:v for v in m['members']}
    laps=[c for c in m['connections'] if c['detail_ref']['id']=='review_collector_lap']
    assert laps
    for c in laps:
        first,second=[members[i] for i in c['member_ids']]
        along=0 if first['axis'][0][1]==first['axis'][1][1] else 1
        normal=1-along
        assert first['axis'][1][along]-second['axis'][0][along]==pytest.approx(25)
        assert abs(first['axis'][0][normal]-second['axis'][0][normal])==pytest.approx(.625)
        assert first['axis'][0][2]==second['axis'][0][2]
        scene=build_scene(m,p,c)
        parts=[v for v in scene['parts'] if v['kind']=='member']
        assert len(parts)==2
        assert {v['member']['source_member_index'] for v in parts}=={0,1}
        assert all(v['member']['profile_id']=='REBAR-5' for v in parts)
        assert not scene['welds'] and not scene['fasteners']
        assert scene['interfaces'][0]['length_in']==25
        assert scene['interfaces'][0]['kind']=='reinforcement_bond_lap'
        assert scene['interfaces'][0]['basis']=='A'


def test_embedded_bar_ends_have_their_actual_host_bond_disposition(actual):
    from steltic_openbim.assembly_templates import build_scene
    m,p=actual
    bars={v['id']:v for v in m['members'] if v['kind']=='diaphragm_collector_bar'}
    links={(v['member_id'],v['end']):v for v in m['connection_endpoint_links'] if v['member_id'] in bars}
    assert len(links)==2*len(bars)
    c=next(c for c in m['connections'] if c['detail_ref']['id']=='review_collector_bond')
    scene=build_scene(m,p,c)
    host=next(v for v in scene['parts'] if v['id']=='TOPPING')
    assert host['representation_role']=='context_only'
    assert c['parameters']['host_panel_id'] in host['description']
    assert 'capacity unverified' in scene['interfaces'][0]['description']


def test_actual_concrete_host_excludes_the_source_deck_depth(actual):
    m,p=actual
    floors=[v for v in m['panels'] if v['kind']=='floor']
    assert len(floors)==3
    for floor in floors:
        assert floor['thickness_in']==2.5
        assert floor['thickness_direction']=='negative_global_z'
        assert floor['material_id']=='CFS4-LWC'
        deck=next(v for v in m['panels'] if v['kind']=='deck' and v['floor_stack_id']==floor['floor_stack_id'])
        assert deck['thickness_in']==1.5 and deck['material_id']=='CFS4-DECK'
        assert deck['vertices']==[[q[0],q[1],q[2]-2.5] for q in floor['vertices']]
        assert deck['openings']==[oid+':DECK' for oid in floor['openings']]
    from steltic_openbim.ifc_export import opening_boundary
    from steltic_openbim.panel_geometry import panel_rings
    openings={o['id']:dict(o,vertices=opening_boundary(o)) for o in m['openings']}
    for panel in (v for v in m['panels'] if v['kind'] in ('floor','deck')):
        related=[openings[oid] for oid in panel['openings']]
        assert all(o['host_id']==panel['id'] for o in related)
        rings,applied,findings=panel_rings(panel,related)
        assert set(applied)==set(panel['openings']) and not findings
        assert sum(len(r['holes']) for r in rings)==2
