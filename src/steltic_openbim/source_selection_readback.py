"""Compare occurrence-selected HR connection fields with the native and drawing assemblies."""
from collections import Counter,defaultdict
import re
import numpy as np


def alloys(value):
    s=str(value).upper()
    result=set()
    for pattern in (r'\b4140\b',r'\bA\s*193[- .]*(?:(?:GRADE|GR)[ .-]*)?B\s*7\b',
                    r'\bA\s*572\s*(?:(?:GRADE|GR)\.?\s*)?[- ]*50\b',
                    r'\bF\s*1554\s*[- ]*(?:(?:GRADE|GR)\.?\s*)?(36|55|105)\b',
                    r'\bA\s*(325|490)\b',r'\bA\s*36\b'):
        for m in re.finditer(pattern,s):
            result.add(re.sub(r'(?:GRADE|GR)|[^0-9A-Z]','',m.group()))
    return result


def geometry_bounds(part):
    g=part.get('geometry',{})
    if g.get('type')=='mesh':
        verts=[p for f in g['faces'] for p in f]
        return [(min(p[i] for p in verts),max(p[i] for p in verts)) for i in range(3)]
    if g.get('type')=='box':
        a=g['origin'];x=g['x_axis'];y=g['y_axis'];z=[x[(i+1)%3]*y[(i+2)%3]-x[(i+2)%3]*y[(i+1)%3] for i in range(3)]
        verts=[[a[i]+u*g['size'][0]*x[i]+v*g['size'][1]*y[i]+w*g['size'][2]*z[i] for i in range(3)]
               for u in (0,1) for v in (0,1) for w in (0,1)]
        return [(min(p[i] for p in verts),max(p[i] for p in verts)) for i in range(3)]
    return None


def plate_thickness(part):
    g=part.get('geometry',{})
    if g.get('type')=='box':
        return min(g['size'])
    faces=g.get('faces',[])
    if not faces:return None
    verts=np.vstack(faces)
    normals=set()
    for face in faces:
        ring=np.asarray(face)
        n=np.cross(ring,np.roll(ring,-1,axis=0)).sum(axis=0)
        length=np.linalg.norm(n)
        if length>1e-8:
            n=n/length
            if n[np.argmax(np.abs(n))]<0:n=-n
            normals.add(tuple(np.round(n,8)))
    return min((np.ptp(verts@normal) for normal in normals),default=None)


