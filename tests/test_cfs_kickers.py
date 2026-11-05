import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_rod_actual_receivers import contact


@pytest.mark.parametrize('key', ['cfs17','cfs19','cfs30'])
def test_every_source_kicker_type_has_actual_flange_and_web_contact(key):
    package=evidence(key)['package'];s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    members={m['id']:m for m in model['members']};seen=set();checked=0
    connections=[c for c in model['connections'] if c.get('parameters',{}).get('actual_cfs_kicker')]
    assert connections
    for c in connections:
        par=c['parameters'];data=par['actual_cfs_kicker'];angle,roof,*rest=[members[mid] for mid in c['member_ids']];high=[m for m in rest if m['kind']=='purlin']
        assert roof['kind']=='rafter' and all(h['kind']=='purlin' for h in high)
        if not par.get('post_top'):
            assert par['lower_count']=={'cfs17':3,'cfs19':4,'cfs30':6}[key]
            assert par['upper_count']==(6 if key=='cfs30' else 4)
            assert len([m for m in rest if m['kind']=='flange_cross_plate'])==1
        else:
            assert par['lower_count']==par['upper_count']=={'cfs17':4,'cfs19':5,'cfs30':6}[key]
        length=math.dist(*angle['axis']);delta=[b-a for a,b in zip(*angle['axis'])]
        if data['source_length_in']:assert length==pytest.approx(30)
        else:assert abs(delta[1])==pytest.approx(abs(delta[2]))
        shape=(roof['profile_id'],tuple(h['profile_id'] for h in high),data['face_side'],
               delta[1]>0,par.get('post_top'),round((roof['axis'][1][2]-roof['axis'][0][2])/(roof['axis'][1][0]-roof['axis'][0][0]),5),
               par['lower_count'],par['upper_count'],data['foot_centre_y']>roof['axis'][0][1])
        if shape in seen:continue
        seen.add(shape);checked+=1
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        assert sum(len(f['points']) for f in scene['fasteners'] if f['id']=='LOW-ANGLE')==par['lower_count']
        assert sum(len(f['points']) for f in scene['fasteners'] if f['id']=='HIGH')==par['upper_count']
        if par.get('post_top'):
            assert next(f for f in scene['fasteners'] if f['id']=='LOW-ANGLE')['grip']==pytest.approx(.375)
            assert sum(len(f['points']) for f in scene['fasteners'] if f['id']=='LOW-RAFTER')==par['lower_count']
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:
                    assert contact(parts[target],f,q),(key,c['id'],f['id'],target,q)
    assert checked>=8


@pytest.mark.parametrize('key', ['cfs17','cfs19','cfs30'])
def test_source_cross_plate_contacts_all_six_real_flanges_once_per_station(key):
    package=evidence(key)['package'];s=scenario(key)
    model=build_model(package,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    members={m['id']:m for m in model['members']};seen=set();stations=set()
    connections=[c for c in model['connections'] if c.get('parameters',{}).get('actual_cfs_cross_plate')]
    assert connections
    for c in connections:
        plate,roof=[members[mid] for mid in c['member_ids']]
        station=(roof['id'],tuple(round(x,5) for x in c['point']));assert station not in stations;stations.add(station)
        assert math.dist(*plate['axis'])==pytest.approx(19)
        assert plate['source_plate_size_in']==[4,19] and plate['source_sheet_gauge']=='12 ga'
        n=[round(b-a,5) for a,b in zip(*roof['axis'])];shape=(roof['profile_id'],tuple(n))
        if shape in seen:continue
        seen.add(shape);scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        assert len(scene['fasteners'])==6
        assert sum(len(f['points']) for f in scene['fasteners'])==(18 if key=='cfs30' else 12)
        for f in scene['fasteners']:
            for q in f['points']:
                for target in f['connects']:assert contact(parts[target],f,q),(key,c['id'],f['id'],target,q)
