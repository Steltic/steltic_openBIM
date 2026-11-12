import copy

import pytest
from shapely.geometry import Polygon

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.stmf_fit import slotted_end_selection
from steltic_openbim.stmf_opposed_gussets import fit_opposed
from steltic_openbim.stmf_receivers import stiffen_chord, support_welds


@pytest.mark.parametrize('toward', [-1, 1])
def test_chord_backing_fits_opposite_side_of_web_and_reaches_both_flanges(toward):
    assembly=Assembly('STMF receiver',{})
    d=dict(d=11.1,tf=1.12,tw=.68,bf=10.3)
    spec=dict(rib_depth_in=4.5,rib_t_in=1.5,diaphragm_t_in=2.75,flange_root_clip_in=.875,
              max_pitch_in=6.,material='A572 Grade 50',fillet_in=.625)
    face=toward*d['tw']/2
    start,end=[0,0,face],[-20,0,face]
    support_welds(assembly,'M0',start,end,.75,spec)
    stiffen_chord(assembly,'M0',start,end,toward,d,spec)
    assert [w['a'][1] for w in assembly.welds[:2]]==[-.375,.375]
    assert {w['size'] for w in assembly.welds[:2]}=={.625}
    diaphragms=[p for p in assembly.parts if p['id'].startswith('M0-D')]
    assert len(diaphragms)==4
    assert len(assembly.parts)-len(diaphragms)==3
    for p in diaphragms:
        assert p['bounds'][1]==pytest.approx([-4.43,4.43])
        assert p['bounds'][2]==pytest.approx(sorted((-face,-face-toward*4.5)))
        assert p['selected_material']==spec['material']
    assert len([w for w in assembly.welds if w['kind']=='CJP'])==21


def source(width=18.969655):
    scope={'attachment':'slotted_hss','member_section':'HSS8','member_axis':'diagonal'}
    def selected(role,field,value):
        return {'role':role,'field':field,'value':value,'applicability':scope}
    fields=[selected('gusset','whitmore_effective_width_in',width),
            selected('brace_slot_weld','length_in',9.5),selected('brace_slot_weld','count',4),
            selected('slot','tip_overrun_in',.125)]
    link={'record_id':'source','selected':[0,1,2,3],'hss_members':{'web':'selected'}}
    return {'records':{'source':{'fields':fields}},'occurrences':{'end':{'applications':[link]}}}


def test_width_and_slot_apply_only_to_signed_member_section_axis_and_end():
    data=source()
    assert slotted_end_selection(data,'end','web','HSS8',False)==dict(
        width=18.969655,length=9.5,count=4.,tip_overrun=.125)
    for args in [('end','another','HSS8',False),('end','web','HSS6',False),
                 ('end','web','HSS8',True),('other','web','HSS8',False)]:
        assert slotted_end_selection(data,*args)=={}
    data['occurrences']['end']['overrides']=[dict(record_id='source',field_index=0,value=19.0)]
    assert slotted_end_selection(data,'end','web','HSS8',False)['width']==19.
    data['records']['other']=source(15.)['records']['source']
    data['occurrences']['end']['applications'].append(dict(
        data['occurrences']['end']['applications'][0],record_id='other'))
    with pytest.raises(ValueError,match='Conflicting STMF width'):
        slotted_end_selection(data,'end','web','HSS8',False)


def gusset(x,protected):
    scene=Assembly('Slotted terminal',{})
    scene.polygon('GUSSET',[[0,0,0],[6,0,0],[6,0,8],[0,0,8]],.75)
    scene.box('web',[protected-1,-.25,1],[1.,.25,6.])
    scene.weld('W',[protected,0,1],[protected,0,7],['GUSSET','web'],.5)
    frame=dict(origin=[x,0,0],x_axis=[1,0,0],y_axis=[0,1,0])
    made=dict(title=scene.title,parts=scene.parts,welds=scene.welds)
    made['checked_transfer_sections_xz_in']=[[[protected,1],[protected,7]]]
    return made,frame


def outline(scene):
    return Polygon([(p[0],p[2]) for p in scene['parts'][0]['polygon']])


def test_only_free_material_is_trimmed_between_opposite_terminal_gussets():
    first=gusset(0,1)
    second=gusset(5,5)
    fit_opposed({'web':[first,second]}, {})
    assert outline(first[0]).bounds[2]==pytest.approx(5-1/32)
    assert outline(second[0]).bounds==(0.,0.,6.,8.)
    assert len(first[0]['welds'])==len(second[0]['welds'])==1
    assert first[0]['checked_transfer_sections_xz_in']==[[[1,1],[1,7]]]


def test_opposing_checked_sections_prevent_free_edge_trim_and_skew_faces_are_not_cut():
    first=gusset(0,1)
    second=gusset(5,5)
    first[0]['checked_transfer_sections_xz_in']=[[[5.5,0],[5.5,8]]]
    second[0]['checked_transfer_sections_xz_in']=[[[.5,0],[.5,8]]]
    original=[copy.deepcopy(row[0]['parts'][0]['polygon']) for row in (first,second)]
    fit_opposed({'web':[first,second]}, {})
    assert [row[0]['parts'][0]['polygon'] for row in (first,second)]==original
    second[1]['y_axis']=[0,.8,.6]
    fit_opposed({'web':[first,second]}, {})
    assert [row[0]['parts'][0]['polygon'] for row in (first,second)]==original
