"""Locate connection-selected flange inserts, post tapers and welds on the affected members."""
from copy import deepcopy
import math

from .fabricated_i_section import KEYS,cropped
from .hr_detail_selections import selected_fields
from .pilots.model import add,sub,mul,unit,dot,cross


def by_role(fields,role):
    return {k[1]:fields.get(k) for k in fields if k[0]==role}


def dims(profile):
    if profile['family']!='i':raise ValueError('Transfer fabrication needs a rolled W section')
    return {k:profile['dimensions'][k] for k in KEYS}


def interval(member,first,last,start,end,record):
    if first>last:first,last,start,end=last,first,end,start
    rows=member.setdefault('fabricated_i_sections',[])
    row=dict(start_in=first,end_in=last,start_dimensions=start,end_dimensions=end,source_record_ids=record)
    if row not in rows:rows.append(row)


def at_member(member,point):
    start,end=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]
    ray=unit(sub(end,start));s=dot(sub(point,start),ray)
    if math.dist(add(start,mul(ray,s)),point)>.02:raise ValueError('Selected transfer point is outside its member')
    return s,math.dist(start,end),ray


def populate(package,model):
    members={m['id']:m for m in model['members']}
    physical={m['id']:m for m in package['physical']['members']}
    profiles={p['id']:p for p in model['profiles']}
    for c in model['connections']:
        if c.get('detail_ref',{}).get('id')!='review_transfer_truss':continue
        fields=selected_fields(package,c)
        insert=by_role(fields,'transfer_support_transition');splice=by_role(fields,'transfer_post_splice')
        weld=by_role(fields,'transfer_post_gusset_weld')
        if not (insert or splice or weld):continue
        attached=[members[mid] for mid in c['member_ids']]
        spec={}
        if insert:
            columns=[m for m in attached if m['kind']=='column']
            if len(columns)!=1:raise ValueError('Transition requires one support column')
            m=columns[0];original=dims(profiles[m['profile_id']]);s,_,_=at_member(m,c['point'])
            near,far=s-insert['length_in']/2,s+insert['length_in']/2
            recess=insert['recess_in'];extra=insert['projection_in']
            if (abs(insert['width_in']-recess-extra)>1e-5 or abs(original['tf']-insert['thickness_in'])>1e-5 or
                    min(recess,extra)<=0.):
                raise ValueError('Selected flange insert width, thickness or finish plane disagrees with the support')
            cut=dict(original,bf=original['bf']-2*recess)
            interval(m,near,far,cut,cut,c['design_record_ids'])
            spec['insert']=dict(insert,member=m['id'],original=original,weld=by_role(fields,'transfer_support_transition_weld'),
                                stiffener=by_role(fields,'transfer_support_stiffener'),stiffener_weld=by_role(fields,'transfer_support_stiffener_weld'))
            physical[m['id']]['fabricated_i_sections']=deepcopy(m['fabricated_i_sections'])
        if weld or splice:
            posts=[m for m in attached if m['kind']=='transfer_vertical']
            if len(posts)!=1:raise ValueError('Selected transfer weld needs the located vertical post')
            m=posts[0]
            if weld:spec['post_weld']=dict(weld,member=m['id'])
            if splice:
                upper=[m2 for m2 in attached if m2['kind']=='column' and m2['profile_id'].upper()==splice['upper_section'].upper()]
                if len(upper)!=1:raise ValueError('Selected transition lacks its mating upper column')
                station,extent,_=at_member(m,c['point'])
                if min(station,extent-station)>1e-5:raise ValueError('Selected tapered splice must lie at a post end')
                sign=1 if station<extent/2 else -1
                lo=station+sign*splice['transition_length_in']
                original=dims(profiles[m['profile_id']]);finished=dims(profiles[upper[0]['profile_id']])
                interval(m,lo,station,original,finished,c['design_record_ids'])
                spec['splice']=dict(splice,member=m['id'],upper=upper[0]['id'],finished=finished)
                physical[m['id']]['fabricated_i_sections']=deepcopy(m['fabricated_i_sections'])
        c.setdefault('parameters',{})['transfer_fabrication']=spec


def shown_sections(member,workpoint,inward,lo,hi):
    station,_,ray=at_member(member,workpoint);sign=dot(inward,ray)
    return cropped(member.get('fabricated_i_sections',[]),station+lo*sign,station+hi*sign)


