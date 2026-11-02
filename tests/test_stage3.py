import copy
import json
from pathlib import Path
import zipfile
import pytest

from steltic_openbim.pilots import hr22,cfs16,cfs8
from steltic_openbim.pilots.model import stable_hash
from steltic_openbim.pilots.model import cross
from steltic_openbim.pilots.checks import inspect
from steltic_openbim.pilots.geometry import member_faces,part_faces,strips
from steltic_openbim.review import questions,record_answers
from steltic_openbim.bim_contract import validate

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def pilots():
    catalog=json.loads((Path(hr22.__file__).parent/'catalog.json').read_text())
    result={}
    with zipfile.ZipFile(ROOT/'tests/fixtures/stage3_replay_inputs.zip') as z:
        for key,module in [('hr22',hr22),('cfs16',cfs16),('cfs8',cfs8)]:
            source=json.loads(z.read(key+'/bim_package.json')); before=stable_hash(source)
            model=module.build(source,catalog)
            assert stable_hash(source)==before
            result[key]=(source,model)
    return result


@pytest.mark.parametrize('key',['hr22','cfs16','cfs8'])
def test_actual_pilot_counts_coordinates_and_source_preservation(pilots,key):
    source,p=pilots[key]; report=inspect(p,source,key)
    assert report['passed'],[r for r in report['checks'] if not r['passed']]


def test_changed_source_cannot_reuse_recipe(pilots):
    source=copy.deepcopy(pilots['hr22'][0]); source['design_records'][0]['data']['section']='CHANGED'
    with pytest.raises(ValueError,match='different source revision'):
        hr22.build(source,{})


def test_answers_are_source_bound_and_do_not_release_geometry(pilots):
    p=pilots['cfs8'][1]; before=stable_hash(p); q=questions(p); iid=q['groups'][0]['items'][0]['id']
    answer={'id':iid,'accepted':True,'accepted_by':'test reviewer','value':'Fixture answer only'}
    result=record_answers(p,q,[answer])
    assert result['status']=='awaiting_recipe_implementation_and_recheck'
    assert stable_hash(p)==before
    q['source_package_sha256']='stale'
    with pytest.raises(ValueError,match='Stale'): record_answers(p,q,[answer])


def test_answer_requires_explicit_acceptance(pilots):
    p=pilots['hr22'][1]; q=questions(p); iid=q['groups'][0]['items'][0]['id']
    with pytest.raises(ValueError,match='explicit accepted'):
        record_answers(p,q,[{'id':iid,'value':'assume default','accepted':False}])


def test_pending_review_prevents_ready_even_if_source_findings_removed(pilots):
    p=copy.deepcopy(pilots['hr22'][1]); p['source_findings']=[]; p['readiness']={'status':'ready'}
    for item in p['physical']['coverage'].values(): item['complete']=True
    assert any(f['code']=='coordination_required' for f in validate(p))


def test_rbs_is_a_real_flange_reduction_in_mesh(pilots):
    p=pilots['hr22'][1]; bm=next(m for m in p['physical']['members'] if m['kind']=='moment_beam'); profiles={p['id']:p for p in p['physical']['profiles']}
    faces=member_faces(bm,profiles); assert len(faces)>100
    # With the same endpoints, removing RBS changes the actual mesh vertices.
    plain=dict(bm,rbs=None); assert faces!=member_faces(plain,profiles)


def test_channel_preview_preserves_outer_depth(pilots):
    p=pilots['cfs16'][1]; profiles={p['id']:p for p in p['physical']['profiles']}
    profile=profiles['1400S300-118']; polygons=strips(profile,profiles)
    assert max(v[1] for poly in polygons for v in poly)==pytest.approx(profile['dimensions']['d']/2)
    assert min(v[1] for poly in polygons for v in poly)==pytest.approx(-profile['dimensions']['d']/2)


def test_connection_parts_have_renderable_geometry(pilots):
    for _,p in pilots.values():
        profiles={v['id']:v for v in p['physical']['profiles']}
        for c in p['physical']['connections']:
            for part in c.get('parts',[]): assert part_faces(part,profiles)


def test_plate_handedness_and_material_grades(pilots):
    hr=pilots['hr22'][1]
    for c in hr['physical']['connections']:
        for part in c.get('parts',[]):
            if part['id']=='shear-plate':
                g=part['geometry']; assert cross(g['x_axis'],g['y_axis'])==[0,0,1]
    cfs=pilots['cfs16'][1]
    assert all(m['material_id']=='tube' for m in cfs['physical']['members'] if m['kind']=='door_header')
    wall=pilots['cfs8'][1]
    assert all(m['material_id']=='cfs33' for m in wall['physical']['members'] if m['profile_id'].endswith('-43'))
