"""Accepted pilot bracing fit at actual beam flanges and transverse infills."""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .review_receiver_geometry import horizontal_frame,point,vector,extract


def bind(members,connections,profiles,changes):
    lookup={m['id']:m for m in members};remove=set();links=[]
    for c in list(connections):
        if c['detail_ref']['id']!='hr_required_bottom_flange_brace' or c['id'].startswith('TEST-C:'):continue
        beam=lookup[c['member_ids'][0]];kicker=lookup.get('TEST-KICK-'+c['id'])
        if kicker is None:raise ValueError('Required pilot brace has no physical kicker')
        origin=c['point'];u=unit(sub(*beam['axis'][::-1]));v=cross([0,0,1],u);options=[]
        for support in members:
            if support['kind']!='infill' or support.get('level')!=beam.get('level'):continue
            aa,bb=[add(q,o) for q,o in zip(support['axis'],support['end_offsets'])];su=unit(sub(bb,aa))
            for sign in (-1,1):
                desired=add(origin,mul(v,36*sign));s=dot(sub(desired,aa),su)
                if not 6<=s<=math.dist(aa,bb)-6:continue
                q=add(aa,mul(su,s));span=abs(dot(sub(q,origin),u))
                transverse=abs(dot(sub(q,origin),v))
                if span>60.01 or not 6<=transverse<=120.01:continue
                options.append((span,math.dist(q,origin),support['id'],sign,support,q))
        if not options:raise ValueError('No actual adjacent infill for pilot kicker '+c['id'])
        *_,support,end=min(options,key=lambda row:row[:4])
        before=copy.deepcopy(kicker['axis'])
        side=1 if dot(sub(end,origin),v)>0 else -1
        foot=add(origin,add(mul(v,side*(profiles[beam['profile_id']]['dimensions']['bf']/2+2)),[0,0,-8]))
        ku=unit(sub(end,foot));head=add(end,mul(ku,-2))
        normal=unit(cross([0,0,1],ku));support_u=unit(sub(*support['axis'][::-1]))
        if abs(dot(support_u,normal))<1e-7:
            # Collinear-in-plan brace/receiver: its gusset laps the web face.
            shift=mul(normal,profiles[support['profile_id']]['dimensions']['tw']/2+.375)
            foot=add(foot,shift);head=add(head,shift)
        kicker['axis']=[foot,head]
        ku=unit(sub(*kicker['axis'][::-1]));kicker['local_y']=unit(cross([0,0,1],ku))
        kicker['fit_basis']='A: single angle on a gusset below/outside the actual bottom flange to the nearest actual adjacent infill web. Transverse infills are reached 36 in into their bay; parallel infills across the actual 10 ft spacing. Source force/stiffness requirements remain; no new brace/attachment capacity check.'
        c['member_ids']=[beam['id'],support['id'],kicker['id']]
        c['parameters']=dict(physical_hr_kicker=dict(beam_id=beam['id'],support_id=support['id'],kicker_id=kicker['id'],
            support_axis=[point(q,origin,horizontal_frame(u)) for q in support['axis']],
            brace_axis=[point(q,origin,horizontal_frame(u)) for q in kicker['axis']],
            support_web_workpoint=point(end,origin,horizontal_frame(u))))
        c['representation']='Actual beam, infill and accepted fictional kicker with both end attachments'
        for endname in ('start','end'):
            remove.add('TEST-C:'+kicker['id']+':'+endname)
            links.append(dict(member_id=kicker['id'],end=endname,connection_id=c['id'],basis=kicker['fit_basis']))
        changes.append(dict(kind='pilot_kicker_actual_receivers',connection_id=c['id'],previous_axis=before,axis=copy.deepcopy(kicker['axis']),member_ids=list(c['member_ids']),basis=kicker['fit_basis']))
    connections[:]=[c for c in connections if c['id'] not in remove]
    return links


