import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.guid
import ifcopenshell.util.unit
import numpy as np
import pytest

from steltic_openbim.ifc_assembly_verification import Readback
from steltic_openbim.ifc_plate_crossing import delivered_plate_crossing,plate_interfaces


def crossing_file(tmp_path,change,with_assembly=False):
    f=ifcopenshell.file(schema='IFC4')
    ifcopenshell.api.root.create_entity(f,ifc_class='IfcProject')
    ifcopenshell.api.unit.assign_unit(f)
    ctx=ifcopenshell.api.context.add_context(f,context_type='Model')
    body=ifcopenshell.api.context.add_context(f,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=ctx)
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    def add(name,start,stop):
        x,y,z=start
        xx,yy,zz=stop
        vertices=[(u*.0254,v*.0254,w*.0254) for w in (z,zz) for u,v in ((x,y),(xx,y),(xx,yy),(x,yy))]
        cls='IfcMember' if name!='plate' else ('IfcElementAssembly' if with_assembly else 'IfcPlate')
        o=ifcopenshell.api.root.create_entity(f,ifc_class=cls,name=name)
        geom=ifcopenshell.api.geometry.add_mesh_representation(f,context=body,vertices=[vertices],faces=[faces])
        ifcopenshell.api.geometry.assign_representation(f,product=o,representation=geom)
        ifcopenshell.api.geometry.edit_object_placement(f,product=o)
        pset=ifcopenshell.api.pset.add_pset(f,product=o,name='Steltic_Coordination')
        ifcopenshell.api.pset.edit_pset(f,pset=pset,properties={'SourceId':name})
        return o
    add('a',(-8.,-.75,-.5),(8.,.75,0.))
    z=.85 if change=='gap' else .65 if change=='penetrating' else .75
    add('b',(-1.,-8.,z),(1.,8.,z+.5))
    mx=1.6 if change=='shortplate' else 3.
    offset=.4 if change=='moved_plate' else 0.
    plate=add('plate',(-mx+offset,-3.,0.),(mx+offset,3.,.75))
    welds=[dict(member='a',points_in=[[-2,y,0],[2,y,0]],size_in=.25) for y in [-.75,.75]]
    welds.extend(dict(member='b',points_in=[[x,-2,.75],[x,2,.75]],size_in=.25) for x in (-1.,1.))
    if change=='moved_weld':
        welds[0]['points_in']=[[-1.9,-.75,0],[2.1,-.75,0]]
    if with_assembly:
        native_context=ifcopenshell.api.context.add_context(f,context_type='Model',context_identifier='Reference',
            target_view='MODEL_VIEW',parent=ctx)
        ref=ifcopenshell.api.root.create_entity(f,ifc_class='IfcAnnotation',name='plate:references')
        units=.0254/ifcopenshell.util.unit.calculate_unit_scale(f)
        polylines=[]
        for path in welds[:3] if change=='missing_reference' else welds:
            points=[f.createIfcCartesianPoint([float(c*units) for c in p]) for p in path['points_in']]
            polylines.append(f.createIfcPolyline(points))
        representation=f.create_entity('IfcShapeRepresentation',ContextOfItems=native_context,
            RepresentationIdentifier='Reference',RepresentationType='GeometricCurveSet',
            Items=[f.createIfcGeometricCurveSet(polylines)])
        ifcopenshell.api.geometry.assign_representation(f,product=ref,representation=representation)
        ifcopenshell.api.geometry.edit_object_placement(f,product=ref)
        names={'CROSSING-PLATE':'A36' if change=='wrong_plate_grade' else 'ASTM A572 Gr 50'}
        names.update({f'W{i}':'E60XX' if change=='wrong_weld_grade' and i==2 else 'E7018' for i in range(4)})
        constituents=[f.create_entity('IfcMaterialConstituent',Name=key,Material=f.createIfcMaterial(value))
                      for key,value in names.items()]
        material_set=f.create_entity('IfcMaterialConstituentSet',Name='T',MaterialConstituents=constituents)
        f.create_entity('IfcRelAssociatesMaterial',GlobalId=ifcopenshell.guid.new(),RelatedObjects=[plate],RelatingMaterial=material_set)
    path=tmp_path/'delivered.ifc'
    f.write(str(path))
    rb=Readback(path)
    return rb,welds


