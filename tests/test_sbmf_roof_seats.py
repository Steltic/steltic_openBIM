import pytest
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.pilots.geometry import member_faces
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module',params=('cfs10','cfs18'))
def actual(request):
    key=request.param;p=evidence(key)['package'];before=fingerprint(p);s=scenario(key)
    m=build_model(p,dict(design_scenario=dict(id=key,answers_sha256=fingerprint(s['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_all_heel_bolts_cross_actual_caps_shims_and_chord_flanges(actual):
    m,p=actual;count=0;supports=set()
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_roof_seat':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']};supports.add(c['parameters']['support'])
        assert len(s['fasteners'])==2
        for f in s['fasteners']:
            assert f['basis']=='A' and f['count']==1
            for q in f['points']:
                for label in f['connects']:assert contact(parts[label],f,q),(c['id'],label,q)
        assert len(s['interfaces'])==2
        count+=1
    assert supports=={'column','header'} and count==(114 if m['pilot']=='cfs10' else 170)


def test_one_real_closure_per_hss_and_heel_footprints_are_supported(actual):
    m,p=actual;lookup={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    caps=[v for v in m['members'] if v['kind']=='column_cap']
    assert len({v['id'] for v in caps})==len(caps)
    for cap in caps:
        c=next(v for v in m['connections'] if v['id']==cap['id']+'-WELD');column=lookup[c['member_ids'][1]]
        ctop=column['axis'][1][2]+column['end_offsets'][1][2]
        lower=min(q[2] for face in member_faces(cap,profiles) for q in face)
        assert lower==pytest.approx(ctop)
        scene=build_scene(m,p,c);assert len(scene['welds'])==4
        assert all(w['basis']=='A' for w in scene['welds'])
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_roof_seat':continue
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']};cap=parts['CAP']
        for f in s['fasteners']:
            q=f['points'][0]
            assert cap['bounds'][0][0]<q[0]<cap['bounds'][0][1]
            assert cap['bounds'][1][0]<q[1]<cap['bounds'][1][1]


def test_no_generic_track_is_inserted_at_the_main_roof_headers(actual):
    m,p=actual
    for c in m['connections']:
        if not c['id'].startswith('ROOF-') or 'SEAT' not in c['id'] or c['point'][1] not in (0,600):continue
        assert c['detail_ref']['id']=='review_sbmf_roof_seat'
        s=build_scene(m,p,c)
        assert not any(v['id'] in ('STUD','TRACK') for v in s['parts'])
        assert 'schedules/sched-purlin' in c['design_record_ids']