def draw(ctx):
    a=ctx.a;beam,support,kicker=ctx.ms;axes=horizontal_frame(sub(*beam['axis'][::-1]));origin=ctx.c['point']
    extract(ctx,beam,'BEAM',axes,42);extract(ctx,support,'INFILL',axes,60);extract(ctx,kicker,'KICKER',axes,120)
    for part in a.parts:
        if part['id'] in ('BEAM','INFILL'):part['drawing_style']='outline'
    start,end=[point(q,origin,axes) for q in kicker['axis']]
    # The bolt pattern follows the angle axis and its actual long leg. Plates
    # meet the beam flange / infill web, instead of floating at a workpoint.
    from .review_assemblies import hull
    ku=unit(sub(end,start));normal=vector(kicker['local_y'],axes);depth=cross(ku,normal);thick=.375
    support_point=ctx.params['physical_hr_kicker']['support_web_workpoint']
    su=vector(unit(sub(*support['axis'][::-1])),axes);webnormal=cross(su,[0,0,1])
    if dot(sub(start,support_point),webnormal)<0:webnormal=mul(webnormal,-1)
    webface=add(support_point,mul(webnormal,ctx.p[support['profile_id']]['dimensions']['tw']/2))
    denom=dot(su,normal)
    if abs(denom)<1e-7:
        if abs(dot(sub(webface,start),normal)+thick)>1e-5:raise ValueError('Parallel kicker gusset must actually lap the selected web face')
    else:webface=add(webface,mul(su,(-thick-dot(sub(webface,start),normal))/denom))
    side=1 if start[1]>0 else -1;half=ctx.p[beam['profile_id']]['dimensions']['bf']/2
    lower_mid=[0,side*(half-1.5),0]
    lower_mid[0]=(-thick-dot(sub(lower_mid,start),normal))/normal[0] if abs(normal[0])>1e-7 else 0
    horizontal=unit(cross(normal,[0,0,1]));span=1.5/abs(horizontal[1])
    seams=[(add(lower_mid,mul(horizontal,-span)),add(lower_mid,mul(horizontal,span))),
           (add(webface,[0,0,-4]),add(webface,[0,0,4]))]
    for i,(q,host) in enumerate(((start,'BEAM'),(end,'INFILL'))):
        label='TAB'+str(i);stations=(2,5) if i==0 else (-5,-2)
        centres=[add(add(q,mul(ku,s)),mul(depth,1.5)) for s in stations]
        points=[add(v,mul(normal,-thick)) for v in centres]
        outline=[]
        for v in points:
            for x,z in ((-1.5,-1.5),(-1.5,1.5),(1.5,-1.5),(1.5,1.5)):
                outline.append(add(v,add(mul(ku,x),mul(depth,z))))
        outline.extend(seams[i]);coords=hull([(dot(sub(v,start),ku),dot(sub(v,start),depth)) for v in outline])
        polygon=[add(start,add(add(mul(ku,x),mul(depth,z)),mul(normal,-thick))) for x,z in coords]
        host_part=next(part for part in a.parts if part['id']==host)
        polygon=clear_host(polygon,normal,thick,ku,depth,host_part['member'],ctx.p)
        a.polygon(label,polygon,thick,normal=normal,basis='A',description='A fitted gusset to actual host face; two holes at 3 in pitch, 1.5 in edge envelope; local attachment capacity unverified')
        group=a.fastener('B'+str(i),points,normal,.75,.625,['KICKER',label],'A two 3/4 in A325 bolts through the actual angle leg and gusset; 3 in pitch, 1.5 in transverse gauge','A')
        from .connection_cuts import drill_receivers
        drill_receivers(a,group,.8125)
        a.weld('W'+str(i),*seams[i],[host,label],.25,basis='A',description='A 1/4 in gusset fillets to actual '+('bottom flange' if i==0 else 'infill web'))
    a.dim(start,end,'Actual kicker workline / A',basis='A');a.front_axes=(1,2);a.section_axis=2;a.section_at=end[2]
    a.notes.append(kicker['fit_basis'])
    a.notes.append('Receiving beam and infill are shown as dashed outlines in the elevation and isometric so both brace attachments remain visible. Their full physical geometry is retained; this is a drawing display convention.')


def clear_host(polygon,normal,thick,u,v,member,profiles):
    """Trim a plate to finite section material present across its full thickness."""
    from shapely import set_precision
    from shapely.geometry import Polygon,MultiPoint
    from shapely.ops import unary_union
    from .assembly_scene import clip_faces
    from .pilots.geometry import member_solids
    base=polygon[0];lo=dot(base,normal);hi=lo+thick
    project=lambda q:(dot(sub(q,base),u),dot(sub(q,base),v))
    original=Polygon([project(q) for q in polygon]);occupied=[]
    for solid in member_solids(member,profiles):
        stations=[dot(q,normal) for face in solid for q in face]
        if max(stations)<=lo+1e-6 or min(stations)>=hi-1e-6:continue
        layer=clip_faces(solid,normal,lo)
        if not layer:continue
        layer=clip_faces(layer,mul(normal,-1),-hi)
        if layer:
            footprint=MultiPoint([project(q) for face in layer for q in face]).convex_hull
            if footprint.area>1e-8:occupied.append(footprint)
    if not occupied:return polygon
    result=set_precision(original.difference(unary_union(occupied)),1e-7)
    if original.area-result.area<1e-8:return polygon
    if result.geom_type!='Polygon' or result.interiors:
        raise ValueError('Receiving member splits the fitted gusset or traps an interior cut')
    return [add(base,add(mul(u,x),mul(v,y))) for x,y in list(result.exterior.coords)[:-1]]
