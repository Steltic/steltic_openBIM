"""Controls for actual finite parts, holes, slots and screw/ply engagement."""
import math

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

from steltic_openbim.ifc_assembly_verification import Assessment, Readback, grip_engages, same_face, selected, verify_assembly_fit
from steltic_openbim.joint_mesh_readback import Mesh, common_plate_section, cross_section, shared_face_area


def cylinder(radius, low, high, hole=None, x=0.):
    ring = np.array([(math.cos(a), math.sin(a)) for a in np.linspace(0.,2*math.pi,24,endpoint=False)])
    def level(rad,z):
        xy = ring*rad + [x,0.]
        return np.column_stack((xy,np.full(len(ring),z)))
    n=len(ring)
    verts=[level(radius,low),level(radius,high)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.append((i,j,n+j,n+i))
    if hole is None:
        faces.extend([tuple(reversed(range(n))),tuple(range(n,2*n))])
    else:
        verts.extend((level(hole,low),level(hole,high)))
        for i in range(n):
            j=(i+1)%n
            faces.extend([(2*n+i,3*n+i,3*n+j,2*n+j),(i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)])
    return Mesh(np.vstack(verts),tuple(faces))


def export_readback(tmp_path, meshes, references=None, reader=False):
    """Write a real IFC file, reopen it, and return only its decoded face sets."""
    api=ifcopenshell.api.run
    model=ifcopenshell.file(schema='IFC4')
    api('root.create_entity',model,ifc_class='IfcProject',name='Readback control')
    unit=api('unit.add_si_unit',model,unit_type='LENGTHUNIT')
    api('unit.assign_unit',model,units=[unit])
    context=api('context.add_context',model,context_type='Model')
    body=api('context.add_context',model,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=context)
    for name, mesh in meshes.items():
        p=api('root.create_entity',model,ifc_class='IfcMember',name=name)
        shape=api('geometry.add_mesh_representation',model,context=body,vertices=[(mesh.vertices*.0254).tolist()],faces=[[list(f) for f in mesh.faces]])
        api('geometry.assign_representation',model,product=p,representation=shape)
    for name,lines in (references or {}).items():
        annotation=api('root.create_entity',model,ifc_class='IfcAnnotation',name=name+':references')
        curves=[]
        for line in ([lines] if np.asarray(lines).ndim==2 else lines):
            points=[model.create_entity('IfcCartesianPoint',Coordinates=tuple(float(x)*.0254 for x in p)) for p in line]
            curves.append(model.create_entity('IfcPolyline',Points=points))
        group=model.create_entity('IfcGeometricCurveSet',Elements=curves)
        rep=model.create_entity('IfcShapeRepresentation',ContextOfItems=body,RepresentationIdentifier='Reference',RepresentationType='GeometricCurveSet',Items=[group])
        api('geometry.assign_representation',model,product=annotation,representation=rep)
    name=tmp_path/'control.ifc'
    model.write(str(name))
    rb=Readback(name)
    if reader:
        rb.members={p.Name:p for p in rb.file.by_type('IfcMember')}
        return rb
    decoded={}
    for obj in rb.file.by_type('IfcMember'):
        _,mesh,placement=rb.mesh(obj)
        decoded[obj.Name]=mesh.transformed(placement)
    return decoded


@pytest.mark.parametrize('condition,required',[
    ('drilled',set()),
    ('filled',{'fastener_crosses_uncut_bearing_ply'}),
    ('outside',{'actual_fastener_footprint_leaves_ply'}),
    ('short',{'fastener_shaft_misses_ply'}),
    ('wrong_actual_diameter',{'actual_shaft_diameter_differs'}),
    ('wrong_bore',{'actual_bore_diameter_or_center_differs'}),
])
def test_actual_ifc_pin_through_selected_ply(tmp_path,condition,required):
    x=2.2 if condition=='outside' else 0.
    shaft_radius=.35 if condition=='wrong_actual_diameter' else .5
    parts={'GUSSET':dict(id='GUSSET',kind='plate',parameters={}),
           'PIN':dict(id='PIN',kind='pin',connects=['GUSSET'],parameters=dict(point=[x,0.,-2.],axis=[0.,0.,1.],diameter=1.,grip=1. if condition=='short' else 4.))}
    meshes=export_readback(tmp_path,{'GUSSET':cylinder(2.,-.5,.5,None if condition=='filled' else .65), 'PIN':cylinder(shaft_radius,-2.,2.,x=x)})
    check=Assessment(None,dict(members=[],profiles=[]),{})
    fields={('pin_hole','diameter_in'):[1.5 if condition=='wrong_bore' else 1.3]}
    check.fastener_checks(parts,meshes,fields, {'GUSSET'})
    codes={f['code'] for f in check.findings}
    assert required <= codes
    if not required:
        assert codes == set()
        assert check.counts['actual_bore_checks']==1


def cuboid(start,end):
    x0,y0,z0=start; x1,y1,z1=end
    return Mesh(np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]],float),
                ((3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)))


