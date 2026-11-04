"""Selected X-brace crossings, separate from coincident analysis worklines.

Gold connection selections are retained. Missing local set-out is explicitly A;
this recipe does not approve a new brace restraint or rerun capacity checks.
"""
import copy,math,re
from collections import defaultdict
from .assembly_templates import NUMBER,number,effective
from .pilots.model import add,sub,mul,dot,cross,unit


def value(pattern,text,default):
    hit=re.search(pattern,text,re.I)
    return number(hit[1]) if hit else default


def selection(records,profiles,left,right):
    text='\n'.join(str(r.get('components','')) for r in records)
    checks='\n'.join(str(c.get('limit_state','')) for r in records for c in r.get('checks',[]))
    selected=bool(re.search(r'\bcrossing\b',text,re.I))
    thickness=value(r'slotted(?: on two opposite walls)? for a '+NUMBER+r' in',text,.5)
    length=value(r'welds? x '+NUMBER+r' in',text,8)
    size=value(r'four '+NUMBER+r' in E70',text,.25)
    v=unit(sub(*reversed(left['axis'])));u=unit(sub(*reversed(right['axis'])))
    sine=math.sqrt(max(0,1-dot(v,u)**2));depth=effective(profiles,left['profile_id'])
    half_depth=effective(profiles,right['profile_id'])
    # Explicit source end distance takes precedence. Otherwise the proposed
    # clearance accounts for the crossing angle and both finite tube depths.
    end_default=(depth+half_depth*abs(dot(v,u)))/(2*sine)+2*thickness+1
    end=value(r'each half ends '+NUMBER+r' in from the crossing',text,end_default)
    width=value(r'gusset '+NUMBER+r' in wide',text,2*(end+length+1))
    slot_length=value(r'slot fillets .*?four slot edges, '+NUMBER+r' in long',checks,width+1)
    continuous_width=value(r'two walls slotted \('+NUMBER+r' in',checks,thickness+.125)
    return dict(mode='continuous_and_split',source_selected=selected,thickness_in=thickness,
        source_width_in=width if re.search(r'gusset '+NUMBER+r' in wide',text,re.I) else None,
        proposed_width_in=width,continuous_slot_length_in=slot_length,continuous_slot_width_in=continuous_width,
        continuous_weld_size_in=value(r'slot fillets '+NUMBER+r' in',text,size),
        split_weld_length_in=length,split_weld_size_in=size,split_slot_width_in=thickness+.125,
        end_distance_in=end,end_distance_basis='S' if re.search(r'each half ends',text,re.I) else 'A',
        slot_length_basis='S' if re.search(r'four slot edges, '+NUMBER+r' in long',checks,re.I) else 'A',
        local_fit_basis='A: plate free edges, machining end clearances and unspecified fit; source selections remain in the record',
        capacity_status='source_checked_selection' if selected else 'proposal_not_capacity_checked')


def split_member(member,point,gap):
    a,b=member['axis'];v=sub(b,a);fraction=dot(sub(point,a),v)/dot(v,v)
    if not 0<fraction<1:raise ValueError('Crossing must be interior to the split brace')
    claims=[dict(analysis_id=aid,start=0.,end=1.) for aid in member.get('analysis_ids',[])]+member.get('analysis_segments',[])
    if len(claims)>1:raise ValueError('Split crossing needs a single explicit analysis interval')
    direction=unit(v);parts=[]
    for side,(lo,hi,ends,offsets) in enumerate(((0,fraction,[a,point],[member['end_offsets'][0],mul(direction,-gap)]),(fraction,1,[point,b],[mul(direction,gap),member['end_offsets'][1]]))):
        part=copy.deepcopy(member);part.update(id=member['id']+':crossing-half:'+str(side),axis=copy.deepcopy(ends),end_offsets=copy.deepcopy(offsets),analysis_ids=[],analysis_segments=[],source_member_ids=[member['id']],joint_workpoints=copy.deepcopy(ends))
        if claims:
            claim=claims[0];start=claim['start'];span=claim['end']-start
            part['analysis_segments']=[dict(analysis_id=claim['analysis_id'],start=start+lo*span,end=start+hi*span)]
        part['crossing_piece_basis']='Source split diagonal; A unspecified cut-back' if member.get('basis')=='S' else 'Accepted fictional crossing piece'
        parts.append(part)
    return parts


def slot(member,point,normal,lo,hi,width,connection_id,basis):
    a,b=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])];direction=unit(sub(b,a));length=math.dist(a,b)
    transverse=[member['local_y'],cross(direction,member['local_y'])]
    coordinate=max(range(2),key=lambda i:abs(dot(transverse[i],normal)))
    if abs(dot(transverse[coordinate],normal))<.99999:raise ValueError('Crossing slot plane is not aligned with the selected section axes')
    station=dot(sub(point,a),direction)
    start=max(0,station+lo);end=min(length,station+hi)
    if end<=start:raise ValueError('Selected slot misses its physical brace')
    member.setdefault('slots',[]).append(dict(start_in=start,end_in=end,width_in=width,centre_in=0,section_axis=coordinate,
        connection_id=connection_id,basis=basis,end_shape='rectangular design envelope; machining radii not specified'))


