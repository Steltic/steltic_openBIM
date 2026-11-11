"""The selected steel shell, infill and moving core are separately measurable in STEP."""
import copy
import json
from pathlib import Path

import ifcopenshell
import pytest

from steltic_openbim.brb_casing import DELEGATED_MATERIAL,requirements,bind_receiver_profiles
from steltic_openbim.brb_casing_readback import check
from steltic_openbim.brb_core_readback import core_sections
from steltic_openbim.brb_supplier_core import prepare,write_cores
from steltic_openbim.drawing_workflow import initial_state,write_json
from steltic_openbim.ifc_assembly_verification import Readback
from steltic_openbim.ifc_export import export_drawing


def sample(selected=True):
    p=json.loads((Path(__file__).parent/'fixtures/synthetic_bim_package.json').read_bytes())
    ph=p['physical'];m=ph['members'][0]
    m.update(profile_id='BRB6',kind='brace',design_record_ids=['members/brace'])
    profile=dict(id='BRB6',status='declared',family='rhs',core_area_in2=6.,dimensions=dict(b=10.,h=10.,t=.375))
    ph['profiles'].append(profile)
    checks=[dict(limit_state='brace elongation 2.40 in over the yielding length 72 in (0.60 Lwp)')]
    if selected:checks.append(dict(limit_state='global stability of the casing (steel HSS12X12X1/2 A500 Gr C, concrete fill neglected)'))
    original=dict(id='members/brace',table='members',source_pointer='/members/0',waived=False,
                  data=dict(design_note='BRB6: Asc = 6 in2, A36 core',checks=checks))
    p['design_records'].append(original)
    text=('ASTM A36 steel core in a mortar-filled steel casing by the BRB manufacturer' if selected else
          'steel core ASTM A36; casing, core extensions and end details by the BRB supplier')
    ph['materials'].append(dict(id='report',source_item='Buckling-restrained braces',specification=text))
    return p


@pytest.mark.parametrize('defect',['none','base_plate_alloy','wrong_wall','no_mortar','mortar_alloy','filled_sliding_gap',
                                   'duplicated_face','incorrect_ownership','missing_shape_aspect'])
def test_actual_brb_constituents(tmp_path,defect):
    p=sample();ph=p['physical'];m=ph['members'][0]
    expected=requirements([m],{},p['design_records'],ph['materials'])[m['id']]
    prepare(p,ph);write_cores(p,ph)
    profile=next(row for row in ph['profiles'] if row['id']=='BRB6')
    assert profile['dimensions']=={'b':12.,'h':12.,'t':.5}
    if defect=='wrong_wall':profile['dimensions']['t']=.375
    if defect=='no_mortar':m['section_plies']=[row for row in m['section_plies'] if row['id']=='YIELDING-CORE']
    if defect=='filled_sliding_gap':
        for row in m['section_plies']:
            if row['id']=='MORTAR-LEFT':
                for _,ring in row['sections']:
                    for i in (1,2):ring[i][0]=0.
    state=initial_state(p,1);write_json(tmp_path/'state.json',state);write_json(tmp_path/'source.json',p)
    path=tmp_path/'body.ifc';export_drawing(tmp_path,path)
    if defect in ('base_plate_alloy','mortar_alloy','duplicated_face','incorrect_ownership','missing_shape_aspect'):
        file=ifcopenshell.open(str(path));product=file.by_type('IfcMember')[0]
        aspects={a.Name:a for a in product.Representation.Representations[0].Items[0].MappingSource.HasShapeAspects}
        mats={x.Name:x for x in next(r.RelatingMaterial for r in product.HasAssociations
                  if r.is_a('IfcRelAssociatesMaterial')).MaterialConstituents}
        if defect=='base_plate_alloy':mats['MAIN'].Material.Name='ASTM A572 Grade 50 connection plates'
        if defect=='mortar_alloy':mats['MORTAR-INFILL'].Material.Name='ASTM A36'
        if defect=='duplicated_face':
            body=aspects['MORTAR-INFILL'].ShapeRepresentations[0].Items[0]
            body.Faces=tuple(body.Faces)+(aspects['MAIN'].ShapeRepresentations[0].Items[0].Faces[0],)
        if defect=='incorrect_ownership':
            aspects['MAIN'].Name='MORTAR-INFILL';aspects['MORTAR-INFILL'].Name='MAIN'
        if defect=='missing_shape_aspect':file.remove(aspects['MORTAR-INFILL'])
        file.write(str(path))
    rb=Readback(path);body=rb.member(m['id'])
    info,errors=check(rb.members[m['id']],body,expected,profile,120.)
    assert bool(errors)==(defect!='none'),(info,errors)
    if defect=='none':
        assert info['actual_casing_dimensions']['walls_in']==pytest.approx([.5]*4)
        assert info['minimum_transverse_core_clearance_in']==pytest.approx(1/16,abs=.0001)
        _,errors=core_sections(body,6.,72.);assert not errors


def test_same_core_area_can_have_two_selected_shells_and_disjoint_schedule_marks():
    p=sample();ph=p['physical'];a=ph['members'][0]
    b=dict(copy.deepcopy(a),id='other',design_record_ids=['members/another']);ph['members'].append(b)
    record=copy.deepcopy(p['design_records'][-1]);record['id']='members/another'
    record['data']['checks'][1]['limit_state']='global stability of casing (steel HSS8X8X1/4 A500 Gr C)'
    p['design_records'].append(record)
    m=copy.deepcopy(ph);m['member_schedule']=[dict(mark='BR1',member_ids=[a['id'],b['id']],count=2)]
    prepare(p,m)
    assert len({row['profile_id'] for row in m['members']})==2
    assert [row['source_profile_id'] for row in m['members']]==['BRB6']*2
    assert [(r['mark'],r['casing_section'],r['count']) for r in m['member_schedule']]==[
        ('BR1-1','HSS12X12X1/2',1),('BR1-2','HSS8X8X1/4',1)]
    ph['assemblies']=[dict(id='end',receivers=[dict(id='BRACE',kind='member',profile_id='BRB6')])]
    ph['connections']=[dict(id='end-'+v['id'],assembly_instance=dict(template_id='end',bindings={'BRACE':v['id']}))
                       for v in ph['members']]
    bind_receiver_profiles(ph)
    placed={t['id']:t for t in ph['assemblies']}
    for v,c in zip(ph['members'],ph['connections']):
        t=placed[c['assembly_instance']['template_id']]
        assert t['revision']==c['assembly_instance']['revision']
        assert t['receivers'][0]['profile_id']==v['profile_id']


def test_delegated_shell_is_labelled_without_inventing_grade_or_mortar():
    p=sample(False);ph=p['physical'];m=ph['members'][0];prepare(p,ph);write_cores(p,ph)
    assert m['brb_casing']['material']==DELEGATED_MATERIAL
    assert [row['id'] for row in m['section_plies']]==['YIELDING-CORE']
    assert next(q['specification'] for q in ph['materials'] if q['id']==m['material_id'])==DELEGATED_MATERIAL