def join(a,b):
    offset=len(a.vertices)
    return Mesh(np.vstack((a.vertices,b.vertices)),a.faces+tuple(tuple(k+offset for k in f) for f in b.faces))


@pytest.mark.parametrize('filled,expected',[(False,False),(True,True)])
def test_actual_ifc_slot_requires_material_removed(tmp_path,filled,expected):
    a=cuboid([0.,-1.,-1.],[10.,-.25,1.]);b=cuboid([0.,.25,-1.],[10.,1.,1.])
    mesh=cuboid([0.,-1.,-1.],[10.,1.,1.]) if filled else join(a,b)
    decoded=export_readback(tmp_path,{'B':mesh})
    class Product:
        def member(self,mid):return decoded[mid]
    source=dict(id='B',kind='brace',axis=[[0,0,0],[10,0,0]],local_y=[0,1,0],slots=[dict(start_in=0.,end_in=3.,centre_in=0.,width_in=.5,section_axis=0)])
    check=Assessment(Product(),dict(members=[source],profiles=[]),{})
    check.member_checks('B')
    assert bool(check.findings)==expected
    assert check.counts['actual_slots']==1


def test_screw_requires_positive_engagement_inside_grip():
    assert grip_engages([-.05,0.,.125,.185],.185)
    assert not grip_engages([-.05,0.,.25,.31],.185)
    assert not grip_engages([0.,.01,.125],.185)


@pytest.mark.parametrize('top,overlaps',[(0.,False),(.2,True)])
def test_actual_gusset_contact_vs_receiver_penetration(tmp_path,top,overlaps):
    actual=export_readback(tmp_path,{'GUSSET':cuboid([-2,-2,0],[2,2,.4]),'STEEL':cuboid([-3,-3,-1],[3,3,top])})
    proof=common_plate_section(actual['GUSSET'],actual['STEEL'])
    assert bool(proof)==overlaps
    if overlaps:
        assert proof['common_material_area_in2']==pytest.approx(16.)
        assert proof['closed_plate'] and proof['closed_member']


@pytest.mark.parametrize('face,gap',[(1.,False),(1.1,True)])
def test_actual_supplier_core_interface_requires_finite_face_contact(tmp_path,face,gap):
    parts=export_readback(tmp_path,{'CORE':cuboid([0,0,0],[1,2,.5]),'CASING':cuboid([face,0,0],[3,2,.5])})
    area=shared_face_area(parts['CORE'],parts['CASING'])
    assert area==pytest.approx(0. if gap else 1.)


def test_closed_material_section_retains_bore_and_detects_corrupt_ring():
    ring=cylinder(2.,-.25,.25,.6)
    shape,*_=cross_section(ring,[0,0,1])
    assert ring.closed and len(shape.interiors)==1
    assert not Mesh(ring.vertices,ring.faces[1:]).closed
    face=ring.polygons[0]
    assert same_face(face,np.roll(face[::-1],1,axis=0))
    assert not same_face(face,face[[0,2,1,3]])


