from copy import deepcopy

import pytest

from steltic_openbim.fabricated_i_section import cropped
from steltic_openbim.pilots.geometry import member_faces
from steltic_openbim.transfer_fabrication_readback import check_sections,w_shape
from test_brb_core_readback import as_mesh
from test_ifc_assembly_verification import export_readback


WIDE=dict(bf=17.7,d=21.6,tf=4.2,tw=2.5)
SMALL=dict(bf=17.2,d=20.24,tf=3.5,tw=2.1)


@pytest.mark.parametrize('change',['none','uncut','short','taper_wrong_way','cut_web','shift'])
def test_actual_taper_differs_from_unmachined_and_reversed_stock(tmp_path,change):
    rows=[dict(start_in=88.,end_in=100.,start_dimensions=WIDE,end_dimensions=SMALL)]
    source=deepcopy(rows)
    if change=='uncut':rows=[]
    if change=='short':rows[0]['start_in']=95.
    if change=='taper_wrong_way':rows[0].update(start_dimensions=SMALL,end_dimensions=WIDE)
    if change=='cut_web':rows[0]['end_dimensions']=dict(SMALL,tw=1.5)
    if change=='shift':rows[0].update(start_in=86.,end_in=98.)
    p=dict(id='W14',dimensions=WIDE,family='i')
    m=dict(id='post',profile_id=p['id'],axis=[[0.,0.,0.],[0.,0.,100.]],local_y=[1.,0.,0.],
           end_offsets=[[0.,0.,0.],[0.,0.,0.]],fabricated_i_sections=rows)
    real=export_readback(tmp_path,{'POST':as_mesh(member_faces(m,{'W14':p}))})['POST']
    issues=[]
    target=[(at,w_shape({k:WIDE[k]+(SMALL[k]-WIDE[k])*max(0.,(at-88.)/12.) for k in WIDE}))
            for at in (80.,88.2,94.,99.5)]
    check_sections(real,target,issues)
    assert bool(issues)==(change!='none')
    reverse=cropped(source,100.,80.)
    assert reverse[0]['start_dimensions']==pytest.approx(SMALL)
    assert reverse[0]['end_dimensions']==pytest.approx(WIDE)


@pytest.mark.parametrize('change',['none','missing','oversize','cut_full_length'])
def test_support_insert_has_the_selected_local_recess(tmp_path,change):
    narrow=dict(WIDE,bf=WIDE['bf']-3.1)
    dimension=dict(narrow,bf=narrow['bf']-.1) if change=='oversize' else narrow
    cuts=[] if change=='missing' else [dict(start_in=27. if change!='cut_full_length' else 0.,
         end_in=73. if change!='cut_full_length' else 100.,start_dimensions=dimension,end_dimensions=dimension)]
    p=dict(id='W',dimensions=WIDE,family='i')
    m=dict(id='column',profile_id='W',axis=[[0.,0.,0.],[0.,0.,100.]],local_y=[1.,0.,0.],
           end_offsets=[[0.,0.,0.],[0.,0.,0.]],fabricated_i_sections=cuts)
    real=export_readback(tmp_path,{'COL':as_mesh(member_faces(m,{'W':p}))})['COL']
    issues=[]
    check_sections(real,[(26.99,w_shape(WIDE)),(27.01,w_shape(narrow)),(50.,w_shape(narrow)),
                         (72.99,w_shape(narrow)),(73.01,w_shape(WIDE))],issues)
    assert bool(issues)==(change!='none')
