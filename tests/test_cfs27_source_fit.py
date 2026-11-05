from collections import Counter
import math
import pytest
from steltic_openbim.review_cases import build_model,evidence,scenario
from steltic_openbim.drawing_workflow import fingerprint
from steltic_openbim.assembly_templates import build_scene
from steltic_openbim.pilots.model import unit,cross,dot,add,mul
from test_sbmf_header_fit import contact as axial_contact


@pytest.fixture(scope='module')
def actual():
    p=evidence('cfs27')['package'];before=fingerprint(p)
    m=build_model(p,dict(design_scenario=dict(id='cfs27',answers_sha256=fingerprint(scenario('cfs27')['answers']))))
    assert fingerprint(p)==before
    return m,p


def contact(part,fastener,q):
    # Resolve oblique screw rays in their own orthonormal frame. The legacy
    # helper only traces an axis-aligned ray and would miss a sloped roof leg.
    if sum(abs(v)>1e-6 for v in fastener['axis'])==1:return axial_contact(part,fastener,q)
    z=unit(fastener['axis']);x=unit(cross([0,1,0] if abs(z[1])<.9 else [1,0,0],z));y=cross(z,x)
    transform=lambda p:[dot(p,v) for v in (x,y,z)]
    return axial_contact(dict(part,faces=[[transform(p) for p in face] for face in part['faces']]),dict(fastener,axis=[0,0,1]),transform(q))


def test_source_members_braces_and_distinct_post_kicker_groups(actual):
    m,p=actual;counts=Counter(v['kind'] for v in m['members'])
    assert counts['column']==62 and counts['rafter']==62
    assert counts['purlin']==300 and counts['strap']==24 and counts['flange_brace']==396
    kickers=[c for c in m['connections'] if c.get('parameters',{}).get('source_post')]
    assert len(kickers)==6
    for c in kickers:
        scene=build_scene(m,p,c);count=2 if c['point'][0]==210 else 5
        assert len(scene['fasteners'])==3
        assert all(f['count']==count for f in scene['fasteners'])
        member=next(v for v in m['members'] if v['id']==c['member_ids'][0])
        assert math.isclose(math.dist(*member['axis']),25.5,abs_tol=1e-8)
    assert sum(c['detail_ref']['id']=='review_single_strut' for c in m['connections'])==62
    assert sum(c['detail_ref']['id']=='review_single_strap_node' for c in m['connections'])==40
    assert not any(c['detail_ref']['id'] in ('review_next_secondary','review_next_portal_joint','review_cfs_strap','review_screwed_flybrace') for c in m['connections'])
    assert all(v.get('physical_constituent_member_ids') for v in m['panels'])
    assert len(m['panels'])==10
    assert len(m['physical_interfaces'])>=2


def test_all_strap_and_fly_brace_fasteners_engage_actual_receivers(actual):
    m,p=actual
    for c in m['connections']:
        if c['detail_ref']['id'] not in ('review_single_strap_node','review_single_flybrace','review_single_strut','review_single_stitch','review_single_endwall'):continue
        scene=build_scene(m,p,c);parts={v['id']:v for v in scene['parts']}
        for f in scene['fasteners']:
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)


def test_roof_straps_clear_secondary_feet_and_actual_nested_z_flange_planes(actual):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from steltic_openbim.assembly_scene import section_polygons,bounds
    from steltic_openbim.review_receiver_geometry import point
    m,p=actual
    for slope in (0,1):
        u=unit([1,0,(1 if slope==0 else -1)*2/9]);axes=(u,[0,1,0],cross(u,[0,1,0]));origin=[0,0,192] if slope==0 else [216,0,240];groups={'straps':[],'supports':[]}
        for c in m['connections']:
            par=c.get('parameters',{});family=c['detail_ref']['id']
            if not par.get('roof') or int(par['axes'][0][2]<0)!=slope:continue
            group='straps' if family=='review_single_strap_node' else 'supports' if family=='review_single_channel_z' and par['purpose']=='support' else None
            if group is None:continue
            for part in build_scene(m,p,c)['parts']:
                if part['kind'] in ('fastener','rod'):continue
                if group=='straps' and part['id']=='M0':continue
                if group=='supports' and not part['id'].startswith(('CLIP','PACK','Z')):continue
                faces=[[point(add(c['point'],[sum(a[k]*q[j] for j,a in enumerate(par['axes'])) for k in range(3)]),origin,axes) for q in face] for face in part['faces']]
                groups[group].append((c['id'],part['id'],dict(faces=faces,bounds=bounds(faces))))
        for z in (7.02,7.1,7.18,7.22,7.3,7.36,7.4,7.8):
            slices={k:[(cid,pid,unary_union([Polygon(r) for r in section_polygons(part,2,z)])) for cid,pid,part in rows if part['bounds'][2][0]<z<part['bounds'][2][1]] for k,rows in groups.items()}
            for cid,pid,a in slices['straps']:
                for other,opid,b in slices['supports']:
                    assert a.intersection(b).area<1e-6,(cid,pid,other,opid,z,a.intersection(b).area)


def test_wall_strap_collectors_clear_shared_eave_brackets(actual):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from steltic_openbim.assembly_scene import section_polygons,bounds
    from steltic_openbim.review_receiver_geometry import point
    m,p=actual
    for side in (0,1):
        n=[-1 if side==0 else 1,0,0];axes=([0,0,1],cross(n,[0,0,1]),n);origin=[432*side,0,192];groups={'straps':[],'brackets':[]}
        for c in m['connections']:
            par=c.get('parameters',{});family=c['detail_ref']['id']
            if int(c['point'][0]>216)!=side:continue
            group='straps' if family=='review_single_strap_node' and not par['roof'] else 'brackets' if family=='review_single_strut' else None
            if group is None:continue
            frame=par.get('axes',([1,0,0],[0,1,0],[0,0,1]))
            for part in build_scene(m,p,c)['parts']:
                if group=='straps' and part['id']=='M0':continue
                if group=='brackets' and part['id'] not in ('COLUMN-LEG','STRUT-LEG'):continue
                if part['kind'] in ('fastener','rod'):continue
                faces=[[point(add(c['point'],[sum(a[k]*q[j] for j,a in enumerate(frame)) for k in range(3)]),origin,axes) for q in face] for face in part['faces']]
                groups[group].append((c['id'],part['id'],dict(faces=faces,bounds=bounds(faces))))
        for z in (7.02,7.1,7.18,7.22,7.3,7.36,7.4):
            slices={k:[(cid,pid,unary_union([Polygon(r) for r in section_polygons(part,2,z)])) for cid,pid,part in rows if part['bounds'][2][0]<z<part['bounds'][2][1]] for k,rows in groups.items()}
            for cid,pid,a in slices['straps']:
                for other,opid,b in slices['brackets']:assert a.intersection(b).area<1e-6,(cid,pid,other,opid,z)