@pytest.mark.parametrize('offset,expected',[(0.,False),(2.,True)])
def test_actual_weld_curve_reaches_both_named_parts(tmp_path,offset,expected):
    line=[[2.,0.,.5+offset],[8.,0.,.5+offset]]
    rb=export_readback(tmp_path,{'B':cuboid([0,0,0],[10,1,1]),'G':cuboid([0,-.5,0],[10,0,1])},{'CON':line},reader=True)
    member=dict(id='B',kind='brace',axis=[[0,0,0],[10,0,0]],local_y=[0,1,0])
    check=Assessment(rb,dict(members=[member],profiles=[]),{})
    check.context={'template':'test'}
    parts={'GUSSET':dict(id='GUSSET',kind='plate',connects=[]), 'WB1':dict(id='WB1',kind='weld',connects=['BRACE','GUSSET'],geometry=dict(type='polyline',points=line),parameters=dict(size_in=.25))}
    check.paths('CON',parts,{'GUSSET':rb.member('G')},{'bindings':{'BRACE':'B'}},np.eye(4),rb.curves('CON'),{'BRACE':'B'},{'GUSSET'},{('brace_slot_weld','length_in'):[6.]})
    codes={f['code'] for f in check.findings}
    assert ('weld_reference_outside_attachment_reach' in codes)==expected
    assert check.counts['actual_weld_attachment_checks']==2


def test_selected_slots_and_flat_bar_fillets_apply_to_their_own_members():
    fields=[dict(role='slot',field='clearance_in',value=.125,applicability={'attachment':'slotted_hss'}),
            dict(role='flat_bar_end_fillet',field='size_in',value=.5,applicability={'attachment':'flat_bar_end','section_in':[1.75,.75]})]
    handoff={'records':{'R':{'fields':fields}},'occurrences':{'C':{'applications':[{'record_id':'R','selected':[0,1],'hss_members':{'H':'selected'}}]}}}
    hss=selected(handoff,'C','H',{'family':'rectangular_hollow','dimensions':{}})
    flat=selected(handoff,'C','F',{'family':'flat','dimensions':{'width':1.75,'thickness':.75}})
    other=selected(handoff,'C','SMALL',{'family':'flat','dimensions':{'width':1.25,'thickness':.625}})
    assert set(hss)=={('slot','clearance_in')}
    assert set(flat)=={('flat_bar_end_fillet','size_in')}
    assert not other


@pytest.mark.parametrize('wrong',[False,True])
def test_source_crossing_checks_four_actual_ifc_weld_lengths(tmp_path,wrong):
    lines=[[[0.,float(i),0.],[2. if not wrong or i else 1.5,float(i),0.]] for i in range(4)]
    rb=export_readback(tmp_path,{'A':cuboid([0,0,0],[3,4,.5])},{'X':lines},reader=True)
    material=dict(role='flat_bar_crossing_fillet')
    fields=[dict(material,field=k,value=v) for k,v in [('count',4),('size_in',.25),('length_in',2.)]]
    src=dict(id='X',record_id='R',selected=[0,1,2],member_ids=['A','B'],point_in=[0,0,0]);handoff={'records':{'R':{'fields':fields}},'crossing_interfaces':[src]}
    parts={str(i):dict(id=str(i),kind='weld',connects=['A','B'],parameters={'size_in':.25},geometry={'type':'polyline','points':line}) for i,line in enumerate(lines)}
    check=Assessment(rb,dict(members=[],profiles=[]),handoff)
    check.crossing({'point':[0,0,0],'drawing_ref':'1/C001'},parts,{'origin':[0,0,0],'bindings':{'A':'A','B':'B'}},np.eye(4),rb.curves('X'),src,{})
    assert bool(check.findings)==wrong
    skipped=verify_assembly_fit(tmp_path/'control.ifc',dict(members=[],profiles=[],connections=[]),handoff)
    assert not skipped['passed'] and skipped['findings'][0]['code']=='required_crossing_occurrence_count'
