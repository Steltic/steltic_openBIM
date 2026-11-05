from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from test_sbmf_header_fit import contact


def test_all_six_wind_posts_fit_the_actual_end_frame_with_slotted_flange_bolts():
    p=evidence('cfs18')['package'];before=fingerprint(p);s=scenario('cfs18')
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(s['answers']))));count=0
    assert fingerprint(p)==before
    lookup={v['id']:v for v in m['members']}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_post_head':continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert lookup[c['member_ids'][0]]['axis'][1][2]==288
        assert len(scene['fasteners'])==2
        for f in scene['fasteners']:
            assert f['count']==2 and f['basis']=='A'
            assert f['slot']['direction']==[0,0,1] and f['slot']['travel_in']==1
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        count+=1
    assert count==6
