from test_cfs26_primary import actual
from test_sbmf_header_fit import contact
from steltic_openbim.assembly_templates import build_scene


def test_all_source_roof_end_screws_and_receiving_bolts_contact(actual):
    m,p=actual;ends=0;nodes=0
    for c in m['connections']:
        if c['detail_ref']['id']!='review_canopy_roof_strap':continue
        nodes+=1;ends+=len(c['parameters']['ends'])
        s=build_scene(m,p,c);parts={v['id']:v for v in s['parts']}
        assert len([v for v in s['parts'] if v['id']=='GUSSET'])==1
        for f in s['fasteners']:
            if f['id'].startswith('STRAP'):assert len(f['points'])==19
            for q in f['points']:
                for name in f['connects']:assert contact(parts[name],f,q),(c['id'],f['id'],name,q)
        assert sum(f['count'] for f in s['fasteners'] if f['id'].startswith('FRAME'))==2*len(c['parameters']['ends'])
    assert nodes==16 and ends==24


def test_gussets_and_packing_clear_adjacent_cap_and_purlin_clips(actual):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from steltic_openbim.assembly_scene import section_polygons,bounds
    from steltic_openbim.review_cfs26_purlins import AXES
    from steltic_openbim.review_receiver_geometry import point
    from steltic_openbim.pilots.model import add,mul
    m,p=actual;groups={'gussets':[],'clips':[]}
    for c in m['connections']:
        family=c['detail_ref']['id'];par=c.get('parameters',{})
        group='gussets' if family=='review_canopy_roof_strap' else 'clips' if family=='review_canopy_purlin' or family=='review_canopy_longitudinal' and par['purpose']=='cap' else None
        if not group:continue
        for part in build_scene(m,p,c)['parts']:
            if group=='gussets' and not part['id'].startswith(('GUSSET','PACK','M1','M2')):continue
            if group=='clips' and not part['id'].startswith(('CLIP','CAP')):continue
            if part['kind'] in ('fastener','rod'):continue
            faces=[]
            for face in part['faces']:
                ring=[]
                for q in face:
                    world=c['point'][:]
                    for a,v in zip(par['axes'],q):world=add(world,mul(a,v))
                    ring.append(point(world,[0,0,168],AXES))
                faces.append(ring)
            groups[group].append((c['id'],dict(faces=faces,bounds=bounds(faces))))
    for z in (7.02,7.1,7.18,7.22,7.3,7.35,7.4,7.45):
        sections={k:[(cid,unary_union([Polygon(v) for v in section_polygons(part,2,z)])) for cid,part in rows] for k,rows in groups.items()}
        for gid,g in sections['gussets']:
            if g.is_empty:continue
            for cid,c in sections['clips']:assert g.intersection(c).area<1e-6,(gid,cid,z)
