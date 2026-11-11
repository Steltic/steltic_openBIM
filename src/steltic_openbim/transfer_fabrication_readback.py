"""Read the actual local cross sections of transfer posts, upper columns and support inserts."""
import numpy as np
from shapely.geometry import LineString,Point,box
from shapely.ops import unary_union

from .joint_mesh_readback import Mesh,TOL,transform,unit
from .selected_plate_readback import grade
from .transfer_joint_readback import face_region


def combined_mesh(shapes):
    vertices=[];faces=[];offset=0
    for mesh in shapes:
        vertices.append(mesh.vertices)
        faces.extend(tuple(j+offset for j in f) for f in mesh.faces)
        offset+=len(mesh.vertices)
    return Mesh(np.vstack(vertices),tuple(faces))


def w_shape(d):
    width,depth,tf,tw=(d[k] for k in ('bf','d','tf','tw'))
    return unary_union([box(-width/2,-depth/2,width/2,-depth/2+tf),
                        box(-tw/2,-depth/2+tf,tw/2,depth/2-tf),
                        box(-width/2,depth/2-tf,width/2,depth/2)])


def localized(mesh,origin,axes):
    return Mesh((mesh.vertices-origin)@np.column_stack(axes),mesh.faces)


def check_sections(mesh,requirements,issues):
    data=[]
    for station,target in requirements:
        where=mesh.section([0.,0.,1.],station,([1.,0.,0.],[0.,1.,0.]))
        diff=float(where.symmetric_difference(target).area)
        data.append(dict(station_in=station,area_in2=float(where.area),difference_in2=diff))
        if diff>TOL*max(1.,target.length):
            issues.append(dict(issue='Actual transfer cross-section differs from its HR-selected stock or treatment',station_in=station,difference_in2=diff))
    return data


def select_roles(handoff,cid):
    result={}
    oc=handoff.get('occurrences',{}).get(cid,{})
    overrides={(s['record_id'],s['field_index']):s['value'] for s in oc.get('overrides',[])}
    for app in oc.get('applications',[]):
        rid=app['record_id'];record=handoff['records'][rid]
        for i in app.get('selected',[]):
            f=record['fields'][i]
            if not f['role'].startswith('transfer_'):continue
            spec=result.setdefault(f['role'],{})
            value=overrides.get((rid,i),f['value']);key=f['field']
            if key in spec and spec[key]!=value:raise ValueError('Conflicting transfer fabrication source '+f['role']+'.'+key)
            spec[key]=value
    return result


def matching_welds(parts,targets,matrix,curves,names,metal,issues):
    result=[]
    for k,p in parts.items():
        if p['kind']!='weld' or set(p.get('connects',[]))!=targets:continue
        pred=transform(p['geometry']['points'],matrix)
        hits=[line for line in curves if line.shape==pred.shape and
              min(np.max(abs(line-pred)),np.max(abs(line[::-1]-pred)))<=TOL]
        if (len(hits)!=1 or p.get('parameters',{}).get('weld_type')!='CJP' or
                metal.upper() not in names.get(k,'').upper()):
            issues.append(dict(issue='Transfer groove weld type, material or actual trajectory differs',part=k))
        else:result.append(hits[0])
    return result


def matching_sections(post,upper,d1,d2,length):
    keys=('d','bf','tf','tw')
    probes={0.,.125,.25};probes.update(np.clip(-z/length,0.,1.) for z in post.vertices[:,2] if -length<z<0.)
    fractions=sorted({0.,1.,*probes})
    tests=[(-length-.01,w_shape(d1))]
    for a,b in zip(fractions,fractions[1:]):
        for weight in (.15,.5,.85):
            fraction=a+(b-a)*weight
            dims={k:d2[k]*(1-fraction)+d1[k]*fraction for k in keys}
            tests.append((-length*fraction,w_shape(dims)))
    return tests,[(.001,w_shape(d2))]


