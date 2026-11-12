from types import SimpleNamespace

import numpy as np
import pytest

from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.transfer_girder_slip import draw
from steltic_openbim.transfer_slip_readback import measure
from test_brb_core_readback import as_mesh


@pytest.fixture
def girder(monkeypatch):
    monkeypatch.setattr('steltic_openbim.review_hr_details.support',
                        lambda ctx, _pid: ctx.a.box('M1',[0,14,-24],[1,24,24]))
    stock=dict(beam_gap_in=2.,backing_projection_in=.5,bolt_line_in=5.75,web_in=.43,beam_depth_in=23.7,
               inner_fan_gap_in=17.7,diaphragm_height_in=22.5,diaphragm_thickness_in=2.,fan_stock_in=4.,
               tab_depth_in=20.5,tab_thickness_in=.5,tab_length_in=9.5,bolt_count=6,pitch_in=3.,
               running_gap_in=.0625,sleeve_length_in=.625,slot_length_in=4.,slot_width_in=1.8125,
               sleeve_od_in=1.75,sleeve_bore_in=1.0625,keeper_length_in=6.5,keeper_height_in=2.5,
               keeper_thickness_in=.5,bolt_in=1.,beam_bore_in=1.125,travel_each_in=1.,
               material='A572',weld_material='E70',sleeve_material='QT steel',bolt_material='A490-X',fillet_in=.3125)
    profile=dict(id='W',family='i',dimensions=dict(d=23.7,bf=7.04,tf=.59,tw=.43))
    a=Assembly('Sliding girder',{'W':profile})
    ctx=SimpleNamespace(a=a,pid='W',p=a.profiles,package=dict(design_records=[dict(id='design',data=dict(sliding_receiver=stock))]),
                        c=dict(design_record_ids=['design'],parameters=dict(sliding_receiver=dict(record_id='design'))))
    draw(ctx)
    return {p['id']:as_mesh(p['faces']) for p in a.parts},{w['id']:np.array([w['a'],w['b']]) for w in a.welds},stock


@pytest.mark.parametrize('mutation',[None,'detached_fan','short_groove','keeper_clamps_tab','insufficient_travel'])
def test_full_length_attachment_and_axial_travel(girder,mutation):
    parts,curves,stock=girder
    if mutation in ('detached_fan','keeper_clamps_tab'):
        part='FAN-R' if mutation=='detached_fan' else 'P2-KEEP1'
        shift=np.eye(4);shift[1,3]=13.35 if part=='FAN-R' else -.0625
        parts[part]=parts[part].transformed(shift)
    if mutation=='short_groove':curves['FAN-L-CJP'][0,2]+=.5
    if mutation=='insufficient_travel':stock['travel_each_in']=1.5
    facts,findings=measure(parts,curves,stock)
    assert bool(findings)==bool(mutation)
    if not mutation:
        assert facts['girder_setback_in']==2.
        assert len(facts['fan_welds'])==2
        assert [len(side['slots']) for side in facts['tabs']]==[6,6]
