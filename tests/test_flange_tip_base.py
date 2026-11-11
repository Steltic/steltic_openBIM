from types import SimpleNamespace

import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.assembly_templates import findnum
from steltic_openbim.brace_base_attachment import locate_grade_interfaces
from steltic_openbim.review_hr_details import base


def test_stiffened_base_uses_flange_normal_for_selected_overhang_and_every_rod_row():
    profiles={'W':dict(id='W',family='i',dimensions=dict(d=22.8,bf=18.6,tw=2.,tf=3.))}
    text=('stiffened column base: base plate PL 4.75 x 38 x 130 in ASTM A588 on 2 in non-shrink grout; '
          'column flanges and web CJP-welded to the base plate; '
          'four stiffener plates PL 2.5 x 48 x 53.25 in ASTM A572 Gr 50 at the flange tips '
          '(outer faces flush with the tips), projecting 53.25 in beyond each flange face, '
          'CJP-welded to the flange and to the base plate; 20 x 2.75 in ASTM F1554-105 anchor rods; '
          'rod layout: on each flange side 5 rows of two rods, one outside each stiffener 4.62 in from its face, '
          'at 4.625, 15.625, 26.625, 37.625, 48.625 in from the flange face, 4.25 in holes (AISC Manual Table 14-2)')
    a=Assembly('Stiffened base',profiles)
    base(SimpleNamespace(a=a,p=profiles,pid='W',text=text,params={},selected={},
                         n=lambda pattern,default:findnum(pattern,text,default)))
    parts={p['id']:p for p in a.parts}
    assert parts['P1']['bounds']==[[-65,65],[-19,19],[2,6.75]]
    assert len(parts['P1']['holes'])==20
    anchors=a.fasteners[0]['points']
    assert len(anchors)==len(set(map(tuple,anchors)))==20
    assert sorted(set(round(abs(q[0])-11.4,6) for q in anchors))==[4.625,15.625,26.625,37.625,48.625]
    assert sorted(set(round(abs(q[1])-9.3,6) for q in anchors))==[4.62]
    stiffeners=[p for p in a.parts if p['id'].startswith('FLANGE-STIFFENER-')]
    assert len(stiffeners)==4
    for part in stiffeners:
        assert part['selected_material']=='ASTM A572 Gr 50'
        assert [hi-lo for lo,hi in part['bounds']]==pytest.approx([53.25,2.5,48])
        assert len([w for w in a.welds if w['kind']=='CJP' and part['id'] in w['connects']])==2
    assert len([w for w in a.welds if w['kind']=='CJP' and w['connects']==['M1','P1']])==3


def test_only_grade_end_with_a_continuing_column_holds_for_diaphragm_attachment():
    column=dict(id='C',kind='column',axis=[[0,0,0],[0,0,400]],end_offsets=[[0,0,-144],[0,0,0]])
    brace=dict(id='B',kind='brace')
    def connection(cid,height):
        return dict(id=cid,point=[0,0,height],member_ids=['B','C'],detail_ref={'id':'review_brace'},
                    parameters={'joint':'base'},design_record_ids=['source'])
    grade=connection('grade',0);footing=connection('footing',-144)
    model=dict(members=[column,brace],connections=[grade,footing],assumptions=[
               dict(id='grade-acceptance',answer='The grade slab and foundation walls receive the source base shear.')])
    package={'provenance':{}}
    locate_grade_interfaces(package,model);locate_grade_interfaces(package,model)
    assert [f['connection_id'] for f in package['provenance']['openbim_translation_findings']]==['grade']
    assert grade['parameters'].get('grade_diaphragm_interface')
    assert not footing['parameters'].get('grade_diaphragm_interface')
