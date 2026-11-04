"""Unlocated section groups must not become complete building drawings."""
import copy
import json
from pathlib import Path
from pypdf import PdfReader
import pytest

from steltic_openbim.bim_contract import validate,mapping_geometry_findings
from steltic_openbim.drawing_workflow import DrawingStore,initial_state,apply_answer,fingerprint
from steltic_openbim.source_worklines import build,required,physical_view


def grouped_package():
    p=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_text())
    p['module']='HR';p['layout_evidence']={'levels_in':[0,120,240]}
    nodes=[];elements=[]
    for k in range(3):
        for i,(x,y) in enumerate([(0,0),(240,0),(240,240),(0,240)]):
            nodes.append(dict(id=f'n{k}-{i}',point=[x,y,k*120]))
    def add(a,b,kind):elements.append(dict(id=f'e{len(elements)+1}',node_ids=[a,b],kind=kind,profile_id='TEST'))
    for k in (1,2):
        for i in range(4):
            add(f'n{k-1}-{i}',f'n{k}-{i}','col')
            add(f'n{k}-{i}',f'n{k}-{(i+1)%4}','beam')
    p['analysis']={'nodes':nodes,'elements':elements}
    p['physical']['members'][0]['analysis_ids']=[e['id'] for e in elements]
    p['readiness']={'status':'ready'}
    return p


def test_catchall_mapping_cannot_pass_as_complete_occurrence_geometry():
    p=grouped_package()
    assert mapping_geometry_findings(p)
    assert 'analysis_occurrence_geometry' in {f['code'] for f in validate(p)}
    assert required(p)
    model=build(p)
    assert model['counts']['drawn_occurrences']==16 and model['counts']['levels']==2
    assert {m['id'] for m in model['members']}=={e['id'] for e in p['analysis']['elements']}
    nodes={n['id']:n['point'] for n in p['analysis']['nodes']}
    for m,e in zip(model['members'],p['analysis']['elements']):
        assert m['axis']==[nodes[n] for n in e['node_ids']]


def test_collinear_chain_is_a_real_physical_member():
    p=grouped_package();m=p['physical']['members'][0];a,b=m['axis'];mid=[(x+y)/2 for x,y in zip(a,b)]
    p['analysis']={'nodes':[{'id':i,'point':v} for i,v in zip('abc',[a,mid,b])],
                   'elements':[dict(id='one',node_ids=['a','b']),dict(id='two',node_ids=['b','c'])]}
    m['analysis_ids']=['one','two']
    assert not mapping_geometry_findings(p)
    p['analysis']['nodes'][1]['point'][1]+=10
    assert mapping_geometry_findings(p)


@pytest.mark.parametrize('operation',['regenerate','import'])
def test_old_ready_revision_gains_requests_without_losing_history(tmp_path,operation):
    p=grouped_package();source_hash=fingerprint(p);store=DrawingStore(tmp_path)
    old=initial_state(p,1);old.update(requests=[],features=[],drawing_status='source_geometry',source_readiness='ready')
    store.publish('Existing',p,old)
    current=store.current('Existing');old_pdf=(current[0]/'drawings.pdf').read_bytes()
    new=store.regenerate('Existing',old) if operation=='regenerate' else store.import_package('Existing',p,1)
    assert new['revision']==2 and new['drawing_status']=='provisional' and new['source_readiness']=='needs_input'
    assert {r['id'] for r in new['requests']}=={'MODEL-OCCURRENCES','MODEL-CONNECTIONS','MODEL-FLOORS','MODEL-OPENINGS','analysis_occurrence_geometry'}
    assert all(r['accepted'] and not r['confirmed'] and r['proposal'] for r in new['requests'])
    assert (current[0]/'drawings.pdf').read_bytes()==old_pdf and fingerprint(p)==source_hash
    directory=store.current('Existing')[0];manifest=json.loads((directory/'drawing_manifest.json').read_text())
    assert manifest['representation']=='captured_source_worklines'
    assert {'S101','S102'}<={s['number'] for s in manifest['sheets']}
    assert set.union(*[set(v['member_ids']) for v in manifest['views']])=={e['id'] for e in p['analysis']['elements']}
    assert not any(d.get('kind')=='confirmed_opening' for d in manifest['dimensions'])
    assert len(PdfReader(directory/'drawings.pdf').pages)==len(manifest['sheets'])


def test_upper_storey_openings_can_be_resolved_in_recovered_bounds():
    p=grouped_package();s=initial_state(p,1);f=copy.deepcopy(next(f for f in s['features'] if f['level']==2))
    f.update(x_ft=15,y_ft=15,width_ft=2,height_ft=2)
    body=dict(revision=1,source_model_sha256=fingerprint(p),id='MODEL-OPENINGS',action='resolve_openings',author='Synthetic test',note='Confirmed test coordinates',features=[f])
    result=apply_answer(p,s,body)
    assert len(result['features'])==1 and result['features'][0]['confirmed']
    assert next(r for r in result['requests'] if r['id']=='MODEL-OPENINGS')['confirmed']


def test_candidate_replay_members_receive_storeys_without_using_prototype_levels():
    p=grouped_package();p['physical']['members'][0].update(status='candidate',geometry_basis='analysis_axis')
    assert required(p)
    assert {m['level'] for m in build(p)['members']}=={1,2}


def test_unmapped_source_members_are_recovered_and_missing_storey_labels_are_inferred():
    p=grouped_package();p['physical']['members'][0]['analysis_ids']=[]
    assert required(p)
    original=p['physical']['members'][0];original['axis']=[[0,0,120],[240,0,240]]
    view=physical_view(p)
    assert view['members'][0]['level']==2 and 'level' not in original
    assert view['members'][0]['axis']==original['axis']