def apply(builder):
    if builder.key not in ('hr3','hr18','hr21','hr30','hr33'):return
    groups=defaultdict(list)
    for m in builder.members:
        if m['kind']=='brace':groups[tuple(round((a+b)/2,6) for a,b in zip(*m['axis']))].append(m)
    for number_,(point,group) in enumerate(groups.items()):
        if len(group)<2:continue
        if len(group)!=2:raise ValueError('Multiple braces at crossing need an explicit selection')
        left,right=sorted(group,key=lambda m:m['id']);ids={left['id'],right['id']}
        existing=next((c for c in builder.connections if c['detail_ref']['id']=='review_brace_crossing' and set(c['member_ids'])==ids),None)
        refs=existing['design_record_ids'] if existing else [builder.record('connections','conn-brace-'+m['profile_id']) for m in (left,right)]
        refs=list(dict.fromkeys(r for r in refs if r))
        records=[builder.records[r]['data'] for r in refs]
        chosen=selection(records,builder.profiles,left,right);cid=existing['id'] if existing else 'X-CROSS-'+str(number_)
        if existing:builder.connections.remove(existing)
        halves=split_member(right,list(point),chosen['end_distance_in'])
        for half in halves:
            half['crossing_piece_basis']=('S: selected split diagonal; ' if chosen['source_selected'] else 'A: accepted fictional split-diagonal proposal; ')+chosen['end_distance_basis']+': end cut-back, source analysis interval unchanged'
        normal=unit(cross(sub(*reversed(left['axis'])),sub(*reversed(right['axis']))))
        slot(left,point,normal,-chosen['continuous_slot_length_in']/2,chosen['continuous_slot_length_in']/2,chosen['continuous_slot_width_in'],cid,chosen['slot_length_basis']+': crossing slot length; explicit clearance and rectangular-end design envelope')
        extension=chosen['split_weld_length_in']+.5
        for half in halves:
            ends=[add(p,o) for p,o in zip(half['axis'],half['end_offsets'])];close=min(range(2),key=lambda i:math.dist(ends[i],point))
            slot(half,ends[close],normal,0 if close==0 else -extension,extension if close==0 else 0,chosen['split_slot_width_in'],cid,'S: source weld length; A: 1/2 in slot-end clearance and rectangular machining envelope')
        builder.members.remove(right);builder.members.extend(halves)
        for c in builder.connections:
            if right['id'] not in c['member_ids']:continue
            selected=min(halves,key=lambda h:min(math.dist(q,c['point']) for q in h['axis']))
            c['member_ids']=[selected['id'] if mid==right['id'] else mid for mid in c['member_ids']]
        con=builder.connection(cid,'review_brace_crossing',point,[left]+halves,refs,parameters=dict(joint='crossing',crossing=chosen),basis='S' if chosen['source_selected'] else 'A')
        if not chosen['source_selected']:
            con['source_context_records']=list(refs);con['design_record_ids']=[]
            con['scope']='coordination';con['engineering_status']='not_checked'
        builder.changes.append(dict(kind='explicit_brace_crossing',connection_id=cid,original_split_member=copy.deepcopy(right),physical_halves=[h['id'] for h in halves],selection=chosen,source_record_ids=refs))
    builder.note('X-CROSSINGS','Source centre-gusset selections are located explicitly. One diagonal remains continuous with a slot; the other has two physical halves. Unspecified fit and slot end clearances are A. '+('HR33 has no source centre connection: the gusset/split arrangement is an accepted fictional coordination proposal, with restraint, member and connection capacity checks still required.' if builder.key=='hr33' else 'Source analysis members and their complete interval mappings are retained.'))


