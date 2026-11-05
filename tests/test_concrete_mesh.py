import copy
from collections import defaultdict

import pytest

from steltic_openbim.review_concrete_mesh import clear_runs
from steltic_openbim import bim_bonds as B,bim_assemblies as A


def test_wire_trims_merge_overlapping_voids_and_never_bridge_a_hole():
    assert clear_runs(2,98,[(20,30),(28,40),(70,80)],2)==[(2,18),(42,68),(82,98)]
    assert clear_runs(2,98,[(0,100)],2)==[]


@pytest.fixture(scope='module')
def actual():
    from steltic_openbim.review_cases import evidence,scenario,build_model
    from steltic_openbim.drawing_workflow import fingerprint
    p=evidence('cfs4')['package'];s=scenario('cfs4')
    m=build_model(p,dict(design_scenario=dict(id='cfs4',source_sha256=s['source_sha256'],answers_sha256=fingerprint(s['answers']))))
    return m,p


def test_design_mat_retains_source_size_spacing_and_unresolved_full_schedule(actual):
    model,package=actual
    profile=next(p for p in model['profiles'] if p['id']=='WWR-W2.9')
    assert profile['dimensions']['d']==.192 and profile['nominal_area_in2']==.029
    wires=[m for m in model['members'] if m['id'].startswith('WWR-')]
    assert wires and {w['level'] for w in wires}=={1,2,3}
    rows=defaultdict(set)
    for wire in wires:
        along=0 if wire['axis'][0][1]==wire['axis'][1][1] else 1
        rows[wire['level'],along].add(wire['axis'][0][1-along])
        assert not wire['design_record_ids']
        assert wire['source_context_record_ids']==['diaphragms/diaphragm-floors']
        assert wire['engineering_status']=='not_verified' and 'supplier' in wire['fabrication_status']
    for stations in rows.values():
        values=sorted(stations)
        assert all(b-a==6 for a,b in zip(values,values[1:]))
    assert 'diaphragms/diaphragm-floors' not in model['record_coverage']['used']
    for panel in model['panels']:
        if panel['kind']!='floor':continue
        mat=panel['reinforcement_design_mat']
        assert mat['factory_crossing_count']>0 and len(mat['fabrication_requirements'])==3
        assert mat['source_selection']==next(r['data']['selection'] for r in package['design_records'] if r['id']==mat['source_context_record_id'])


def test_every_wire_fits_its_actual_concrete_and_accepted_openings(actual):
    from steltic_openbim.ifc_export import opening_boundary
    model,_=actual
    wires=[m for m in model['members'] if m['id'].startswith('WWR-')]
    physical=dict(members=wires,profiles=model['profiles'],panels=model['panels'],materials=model['materials'],
                  openings=[dict(o,vertices=opening_boundary(o)) for o in model['openings']],interfaces=[],assemblies=[],connections=[])
    for wire in wires:
        tid=wire['id']+':BOND'
        template=dict(id=tid,parts=[],receivers=[dict(id='WIRE',kind='member',axis=copy.deepcopy(wire['axis'])),dict(id='HOST',kind='panel')],
            bond_interfaces=[dict(id='BOND',kind='reinforcement_bond_development',host_receiver='HOST',bar_receivers=['WIRE'],basis='Explicit test mat geometry, engineering unverified',engineering_status='not_verified')])
        physical['assemblies'].append(template)
        physical['connections'].append(dict(id=tid,assembly_instance=dict(template_id=tid,origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0],bindings={'WIRE':wire['id'],'HOST':wire['host_panel_id']})))
    errors,valid=B.evaluate(physical)
    assert not errors and len(valid)==len(wires)
    profiles={p['id']:p for p in model['profiles']}
    collectors=[m for m in model['members'] if m['kind']=='diaphragm_collector_bar']
    for level in (1,2,3):
        mesh_bottom=min(w['axis'][0][2]-.192/2 for w in wires if w['level']==level)
        collector_top=max(m['axis'][0][2]+profiles[m['profile_id']]['dimensions']['d']/2 for m in collectors if m['level']==level)
        assert mesh_bottom>collector_top, 'Do not pass mesh through the selected collector bars'


def test_mesh_detail_uses_wire_size_instead_of_collector_size(actual):
    from steltic_openbim.assembly_templates import build_scene
    model,package=actual
    c=next(c for c in model['connections'] if c['id'].startswith('WWR-'))
    scene=build_scene(model,package,c)
    wire=next(p for p in scene['parts'] if p['kind']=='member')
    assert wire['member']['profile_id']=='WWR-W2.9'
    assert any('W2.9' in text for text in scene['notes'])
    assert not scene['fasteners'] and not scene['welds']
    assert scene['interfaces'][0]['native_bond']['kind']=='reinforcement_bond_development'
