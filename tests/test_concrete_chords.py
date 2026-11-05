import math
from collections import defaultdict
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs4')['package'];s=scenario('cfs4')
    m=build_model(p,dict(design_scenario=dict(id='cfs4',answers_sha256=fingerprint(s['answers']))))
    return m,p


def test_two_source_edge_runs_are_continuous_contact_lapped_and_explicitly_unverified(actual):
    m,_=actual;groups=defaultdict(list)
    for bar in m['members']:
        if bar['kind']!='diaphragm_chord_bar':continue
        assert bar['profile_id']=='REBAR-4' and bar['material_id']=='CFS4-REBAR-GR60'
        assert bar['engineering_status']=='not_verified' and not bar['design_record_ids']
        assert bar['source_context_record_ids']==['diaphragms/diaphragm-floors']
        groups[bar['level'],*bar['chord_edge'],bar['source_bar_index']].append(bar)
    assert len(groups)==3*4*2
    for (_,along,_,_),bars in groups.items():
        bars.sort(key=lambda b:b['axis'][0][along])
        for a,b in zip(bars,bars[1:]):
            assert a['axis'][1][along]-b['axis'][0][along]==20
            assert abs(a['axis'][0][1-along]-b['axis'][0][1-along])==.5
        assert all(math.dist(*b['axis'])<=240 for b in bars)
    assert 'diaphragms/diaphragm-floors' in m['record_coverage']['used']
    assert all(p.get('attachment_schedule',{}).get('blocking_member_ids') for p in m['panels'] if p['kind']=='deck')


def test_edge_bars_clear_mesh_and_collector_bars_in_the_actual_topping(actual):
    m,_=actual;profiles={p['id']:p for p in m['profiles']}
    edges=[p for p in m['members'] if p['kind']=='diaphragm_chord_bar']
    others=[p for p in m['members'] if p['kind'] in ('reinforcement_bar','diaphragm_collector_bar')]
    def bounds(bar):return [(min(q[i] for q in bar['axis']),max(q[i] for q in bar['axis'])) for i in range(3)]
    spans={b['id']:bounds(b) for b in edges+others}
    for a in edges:
        for b in others:
            if a['level']!=b['level']:continue
            aa,bb=spans[a['id']],spans[b['id']]
            distance=math.sqrt(sum(max(x[0]-y[1],y[0]-x[1],0)**2 for x,y in zip(aa,bb)))
            radius=.25+profiles[b['profile_id']]['dimensions']['d']/2
            assert distance>=radius-1e-7,(a['id'],b['id'],distance,radius)


def test_corner_view_binds_each_real_straight_bar_without_inventing_a_weld(actual):
    m,p=actual
    corners=[c for c in m['connections'] if c['id'].startswith('EDGE-CORNER-')]
    assert len(corners)==12
    for c in corners:
        scene=build_scene(m,p,c)
        assert not scene['fasteners'] and not scene['welds']
        assert len(scene['interfaces'])==4
        for item in scene['interfaces']:
            bond=item['native_bond']
            assert bond['kind']=='reinforcement_bond_development'
            assert len(bond['bar_receivers'])==1 and bond['engineering_status']=='not_verified'
        assert any('No welded intersection' in note for note in scene['notes'])
