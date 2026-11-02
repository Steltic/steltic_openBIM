"""Acceptance checks for the three immutable, published fictional pilots."""
import copy
import json
import math
from pathlib import Path
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from steltic_openbim.drawing_workflow import initial_state,fingerprint,DrawingStore,StaleRevision,apply_answer
from steltic_openbim.design_scenarios import SCENARIOS,adopt_scenario,available_scenario
from steltic_openbim.design_geometry import build_model,interval_in_rectangle
from steltic_openbim.design_pdf import feet,inches,generate
from steltic_openbim.drawing_api import router

PILOT_KEYS=('hr22','cfs16','cfs8')


@pytest.fixture(scope='module')
def sources():
    with zipfile.ZipFile(Path(__file__).resolve().parents[1]/'docs/stage3/pilots.zip') as z:
        return {key:json.loads(z.read(key+'/bim_package.json')) for key in PILOT_KEYS}


def body(state,**extra):
    return dict(revision=state['revision'],source_model_sha256=state['source_model_sha256'],author='Fictional pilot acceptance test',confirm_fictional=True,**extra)


@pytest.fixture(scope='module')
def adopted(sources):
    result={}
    for key,p in sources.items():
        s=initial_state(p,3);before=fingerprint(p);state=adopt_scenario(p,s,body(s));model=build_model(p,state)
        assert fingerprint(p)==before
        result[key]=(state,model)
    return result


def test_explicit_fictional_adoption_is_source_bound(sources):
    p=sources['hr22'];s=initial_state(p,1);b=body(s)
    with pytest.raises(ValueError,match='Explicitly confirm'):adopt_scenario(p,s,dict(b,confirm_fictional=False))
    with pytest.raises(StaleRevision):adopt_scenario(p,s,dict(b,revision=0))
    with pytest.raises(ValueError,match='bound'):adopt_scenario(p,s,dict(b,pilot='cfs8'))
    changed=copy.deepcopy(p);changed['building_id']='A real replacement job'
    assert available_scenario(changed) is None
    assert s['drawing_status']=='provisional' and all(not r['confirmed'] for r in s['requests'])


@pytest.mark.parametrize('key',PILOT_KEYS)
def test_all_answers_marks_and_joint_references_are_traceable(sources,adopted,key):
    state,m=adopted[key]
    assert state['drawing_status']=='design_test'
    assert len(state['requests'])==len(SCENARIOS[key]['answers'])
    assert all(r['confirmed'] and r['resolution_basis']=='user_authorized_fictional_assumption' for r in state['requests'])
    assert state['source_readiness']=='needs_input'
    mids={a['id'] for a in m['members']};refs={d['reference'] for d in m['details']}
    assert len(mids)==len(m['members'])
    assert sum(a['count'] for a in m['member_schedule'])==len(mids)
    assert {i for a in m['member_schedule'] for i in a['member_ids']}==mids
    for member in m['members']:
        assert member['mark'] and member['connection_refs'] and set(member['connection_refs'])<=refs
        assert math.dist(*member['axis'])>.01
        assert all(math.isfinite(v) for p in member['axis'] for v in p)
    for c in m['connections']:assert set(c['member_ids'])<=mids and c['drawing_ref'] in refs
    assert fingerprint(sources[key])==SCENARIOS[key]['source_sha256']


@pytest.mark.parametrize('key',PILOT_KEYS)
def test_secondary_members_are_really_interrupted_at_openings(adopted,key):
    state,m=adopted[key]
    for f in state['features']:
        axes=['xyz'.index(c) for c in f['plane']];normal=next(i for i in range(3) if i not in axes)
        lo=[f[k]*12 for k in ('x_ft','y_ft','z_ft')];hi=lo.copy();hi[axes[0]]+=f['width_ft']*12;hi[axes[1]]+=f['height_ft']*12
        allowed={'joist'} if f['plane']=='xy' else {'stud','stud_bridging','bridging_anchor','bottom_track','girt'}
        for member in m['members']:
            a,b=member['axis']
            if member['kind'] in allowed and max(abs(a[normal]-lo[normal]),abs(b[normal]-lo[normal]))<=15:
                assert interval_in_rectangle(a,b,lo,hi,axes) is None,(f['id'],member['id'])
        assert any(a['id'].startswith('TEST-'+f['id']+'-') for a in m['members'])