@pytest.mark.parametrize('change',['none','gap','penetrating','thickness','sameface','doubleedge','too_long','shortplate','wrongmember','missing'])
def test_measured_placed_plate_and_two_longitudinal_fillets_per_bar(tmp_path,change):
    rb,_=crossing_file(tmp_path,change)
    shapes={}
    for obj in rb.file.by_type('IfcElement'):
        _,mesh,matrix=rb.mesh(obj)
        shapes[obj.Name]=mesh.transformed(matrix)
    axes={'a':[[-8,0,0],[8,0,0]],'b':[[0,-8,0],[0,8,0]]}
    welds=[dict(member='a',points_in=[[-2,y,0],[2,y,0]],size_in=.25) for y in [-.75,.75]]
    welds.extend(dict(member='b',points_in=[[x,-2,.75],[x,2,.75]],size_in=.25) for x in (-1.,1.))
    if change=='sameface':welds[-1]['points_in']=[[1.,-2,0],[1.,2,0]]
    if change=='doubleedge':welds[-1]['points_in']=welds[-2]['points_in']
    if change=='too_long':welds[0]['points_in'][0][0]=-2.25
    if change=='wrongmember':welds[-1]['member']='a'
    if change=='missing':welds.pop()
    selected=dict(plate_thickness_in=.625 if change=='thickness' else .75,per_bar_count=2,size_in=.25,length_in=4.)
    facts,errors=plate_interfaces([0,0,0],axes,{k:shapes[k] for k in axes},shapes['plate'],welds,selected)
    assert bool(errors)==(change!='none'),errors
    if change=='none':
        assert facts['plate_thickness_in']==pytest.approx(.75)
        assert facts['interfaces']['a']['contact_area_in2']==pytest.approx(9.)


@pytest.mark.parametrize('change',['none','flipped','bad_normal','moved_plate','moved_weld','wrong_plate_grade',
                                  'wrong_weld_grade','missing_reference','wrong_size','unrelated_binding'])
def test_selected_crossing_from_delivered_member_solids_and_annotation(tmp_path,change):
    rb,welds=crossing_file(tmp_path,change,with_assembly=True)
    plate=dict(length_in=6.,width_in=6.,thickness_in=.75,material='ASTM A572 Grade 50')
    fillet=dict(count_per_bar=2,size_in=.25,length_in=4.,material='E70XX',run='longitudinal')
    rec={'fields':[dict(role=role,field=k,value=v) for role,values in
                   [('flat_bar_crossing_plate',plate),('flat_bar_crossing_fillet',fillet)] for k,v in values.items()]}
    face_sign=1 if change=='flipped' else -1
    source=dict(id='X',kind='flat_bar_crossing_plate',member_ids=['a','b'],record_id='design',selected=list(range(9)),
                plate=dict(plate,record_id='design',normal=[0.,1.,0.] if change=='bad_normal' else [0.,0.,1.]),
                welds=fillet,point_in=[0.,0.,.375],member_faces=[dict(member_id='a',face_sign=face_sign),dict(member_id='b',face_sign=-face_sign)])
    members={'a':dict(axis=[[-8,0,0],[8,0,0]]),'b':dict(axis=[[0,-8,0],[0,8,0]])}
    parts={'CROSSING-PLATE':dict(id='CROSSING-PLATE',kind='plate')}
    for i,weld in enumerate(welds):
        key=f'W{i}'
        contacts=['CROSSING-PLATE',weld['member'].upper()]
        if change=='unrelated_binding' and i==0:contacts.append('other')
        parts[key]=dict(id=key,kind='weld',connects=contacts,geometry=dict(points=weld['points_in']),
                        parameters=dict(size_in=.125 if change=='wrong_size' and i==0 else .25))
    _,mesh,placement=rb.mesh(rb.assemblies['plate'])
    facts,errors=delivered_plate_crossing(rb,source,rec,'T',parts,({'bindings':{'A':'a','B':'b'}},np.eye(4)),
            rb.curves('plate'),{'CROSSING-PLATE':mesh.transformed(placement)},members,'plate')
    assert bool(errors)==(change!='none'),errors
    if change=='none':
        assert facts['checked_welds']==4 and len(facts['interfaces'])==2
        assert facts['interfaces']['a']['face_sign']==-1


@pytest.mark.parametrize('rotation_deg',[0.,15.])
def test_square_plate_keeps_selected_building_horizontal_and_vertical(tmp_path,rotation_deg):
    rb,welds=crossing_file(tmp_path,'none')
    upright=np.eye(4)
    upright[:3,:3]=[[1.,0,0],[0,0,-1.],[0,1.,0]]
    angle=np.deg2rad(rotation_deg)
    inplane=np.eye(4)
    inplane[:2,:2]=[[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]]
    _,plate,placement=rb.mesh(rb.file.by_type('IfcPlate')[0])
    shapes={k:rb.member(k).transformed(upright) for k in ('a','b')}
    for w in welds:
        w['points_in']=np.asarray(w['points_in'])@upright[:3,:3].T
    selected=dict(plate_thickness_in=.75,plate_length_in=6.,plate_width_in=6.,rectangular=True,
                  horizontal_vertical=True,per_bar_count=2,size_in=.25,length_in=4.)
    _,errors=plate_interfaces([0,-.375,0],{'a':[[-8,0,0],[8,0,0]],'b':[[0,0,-8],[0,0,8]]},shapes,
                             plate.transformed(upright@inplane@placement),welds,selected)
    assert bool(errors)==bool(rotation_deg),errors
