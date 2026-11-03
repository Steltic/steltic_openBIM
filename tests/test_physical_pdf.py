import copy
import json
from pathlib import Path

from pypdf import PdfReader
import pytest
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


@pytest.mark.parametrize('module',['HR','CFS'])
def test_declared_model_has_grids_sections_marks_and_only_source_connection_parts(tmp_path,module):
    p = source_frame()
    p['module']=module
    if module=='CFS':
        for member in p['physical']['members']:
            if member['kind']=='column':member['kind']='post'
    before=fingerprint(p)
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


def test_opening_without_optional_kind_retains_source_vertices_and_level(tmp_path):
    p=source_frame();p['module']='CFS'
    vertices=[[20,0,190],[56,0,190],[56,0,274],[20,0,274]]
    p['physical']['panels']=[dict(id='wall',kind='wall',status='declared',level=1,thickness=0.5,material_id='steel',vertices=[[0,0,180],[360,0,180],[360,0,300],[0,0,300]])]
    p['physical']['openings']=[dict(id='gate',host_id='wall',level=2,vertices=vertices,basis='source geometry')]
    from steltic_openbim.drawing_pdf import source_openings
    feature=source_openings(p)[0]
    assert feature['kind']=='opening' and feature['level']==2
    assert feature['source_vertices']==vertices and feature['confirmed']
    report=generate(p,initial_state(p,1),tmp_path)
    assert any(d.get('feature_id')=='SRC-gate' for d in report['dimensions'])


def test_reference_only_connections_have_no_invented_assembly(tmp_path):
    p=source_frame(); p['physical']['connections'][0].pop('parts')
    p['physical']['connections'][0]['detail_ref']=dict(id='SPEC-ONLY',revision='1')
    report=generate(p,initial_state(p,1),tmp_path)
    assert not any(v.get('kind')=='source_connection_assembly' for v in report['views'])
    text='\n'.join(page.extract_text() for page in PdfReader(tmp_path/'drawings.pdf').pages)
    assert 'No located part geometry supplied' in text and 'TBD - resolve query' in text


@pytest.mark.parametrize('kind,roof',[('floor',False),('roof',True)])
def test_top_floor_is_only_labelled_roof_when_source_declares_it(tmp_path,kind,roof):
    p=source_frame();p['module']='CFS'
    p['physical']['panels']=[dict(id='top',kind=kind,status='declared',thickness=.5,material_id='steel',vertices=[[0,0,180],[360,0,180],[360,360,180],[0,360,180]])]
    report=generate(p,initial_state(p,1),tmp_path)
    framing=next(row for row in report['sheets'] if row['number']=='S101')
    assert framing['title'].startswith('Roof' if roof else 'Level 1')


def test_physical_joint_offset_keeps_floor_plan_connection_callout(tmp_path):
    p=source_frame(); joint=p['physical']['joints'][0]; joint['point'][2]-=12
    for end in joint['member_ends']: end['joint_offset']=[0,0,-12]
    report=generate(p,initial_state(p,1),tmp_path)
    assert any(c['sheet']=='S101' and 'C001' in c['reference'] for c in report['callouts'])


def test_splice_reference_is_visible_with_attachment_context_without_solid_dimensions(tmp_path):
    p=source_frame(); connection=p['physical']['connections'][0]
    connection['parts'][0]['geometry']={'type':'polyline','points':[[-4,0,180],[4,0,180]]}
    joint=p['physical']['joints'][0]
    joint['member_ends']=[dict(member_id='C00',end='end')]
    joint['attachments']=[dict(member_id='beam',station=0,offset=[0,0,0])]
    report=generate(p,initial_state(p,1),tmp_path)
    views=[v for v in report['views'] if v.get('kind')=='source_connection_reference']
    assert len(views)==4 and all('beam' in v['contextual_member_ids'] for v in views)
    assert not any(d.get('reference')=='Source connection-part envelope' for d in report['dimensions'])
    text='\n'.join(page.extract_text() for page in PdfReader(tmp_path/'drawings.pdf').pages)
    assert 'Amber dashed lines: source reference locations only' in text and 'Physical plate/weld set-out: TBD' in text


def test_physical_centroid_below_floor_keeps_plan_connection_callout(tmp_path):
    p=source_frame()
    for m in p['physical']['members']:
        if m['kind']=='beam':
            for point in m['axis']:point[2]-=12
    for joint in p['physical']['joints']:
        joint['point'][2]-=12
        for end in joint['member_ends']:
            if end['member_id']=='C00':end['joint_offset']=[0,0,-12]
    report=generate(p,initial_state(p,1),tmp_path)
    assert any(c['sheet']=='S101' and 'C001' in c['reference'] for c in report['callouts'])