def test_housing_openings_avoid_braced_bays_and_floor_datums_close(sources,adopted):
    state,m=adopted['cfs8']
    for f in state['features']:
        if f['plane']=='xy':continue
        along=0 if f['plane']=='xz' else 1;normal=1-along
        a=[f[k]*12 for k in ('x_ft','y_ft','z_ft')];b=a.copy();b[along]+=f['width_ft']*12;b[2]+=f['height_ft']*12
        for brace in [a for a in m['members'] if a['kind']=='strap']:
            if max(abs(p[normal]-a[normal]) for p in brace['axis'])<15:
                assert interval_in_rectangle(*brace['axis'],a,b,(along,2)) is None,(f['id'],brace['id'])
    for member in m['members']:
        if member['kind']=='walkway_joist':
            ffl=(120,236,352)[member['level']-1]
            assert all(abs(p[2]+4+.75-ffl)<1e-7 for p in member['axis'])
    assert len([a for a in m['members'] if a['kind']=='walkway_post'])==7
    assert len([a for a in m['panels'] if a['kind']=='assumed_footing'])==7
    assert not any(a['kind']=='truss_envelope' for a in m['panels'])


def test_feet_and_fraction_dimensions_carry_at_twelve_inches():
    assert feet(11.999)=="1'-0\""
    assert feet(107.25)=="8'-11-1/4\""
    assert inches(.875)=='7/8"'


@pytest.mark.parametrize('key',PILOT_KEYS)
def test_drawings_have_valid_scales_refs_and_all_opening_dimensions(sources,adopted,tmp_path,key):
    state,model=adopted[key];report=generate(sources[key],state,tmp_path/key)
    pdf=PdfReader(tmp_path/key/'drawings.pdf');assert len(pdf.pages)==len(report['sheets'])
    texts=[p.extract_text() for p in pdf.pages]
    assert all('FICTIONAL TEST BUILDING' in t for t in texts)
    assert 'ADOPTED FICTIONAL TEST ANSWER' in texts[1]
    assert all('TBD - resolve query' not in t for t in texts)
    assert all(abs(v['points_per_inch']*v['scale_denominator']-72)<1e-8 for v in report['views'])
    sheets={a['number'] for a in report['sheets']}
    assert all(c['reference'].split('/')[-1] in sheets for c in report['callouts'])
    assert len([d for d in report['dimensions'] if d['sheet']=='S301'])==len(model['openings'])*5
    assert all(float(p.mediabox.width)>2300 and float(p.mediabox.height)>1600 for p in pdf.pages)
    stored=json.loads((tmp_path/key/'design_model.json').read_text(encoding='utf-8'))
    assert fingerprint(stored)==report['model_sha256']
    if key=='cfs16':assert '40 No. 12' in '\n'.join(texts) and 'schedules/sched-purlin/row-1' in '\n'.join(texts)
    if key=='cfs8':assert 'screws per bay 58' in '\n'.join(texts) and '1-3/4 in. ASTM A449' in '\n'.join(texts)


def test_api_adopts_regenerates_and_reopens_without_silent_fiction(sources,tmp_path):
    p=sources['cfs16'];store=DrawingStore(tmp_path);s=store.import_package('Pilot',p)
    app=FastAPI();app.include_router(router(store));c=TestClient(app);url='/api/project/Pilot/drawings'
    assert c.get(url).json()['available_test_scenario']=='cfs16'
    assert c.post(url+'/fictional-design',json=dict(body(s),confirm_fictional=False)).status_code==422
    result=c.post(url+'/fictional-design',json=body(s));assert result.status_code==200,result.text
    r=result.json();assert r['revision']==2 and r['drawing_status']=='design_test'
    assert c.get(url+'/file/design_model.json').status_code==200
    assert c.post(url+'/fictional-design',json=body(s)).status_code==409
    r2=c.post(url+'/regenerate',json=body(r)).json();assert r2['features']==r['features'] and r2['revision']==3
    r3=c.post(url+'/answers',json=body(r2,id='CFS16-DOORS',action='reopen',note='Reconsider the door layout')).json()
    assert r3['drawing_status']=='provisional' and 'design_model.json' not in r3['artifacts']
    assert c.get(url+'/file/design_model.json').status_code==404
    assert len(c.get(url+'/history').json()['revisions'])==4
    changed=copy.deepcopy(p);changed['building_id']='Replacement'
    fresh=store.import_package('Pilot',changed,r3['revision'])
    assert 'design_scenario' not in fresh and fresh['drawing_status']=='provisional'


def test_editing_test_openings_retains_assumed_basis_and_updates_register(sources,adopted):
    state,_=adopted['cfs16'];f=copy.deepcopy(state['features'][0]);f['y_ft']=140
    updated=apply_answer(sources['cfs16'],state,body(state,id='CFS16-DOORS',action='resolve_openings',features=[f],note='Fictional revision: one door at Y=140 ft.'))
    model=build_model(sources['cfs16'],updated)
    assert updated['drawing_status']=='design_test'
    assert '140 ft' in next(r['answer'] for r in model['assumptions'] if r['id']=='CFS16-DOORS')
    assert all(f['basis'].startswith('A') for f in updated['features'])
