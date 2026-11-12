from copy import deepcopy

import pytest

from steltic_openbim.bim_assemblies import fingerprint, transformed
from steltic_openbim.hr_connection_frames import beam_connection_view
from steltic_openbim.hr_skid_bay import reviewed_bay


def test_both_opening_header_ends_attach_to_the_finite_trimmer():
    from steltic_openbim.ifc_beam_ends import beam_end_fits
    wp=[0,0,0]
    def member(mid,kind,end,y):
        return dict(id=mid,kind=kind,profile_id='W',axis=[wp,end],local_y=y,end_offsets=[[0,0,0]]*2)
    support=member('S','opening_trimmer',[0,-30,0],[1,0,0])
    left=member('L','opening_trimmer',[-30,0,0],[0,-1,0])
    right=member('R','opening_header',[30,0,0],[0,1,0])
    def detail(mid):
        return dict(id=mid+'-connection',point=wp,joint_id='J',member_ids=[mid,'S'],detail_ref=dict(legacy_family='test_floor_opening'),
                    assembly_instance=dict(template_id='T',origin=wp,x_axis=[0,-1,0],y_axis=[1,0,0],bindings=dict(M1=mid,M2='S')))
    template=dict(id='T',parts=[],receivers=[dict(id='M1',kind='member',axis=[[0,-10,0],[0,10,0]]),
                                            dict(id='M2',kind='member',axis=[[1.5,0,0],[12,0,0]])])
    joint=dict(id='J',point=wp,attachments=[],member_ends=[dict(member_id=mid,end='start') for mid in ('S','L','R')])
    physical=dict(members=[support,left,right],profiles=[dict(id='W',family='i',dimensions=dict(d=18.,tw=.32,tf=.5,bf=6.))],
                  joints=[joint],connections=[detail('L'),detail('R')],assemblies=[template])
    view=beam_connection_view(physical)
    assert beam_connection_view(view) is view
    fits=beam_end_fits(view)
    assert not fits.get('S')
    for c in view['connections']:
        f=c['assembly_instance']
        assert f['bindings']==dict(M1='S',M2=c['member_ids'][0])
        assert transformed([0,1,0],f)==[0,-1,0]
        assert len(fits[f['bindings']['M2']])==1


@pytest.mark.parametrize('end,sign', [('start',1),('end',-1)])
def test_equal_section_tee_binds_fixed_hardware_to_branch(end,sign):
    joint = [0,0,0]
    far = [0,80*sign,0]
    branch = dict(id='B',kind='infill',profile_id='W',local_y=[-1,0,0],
                  axis=[joint,far] if end=='start' else [far,joint],end_offsets=[[0,0,0]]*2)
    through = dict(id='S',kind='girder',profile_id='W',local_y=[0,1,0],
                   axis=[[-80,0,0],[80,0,0]],end_offsets=[[0,0,0]]*2)
    inst = dict(template_id='T',origin=joint,x_axis=[1,0,0],y_axis=[0,1,0],bindings=dict(M1='B',M2='S'))
    c = dict(id='C',joint_id='J',assembly_instance=inst,detail_ref=dict(legacy_family='review_beam'))
    template = dict(id='T', parts=[dict(id='plate',material_id='steel')], receivers=[
        dict(id='M1',kind='member',axis=[[0,0,0],[0,20,0]],source_context_axis=[[0,-20,0],[0,20,0]]),
        dict(id='M2',kind='member',axis=[[1.5,0,0],[20,0,0]])])
    p = dict(members=[branch,through],assemblies=[template],connections=[c],
             joints=[dict(id='J',member_ends=[dict(member_id='B',end=end)],
                          attachments=[dict(member_id='S',station=.5)])])
    before = deepcopy(p)
    result = beam_connection_view(p)
    located = result['connections'][0]['assembly_instance']
    assert located['bindings']==dict(M1='S',M2='B')
    assert transformed([1.5,0,0],located)==pytest.approx([0,1.5*sign,0])
    variant = result['assemblies'][-1]
    assert variant['parts']==before['assemblies'][0]['parts']
    assert located['revision']==fingerprint({k:v for k,v in variant.items() if k!='revision'})
    assert p==before and beam_connection_view(result) is result
    for r in variant['receivers']:
        m = through if r['id']=='M1' else branch
        assert transformed(r['local_y'],located,True)==pytest.approx(m['local_y'])


def test_written_skid_bay_bears_on_both_x_girders_and_keeps_leg_reactions():
    _, model = reviewed_bay()
    members = {m['id']:m for m in model['members']}
    connections = {c['id']:c for c in model['connections']}
    for mid,x in [('SKID-BEAM-0',264),('SKID-BEAM-1',456),
                  ('INF-FLOOR-9-300.0',300),('INF-FLOOR-9-360.0',360),('INF-FLOOR-9-420.0',420)]:
        assert members[mid]['axis']==[[x,240,312],[x,480,312]]
        for end,host in enumerate(['hr:element:58','hr:element:61']):
            assert connections[mid+':'+str(end)]['member_ids']==[mid,host]
    for i in range(4):
        foot = connections[f'SKID-LEG-{i}-FOOT']
        host = members[foot['member_ids'][1]]
        assert foot['point'][0]==host['axis'][0][0]
        assert foot['point'][1] in (300,420)
        assert connections[f'SKID-DIAG-{i}:0']['member_ids'][1]==host['id']
    # The vessel's design reactions go to numbered grids, independently of the skid.
    assert all(members[f'VESSEL-BEAM-{i}']['axis'][0][0]==240 for i in range(2))
