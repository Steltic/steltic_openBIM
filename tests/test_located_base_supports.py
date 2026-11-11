from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Polygon,box
from shapely.ops import unary_union

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.base_plate_extensions import add,share_supports
from steltic_openbim.brace_base_attachment import add_cap_plate,base_attachment
from steltic_openbim.review_base_selection import flange_rows


def test_integral_tongue_retains_stock_and_finite_source_width():
    a=Assembly('Sole',{})
    p=add(a,32,30,2,2.75,[dict(axis=0,sign=-1,width_in=12,length_in=14,
                                  source_record_id='base',brace_connection_id='brace-1')])
    measured=unary_union([Polygon([(q[0],q[1]) for q in face]) for face in p['faces']
                          if np.allclose(np.array(face)[:,2],2)])
    assert measured.equals(box(-16,-15,16,15).union(box(-30,-6,-16,6)))
    assert p['bounds'][2]==[2,4.75] and 'brace_connection_id' not in p['parameters']['integral_gusset_tongues'][0]
    row=flange_rows('rods in two rows, 4 per row, 6.60 in from the flange faces; rods 2 in from the plate edges',30)
    assert row==pytest.approx((1,4,0,6.6,26/3))


def test_selected_upper_cap_stock_and_weld_terminate_on_the_real_column_face():
    a=Assembly('Cap',{})
    stock=dict(width=16,length=39,grout=2,thickness=2,record_id='column-base',material='A572 Gr50')
    add_cap_plate(a,stock,8.25)
    assert a.parts[0]['bounds']==[[8.25,47.25],[-8,8],[2,4]]
    assert a.parts[1]['bounds'][2]==[0,2]
    assert a.welds[0]['connects']==['BASE','COLUMN']
    assert a.welds[0]['a']==[8.25,-8,3] and a.welds[0]['b']==[8.25,8,3]


def test_gusset_support_uses_distinct_horizontal_and_vertical_source_runs():
    text='base gusset 0.5 in A572 Gr 50 welded to the base plate (21.2 in) and the column flange (18.0 in); 3/8 in E70 fillets both sides'
    ctx=SimpleNamespace(package={'design_records':[{'id':'end','data':{'components':text}}]},c={'design_record_ids':['end']})
    spec=base_attachment(ctx,'W14X145')
    assert (spec['horizontal_length'],spec['column_length'],spec['horizontal_fillet'],spec['faces'])==(21.2,18,.375,2)


def test_secondary_draws_one_located_physical_sole():
    def conn(cid,tid,bindings,family):
        return dict(id=cid,joint_id='j',member_ids=list(bindings.values()),assembly_id=tid,
                    detail_ref={'legacy_family':family},parameters={'joint':'base'},
                    assembly_instance={'template_id':tid,'revision':'v','bindings':bindings,'origin':[0,0,0]})
    base=conn('base','tb',{'M1':'column'},'review_base')
    br=conn('brace','tg',{'COLUMN':'column','BRACE':'diagonal'},'review_brace')
    part={'id':'BASE','parameters':{'referenced_part_id':'P1'}}
    package={'physical':{'connections':[base,br],'assemblies':[{'id':'tb','revision':'v','parts':[{'id':'P1'}]},
             {'id':'tg','revision':'v','parts':[part,{'id':'GUSSET'}]}]}}
    scene={'id':'tg','parts':[dict(part)],'welds':[],'interfaces':[]}
    share_supports(package,{'connection_assemblies':[scene]})
    assert [p['id'] for t in package['physical']['assemblies'] for p in t['parts']]==['P1','GUSSET']
    assert scene['parts'][0]['representation_role']=='context_only'
    assert br['parameters']['shared_constituents'][0]['owner_connection_id']=='base'


@pytest.mark.parametrize('offset,fails',[(0,True),(2,False),(6,False)])
def test_washer_on_a_different_occurrence_cannot_occupy_gusset_steel(tmp_path,offset,fails):
    from test_ifc_assembly_verification import cylinder,cuboid,export_readback
    from steltic_openbim.ifc_shared_gusset_readback import PlacedGusset
    from steltic_openbim.base_hardware_clearance import check
    washer=cylinder(1.75,0,.5,hole=.55)
    panel=cuboid([-2,offset-.25,0],[2,offset+.25,5])
    reader=export_readback(tmp_path,{'sole hardware':washer,'brace part':panel},reader=True)
    reader.assemblies={'base':reader.members['sole hardware']}
    reader.ranges={'plate':[dict(id='WASHER-TOP-1',face_start=0,face_count=len(washer.faces))]}
    _,mesh,matrix=reader.mesh(reader.members['brace part'])
    checker=SimpleNamespace(rb=reader,owned_gussets=[PlacedGusset('brace','C5','GUSSET',mesh,matrix)],
               templates={'plate':{'parts':[dict(id='WASHER-TOP-1',kind='plate')]}},
               members={'column':{'kind':'column'}},
               connections={'brace':dict(id='brace',point=[0,0,0],member_ids=['column'],parameters={'joint':'base'}),
                            'base':dict(id='base',point=[0,0,0],member_ids=['column'],assembly_instance={'template_id':'plate'})})
    count,issues=check(checker)
    assert count==1 and bool(issues)==fails
    if fails:assert issues[0]['code']=='base_hardware_intersects_gusset' and issues[0]['common_material_area_in2']>0
