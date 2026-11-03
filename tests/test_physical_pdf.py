import copy
import json
from pathlib import Path

from pypdf import PdfReader
from steltic_openbim.drawing_pdf import generate
from steltic_openbim.drawing_workflow import initial_state, fingerprint


def source_frame():
    p = json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())
    template = p['physical']['members'][0]
    members = []
    for i, x in enumerate((0, 360)):
        for j, y in enumerate((0, 360)):
            members.append(dict(copy.deepcopy(template), id=f'C{i}{j}', kind='column', axis=[[x,y,0],[x,y,180]]))
    members.append(dict(copy.deepcopy(template), id='beam', axis=[[0,0,180],[360,0,180]]))
    members.append(dict(copy.deepcopy(template), id='beam2', axis=[[0,360,180],[360,360,180]]))
    p['physical']['members'] = members
    p['physical']['joints'][0].update(point=[0,0,180], member_ends=[dict(member_id='beam',end='start'),dict(member_id='C00',end='end')])
    p['physical']['joints'][1]['point'] = [360,0,180]
    p['physical']['connections'][0]['parts'][0]['geometry']['origin'] = [0,0,180]
    p['layout_evidence']['levels_in'] = [0,180]
    return p


def test_declared_hr_has_grids_sections_marks_and_only_source_connection_parts(tmp_path):
    p = source_frame(); before = fingerprint(p)
    report = generate(p, initial_state(p,1), tmp_path)
    assert fingerprint(p) == before
    index = json.loads((tmp_path/'member_index.json').read_text())
    assert {m['id']:m['axis'] for m in index} == {m['id']:m['axis'] for m in p['physical']['members']}
    assert report['representation'] == 'source_physical_geometry'
    assert any(d.get('reference','').startswith('Grid') and d['value_in']==360 for d in report['dimensions'])
    assert any(d.get('reference')=='Source level interval' and d['value_in']==180 for d in report['dimensions'])
    assert report['labels'] and report['callouts']
    assembly = [v for v in report['views'] if v.get('kind')=='source_connection_assembly']
    assert len(assembly)==4 and all(v['part_ids']==['plate'] for v in assembly)
    assert len(PdfReader(tmp_path/'drawings.pdf').pages)==len(report['sheets'])
    assert not any('fictional test' in page.extract_text().lower() for page in PdfReader(tmp_path/'drawings.pdf').pages)


def test_reference_only_connections_have_no_invented_assembly(tmp_path):
    p=source_frame(); p['physical']['connections'][0].pop('parts')
    p['physical']['connections'][0]['detail_ref']=dict(id='SPEC-ONLY',revision='1')
    report=generate(p,initial_state(p,1),tmp_path)
    assert not any(v.get('kind')=='source_connection_assembly' for v in report['views'])
    text='\n'.join(page.extract_text() for page in PdfReader(tmp_path/'drawings.pdf').pages)
    assert 'No located part geometry supplied' in text and 'TBD - resolve query' in text


def test_physical_joint_offset_keeps_floor_plan_connection_callout(tmp_path):
    p=source_frame(); joint=p['physical']['joints'][0]; joint['point'][2]-=12
    for end in joint['member_ends']: end['joint_offset']=[0,0,-12]
    report=generate(p,initial_state(p,1),tmp_path)
    assert any(c['sheet']=='S101' and 'C001' in c['reference'] for c in report['callouts'])
