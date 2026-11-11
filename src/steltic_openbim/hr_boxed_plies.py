"""Represent source-selected side plates and local tapered inserts on a column."""
import math
import re
from collections import defaultdict

from .pilots.model import add,sub,mul,dot,cross,unit


def cropped_plies(plies,lo,hi):
    """Crop longitudinal plate sections, interpolating the actual specified taper."""
    result=[]
    for p in plies:
        sections=[]
        for (s,ring),(t,other) in zip(p['sections'],p['sections'][1:]):
            low,high=max(lo,s),min(hi,t)
            if high<=low+1e-8:continue
            for at in (low,high):
                if sections and abs(at-lo-sections[-1][0])<1e-8:continue
                f=(at-s)/(t-s)
                lerp=[[u+(x-u)*f,v+(y-v)*f] for (u,v),(x,y) in zip(ring,other)]
                sections.append([at-lo,lerp])
        if sections:result.append(dict(p,sections=sections))
    return result


def plate_solids(member,origin,axis,lo,hi,roles=None):
    y=member['local_y'];z=cross(axis,y);base=add(origin,mul(axis,lo))
    for ply in cropped_plies(member.get('section_plies',[]),lo,hi):
        knots=ply['sections'];rings=[]
        for at,ring in knots:
            q=add(base,mul(axis,at))
            rings.append([add(q,add(mul(y,u),mul(z,v))) for u,v in ring])
        faces=[list(reversed(rings[0])),rings[-1]]
        for a,b in zip(rings,rings[1:]):
            faces.extend([[a[i],a[(i+1)%len(a)],b[(i+1)%len(b)],b[i]] for i in range(len(a))])
        if roles is not None:roles.append(ply.get('constituent_id',ply['id']))
        yield faces


def add_column_plies(package,model):
    """Keep the design's bare W analysis identity and locate the selected steel."""
    from .saved_assemblies import material_for
    physical=package['physical'];members={m['id']:m for m in physical['members']}
    records={r['id']:r['data'] for r in package['design_records']}
    profiles={p['id']:p for p in physical['profiles']}
    catalog={m['id']:m for m in physical['materials']}
    photo={m['id']:m for m in model['members']}
    selected={}
    for m in members.values():
        if m['kind']!='column' or m.get('section_plies'):continue
        for rid in m.get('design_record_ids',[]):
            note=records.get(rid,{}).get('design_note','')
            match=re.search(r'boxed with 2 PL ([\d.]+) in side plates \(([^,]+), CJP to the flange tips over the full height',note,re.I)
            if match and profiles[m['profile_id']]['family']=='i':
                selected[m['id']]=(rid,float(match[1]),match[2]);break
    if not selected:return
    inserts=defaultdict(list)
    for c in physical['connections']:
        if c.get('detail_ref',{}).get('legacy_family')!='review_stmf_end':continue
        ids=c.get('member_ids',[]);mid=next((i for i in ids if i in selected),None)
        if not mid:continue
        chord=next((members[i] for i in ids if members[i]['kind']=='truss_chord'),None)
        if not chord:continue
        for rid in c['design_record_ids']:
            text=records.get(rid,{}).get('components','')
            spec=re.search(r'(W\S+), levels (\d+)-(\d+) \(([XY]) face\): insert plate ([\d.]+) in .*?chord depth \+ 2 x ([\d.]+) in long.*?1:([\d.]+) transitions',text,re.I)
            if not spec:continue
            pid,first,last,direction,thickness,allowance,taper=spec.groups()
            if pid!=members[mid]['profile_id'] or direction!=c['parameters']['direction'] or not int(first)<=chord['level']<=int(last):continue
            col=members[mid];endpoints=[add(p,o) for p,o in zip(col['axis'],col['end_offsets'])]
            ca=unit(sub(endpoints[1],endpoints[0]))
            ce=min(chord['axis'],key=lambda p:math.dist(p,c['point']))
            far=max(chord['axis'],key=lambda p:math.dist(p,c['point']))
            side=1 if dot(sub(far,ce),col['local_y'])>0 else -1
            station=dot(sub(ce,endpoints[0]),ca)
            half=profiles[chord['profile_id']]['dimensions']['d']/2+float(allowance)
            inserts[mid,side].append((station-half,station+half,float(thickness),float(taper),rid))
    for mid,(rid,t,grade) in selected.items():
        m=members[mid];dims=profiles[m['profile_id']]['dimensions']
        extent=math.dist(*[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])])
        material=material_for({'id':'SIDE','selected_material':grade},'plate',None,catalog,[rid])
        plies=[]
        for side in (-1,1):
            knots={0.:t,extent:t};refs={rid}
            for lo,hi,ti,taper,ref in inserts[mid,side]:
                transition=abs(ti-t)*taper;refs.add(ref)
                for station,value in [(lo-transition,t),(lo,ti),(hi,ti),(hi+transition,t)]:
                    if 0<=station<=extent:knots[station]=value
            face=side*dims['bf']/2;clear=dims['d']/2-dims['tf']
            sections=[]
            for at,thick in sorted(knots.items()):
                low,high=sorted((face,face-side*thick))
                sections.append([at,[[low,-clear],[high,-clear],[high,clear],[low,clear]]])
            plies.append(dict(id='SIDE'+('1' if side>0 else '0'),material_id=material,
                source_record_ids=sorted(refs),sections=sections,
                basis='Selected full-height side plate inset between flange tips; outer face flush with flange edges and local source insert tapers'))
        m['section_plies']=plies
        photo[mid]['section_plies']=plies
    physical['materials']=list(catalog.values())
