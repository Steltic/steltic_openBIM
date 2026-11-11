from copy import deepcopy
import pytest
from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.brb_occurrence_setout import selected_end,head_fit
from steltic_openbim.brb_terminal_readback import check_setout
from test_brb_core_readback import as_mesh
from test_ifc_assembly_verification import export_readback


def case():
    m={'id':'brace-a','axis':[[0,0,0],[100,0,0]]}
    row=dict(connection_id='a:0',end_index=0,pin_station_in=10.,head_front_station_in=18.,head_back_station_in=19.,
             casing_face_station_in=22.6725,full_travel_in=3.61,head_to_casing_clearance_in=3.6725,
             core_terminal_area_in2=9.6,actual_CJP_area_in2=9.6)
    selected=dict(member_id='brace-a',workpoint_length_in=100.,yielding_length_in=53.,end_locations=[row,dict(row,connection_id='a:1',end_index=1)])
    spec=dict(yielding_length_workpoint_ratio=.53,reported_elongation_in=3.61,terminal=dict(physical_occurrences=[selected]))
    return m,row,spec


@pytest.mark.parametrize('alter',['none','foreign','wrong_end','missing_end','workpoint','bad_sum','travel'])
def test_checked_occurrence_requires_exact_frame_and_both_ends(alter):
    m,row,spec=case();entry=spec['terminal']['physical_occurrences'][0]
    if alter=='foreign':m['id']='different'
    elif alter=='wrong_end':row['connection_id']='other'
    elif alter=='missing_end':entry['end_locations'].pop()
    elif alter=='workpoint':m['axis'][1][0]=99.
    elif alter=='bad_sum':row['casing_face_station_in']+=.25
    elif alter=='travel':row['full_travel_in']=4.
    if alter=='none':
        assert head_fit(selected_end(spec,m,'a:0',0))==pytest.approx(dict(front_in=18.,thickness_in=1.,required_travel_in=3.61,casing_gap_in=3.6725))
    else:
        with pytest.raises(ValueError):selected_end(spec,m,'a:0',0)


@pytest.mark.parametrize('alter',['none','pin','head','casing','area','fused_face','missing_pin'])
def test_individual_setout_is_read_on_real_step(tmp_path,alter):
    m,row,spec=case();a=Assembly('terminal',{})
    for name,lo,hi,width in [('PIN',8.,12.,4.),('END-CAP',18.,19.,5.),('HEAD-CJP',19.,19.1875,2.4),('CORE-END',19.1875,22.6725,2.4),('BRACE',22.6725,80.,12.)]:
        if alter=='missing_pin' and name=='PIN':continue
        if {'PIN':'pin','END-CAP':'head','BRACE':'casing'}.get(name)==alter:lo+=.5;hi+=.5
        if alter=='area' and name=='CORE-END' or alter=='fused_face' and name=='HEAD-CJP':width-=.25
        a.polygon(name,[[lo,-width/2,-2.],[lo,width/2,-2.],[lo,width/2,2.],[lo,-width/2,2.]],hi-lo,normal=[1.,0.,0.])
    shapes=export_readback(tmp_path,{p['id']:as_mesh(p['faces']) for p in a.parts})
    values,errors=check_setout(shapes,[1.,0.,0.],row,spec)
    assert bool(errors)==(alter!='none'),(errors,values)
