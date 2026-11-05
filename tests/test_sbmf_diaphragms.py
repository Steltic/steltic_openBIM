from collections import defaultdict
import pytest
from shapely.geometry import Point
from steltic_openbim.review_cases import evidence,scenario,build_model
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.review_cfs5_diaphragms import region
from steltic_openbim.review_cfs_occurrences import axis
from test_sbmf_header_fit import contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs18')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs18',answers_sha256=fingerprint(scenario('cfs18')['answers']))))
    assert fingerprint(p)==before
    return m,p


def test_every_wsp_screw_crosses_its_actual_panel_and_all_finite_steel_plies(actual):
    m,p=actual;panels={v['id']:v for v in m['panels']};openings={v['id']:v for v in m['openings']}
    regions={key:region(panel,openings) for key,panel in panels.items() if key in ('WING-FLOOR-1','WING-FLOOR-2')}
    positions={};count=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_wsp':continue
        par=c['parameters'];scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        assert parts['WSP']['bound_panel_id']==par['host_panel_id']
        assert parts['WSP']['representation_role']=='context_only'
        for f in scene['fasteners']:
            assert f['diameter']==.19
            for q in f['points']:
                count+=1
                for label in f['connects']:
                    assert contact(parts[label],f,q),(c['id'],label,q)
                xy=[q[i]+c['point'][i] for i in (0,1)]
                assert regions[par['host_panel_id']].buffer(-.3999).covers(Point(*xy)),(c['id'],xy)
                key=(par['host_panel_id'],*[round(v,4) for v in xy])
                assert key not in positions,(c['id'],positions.get(key),key)
                positions[key]=c['id']
    assert count>10000


def test_every_transverse_sheet_edge_has_its_own_supported_fixing_row(actual):
    m,_=actual;members={v['id']:v for v in m['members']};rows=defaultdict(list);supports=defaultdict(list)
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_wsp':continue
        par=c['parameters']
        if par['purpose']=='plain':continue
        mid=c['member_ids'][0]
        for q in par['points_relative']:
            x,y=[q[i]+c['point'][i] for i in (0,1)]
            rows[mid,round(y,4)].append(x)
            if par['purpose']=='strip_support':supports[mid,round(y,4)].append(x)
    strips=[v for v in m['members'] if v['kind']=='diaphragm_blocking' and v['id'].startswith('MEZZ-DIA-')]
    assert len(strips)==28
    for strip in strips:
        roof=strip['level']==2;y=strip['axis'][0][1]
        ys=[y] if roof and y in (24.5,575.5) else [y-.375,y+.375]
        for yy in ys:
            values=sorted(rows[strip['id'],yy]);endpoints=sorted(supports[strip['id'],yy])
            assert len(endpoints)>=2
            assert values[0]-strip['axis'][0][0]<=1.5
            assert strip['axis'][1][0]-values[-1]<=1.5
            assert max(b-a for a,b in zip(values,values[1:]))<=(6 if roof else 4)+1e-6,(strip['id'],yy)


def test_rebates_and_source_nominal_layers_are_explicit_and_do_not_overlap_steel(actual):
    m,_=actual;members={v['id']:v for v in m['members']};profiles={v['id']:v for v in m['profiles']}
    for panel in [v for v in m['panels'] if v['id'] in ('WING-FLOOR-1','WING-FLOOR-2')]:
        roof=panel['id'].endswith('2');schedule=panel['attachment_schedule']
        assert panel['thickness_in']==(19/32 if roof else 23/32)
        assert panel['vertices'][0][2]==(240 if roof else 118.5)
        assert schedule['field_pitch_in']==12 and schedule['boundary_pitch_in']==(6 if roof else 4)
        assert len(panel['underside_recesses'])==len(schedule['blocking_member_ids'])
        bottom=panel['vertices'][0][2]-panel['thickness_in']
        for cut in panel['underside_recesses']:
            strip=members[cut['support_member_id']];t=profiles[strip['profile_id']]['dimensions']['thickness']
            assert t==cut['depth_in']==.1017
            assert axis(strip)[0][2]-t/2==pytest.approx(bottom)
            assert cut['side']=='underside' and cut['basis'].startswith('A ')
    edges=[v for v in m['members'] if v['id'].startswith('WING-J-2-') and v['axis'][0][0]==1818]
    assert len(edges)==3 and all(v['local_y']==[1,0,0] for v in edges)


def test_plain_source_fixing_maxima_hold_across_connection_group_boundaries(actual):
    m,_=actual;rows=defaultdict(list);limits={}
    for c in m['connections']:
        if c['detail_ref']['id']!='review_sbmf_wsp' or c['parameters']['purpose']!='plain':continue
        # Group by host, flange row, and uninterrupted line segment. Drawing
        # groups of six must not reset the pitch or duplicate an end screw.
        key=c['id'].rsplit('-',1)[0];par=c['parameters'];limits[key]=par['source_pitch_in']
        for q in par['points_relative']:rows[key].append([q[i]+c['point'][i] for i in range(3)])
    assert rows
    for key,values in rows.items():
        values.sort()
        for a,b in zip(values,values[1:]):
            assert sum((b[i]-a[i])**2 for i in range(3))**.5<=limits[key]+1e-6,key
