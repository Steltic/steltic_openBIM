from types import SimpleNamespace
from steltic_openbim.review_cfs6_floor_panels import bind_bearing_clearances


def test_bearing_cutback_resolves_later_packs_through_actual_layer_depth_only():
    def member(id,kind,x,a,b):return dict(id=id,kind=kind,axis=[[x,0,a],[x,0,b]],end_offsets=[[0,0,0],[0,0,0]])
    cut=dict(id='CUT',kind='wall_bearing_holdback',host_id='P',x_ft=0,y_ft=-.25,width_ft=2,height_ft=.5,z_ft=10)
    door=dict(cut,id='DOOR',kind='door')
    b=SimpleNamespace(key='cfs6',panels=[dict(id='P',thickness_in=.71875,thickness_direction='negative_global_z')],
        openings=[cut,door],members=[member('PACK','chord_squash_pack',3,110,119.4),
        member('ROD','hold_down_rod',6,100,130),member('BELOW','chord_squash_pack',8,110,119),
        member('OUTSIDE','chord_squash_pack',30,110,130),member('WRONG','stud',10,100,130)])
    bind_bearing_clearances(b)
    assert cut['penetrating_member_ids']==['PACK','ROD']
    assert 'penetrating_member_ids' not in door
    assert 'actual' in cut['penetration_basis']