def inserts(assembly,role,direction,perp,spec):
    original=spec['original'];length=spec['length_in'];width=spec['width_in'];t=spec['thickness_in']
    weld=spec['weld'];pieces={}
    for side in (-1,1):
        outside=side*(original['bf']/2+spec['projection_in']);inner=outside-side*width
        for flange in (-1,1):
            outer=flange*original['d']/2;root=outer-flange*t
            def at(s,y,z):return add(add(mul(direction,s),mul(perp,z)),[0.,y,0.])
            line=sorted([inner,outside]);z=min(outer,root)
            corners=[at(s,y,z) for s,y in [(-length/2,line[0]),(length/2,line[0]),
                                                (length/2,line[1]),(-length/2,line[1])]]
            name=f'TIP-{side}-{flange}'
            p=assembly.polygon(name,corners,t,normal=perp,basis='S',description='Source full-thickness replacement flange-edge insert')
            p.update(selected_material=spec['material'],parameters=dict(source_role='transfer_support_transition',host_role=role))
            pieces[side,flange]=name
            metal=weld['material']
            assembly.weld(name+'-CJP',at(-length/2,inner,(root+outer)/2),at(length/2,inner,(root+outer)/2),
                          [role,name],0.,kind='CJP',basis='S',description='Full-length replacement flange-tip groove weld')
            assembly.welds[-1]['selected_material']=metal
    if spec.get('stiffener'):
        stiffen(assembly,role,direction,perp,spec,pieces)
    return pieces


def stiffen(assembly,role,direction,perp,spec,inserts_by_tip):
    d=spec['original'];stiff=spec['stiffener'];weld=spec['stiffener_weld']
    radius=stiff['cope_radius_in'];thickness=stiff['thickness_in'];offset=stiff['offset_from_workpoint_in']
    half=(d['d']-2*d['tf'])/2;inner=d['tw']/2;outer=d['bf']/2+spec['projection_in']
    seam=outer-spec['width_in']
    if min(half,outer-inner)<=radius or thickness<=0:
        raise ValueError('Selected transverse stiffener or its corner cope does not fit the W shape')
    def at(s,w,z):return add(add(mul(direction,s),mul(perp,z)),[0.,w,0.])
    outline=[(inner+radius,-half),(outer,-half),(outer,half),(inner+radius,half)]
    for i in range(1,81):
        theta=-math.pi*i/160
        outline.append((inner+radius*math.cos(theta),half+radius*math.sin(theta)))
    outline.append((inner,-half+radius))
    for i in range(1,80):
        theta=math.pi*(80-i)/160
        outline.append((inner+radius*math.cos(theta),-half+radius*math.sin(theta)))
    for s in (-offset,offset):
        for side in (-1,1):
            name=f'STIFF-{s:g}-{side}'
            pts=[at(s-thickness/2,side*w,z) for w,z in outline]
            plate=assembly.polygon(name,pts,thickness,normal=direction,basis='S',
                                  description='Source transverse half-stiffener with two rolled-root corner copes')
            plate.update(selected_material=stiff['material'],parameters=dict(source_role='transfer_support_stiffener',host_role=role))
            def groove(suffix,target,p,q):
                assembly.weld(name+'-'+suffix,p,q,[name,target],0.,kind='CJP',basis='S',
                              description='Source transverse stiffener groove at its machined contact edge')
                assembly.welds[-1]['selected_material']=weld['material']
            groove('WEB',role,at(s,side*inner,-half+radius),at(s,side*inner,half-radius))
            for sign in (-1,1):
                a=at(s,side*(inner+radius),sign*half);b=at(s,side*seam,sign*half);c=at(s,side*outer,sign*half)
                groove(f'FLANGE-{sign}',role,a,b)
                groove(f'TIP-{sign}',inserts_by_tip[side,sign],b,c)


def splice_welds(assembly,spec,roles):
    post,top=roles[spec['member']],roles[spec['upper']]
    d=spec['finished'];width,depth,tf=d['bf'],d['d'],d['tf']
    for i,location in enumerate((-(depth-tf)/2,(depth-tf)/2)):
        assembly.weld('POST-FLANGE-CJP'+str(i),[location,-width/2,0.],[location,width/2,0.],
                      [post,top],0.,kind='CJP',basis='S',description='Post and upper column flange groove weld')
        assembly.welds[-1]['selected_material']=spec['material']
    assembly.weld('POST-WEB-CJP',[-depth/2+tf,0.,0.],[depth/2-tf,0.,0.],
                  [post,top],0.,kind='CJP',basis='S',description='Post and upper column web groove weld')
    assembly.welds[-1]['selected_material']=spec['material']