def draw(ctx):
    from .review_receiver_geometry import horizontal_frame,extract,vector,point
    a=ctx.a;selected=ctx.params['crossing'];continuous,low,high=ctx.ms
    axes=horizontal_frame(sub(*reversed(continuous['axis'])))
    normal=[0,1,0];origin=ctx.c['point'];t=selected['thickness_in'];extent=max(45,selected['end_distance_in']+selected['split_weld_length_in']+20)
    for name,member in (('CONT',continuous),('SPLIT-1',low),('SPLIT1',high)):
        extract(ctx,member,name,axes,extent)
    v=unit(vector(sub(*reversed(continuous['axis'])),axes));n=cross(normal,v)
    u=unit(vector(sub(*reversed(high['axis'])),axes))
    if dot(u,n)<0:u=mul(u,-1)
    tail=selected['end_distance_in']+selected['split_weld_length_in']+1
    half_width=selected['proposed_width_in']/2;slot_half=selected['continuous_slot_length_in']/2
    depth=effective(ctx.p,continuous['profile_id']);half_depth=effective(ctx.p,high['profile_id'])
    end_normal=cross(normal,u);tail_points=[add(mul(u,tail),mul(end_normal,side*max(half_depth/2+1,half_width))) for side in (-1,1)]
    tail_points.sort(key=lambda q:dot(q,v));tl,tr=tail_points
    h=depth/2
    # A free-edge outline joins the retained centre width to each selected half.
    # The small flare at each continuous-tube wall follows its selected slot.
    local=lambda x,z:add(mul(v,x),mul(n,z))
    polygon=[local(-half_width,0),local(-slot_half,-h),mul(tr,-1),mul(tl,-1),local(slot_half,-h),local(half_width,0),local(slot_half,h),tr,tl,local(-slot_half,h)]
    a.polygon('GUSSET',[add(q,[0,-t/2,0]) for q in polygon],t,basis='A',description=f'S selected thickness {t:g} in; A fitted free-edge outline and end clearance' if selected['source_selected'] else f'A proposed {t:g} in centre gusset; source has no centre-connection selection')
    for name,member in (('CONT',continuous),('SPLIT-1',low),('SPLIT1',high)):
        direction=unit(vector(sub(*reversed(member['axis'])),axes));inplane=cross(normal,direction)
        d=effective(ctx.p,member['profile_id'])
        if name=='CONT':start=mul(direction,-slot_half);length=2*slot_half;size=selected['continuous_weld_size_in']
        else:
            ends=[point(add(q,o),origin,axes) for q,o in zip(member['axis'],member['end_offsets'])]
            start=min(ends,key=lambda q:math.dist(q,[0,0,0]));direction=unit(start);inplane=cross(normal,direction)
            length=selected['split_weld_length_in'];size=selected['split_weld_size_in']
        for wall in (-1,1):
            for edge in (-1,1):
                first=add(start,add(mul(inplane,wall*d/2),[0,edge*t/2,0]))
                a.weld(f'W{len(a.welds)+1:02}',first,add(first,mul(direction,length)),[name,'GUSSET'],size,basis='S' if selected['source_selected'] else 'A',description='Selected slot-edge fillet; actual continuous or split member')
    matches=list(re.finditer(r'2 PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',ctx.text))
    for group,match in enumerate(matches[:2]):
        rt,rw,rl=map(number,match.groups())
        selected_members=[('CONT',continuous)] if group==0 else [('SPLIT-1',low),('SPLIT1',high)]
        for name,member in selected_members:
            ends=[point(add(q,o),origin,axes) for q,o in zip(member['axis'],member['end_offsets'])]
            direction=unit(sub(ends[1],ends[0]));mid=[0,0,0]
            if group:
                start=min(ends,key=lambda q:math.dist(q,[0,0,0]));direction=unit(start)
                mid=add(start,mul(direction,selected['split_weld_length_in']))
            inplane=cross(normal,direction);width=effective(ctx.p,member['profile_id'],'width')
            text=ctx.text[match.end():]
            weld_size=value(r'(?:lines of |with |longitudinal fillets \()?'+NUMBER+r' in E70',text,.1875)
            weld_length=value(NUMBER+r' in long on each side',text,max(.5,rl/2-1))
            for face in (-1,1):
                x=mul(direction,face);y=inplane
                first=add(mid,add(mul(x,-rl/2),add(mul(y,-rw/2),[0,face*width/2,0])))
                label=f'R-{name}-{face}'
                a.box(label,first,[rl,rw,rt],'S','Source slot reinforcement on the unslotted wall; A local edge fit',x=x,y=y)
                for end in (-1,1):
                    for edge in (-1,1):
                        start=add(mid,add(mul(direction,end*(rl/2-weld_length)),add(mul(inplane,edge*rw/2),[0,face*width/2,0])))
                        a.weld(f'W{len(a.welds)+1:02}',start,add(start,mul(direction,end*weld_length)),[name,label],weld_size,description='Source paired longitudinal reinforcement fillets; separate development lengths each side of slot')
    a.dim(mul(v,-half_width),mul(v,half_width),'Source centre section width' if selected['source_width_in'] else 'Proposed centre width',basis='S' if selected['source_width_in'] else 'A')
    a.section_axis=0;a.section_at=0
    a.notes.append('Continuous member, two separate halves and actual rectangular slot envelopes are shared with the building model. A free-edge outline/slot end clearances; machining radii are unspecified. This is a design detail, not a shop cutting pattern.')
    if not selected['source_selected']:
        for part in a.parts:
            if part['kind']!='member':part['basis']='A'
        for item in a.welds+a.fasteners:item['basis']='A'
        a.notes.append('A: no centre connection was specified in the gold design. This accepted fictional proposal requires connection/brace restraint and capacity verification; no new capacity approval is inferred.')
