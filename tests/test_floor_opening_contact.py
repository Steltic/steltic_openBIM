import math
import pytest
from shapely.geometry import Point,Polygon
from steltic_openbim.review_floor_openings import bind
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.assembly_scene import section_polygons


def contact(part,fastener,pt):
    axis=max(range(3),key=lambda i:abs(fastener['axis'][i]));other=[i for i in range(3) if i!=axis]
    query=Point([pt[i] for i in other])
    for step in range(1,80):
        at=pt[axis]+fastener['axis'][axis]*fastener['grip']*step/80
        if any(Polygon(poly).buffer(1e-7).covers(query) for poly in section_polygons(part,axis,at)):return True
    return False


@pytest.mark.parametrize('paired',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_actual_opening_plies_datums_cut_clearance_and_screw_contact(paired,reverse):
    profiles=[dict(id='C',family='channel',dimensions=dict(d=12,b=2.5,t=.1017,lip=.625)),
              dict(id='PAIR',family='built_up',dimensions={},components=[dict(profile_id='C',offset=[-.11335,0],rotation_deg=180),dict(profile_id='C',offset=[.11335,0],rotation_deg=0)])]
    primary=dict(id='J',kind='joist',profile_id='PAIR' if paired else 'C',axis=[[0,0,0],[100,0,0]],end_offsets=[[0,0,0],[0,0,0]],local_y=[0,1,0])
    if reverse:primary.update(axis=primary['axis'][::-1],local_y=[0,-1,0])
    support=dict(id='H',kind='opening_trimmer',profile_id='PAIR',axis=[[0,-40,3.25],[0,40,3.25]],end_offsets=[[0,0,0],[0,0,0]],local_y=[-1,0,0])
    c=dict(id='end',point=[0,0,0],member_ids=['J'],detail_ref=dict(id='test_floor_opening'),parameters={},design_record_ids=[])
    m=dict(pilot='cfs-fixture',members=[primary,support],profiles=profiles,connections=[c])
    bind(m);scene=build_scene(m,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    assert c['member_ids']==['J','H'] and len(m['connection_endpoint_links'])==1
    assert parts['JOIST']['member']['source_member_index']==0
    assert parts['SUPPORT']['member']['source_member_index']==1
    assert parts['JOIST']['bounds'][0][0]-parts['SUPPORT']['bounds'][0][1]==pytest.approx(.125)
    assert len(scene['fasteners'])==(4 if paired else 2)
    for f in scene['fasteners']:
        assert len(f['points'])==8
        for q in f['points']:
            for joined in f['connects']:assert contact(parts[joined],f,q),(paired,reverse,f['id'],joined,q)
    # Re-preparing the same model cannot apply another cutback or duplicate links.
    before=list(primary['end_offsets'][1 if reverse else 0]);bind(m)
    assert primary['end_offsets'][1 if reverse else 0]==before and len(m['connection_endpoint_links'])==1


def test_short_truss_chord_uses_a_fitted_and_explicitly_unverified_screw_group():
    profiles=[dict(id='CH',family='channel',dimensions=dict(d=2.5,b=1.625,t=.0713,lip=.375)),
              dict(id='H',family='channel',dimensions=dict(d=12,b=2.5,t=.1017,lip=.625))]
    primary=dict(id='CHORD',kind='truss_chord',profile_id='CH',axis=[[0,0,0],[100,0,0]],end_offsets=[[0,0,0],[0,0,0]],local_y=[0,1,0])
    support=dict(id='H',kind='opening_header',profile_id='H',axis=[[0,-40,-4.75],[0,40,-4.75]],end_offsets=[[0,0,0],[0,0,0]],local_y=[-1,0,0])
    c=dict(id='end',point=[0,0,0],member_ids=['CHORD'],detail_ref=dict(id='test_floor_opening'),parameters={},design_record_ids=[])
    model=dict(pilot='cfs-fixture',members=[primary,support],profiles=profiles,connections=[c])
    bind(model);scene=build_scene(model,dict(design_records=[]),c);parts={p['id']:p for p in scene['parts']}
    for f in scene['fasteners']:
        assert f['basis']=='A' and len(f['points'])==2
        for q in f['points']:
            for name in f['connects']:assert contact(parts[name],f,q),(f['id'],name,q)
    assert any('reduced screw count' in note and 'capacity verification' in note for note in scene['notes'])
