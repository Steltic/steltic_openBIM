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
