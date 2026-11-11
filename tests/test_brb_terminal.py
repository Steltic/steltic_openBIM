from copy import deepcopy
import numpy as np
import pytest
from shapely.geometry import box

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.brb_infill_fit import fit_pockets
from steltic_openbim.brb_supplier_core import rectangular_ring
from steltic_openbim.brb_terminal import shaped_sections
from steltic_openbim.brb_terminal_readback import check_cjp,check_transitions
from steltic_openbim.brb_core_readback import core_sections
from steltic_openbim.native_brb import weld_consumable
from steltic_openbim.pilots.geometry import member_faces
from test_brb_core_readback import as_mesh
from test_ifc_assembly_verification import export_readback


def selected():
    return dict(area_in2=4.,material='ASTM A36',yielding_length_in=50.,depth_in=4.,thickness_in=1.,
                terminal=dict(end_area_ratio=2.4,minimum_transition_length_in=12.,head_joint_electrode='E70',head_material='ASTM A572 Grade 50'))


@pytest.mark.parametrize('mutation',['none','short_transition','undersized_terminal','abridged_gauge','no_transition','unavailable_length'])
def test_machined_core_is_measured_from_reopened_step(tmp_path,mutation):
    spec=selected();used=deepcopy(spec);length=90.
    if mutation=='unavailable_length':
        with pytest.raises(ValueError,match='cannot contain'):shaped_sections(spec,73.)
        return
    if mutation=='short_transition':used['terminal']['minimum_transition_length_in']=9.
    if mutation=='undersized_terminal':used['terminal']['end_area_ratio']=2.
    if mutation=='abridged_gauge':used['yielding_length_in']=47.
    sections=shaped_sections(used,length)
    if mutation=='no_transition':sections=[[0.,rectangular_ring(1.,4.)],[length,rectangular_ring(1.,4.)]]
    profile=dict(id='casing',family='rhs',dimensions=dict(h=10.,b=10.,t=.5))
    member=dict(id='brace',kind='brace',profile_id='casing',axis=[[0.,0.,0.],[length,0.,0.]],local_y=[0.,1.,0.],end_offsets=[[0.]*3,[0.]*3],section_plies=[dict(id='YIELDING-CORE',sections=sections)])
    solids=export_readback(tmp_path,{'BRACE':as_mesh(member_faces(member,{'casing':profile}))})
    info,issues=core_sections(solids['BRACE'],4.,50.);facts,errors=check_transitions(info,spec)
    assert bool(issues or errors)==(mutation!='none'),(issues,errors)
    if mutation=='none':assert [r['measured_transition_in'] for r in facts['machined_end_transitions']]==pytest.approx([12.,12.])


@pytest.mark.parametrize('mutation',['none','partial_face','missing_weld','wrong_electrode','wrong_core','wrong_head','gap','zero_penetration'])
def test_reopened_finite_weld_covers_full_selected_core_face(tmp_path,mutation):
    spec=selected();a=Assembly('Full head splice',{});parts={};names={'END-CAP':'ASTM A572 Grade 50','CORE-END':'ASTM A36','HEAD-CJP':'E70XX'}
    if mutation=='wrong_electrode':names['HEAD-CJP']='E60XX'
    if mutation=='wrong_core':names['CORE-END']='ASTM A572 Grade 50'
    if mutation=='wrong_head':names['END-CAP']='ASTM A36'
    for k,x,far,width in [('END-CAP',0.,1.,7.),('HEAD-CJP',1.,1.1875,1. if mutation=='partial_face' else 2.4),('CORE-END',1.1875,4.,2.4)]:
        if k=='HEAD-CJP' and mutation=='missing_weld':continue
        if k=='CORE-END' and mutation=='gap':x+=.02
        if k=='HEAD-CJP' and mutation=='zero_penetration':far=x+.00001
        a.polygon(k,[[x,-width/2,-2.],[x,width/2,-2.],[x,width/2,2.],[x,-width/2,2.]],far-x,normal=[1.,0.,0.]);parts[k]=dict(kind='weld' if k=='HEAD-CJP' else 'plate',parameters={'weld_type':'CJP'})
    meshes=export_readback(tmp_path,{p['id']:as_mesh(p['faces']) for p in a.parts});facts,issues=check_cjp(meshes,parts,names,[1.,0.,0.],spec)
    assert bool(issues)==(mutation!='none'),(issues,facts)
    if mutation=='none':assert facts['measured_fused_core_contact_in2']==pytest.approx(9.6)


def test_mortar_cut_follows_named_end_preserving_the_opposite_relief_and_stock():
    m=dict(axis=[[0.,0.,0.],[60.,0.,0.]],local_y=[0.,1.,0.]);bands={'upper':[[-3.,1.],[3.,1.],[3.,3.],[-3.,3.]]}
    fixed=[('PL1',-1.,1.,box(8.,2.,10.5,3.))];fit_pockets(m,'first',m['axis'][0],fixed,11.,2.,bands)
    row=m['brb_infill_pockets'][0];assert row['depth_in']==pytest.approx(1.5625);assert row['obstruction_ids']==['first/PL1'];assert row['end_index']==0
    fit_pockets(m,'second',m['axis'][1],[],11.,2.,bands);assert m['brb_infill_pockets']==[row]
    fit_pockets(m,'first',m['axis'][0],[],11.,2.,bands);assert m['brb_infill_pockets']==[]


def test_specific_and_global_electrode_survive_adding_materials_for_other_parts():
    catalog={'global':dict(source_schedule={'item':'Welds'},source_item='Welds',specification='E70XX project schedule'),
             'fuse':dict(source_item='weld',specification='E80 custom groove electrode')}
    weld={'attachment_role':'cheek_perimeter_fillet'}
    assert weld_consumable(weld,{},catalog)=='E70XX project schedule'
    assert weld_consumable(weld,{('cheek_perimeter_fillet','material'):'E70-specific'},catalog)=='E70-specific'
    assert weld_consumable(dict(weld,selected_material='E70XX row'),{},catalog)=='E70XX row'
