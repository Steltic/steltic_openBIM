"""Actual CFS wall receivers and centroid datums for fixture detail recipes.

This selects existing geometry. Any local cutback is an explicit fictional fit
decision, never a replacement member selection or a strength calculation.
"""
import copy,itertools,math
from collections import defaultdict
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_receiver_geometry import horizontal_frame,point,vector
from .review_cfs_occurrences import axis


class Nearby:
    def __init__(self,members):
        self.cells=defaultdict(list)
        for m in members:
            a,b=axis(m)
            for key in itertools.product(*(range(math.floor(min(x,y)/64),math.floor(max(x,y)/64)+1) for x,y in zip(a,b))):self.cells[key].append(m)
    def get(self,p):
        seen=set();result=[]
        for key in itertools.product(*(range(math.floor(v/64)-1,math.floor(v/64)+2) for v in p)):
            for m in self.cells[key]:
                if m['id'] not in seen:seen.add(m['id']);result.append(m)
        return result


def local_member(m,origin,axes,extent=24):
    a,b=axis(m);u=unit(sub(b,a));length=math.dist(a,b);t=max(0,min(length,dot(sub(origin,a),u)))
    ends=[add(a,mul(u,s)) for s in (max(0,t-extent),min(length,t+extent))]
    return dict(member_id=m['id'],profile_id=m['profile_id'],kind=m['kind'],axis=[point(q,origin,axes) for q in ends],local_y=vector(m['local_y'],axes),basis=m.get('basis','S'))


def signature(data):
    """Shape identity excludes occurrence IDs but preserves every local datum."""
    if isinstance(data,dict):return {k:signature(v) for k,v in data.items() if k not in ('member_id','basis') and not k.endswith('_ids')}
    if isinstance(data,list):return [signature(v) for v in data]
    if isinstance(data,float):return round(data,6)
    return data


