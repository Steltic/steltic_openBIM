import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_cases import evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.review_cfs6_roof_distribution import apply
from steltic_openbim.assembly_templates import build_scene
from test_floor_opening_contact import contact


def test_source_strong_axis_distribution_uses_actual_stud_and_chord_webs():
    source=evidence('cfs6');s=scenario('cfs6')
    b=CaseModel('cfs6',source['package'],dict(design_scenario=dict(id='cfs6',answers_sha256=fingerprint(s['answers']))),source)
    b.endpoint_links=[];b.levels=[(0,'Base',0),(5,'Roof',576)]
    b.member('CAP','600T150-54','top_track',[0,1080,565.25-.0283],[80,1080,565.25-.0283],5,local_y=[0,0,-1])
    for x in (8,24,40,59):
        kind='chord' if x==59 else 'stud';pid='2X600S200-54' if kind=='chord' else '600S162-54'
        m=b.member('S'+str(x),pid,kind,[x,1080,456.1],[x,1080,565.15],5,local_y=[1,0,0]);b.ends(m,'cfs_stud')
    apply(b)
    beams=[m for m in b.members if m['kind']=='load_distribution'];assert len(beams)==3
    assert all(m['profile_id']=='600S162-54' and m['source_span_in']==16 for m in beams)
    assert beams[-1]['basis']=='A' and beams[-1]['engineering_status']=='longer_fit_span_unverified'
    assert next(m for m in b.members if m['id']=='S59')['end_offsets']==[[0,0,0],[0,0,0]]
    assert not any(c['id'] in ('S8:1','S24:1','S40:1') for c in b.connections)
    model=dict(pilot='cfs6',members=b.members,profiles=list(b.profiles.values()),connections=b.connections)
    for c in b.connections:
        if c['detail_ref']['id']!='review_roof_distribution':continue
        scene=build_scene(model,source['package'],c);parts={p['id']:p for p in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],name,q)
