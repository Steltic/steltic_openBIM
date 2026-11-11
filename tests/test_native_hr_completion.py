import copy
import json
from pathlib import Path

from steltic_openbim.drawing_workflow import DrawingStore, fingerprint
from steltic_openbim.ifc_delivery_readback import verify_ifc
from steltic_openbim.ifc_export import export_drawing
from steltic_openbim.native_hr_completion import complete_native_hr
from steltic_openbim.pdf_verification import verify_dimensions
from steltic_openbim.drawing_workflow import initial_state, write_json


def ordinary_job():
    p=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    physical=p['physical'];beam=physical['members'][0]
    physical['profiles'].append(dict(id='HSS-TEST',family='rhs',dimensions={'b':4.,'h':4.,'t':.25},status='declared'))
    physical['members'].append(dict(copy.deepcopy(beam),id='B',kind='brace',profile_id='HSS-TEST',
                                    axis=[[0.,0.,0.],[60.,0.,60.]],local_y=[0.,1.,0.]))
    physical['joints'][0]['member_ends'].append(dict(member_id='B',end='start'))
    physical['joints'].append(dict(id='free-brace',point=[60.,0.,60.],member_ends=[dict(member_id='B',end='end')],status='declared'))
    physical['joint_dispositions'].append(dict(joint_id='free-brace',kind='free_end',reason='Synthetic test end'))
    c=physical['connections'][0];c.update(parts=[],point=[0.,0.,0.],member_ids=['B','beam'])
    items=[('gusset','thickness_in',.5),('gusset','material','A572 Gr 50'),('brace_slot_weld','count',4),
           ('brace_slot_weld','size_in',.25),('brace_slot_weld','length_in',4.),('slot','clearance_in',.125),
           ('gusset_beam_weld','length_in',8.),('gusset_beam_weld','size_in',.25)]
    fields=[dict(role=r,field=k,value=v,source={'pointer':'/connections/0/components'}) for r,k,v in items]
    h=dict(schema='steltic.hr_source_handoff',version=1,building_id=p['building_id'],source_files={},
           source_bindings={'native_content_sha256':fingerprint(p)},material_schedule={},source_conflicts=[],
           records={'connections/c1':{'fields':fields}},occurrences={c['id']:{'applications':[
               dict(record_id='connections/c1',selected=list(range(len(fields))))]}})
    h['contract_sha256']=fingerprint(h);p['source_handoff']=h
    return p


def test_unregistered_import_authors_gusset_trim_and_slot_and_emits_real_documents(tmp_path):
    original=ordinary_job();source_digest=fingerprint(original)
    store=DrawingStore(tmp_path/'jobs');state=store.import_package('NewHRBuilding',original)
    directory,_=store.current('NewHRBuilding');derived=json.loads((directory/'source.json').read_bytes())
    assert fingerprint(original)==source_digest==state['original_hr_sha256']
    assert json.loads((directory/'hr_original_source.json').read_bytes())==original
    assert derived['design_records']==original['design_records']
    brace=next(m for m in derived['physical']['members'] if m['id']=='B')
    assert brace['axis']==original['physical']['members'][1]['axis']
    assert brace['end_offsets'][0][2]>4 and brace['slots'][0]['width_in']==.625
    c=derived['physical']['connections'][0];t=derived['physical']['assemblies'][0]
    assert c['assembly_instance']['bindings']=={'BRACE':'B','BEAM':'beam'}
    assert t['id']==c['assembly_instance']['template_id']
    assert [p['id'] for p in t['parts'] if p['kind']=='plate']==['GUSSET']
    assert len([p for p in t['parts'] if p['kind']=='weld'])==5
    out=tmp_path/'model.ifc';export_drawing(directory,out)
    assert verify_dimensions(directory,ifc_path=out)['passed']
    readback=verify_ifc(out,derived,fingerprint(derived))
    assert readback['passed'],readback
    # A supplied gusset is authoritative for regeneration, including a
    # deliberately different contour. Its fidelity is checked on delivery.
    assert complete_native_hr(derived) is derived
    again=store.import_package('NewHRBuilding',original,revision=state['revision'])
    assert again['revision']==state['revision']


def test_full_height_box_plate_and_taper_remain_in_actual_ifc(tmp_path):
    from ifcopenshell import open as open_ifc
    source=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    physical=source['physical'];member=physical['members'][0]
    material=dict(physical['materials'][0],id='sideplate',specification='ASTM A572 Grade 50')
    physical['materials'].append(material)
    def ring(t):return [[2-t,-3.5],[2.,-3.5],[2.,3.5],[2-t,3.5]]
    member['section_plies']=[dict(id='SIDE',material_id='sideplate',sections=[
        [0.,ring(.25)],[50.,ring(.25)],[51.,ring(.5)],[120.,ring(.5)]])]
    state=initial_state(source,1)
    write_json(tmp_path/'state.json',state);write_json(tmp_path/'source.json',source)
    path=tmp_path/'model.ifc';export_drawing(tmp_path,path)
    result=verify_ifc(path,source,fingerprint(source))
    assert result['passed'],result
    file=open_ifc(str(path));beam=file.by_type('IfcBeam')[0]
    assigned=next(r.RelatingMaterial for r in beam.HasAssociations if r.is_a('IfcRelAssociatesMaterial'))
    assert {p.Name:p.Description for p in assigned.MaterialConstituents}=={'MAIN':member['material_id'],'SIDE':'sideplate'}
    member['section_plies'][0]['sections'][-1][1]=ring(.25)
    assert not verify_ifc(path,source,state['source_model_sha256'])['passed']


