import math
import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs_occurrences import bind,axis
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    package=evidence('cfs5')['package'];before=fingerprint(package);s=scenario('cfs5')
    model=build_model(package,dict(design_scenario=dict(id='cfs5',answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(package)==before
    from steltic_openbim.review_cfs_wall_bindings import bind as wall_bind
    wall_bind(model)
    bind(model)
    return model,package


def test_parapets_continue_actual_studs_and_keep_fit_exceptions_visible(actual):
    model,package=actual;changed=next(c for c in model['changes'] if c['kind']=='cfs5_actual_continuous_parapets')
    assert len(changed['stud_extensions'])==340
    lookup={m['id']:m for m in model['members']}
    assert not any(m['kind']=='parapet_stud' for m in model['members'])
    short=0
    for row in changed['stud_extensions']:
        stud=lookup[row['member_id']]
        assert stud['profile_id']=='600S162-43' and stud['axis'][0]==row['previous_axis'][0]
        assert axis(stud)[1][2]==pytest.approx(768-.1)
        if stud['backspan_status'].startswith('A '):short+=1
    assert short==70
    assert any('source16in capacity is not assigned' in c.get('basis','') for c in model['changes'])
    assert len([m for m in model['members'] if m['kind']=='parapet_cap'])==4
    assert len([o for o in model['openings'] if o.get('query_id')=='CFS5-PARAPET-CLEARANCES'])==340
    assert all(c['connection_id'] in {v['id'] for v in model['connections']} for c in changed['roof_connections'])


def test_all_actual_parapet_roof_screws_cross_both_attached_sheets(actual):
    model,package=actual;count=0;orientations=set()
    for c in model['connections']:
        if c['detail_ref']['id']!='review_parapet_roof':continue
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        joist=next(m for m in model['members'] if m['id']==c['member_ids'][1])
        expected='1000S200-68' if joist.get('prior_profile_id')=='1000S200-54' else '1000S200-54'
        assert {p['member']['profile_id'] for p in parts.values() if p.get('member')}=={'600S162-43',expected}
        assert [f['count'] for f in scene['fasteners']]==[4,4]
        for fastener in scene['fasteners']:
            for q in fastener['points']:
                for name in fastener['connects']:assert contact(parts[name],fastener,q),(c['id'],fastener['id'],name,q)
        orientations.add((c['parameters']['wall_axis'],c['parameters']['inward']));count+=1
    assert count==340 and orientations=={(0,1),(0,-1),(1,1),(1,-1)}


def test_actual_cap_corner_screws_contact_both_finite_caps(actual):
    model,package=actual;count=0
    for c in model['connections']:
        if not c['id'].startswith('PAR-CORNER-'):continue
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        count+=1
    assert count==4


def test_all_roof_notches_name_only_actual_through_studs(actual):
    model,_=actual;members={m['id']:m for m in model['members']}
    for o in model['openings']:
        if o.get('query_id')!='CFS5-PARAPET-CLEARANCES':continue
        stud=members[o['penetrating_member_ids'][0]];a,d=axis(stud)
        assert a[2]<731.25 and d[2]>732
        assert o['x_ft']*12-1e-6<=a[0]<=12*(o['x_ft']+o['width_ft'])+1e-6
        assert o['y_ft']*12-1e-6<=a[1]<=12*(o['y_ft']+o['height_ft'])+1e-6
        assert o['basis']=='A'


def test_offset_parallel_roof_clips_touch_real_joist_and_intact_track_web(actual):
    model,package=actual;members={m['id']:m for m in model['members']};count=0
    for c in model['connections']:
        data=c.get('parameters',{}).get('physical_floor_stack',{})
        if not any(members[mid].get('parallel_wall_line')=='CFS5-PARAPET-EDGE' for mid in data.get('joist_ids',[])):continue
        scene=build_scene(model,package,c);parts={p['id']:p for p in scene['parts']}
        clips=[f for f in scene['fasteners'] if f['id'].startswith('SIDE-')]
        for f in clips:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        count+=bool(clips)
    assert count>=4