def verify_fabrication(check,c,inst,matrix,parts,meshes,curves,names):
    source=select_roles(check.handoff,c['id'])
    tip=source.get('transfer_support_transition')
    splice=source.get('transfer_post_splice')
    if not tip and not splice:return [],[]
    members=check.members
    bindings=inst['bindings'];wp=np.asarray(c.get('point',inst['origin']),dtype=float)
    issues=[];readings={}
    if tip:
        role,=[r for r,v in bindings.items() if members[v]['kind']=='column']
        m=members[bindings[role]];axis=unit(np.subtract(*m['axis'][::-1]));width=unit(m['local_y'])
        axes=(width,np.cross(axis,width),axis);host=localized(check.rb.member(m['id']),wp,axes)
        dims=check.profiles[m['profile_id']]['dimensions'];l=tip['length_in'];half=dims['bf']/2
        cut=dict(dims,bf=dims['bf']-2*tip['recess_in'])
        probes=[(-l/2-.01,w_shape(dims)),(-l/2+.01,w_shape(cut)),(0.,w_shape(cut)),
                (l/2-.01,w_shape(cut)),(l/2+.01,w_shape(dims))]
        readings['support_sections']=check_sections(host,probes,issues)
        ids=[k for k,p in parts.items() if p.get('parameters',{}).get('source_role')=='transfer_support_transition']
        occupied=set();records=[]
        for k in ids:
            item=localized(meshes[k].transformed(matrix),wp,axes);lo=item.vertices.min(axis=0);hi=item.vertices.max(axis=0)
            side,flange=(1 if s>0 else -1 for s in ((lo[0]+hi[0])/2,(lo[1]+hi[1])/2))
            x=sorted((side*(half-tip['recess_in']),side*(half+tip['projection_in'])))
            y=sorted((flange*dims['d']/2,flange*(dims['d']/2-tip['thickness_in'])))
            target=box(x[0],y[0],x[1],y[1]);stamp=(side,flange)
            if stamp in occupied or not item.closed or max(abs(lo[2]+l/2),abs(hi[2]-l/2))>TOL or grade(names.get(k,''))!=grade(tip['material']):
                issues.append(dict(issue='Actual flange-edge insert extent, integrity, grade or position differs',part=k))
            occupied.add(stamp)
            values=check_sections(item,[(z,target) for z in (-l/2+.01,0.,l/2-.01)],issues)
            seam=matching_welds(parts,{role,k},matrix,curves,names,source['transfer_support_transition_weld']['material'],issues)
            actual=[(line-wp)@np.column_stack(axes) for line in seam]
            longitudinal=[line for line in actual if np.ptp(line[:,2])>l-TOL and
                          max(abs(line[:,0]-side*(half-tip['recess_in'])))<=TOL]
            if len(longitudinal)!=1:issues.append(dict(issue='No unique full-length groove at the support-to-insert seam',part=k))
            records.append(dict(part=k,side=side,flange=flange,actual_sections=values))
        if len(occupied)!=4:issues.append(dict(issue='Selected double-gusset support lacks four distinct integral flange inserts'))
        readings['support_inserts']=records
        check.counts['actual_transfer_support_inserts']+=len(records)
        stiff=source.get('transfer_support_stiffener')
        if stiff:
            ids=[k for k,p in parts.items() if p.get('parameters',{}).get('source_role')=='transfer_support_stiffener']
            inner=dims['tw']/2;outer=dims['bf']/2+tip['projection_in'];half=dims['d']/2-dims['tf']
            radius=stiff['cope_radius_in'];thickness=stiff['thickness_in'];offset=stiff['offset_from_workpoint_in']
            weld_metal=source['transfer_support_stiffener_weld']['material']
            occupied=set();measured=[]
            for k in ids:
                steel=localized(meshes[k].transformed(matrix),wp,axes)
                lo,hi=steel.vertices.min(axis=0),steel.vertices.max(axis=0)
                side=1 if (lo[0]+hi[0])/2>0 else -1
                station=offset if (lo[2]+hi[2])/2>0 else -offset
                expected=box(*[min(side*inner,side*outer),-half,max(side*inner,side*outer),half])
                for corner in (-half,half):
                    expected=expected.difference(Point(side*inner,corner).buffer(radius,quad_segs=80))
                if ((side,station) in occupied or not steel.closed or grade(names.get(k,''))!=grade(stiff['material']) or
                        abs(lo[2]-(station-thickness/2))>TOL or abs(hi[2]-(station+thickness/2))>TOL):
                    issues.append(dict(issue='Actual transverse stiffener count, grade, thickness or station differs from HR',part=k))
                occupied.add((side,station))
                values=check_sections(steel,[(station+f*thickness,expected) for f in (-.45,0.,.45)],issues)
                host_lines=matching_welds(parts,{role,k},matrix,curves,names,weld_metal,issues)
                tip_lines=[line for r in records for line in matching_welds(parts,{k,r['part']},matrix,curves,names,weld_metal,issues)]
                local=[(line-wp)@np.column_stack(axes) for line in host_lines+tip_lines]
                actual=unary_union([LineString(line[:,:2]) for line in local if max(abs(line[:,2]-station))<=TOL])
                source_edges=[LineString([(side*inner,-half+radius),(side*inner,half-radius)])]
                source_edges.extend(LineString([(side*(inner+radius),f*half),(side*outer,f*half)]) for f in (-1,1))
                lengths=[float(actual.intersection(edge.buffer(TOL,cap_style=2)).length) for edge in source_edges]
                if (len(host_lines)!=3 or len(tip_lines)!=2 or
                        any(e.difference(actual.buffer(TOL)).length>TOL for e in source_edges) or
                        abs(lengths[0]-stiff['net_web_contact_in'])>TOL or
                        any(abs(l-stiff['net_flange_contact_in'])>TOL for l in lengths[1:])):
                    issues.append(dict(issue='Actual stiffener groove welds fail their complete web or composite flange contact',part=k,measured_edges_in=lengths))
                measured.append(dict(part=k,station_in=station,web_flange_edge_lengths_in=lengths,sections=values))
            if len(occupied)!=stiff['count']:issues.append(dict(issue='Wrong number of transverse stiffeners at the support',actual=len(occupied)))
            readings['support_stiffeners']=measured
            check.counts['actual_transfer_support_stiffeners']+=len(measured)
    if splice:
        post,=[r for r,v in bindings.items() if members[v]['kind']=='transfer_vertical']
        upper,=[r for r,v in bindings.items() if members[v]['kind']=='column' and members[v]['profile_id'].upper()==splice['upper_section'].upper()]
        p=members[bindings[post]];u=members[bindings[upper]]
        axis=unit(np.subtract(max(u['axis'],key=lambda q:np.linalg.norm(wp-q)),wp))
        width=unit(p['local_y']);axes=(width,np.cross(axis,width),axis)
        a=localized(check.rb.member(p['id']),wp,axes);b=localized(check.rb.member(u['id']),wp,axes)
        before=check.profiles[p['profile_id']]['dimensions'];after=check.profiles[u['profile_id']]['dimensions']
        checks,mating=matching_sections(a,b,before,after,splice['transition_length_in'])
        readings['taper_sections']=check_sections(a,checks,issues)
        readings['upper_column_section']=check_sections(b,mating,issues)
        n=np.array([0.,0.,1.]);basis=np.array([[1.,0.],[0.,1.],[0.,0.]])
        full=face_region(a,n,0.,basis).intersection(face_region(b,n,0.,basis))
        w=w_shape(after)
        if full.symmetric_difference(w).area>TOL*w.length:
            issues.append(dict(issue='Post and upper column terminal surfaces do not fully meet at the workpoint'))
        paths=matching_welds(parts,{post,upper},matrix,curves,names,splice['material'],issues)
        local=[(path-wp)@np.column_stack(axes) for path in paths]
        bf,dep,tf=after['bf'],after['d'],after['tf']
        spans=[LineString([(-bf/2,h),(bf/2,h)]) for h in (-(dep-tf)/2,(dep-tf)/2)]
        spans.append(LineString([(0.,-dep/2+tf),(0.,dep/2-tf)]))
        if len(local)!=3 or any(sum(np.max(abs(line[:,2]))<=TOL and target.hausdorff_distance(LineString(line[:,:2]))<=TOL
                                    for line in local)!=1 for target in spans):
            issues.append(dict(issue='Upper post CJP paths do not cover each mating flange and the web'))
        readings['splice_welds']=len(local)
        check.counts['actual_transfer_tapered_post_splices']+=1
    return [dict(role='connection_fabrication',measurements=[],actual=readings)],issues
