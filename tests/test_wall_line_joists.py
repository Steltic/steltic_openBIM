import copy
import pytest
from steltic_openbim.review_model import CaseModel
from steltic_openbim.review_wall_line_joists import apply


@pytest.mark.parametrize('direction',['X','Y'])
@pytest.mark.parametrize('existing',[False,True])
def test_source_wall_joist_is_on_wall_and_retains_actual_support_span(direction,existing):
    b=object.__new__(CaseModel);b.key='cfs7';b.members=[];b.connections=[];b.profiles={};b.used_records=set();b.changes=[]
    record='framing/chord-squash-floor'
    b.records={record:dict(data=dict(rows=[dict(member='chord-'+direction+'-L',level=1,floor_member='1000S200-68 joist on the wall line')]))}
    ax=0 if direction=='X' else 1
    def pt(along,across,z):return [along,across,z] if ax==0 else [across,along,z]
    b.walls=[dict(direction=direction,line='L',level=k,runs=[dict(start_in=0,end_in=160,position_in=8)]) for k in (1,2)]
    for k in (1,2):
        b.member('TT'+str(k),'600T150-54','top_track',pt(0,8,120*k),pt(160,8,120*k),k,'S',local_y=[0,0,-1])
        for station in (0,8) if existing else (0,16):
            m=b.member(f'J{k}-{station}','1000S200-54','joist',pt(0,station,120*k+5),pt(160,station,120*k+5),k,'S',records=['framing/regular'])
            b.ends(m,'review_cfs_joist',['framing/regular'])
    before=copy.deepcopy(b.members);apply(b)
    wall=[m for m in b.members if m['kind']=='joist' and m['level']==1 and m['axis'][0][1-ax]==8]
    assert len(wall)==1
    m=wall[0];assert m['profile_id']=='1000S200-68' and m['design_record_ids']==[record]
    assert m['axis']==[pt(0,8,125),pt(160,8,125)]
    # Floor schedule cannot add/upgrade roof members; ordinary joists stay intact.
    assert [m for m in b.members if m['level']==2]==[m for m in before if m['level']==2]
    if existing:assert m['source_context_records']==['framing/regular']
    else:assert len([c for c in b.connections if m['id'] in c['member_ids']])==2
    result=copy.deepcopy((b.members,b.connections,b.changes));apply(b)
    assert (b.members,b.connections,b.changes)==result
    apply(b,adopt_roof_wall_joists=True)
    roof=[m for m in b.members if m['kind']=='joist' and m['level']==2 and m['axis'][0][1-ax]==8]
    assert len(roof)==1 and roof[0]['profile_id']=='1000S200-54'
    assert record not in roof[0]['design_record_ids']
    if not existing:
        assert roof[0]['basis']=='A' and b.changes[-1]['source_row'] is None
        assert b.changes[-1]['kind']=='adopted_roof_wall_joist'