def test_fresh_brb_corner_uses_new_brace_column_and_beam_bindings(tmp_path):
    source=ordinary_job();ph=source['physical'];beam,brace=ph['members'];c=ph['connections'][0]
    brace['axis'][1]=[180.,0.,120.]
    ph['joints'][-1]['point']=brace['axis'][1]
    beam['end_offsets']=[[0.,0.,-4.],[0.,0.,-4.]]
    col=dict(copy.deepcopy(beam),id='col',kind='column',axis=[[0.,0.,0.],[0.,0.,140.]],
             local_y=[0.,1.,0.],end_offsets=[[0.,0.,0.],[0.,0.,0.]])
    ph['members'].append(col);c['member_ids'].append('col')
    ph['joints'][0]['member_ends'].append(dict(member_id='col',end='start'))
    ph['joints'].append(dict(id='roof-column',point=col['axis'][1],member_ends=[dict(member_id='col',end='end')],status='declared'))
    ph['joint_dispositions'].append(dict(joint_id='roof-column',kind='free_end',reason='Test top'))
    r=source['source_handoff']['records']['connections/c1']
    data=[('connection','variant','brb_pinned'),('gusset','thickness_in',.875),('gusset','material','A572 Gr 50'),
          ('pin','diameter_in',2.5),('pin','material','AISI 4140 Q&T'),('pin_hole','diameter_in',2.5625),
          ('cheek_plate','thickness_in',.75),('gusset','width_at_hole_in',10.),
          ('gusset_column_weld','length_in',12.),('gusset_column_weld','size_in',.5),
          ('gusset_beam_weld','length_in',15.),('gusset_beam_weld','size_in',.375)]
    r['fields']=[dict(role=k,field=f,value=v,source={'pointer':'/connections/0/components'}) for k,f,v in data]
    h=source.pop('source_handoff');h.pop('contract_sha256');h['source_bindings']['native_content_sha256']=fingerprint(source)
    h['occurrences'][c['id']]['applications'][0]['selected']=list(range(len(data)))
    h['contract_sha256']=fingerprint(h);source['source_handoff']=h
    result=complete_native_hr(source)
    assert not result['provenance'].get('openbim_translation_findings')
    made=result['physical']['connections'][0];t=result['physical']['assemblies'][0]
    assert made['assembly_instance']['bindings']=={'COLUMN':'col','BEAM':'beam','BRACE':'B'}
    assert made['drawing_ref']==made['detail_ref']['source_drawing']=='1/C001'
    assert result['physical']['members'][1]['end_offsets'][0][0]>0
    assert next(p for p in t['parts'] if p['kind']=='pin')['parameters']['diameter']==2.5
    assert {p['id'] for p in t['parts'] if p.get('parameters',{}).get('holes')}=={'GUSSET','CHEEK0','CHEEK1','CLEVIS0','CLEVIS1'}


def test_ordinary_slotted_corner_authors_one_contour_for_both_real_receivers(tmp_path):
    source=ordinary_job();ph=source['physical'];beam,brace=ph['members'];c=ph['connections'][0]
    beam['end_offsets']=[[0.,0.,-4.],[0.,0.,-4.]]
    col=dict(copy.deepcopy(beam),id='col',kind='column',axis=[[0,0,0],[0,0,90]],
             local_y=[0.,1.,0.],end_offsets=[[0,0,0],[0,0,0]])
    ph['members'].append(col);c['member_ids'].append('col')
    ph['joints'][0]['member_ends'].append(dict(member_id='col',end='start'))
    ph['joints'].append(dict(id='ctop',point=[0,0,90],member_ends=[dict(member_id='col',end='end')],status='declared'))
    ph['joint_dispositions'].append(dict(joint_id='ctop',kind='free_end',reason='Free column top at test roof'))
    h=source.pop('source_handoff');h.pop('contract_sha256');fields=h['records']['connections/c1']['fields']
    fields.extend(dict(role=role,field=field,value=value,source={'pointer':'/connections/0/components'})
        for role,field,value in [('connection','variant','slotted_hss_gusset'),('gusset_column_weld','length_in',8.),
                                 ('gusset_column_weld','size_in',.25),('gusset_column_weld','faces',2),
                                 ('gusset_beam_weld','faces',2),('brace_end_clearance','depths',2)])
    h['occurrences'][c['id']]['applications'][0]['selected']=list(range(len(fields)))
    h['source_bindings']['native_content_sha256']=fingerprint(source);h['contract_sha256']=fingerprint(h);source['source_handoff']=h
    result=complete_native_hr(source)
    assert not result['provenance'].get('openbim_translation_findings')
    made=result['physical']['connections'][0];template=result['physical']['assemblies'][0]
    assert made['assembly_instance']['bindings']=={'COLUMN':'col','BEAM':'beam','BRACE':'B'}
    assert {q['id'] for q in template['parts'] if q.get('parameters',{}).get('source_weld_side')}=={'WGB','WGC','WGB-FACE2','WGC-FACE2'}
    assert result['physical']['members'][1]['slots'][0]['connection_id']==c['id']
    directory=tmp_path/'new-corner';directory.mkdir()
    write_json(directory/'state.json',initial_state(result,1));write_json(directory/'source.json',result)
    path=directory/'model.ifc';export_drawing(directory,path)
    readback=verify_ifc(path,result,fingerprint(result));assert readback['passed'],readback