def bind(model):
    lookup={m['id']:m for m in model['members']};near=Nearby(model['members']);profiles={p['id']:p for p in model['profiles']}
    from .assembly_templates import effective
    from .pilots.geometry import strips
    remove=set()
    for c in model['connections']:
        family=c['detail_ref']['id'];primary=lookup[c['member_ids'][0]];origin=c['point'];a,b=axis(primary)
        if family in ('review_final_header','test_wall_opening') and primary['kind'] in ('opening_header','opening_sill'):
            far=max(primary['axis'],key=lambda q:math.dist(q,origin));axes=horizontal_frame(sub(far,origin));candidates=[]
            for m in near.get(origin):
                if m['kind']!='opening_jamb':continue
                aa,bb=axis(m)
                if min(aa[2],bb[2])-.01<=origin[2]<=max(aa[2],bb[2])+.01 and math.dist(aa[:2],origin[:2])<.01:candidates.append(m)
            if candidates:
                jamb=sorted(candidates,key=lambda m:m['id'])[0];u=unit(sub(*reversed(jamb['axis'])));y=jamb['local_y'];z=cross(u,y)
                face=max(dot(add(mul(y,v[0]),mul(z,v[1])),axes[0]) for poly in strips(profiles[jamb['profile_id']],profiles) for v in poly)
                end=min(range(2),key=lambda i:math.dist(primary['axis'][i],origin));offset=mul(axes[0],face+.125)
                if math.dist(primary['end_offsets'][end],offset)>.001:
                    old=copy.deepcopy(primary['end_offsets'][end]);primary['end_offsets'][end]=offset
                    model.setdefault('changes',[]).append(dict(kind='opening_end_face_cutback',member_id=primary['id'],end=end,previous_offset=old,offset=offset,basis='A: header/sill ends 1/8 in clear of the actual jamb face; original workline and selected section retained'))
                data=dict(primary=local_member(primary,origin,axes,32),support=local_member(jamb,origin,axes,24),face_in=face)
                c.setdefault('parameters',{})['physical_opening_joint']=data
                c['member_ids']=list(dict.fromkeys(c['member_ids']+[jamb['id']]))
                if primary['kind']=='opening_header':
                    end=max(range(2),key=lambda i:jamb['axis'][i][2]);top=jamb['axis'][end]
                    if abs(top[2]-origin[2]-effective(profiles,primary['profile_id'])/2)<.01:
                        redundant=next((other for other in model['connections'] if other['id']==jamb['id']+':'+str(end) and other['detail_ref']['id']=='test_wall_opening'),None)
                        if redundant:
                            remove.add(redundant['id']);link=dict(member_id=jamb['id'],end='end' if end else 'start',connection_id=c['id'],basis='A: the existing header/jamb angle serves the jamb head; do not duplicate hardware at the top-flange datum')
                            if link not in model.setdefault('connection_endpoint_links',[]):model['connection_endpoint_links'].append(link)
        elif family=='test_wall_opening' and primary['kind']=='opening_jamb':
            if math.dist(origin,min(primary['axis'],key=lambda q:q[2]))>.01:continue
            candidates=[]
            for m in near.get(origin):
                if m['kind'] not in ('bottom_track','ordinary_track','tier_track'):continue
                aa,bb=axis(m);u=unit(sub(bb,aa));length=math.dist(aa,bb);s=dot(sub(origin,aa),u)
                if not -.01<=s<=length+.01:continue
                q=add(aa,mul(u,s))
                if math.dist(q[:2],origin[:2])<.01 and abs(q[2]-origin[2])<.25:candidates.append(m)
            if candidates:
                track=sorted(candidates,key=lambda m:m['id'])[0];aa,bb=axis(track);axes=horizontal_frame(sub(bb,aa))
                from .review_located_wall_details import section_bounds
                jamb_data=local_member(primary,origin,axes)
                outline=section_bounds(profiles,jamb_data);bounds=[min(v[0][0] for v in outline),max(v[0][1] for v in outline)]
                # A cut track terminating at the jamb workline must actually
                # extend beneath its whole foot. Preserve the workline and log
                # this physical end allowance as an accepted fit proposal.
                for end in range(2):
                    oldpoint=axis(track)[end];station=point(oldpoint,origin,axes)[0]
                    if math.dist(oldpoint[:2],origin[:2])<.25:
                        target=bounds[0]-.125 if end==0 else bounds[1]+.125
                        offset=add(track['end_offsets'][end],mul(axes[0],target-station))
                        if math.dist(offset,track['end_offsets'][end])>.001:
                            previous=copy.deepcopy(track['end_offsets'][end]);track['end_offsets'][end]=offset
                            model.setdefault('changes',[]).append(dict(kind='jamb_bottom_track_end_allowance',member_id=track['id'],end=end,previous_offset=previous,offset=offset,basis='A: extend the actual cut track beneath the complete jamb foot; workline and source section retained'))
                c.setdefault('parameters',{})['physical_jamb_base']=dict(jamb=local_member(primary,origin,axes),track=local_member(track,origin,axes))
                c['member_ids']=list(dict.fromkeys(c['member_ids']+[track['id']]))
                c['source_context_records']=c['design_record_ids'];c['design_record_ids']=[]
                c['basis']='A: jamb-to-track foot clips; header connection source remains on the actual header occurrence'
        elif family in ('cfs_stud_bridging','review_sheathing'):
            if abs(a[2]-b[2])>.01:continue
            axes=horizontal_frame(sub(b,a));candidates=[]
            for m in near.get(origin):
                if m['kind'] not in ('stud','chord','opening_jamb','column'):continue
                aa,bb=axis(m);lo,hi=sorted((aa[2],bb[2]))
                if not lo-.25<=origin[2]<=hi+.25:continue
                delta=sub(aa,origin)
                if abs(dot(delta,axes[1]))>.01:continue
                distance=abs(dot(delta,axes[0]))
                if distance<=16:
                    if family=='cfs_stud_bridging':
                        from .review_located_wall_details import section_bounds
                        local=local_member(m,origin,axes)
                        transverse=[v for v in section_bounds(profiles,local) if v[0][1]-v[0][0]<.3 and v[1][0]<-.5 and v[1][1]>.5]
                        # A corner may contain both wall stud directions at the
                        # same station. Select an actual web facing this bridge.
                        if not transverse:continue
                    candidates.append((distance,m['id'],m))
            if candidates:
                stud=min(candidates)[2];sd=local_member(stud,origin,axes);extra={}
                if family=='cfs_stud_bridging':
                    from .review_located_wall_details import section_bounds
                    into=1 if sum(point(q,origin,axes)[0] for q in axis(primary))/2>sd['axis'][0][0] else -1
                    # Locate the outermost actual web towards the bridge, not
                    # the centre of a multi-ply chord's hollow rod space.
                    webs=[v for v in section_bounds(profiles,sd) if v[0][1]-v[0][0]<.3 and v[1][0]<-.5 and v[1][1]>.5]
                    if not webs:raise ValueError('Bridging receiver has no actual transverse web')
                    web=max(webs,key=lambda v:into*v[0][1 if into>0 else 0]);face=web[0][1 if into>0 else 0]
                    end=min(range(2),key=lambda i:math.dist(primary['axis'][i],origin));offset=mul(axes[0],face+into*.125)
                    if math.dist(primary['end_offsets'][end],offset)>.001:
                        previous=copy.deepcopy(primary['end_offsets'][end]);primary['end_offsets'][end]=offset
                        model.setdefault('changes',[]).append(dict(kind='bridging_end_web_cutback',member_id=primary['id'],end=end,previous_offset=previous,offset=offset,basis='A: bridging ends 1/8 in clear of the actual outer receiver web; no centre-of-chord attachment is implied'))
                    extra=dict(web_face_in=face,web_thickness_in=web[0][1]-web[0][0])
                data=dict(primary=local_member(primary,origin,axes),stud=sd,**extra)
                c.setdefault('parameters',{})['physical_wall_attachment']=data
                c['member_ids']=list(dict.fromkeys(c['member_ids']+[stud['id']]))
        elif family in ('review_cfs_floor','review_cfs_sill','review_final_cfs_joist','review_cfs_joist'):
            if family=='review_cfs_sill' and primary.get('level')==1:continue
            is_joist=primary['kind']=='joist'
            if not is_joist and primary['kind'] not in ('top_track','bottom_track','ordinary_track','tier_track'):continue
            if is_joist:
                far=max(primary['axis'],key=lambda q:math.dist(q,origin));into=unit(sub(far,origin));along=cross(into,[0,0,1]);axes=horizontal_frame(along)
            else:axes=horizontal_frame(sub(b,a))
            candidates=near.get(origin);tracks=[];joists=[];parallel=[];studs=[]
            for m in candidates:
                aa,bb=axis(m);local=[point(q,origin,axes) for q in (aa,bb)];u=unit(sub(bb,aa))
                if m['kind'] in ('top_track','bottom_track','ordinary_track','tier_track') and abs(dot(u,axes[0]))>.999:
                    if abs(local[0][1])<.01 and min(q[0] for q in local)-.01<=0<=max(q[0] for q in local)+.01 and abs(local[0][2])<30:tracks.append(m)
                elif m['kind']=='joist' and abs(dot(u,axes[1]))>.999:
                    if abs(local[0][0])<=24 and abs(local[0][2])<24 and any(abs(q[1])<.01 for q in local):joists.append(m)
                elif m['kind'] in ('joist','rim_track','floor_rim') and abs(dot(u,axes[0]))>.999:
                    if abs(local[0][1])<.01 and abs(local[0][2])<24 and min(q[0] for q in local)-.01<=0<=max(q[0] for q in local)+.01:parallel.append(m)
                elif m['kind'] in ('stud','chord','opening_jamb'):
                    if abs(local[0][1])<.01 and abs(local[0][0])<24 and min(q[2] for q in local)<30 and max(q[2] for q in local)>-30:studs.append(m)
            # Keep the closest lower and upper track. A roof has no upper wall.
            chosen=[]
            for direction in (-1,1):
                options=[m for m in tracks if m['local_y'][2]*direction>.99]
                if options:
                    distance=min(abs(axis(m)[0][2]-origin[2]) for m in options)
                    chosen.extend(m for m in options if abs(abs(axis(m)[0][2]-origin[2])-distance)<.01)
            selected_joists=[]
            for side in (-1,1):
                options=[m for m in joists if (sum(point(q,origin,axes)[1] for q in axis(m))/2)*side>0]
                if options:selected_joists.append(min(options,key=lambda m:(abs(point(axis(m)[0],origin,axes)[0]),abs(axis(m)[0][2]-origin[2]),m['id'])))
            if is_joist and primary not in selected_joists:selected_joists.insert(0,primary)
            if not selected_joists and parallel:
                # At a collinear end joint there can be a real floor member on
                # each side. One arbitrary left-hand member cannot attach a
                # right-hand track which has no overlap with it.
                for side in (-1,1):
                    options=[m for m in parallel if max(side*point(q,origin,axes)[0] for q in axis(m))>2]
                    if options:
                        selected=min(options,key=lambda m:(abs(axis(m)[0][2]-origin[2]),m['id']))
                        if selected not in selected_joists:selected_joists.append(selected)
            selected_studs=[]
            for side in (-1,1):
                options=[m for m in studs if (sum(q[2] for q in axis(m))/2-origin[2])*side>0]
                if options:selected_studs.append(min(options,key=lambda m:(abs(point(axis(m)[0],origin,axes)[0]),abs(sum(q[2] for q in axis(m))/2-origin[2]),m['id'])))
            if primary not in chosen+selected_joists:chosen.insert(0,primary)
            # A full floor stack requires actual floor framing. Leave unresolved
            # roof/supplier interfaces to their own recipes and fit findings.
            if not selected_joists:continue
            items=list(dict((m['id'],m) for m in chosen+selected_joists+selected_studs).values())
            data=dict(receivers=[local_member(m,origin,axes,32) for m in items],joist_ids=[m['id'] for m in selected_joists],track_ids=[m['id'] for m in chosen],stud_ids=[m['id'] for m in selected_studs])
            c.setdefault('parameters',{})['physical_floor_stack']=data
            c['member_ids']=list(dict.fromkeys(c['member_ids']+[m['id'] for m in items]))
    model['connections'][:]=[c for c in model['connections'] if c['id'] not in remove]