def verify_source_selections(package,drawing_model=None):
    handoff=package.get('source_handoff',{})
    records=handoff.get('records',{})
    physical=package['physical']
    templates={x['id']:x for x in physical.get('assemblies',[])}
    materials={m['id']:m for m in physical['materials']}
    scenes={}
    if drawing_model:
        scenes={s['id']:s for s in drawing_model.get('connection_assemblies',drawing_model.get('assemblies',[]))}
    findings=[]
    counts=Counter()
    thickness_cache={}
    result=dict(passed=False,findings=findings,occurrences_checked=0,selected_comparisons=counts)
    if not records and any(c.get('design_record_ids') for c in physical['connections']):
        findings.append(dict(issue='HR connection source selections are missing'))
        return result
    for connection in physical['connections']:
        cid=connection['id']
        occurrence=handoff.get('occurrences',{}).get(cid,{})
        instance=connection.get('assembly_instance',{})
        t=templates.get(instance.get('template_id'),{})
        parts=t.get('parts',connection.get('parts',[]))
        scene=scenes.get(t.get('source_detail'))
        fields=defaultdict(list)
        overrides={(o['record_id'],o['field_index']):o['value'] for o in occurrence.get('overrides',[])}
        for link in occurrence.get('applications',[]):
            rid=link['record_id']
            for index in link['selected']:
                f=records[rid]['fields'][index]
                fields[(f['role'],f['field'])].append((rid,overrides.get((rid,index),f['value'])))
        def check(code,ok,expected,actual,rid=None):
            counts[code]+=1
            if not ok:
                findings.append(dict(issue=code,connection=cid,template=t.get('id'),record=rid,expected=expected,actual=actual))
        def material(p):
            m=materials.get(p.get('material_id'),{})
            return m.get('specification','')+' '+m.get('source_item','')
        def count(parts):
            return sum(p.get('parameters',{}).get('count',1) for p in parts)
        found={kind:[p for p in parts if p['kind']==kind] for kind in ('pin','bolt','anchor','weld')}
        # Older assemblies described pin shafts as bolts. Keep their physical role for comparison.
        legacy=[p for p in found['bolt'] if re.fullmatch(r'PIN(?::\d+)?',p['id'],re.I)]
        found['pin']+=legacy
        found['bolt']=[p for p in found['bolt'] if p not in legacy]
        variants={s for _,s in fields['connection','variant']}
        needs_pin=bool(variants & {'brb_pinned','beam_pin_hinge'})
        needs_bolts=bool(variants & {'brb_bolted','bolted_brb','brb_bolted_splice'})
        beam_bolts=bool(variants & {'single_plate_shear','two_plate_shear','two_plate_bolted','two_plate_beam_end'})
        recognized=needs_pin or needs_bolts or beam_bolts or 'base_plate_anchors' in variants
        if needs_pin or needs_bolts or beam_bolts:
            expected='pin' if needs_pin else 'bolt'
            check('selected_connection_hardware',bool(found[expected]) and (needs_pin or not found['pin']),
                  expected,{k:len(found[k]) for k in ('pin','bolt')},fields['connection','variant'][0][0])
        for p in parts:
            if p['kind']=='grout' or p['id']=='GROUT':
                spec=material(p)
                check('grout_material','grout' in spec.lower() and not re.search(r'\bA(?:36|572|992)\b',spec,re.I),
                      'grout',spec)
        for role in ('pin','bolt','anchor'):
            if not recognized or (role=='pin' and not needs_pin) or (role=='bolt' and not (needs_bolts or beam_bolts)) or (role=='anchor' and 'base_plate_anchors' not in variants):
                continue
            hardware=found[role]
            for rid,value in fields[role,'count']:
                check(role+'_count',count(hardware)==value,value,count(hardware),rid)
            for rid,value in fields[role,'diameter_in']:
                diameters=[p.get('parameters',{}).get('diameter') for p in hardware]
                check(role+'_diameter',bool(diameters) and all(isinstance(d,(float,int)) and abs(d-value)<1e-5 for d in diameters),
                      value,sorted({str(d) for d in diameters}),rid)
                if scene and role=='pin':
                    pins=[g['diameter'] for g in scene['fasteners'] if g['id'].upper()=='PIN']
                    check('drawn_pin_diameter',bool(pins) and all(abs(n-value)<1e-5 for n in pins),value,pins,rid)
            for rid,value in fields[role,'material']:
                expected=alloys(value)
                if expected:
                    grades=[alloys(material(p)) for p in hardware]
                    check(role+'_alloy',bool(grades) and all(g==expected for g in grades),
                          sorted(expected),[sorted(g) for g in grades],rid)
        for rid,value in fields['clevis_outer_fillet','size_in']:
            if not needs_pin:continue
            welds=[p for p in found['weld'] if p['id'] in ('WC0','WC1')
                   or 'outer-face clevis' in p.get('parameters',{}).get('description','').lower()]
            sizes=[p.get('parameters',{}).get('size_in') for p in welds]
            check('clevis_outer_fillet',bool(sizes) and all(isinstance(n,(int,float)) and abs(n-value)<1e-5 for n in sizes),value,sizes,rid)
            if scene:
                drawn=[w.get('size') for w in scene['welds'] if w['id'] in {p['id'] for p in welds}]
                check('drawn_clevis_outer_fillet',len(drawn)==len(welds) and all(n==value for n in drawn),value,drawn,rid)
        for rid,value in fields['reinforcement_fillet','size_in']:
            welds=[p for p in found['weld'] if any(str(i).upper().startswith('REINF') for i in p.get('connects',[]))]
            sizes=[p.get('parameters',{}).get('size_in') for p in welds]
            check('selected_reinforcement_fillet',bool(sizes) and all(n==value for n in sizes),value,sizes,rid)
            if scene:
                drawn=[w.get('size') for w in scene['welds'] if w['id'] in {p['id'] for p in welds}]
                check('drawn_reinforcement_fillet',len(drawn)==len(welds) and all(n==value for n in drawn),value,drawn,rid)
        if variants & {'brb_pinned','brb_bolted','slotted_hss_gusset'}:
            for rid,value in fields['gusset','thickness_in']:
                plates=[p for p in parts if 'GUSSET' in p['id'].upper() and p['kind']=='plate']
                measured=[]
                for p in plates:
                    key=(t.get('id',cid),p['id'])
                    if key not in thickness_cache:thickness_cache[key]=plate_thickness(p)
                    measured.append(thickness_cache[key])
                check('selected_gusset_thickness',bool(measured) and all(n is not None and abs(n-value)<1e-4 for n in measured),
                      value,measured,rid)
        if fields['anchor_pattern','spacing_in'] or fields['anchor_pattern','edge_in']:
            plate=next((p for p in parts if p['id'] in ('P1','BP','BASE-PLATE') and p['kind']=='plate'),{})
            bounds=geometry_bounds(plate)
            pts=[p.get('parameters',{}).get('point') for p in found['anchor']]
            if bounds and pts and all(pts):
                axes=[]
                for i in (0,1):
                    stations=sorted({round(pt[i],5) for pt in pts})
                    if len(stations)>=2:
                        axes.append((min(b-a for a,b in zip(stations,stations[1:])),
                                     (stations[0]-bounds[i][0],bounds[i][1]-stations[-1])))
            else:axes=[]
            for rid,value in fields['anchor_pattern','spacing_in']:
                check('anchor_spacing',any(abs(s-value)<1e-4 for s,_ in axes),value,[a[0] for a in axes],rid)
            for rid,value in fields['anchor_pattern','edge_in']:
                compatible=[e for s,e in axes if all(abs(s-expect)<1e-4 for _,expect in fields['anchor_pattern','spacing_in'])]
                check('anchor_edge',any(all(abs(x-value)<1e-4 for x in e) for e in compatible),value,compatible,rid)
        result['occurrences_checked']+=1
    result['selected_comparisons']=dict(counts)
    result['passed']=not findings
    return result
