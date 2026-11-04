"""Reconcile authored HR splice locations with physical, not analysis, pieces."""
from collections import defaultdict
import copy,math,re
from .physical_pieces import stacked_pieces,joined_piece

SPLICES={'review_splice','hr_column_splice_48in_above_floor'}

def apply(builder):
    if not builder.key.startswith('hr'):return
    foundation_reference_axes(builder)
    join_analysis_beam_nodes(builder)
    column_pieces(builder)
    aligned_bearing_splices(builder)
    embedded_shafts(builder)
    column_boxing(builder)
    brace_receivers(builder)
    core_floor_receivers(builder)
    beam_receivers(builder)
    roof_receivers(builder)
    opening_receivers(builder)
    truss_endpoints(builder)


def truss_endpoints(builder):
    """Tie shifted chord centroids to their actual, already located node plates."""
    if builder.key!='hr28':return
    builder.endpoint_links=getattr(builder,'endpoint_links',[])
    for m in builder.members:
        if not m['id'].startswith('STMF-'):continue
        for end,q in enumerate(m['axis']):
            candidates=[c for c in builder.connections if c['detail_ref']['id'] in ('review_stmf_end','review_stmf_node') and m['id'] in c['member_ids'] and math.dist(q[:2],c['point'][:2])<.01 and abs(q[2]-c['point'][2])<8]
            if len(candidates)!=1:continue
            builder.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=candidates[0]['id'],basis='Actual shifted truss-chord centroid terminates in this same located source node assembly; the workpoint remains at the chord reference plane'))

def core_floor_receivers(builder):
    """Bind floor tabs at composite walls to the selected wall, not a peer beam."""
    from .pilots.model import dot,sub,unit,mul,add,cross
    from .pilots.geometry import strips
    members={m['id']:m for m in builder.members}
    walls=[m for m in builder.members if m['kind']=='composite_wall']
    if not walls:return
    for c in builder.connections:
        if c['detail_ref']['id']!='review_beam':continue
        text=' '.join(str(builder.records[r]['data'].get('design_basis','')) for r in c.get('design_record_ids',[])).lower()
        if 'at the core walls' not in text:continue
        primary=members[c['member_ids'][0]];origin=c['point']
        far=max(primary['axis'],key=lambda q:math.dist(q,origin));ray=unit(sub(far,origin));matches=[]
        for wall in walls:
            if not min(q[2] for q in wall['axis'])-.01<=origin[2]<=max(q[2] for q in wall['axis'])+.01:continue
            along=wall['local_y'];normal=cross([0,0,1],along)
            if abs(dot(ray,normal))<.999:continue
            delta=sub(origin,wall['axis'][0]);section=strips(builder.profiles[wall['profile_id']],builder.profiles)
            width=max(abs(q[0]) for poly in section for q in poly)
            depth=max(abs(q[1]) for poly in section for q in poly)
            if abs(dot(delta,normal))>.01 or abs(dot(delta,along))>width+.01:continue
            # The lower storey owns the attachment immediately below top of steel.
            matches.append((abs(max(q[2] for q in wall['axis'])-origin[2]),wall['id'],wall,depth))
        if not matches:continue
        _,_,wall,depth=min(matches);old=list(c['member_ids']);c['member_ids']=[primary['id'],wall['id']]
        c.setdefault('parameters',{})['core_face_attachment']=dict(wall_id=wall['id'],wall_half_thickness_in=depth,
            wall_centre_transverse_in=dot(sub(wall['axis'][0],origin),cross([0,0,1],ray)),
            embed_thickness_in=.75,embed_width_in=12,embed_height_in=24,beam_end_gap_in=1.25,
            basis='S: source floor shear tab to embedded plate at the core wall. A: 3/4 x 12 x 24 in welded face patch, 1/4 in perimeter fillets, 1-1/4 in beam end gap; local wall/patch capacity not checked.')
        end=min(range(2),key=lambda i:math.dist(primary['axis'][i],origin))
        before=list(primary['end_offsets'][end]);offset=mul(ray,depth+.75+1.25)
        primary['end_offsets'][end]=add(before,offset)
        builder.changes.append(dict(kind='source_core_floor_receiver',connection_id=c['id'],previous_member_ids=old,
            member_ids=c['member_ids'],previous_end_offset=before,end_offset=primary['end_offsets'][end],
            basis=c['parameters']['core_face_attachment']['basis']))


def beam_receivers(builder):
    """At a three-beam node, select the transverse receiver rather than a peer."""
    from .pilots.model import dot,sub,unit
    members={m['id']:m for m in builder.members}
    beams=[m for m in builder.members if m['kind'] in ('beam','girder','moment_beam')]
    for c in builder.connections:
        if c['detail_ref']['id'] not in ('review_beam','review_transfer_slip','review_pin_beam') or len(c['member_ids'])!=2:continue
        primary,support=[members[mid] for mid in c['member_ids']]
        if support['kind'] not in ('beam','girder','moment_beam'):continue
        direction=unit(sub(primary['axis'][1],primary['axis'][0]))
        if abs(dot(direction,unit(sub(support['axis'][1],support['axis'][0]))))<.99999:continue
        posts=[m for m in builder.members if m['kind'] in ('rocking_post','column','transfer_vertical') and math.dist(m['axis'][0][:2],c['point'][:2])<.01
               and min(q[2] for q in m['axis'])-.01<=c['point'][2]<=max(q[2] for q in m['axis'])+.01]
        if posts:
            replacement=min(posts,key=lambda m:m['id']);previous=list(c['member_ids']);c['member_ids']=[primary['id'],replacement['id']]
            builder.changes.append(dict(kind='vertical_receiver_binding',connection_id=c['id'],previous_member_ids=previous,
                member_ids=c['member_ids'],basis='Actual source vertical member at the joint, including rocking and transfer posts'))
            continue
        candidates=[m for m in beams if m['id'] not in c['member_ids'] and any(math.dist(q,c['point'])<.01 for q in m['axis'])
                    and abs(dot(direction,unit(sub(m['axis'][1],m['axis'][0]))))<.01]
        if not candidates:continue
        # At a cross-node either of two collinear girder ends can receive the
        # tab. Keep the choice explicit; the other girder's end joint remains.
        if len(candidates)>1:
            reference=unit(sub(candidates[0]['axis'][1],candidates[0]['axis'][0]))
            if any(abs(dot(reference,unit(sub(m['axis'][1],m['axis'][0]))))<.99999 for m in candidates[1:]):continue
        replacement=min(candidates,key=lambda m:m['id']);previous=list(c['member_ids']);c['member_ids']=[primary['id'],replacement['id']]
        builder.changes.append(dict(kind='transverse_beam_receiver',connection_id=c['id'],previous_member_ids=previous,
            member_ids=c['member_ids'],candidate_member_ids=[m['id'] for m in candidates],
            basis=('Source unique transverse beam' if len(candidates)==1 else 'A: accepted fictional receiving girder end among collinear transverse candidates')+' at the same saved analysis workpoint; no member or capacity change'))


def aligned_bearing_splices(builder):
    """Record the explicit physical interpretation of a source bearing splice."""
    if builder.key!='hr11':return
    members={m['id']:m for m in builder.members}
    for c in sorted(builder.connections,key=lambda c:c['point'][2]):
        if c['detail_ref']['id']!='review_splice':continue
        upper,lower=[members[mid] for mid in c['member_ids'][:2]]
        text=' '.join(str(builder.records[r]['data'].get('components','')) for r in c.get('design_record_ids',[]))
        if 'milled ends in bearing' not in text.lower() or 'bolts' not in text.lower():continue
        if abs(sum(x*y for x,y in zip(upper['local_y'],lower['local_y'])))>.999:continue
        old=upper['local_y'];upper['analysis_local_y']=copy.deepcopy(old);upper['local_y']=copy.deepcopy(lower['local_y'])
        upper['physical_orientation_basis']='A: align flanges/webs at the source bolted milled-bearing splice; original analysis roll retained separately for review'
        builder.changes.append(dict(kind='accepted_bearing_splice_orientation',member_id=upper['id'],previous_local_y=old,
            local_y=upper['local_y'],connection_id=c['id'],basis=upper['physical_orientation_basis']))


def roof_receivers(builder):
    from .review_receiver_geometry import nearest_beam
    members={m['id']:m for m in builder.members}
    for c in builder.connections:
        if c['detail_ref']['id']!='review_roof_seat':continue
        if any(members[mid]['kind'] in ('beam','girder','moment_beam','rafter') for mid in c['member_ids']):continue
        receiver=nearest_beam(dict(members=builder.members),c['point'],c['member_ids'])
        c['member_ids'].append(receiver['id'])
        builder.changes.append(dict(kind='actual_roof_seat_receiver',connection_id=c['id'],receiver_id=receiver['id'],
            basis='Actual source framing adjacent to the accepted fictional supplier joist; local seat fit remains A'))


def foundation_reference_axes(builder):
    """A physical basement extension must not rescale the above-grade analysis."""
    source={m['id']:m for m in builder.package['physical']['members']}
    for m in builder.members:
        original=source.get(m['id'])
        if not original or m['kind']!='column' or len(m.get('analysis_ids',[]))!=1:continue
        a,b=m['axis'];oa,ob=original['axis']
        if math.dist(b,ob)<1e-6 and math.dist(a[:2],oa[:2])<1e-6 and a[2]<oa[2]-.01:
            old=copy.deepcopy(m['axis']);m['end_offsets'][0][2]+=a[2]-oa[2];m['axis'][0]=list(oa)
            m['joint_workpoints']=old
            builder.changes.append(dict(kind='physical_basement_extension',member_id=m['id'],previous_axis=old,
                reference_axis=m['axis'],end_offsets=m['end_offsets'],basis='Physical basement length retained below the source analysis foundation datum; no rescaling of the source analysis interval'))


def embedded_shafts(builder):
    """Preserve the analysis foundation datum and extend the physical shaft."""
    from .review_base_selection import embedment
    from .assembly_templates import NUMBER,number
    members={m['id']:m for m in builder.members}
    for c in builder.connections:
        if c['detail_ref']['id'] not in ('review_base','review_wall_base'):continue
        text='\n'.join(str(builder.records[r]['data'].get('components','')) for r in c.get('design_record_ids',[]))
        length=embedment(text)
        if length is None:continue
        m=members[c['member_ids'][0]]
        if m['kind']!='column':continue
        end=min(range(2),key=lambda i:m['axis'][i][2])
        offset=c['point'][2]-length-m['axis'][end][2]
        previous=list(m['end_offsets'][end]);m['end_offsets'][end][2]=offset
        builder.changes.append(dict(kind='source_embedded_shaft',member_id=m['id'],source_record_ids=list(c['design_record_ids']),
            reference_axis=m['axis'],previous_end_offset=previous,end_offset=m['end_offsets'][end],embedment_in=length,
            basis='Source selected embedded length; analysis foundation datum unchanged'))
        thick=re.search(r'box built of PL '+NUMBER+r' in plates',text,re.I)
        profile=builder.profiles[m['profile_id']]
        if thick and profile['family']=='rhs':
            # The heavier embedded shaft is a real selected piece. It must not
            # exist only in a drawing detail while IFC retains the light shaft.
            pid=m['profile_id']+'-EMBED';ep=copy.deepcopy(profile);ep['id']=pid;ep['dimensions']['t']=number(thick[1]);builder.profiles[pid]=ep
            transition=c['point'][2]+12;old=copy.deepcopy(m);embedded=copy.deepcopy(m)
            embedded.update(id=m['id']+':embedded',profile_id=pid,axis=[[*m['axis'][end][:2],c['point'][2]-length],[*m['axis'][end][:2],transition]],end_offsets=[[0,0,0],[0,0,0]],analysis_ids=[],design_record_ids=list(c['design_record_ids']))
            embedded.pop('analysis_segments',None);embedded['setout_basis']='S heavier embedded box and 12 in above-foundation transition; source inner taper requirement retained in base detail'
            m['axis'][end][2]=transition;m['end_offsets'][end]=[0,0,0];builder.members.append(embedded);c['member_ids'].append(embedded['id'])
            builder.endpoint_links=getattr(builder,'endpoint_links',[])
            for mid,side in ((m['id'],'start' if end==0 else 'end'),(embedded['id'],'start'),(embedded['id'],'end')):
                builder.endpoint_links.append(dict(member_id=mid,end=side,connection_id=c['id'],basis='Actual embedded shaft/end plate and source heavier-to-lighter shaft CJP transition are in this base assembly'))
            builder.changes.append(dict(kind='source_embedded_shaft_piece',member_id=m['id'],previous_axis=old['axis'],embedded_member_id=embedded['id'],profile_id=pid,thickness_in=number(thick[1]),transition_elevation=transition,basis=embedded['setout_basis']))


def column_boxing(builder):
    """Record full-tier side plates as physical pieces, once per actual column."""
    from .assembly_templates import flat,effective
    from .pilots.model import add,mul,cross,unit,sub
    members={m['id']:m for m in builder.members};selected={};old=[]
    for c in builder.connections:
        par=c.get('parameters',{});t=par.get('boxing_t')
        if not t or 'boxing_length_in' in par:continue
        column=next((members[mid] for mid in c['member_ids'] if members[mid]['kind']=='column'),None)
        if column is None:continue
        item=selected.setdefault(column['id'],dict(thickness=t,records=set(),connections=[]))
        if abs(item['thickness']-t)>1e-8:raise ValueError('Conflicting full-height boxing selections on '+column['id'])
        item['records'].update(c.get('design_record_ids',[]));item['connections'].append(c)
        if c['detail_ref']['id']=='review_column_box':old.append(c)
    previous_plates={mid for c in old for mid in c['member_ids'] if members[mid]['kind']=='column_box_plate'}
    builder.members=[m for m in builder.members if m['id'] not in previous_plates]
    builder.connections=[c for c in builder.connections if c not in old]
    for c in builder.connections:c['member_ids']=[mid for mid in c['member_ids'] if mid not in previous_plates]
    for mid,item in selected.items():
        m=members[mid];t=item['thickness'];depth=effective(builder.profiles,m['profile_id']);width=effective(builder.profiles,m['profile_id'],'width')
        m['boxing_thickness_in']=t
        depth=m.get('boxing_width_in',depth)
        pid=flat(builder.profiles,depth,t);u=unit(sub(m['axis'][1],m['axis'][0]));normal=m['local_y'];along=cross(u,normal);plates=[]
        for side in (-1,1):
            offset=mul(normal,side*(width+t)/2);ends=[add(q,offset) for q in m['axis']]
            plate=builder.member(mid+':boxing:'+str(side),pid,'column_boxing',*ends,m['level'],'S',records=sorted(item['records']),local_y=along,
                physical_component_of=mid,setout_basis='Source full-tier boxing; actual column pieces and side-plate thickness retained')
            plates.append(plate)
        for c in item['connections']:
            if c not in old:
                c['member_ids']=list(dict.fromkeys(c['member_ids']+[p['id'] for p in plates]))
                c.setdefault('parameters',{})['boxing_width_in']=depth
        point=[(a+b)/2 for a,b in zip(*m['axis'])];height=m['axis'][1][2]-m['axis'][0][2]
        parameters=dict(boxing_t=t,full_height_in=height,boxing_width_in=depth)
        text=' '.join(str(builder.records[r]['data'].get('components','')) for r in item['records'])
        if 'fillet welds elsewhere' in text:
            intervals=[]
            for c in item['connections']:
                beam=next((members[i] for i in c['member_ids'] if i in members and members[i]['kind'] in ('beam','moment_beam','girder')),None)
                if beam:
                    z=c['point'][2]-point[2];intervals.append((max(-height/2,z-effective(builder.profiles,beam['profile_id'])-12),min(height/2,z+12)))
            cuts=sorted({-height/2,height/2,*[v for pair in intervals for v in pair]})
            parameters['boxing_weld_regions']=[dict(z0=a,z1=b,kind='CJP' if any(lo<=(a+b)/2<=hi for lo,hi in intervals) else 'fillet') for a,b in zip(cuts,cuts[1:]) if b>a]
        # Base and splice records explain why boxing is selected, but their
        # anchors/erection bolts belong to their own joint. They are context for
        # this longitudinal plate-to-shaft attachment, not its hardware schedule.
        direct=[r for r in m.get('design_record_ids',[]) if r.startswith('members/')]
        made=builder.connection(mid+':full-boxing','review_column_box',point,[m]+plates,direct,parameters=parameters,basis='S')
        made['source_context_records']=sorted(item['records'])
    if builder.key=='hr25':
        for c in builder.connections:
            if c['detail_ref']['id']!='review_splice':continue
            upper=members[c['member_ids'][0]]
            if upper['id'] not in selected or upper['axis'][0][0]!=1008 or upper['axis'][0][1] not in (0,1440):continue
            rid=builder.record('connections','conn-boxed-col-4A4E-'+upper['profile_id'])
            if not rid:continue
            c['design_record_ids'].append(rid);builder.used_records.add(rid)
            c.setdefault('parameters',{}).update(boxing_t=selected[upper['id']]['thickness'],boxing_width_in=upper.get('boxing_width_in',effective(builder.profiles,upper['profile_id'])))
            shafts=set(c['member_ids'])
            c['member_ids']+= [m['id'] for m in builder.members if m['kind']=='column_boxing' and m.get('physical_component_of') in shafts and m['id'] not in c['member_ids']]
    if selected:builder.changes.append(dict(kind='source_full_tier_boxing',columns=list(selected),previous_analysis_level_plates=[members[mid] for mid in sorted(previous_plates)],removed_typical_occurrence_ids=[c['id'] for c in old],basis='Side plates follow the actual field-spliced column pieces; original analysis-storey plate geometry remains in this change record'))


def column_pieces(builder):
    groups=defaultdict(list);members={m['id']:m for m in builder.members}
    for m in builder.members:
        if m['kind']=='column' and len(m.get('analysis_ids',[]))==1:
            a,b=m['axis']
            if abs(a[0]-b[0])+abs(a[1]-b[1])<1e-7 and b[2]>a[2]:groups[tuple(round(v,6) for v in a[:2])].append(m)
    replacements={};pieces_by_group={};source_groups={}
    for location,segments in groups.items():
        segments.sort(key=lambda m:m['axis'][0][2]);ids={m['id'] for m in segments}
        if any(abs(a['axis'][1][2]-b['axis'][0][2])>1e-6 for a,b in zip(segments,segments[1:])):continue
        joints=[c for c in builder.connections if c['detail_ref']['id'] in SPLICES and len(set(c['member_ids'])&ids)>=2]
        if not joints:continue
        joints.sort(key=lambda c:c['point'][2]);intervals=[];bottom=segments[0]['axis'][0][2];selected=segments[0]
        for c in joints:
            z=c['point'][2]
            if not bottom<z<segments[-1]['axis'][1][2]:raise ValueError('Source splice lies outside the physical column stack: '+c['id'])
            interval=(bottom,z,selected);intervals.append(interval);bottom=z
            selected=max((members[mid] for mid in c['member_ids'] if mid in ids),key=lambda m:m['axis'][0][2])
        intervals.append((bottom,segments[-1]['axis'][1][2],selected))
        prefix='COLUMN-'+':'.join(format(v,'.6g') for v in location)
        pieces=stacked_pieces(prefix,segments,intervals)
        for part in pieces:
            part['setout_basis']='Source selected column section and source splice elevation; physical continuation across analysis levels. '+part.get('setout_basis','')
            part['reference_line']='Column workline; actual physical pieces end at the recorded field splices'
        pieces_by_group[location]=pieces
        for m in segments:source_groups[m['id']]=location;replacements[m['id']]=[p['id'] for p in pieces if m['id'] in p['source_member_ids']]
    if not replacements:return
    builder.members=[m for m in builder.members if m['id'] not in replacements]+[p for ps in pieces_by_group.values() for p in ps]
    kept=[];dispositions=[]
    for c in builder.connections:
        old=list(c['member_ids']);new=[];family=c['detail_ref']['id']
        for mid in old:
            if mid not in source_groups:new.append(mid);continue
            pieces=pieces_by_group[source_groups[mid]];z=c['point'][2]
            matches=[p for p in pieces if p['axis'][0][2]+p['end_offsets'][0][2]-1e-5<=z<=p['axis'][1][2]+p['end_offsets'][1][2]+1e-5]
            if not matches:raise ValueError('Connection lies outside its actual column stack: '+c['id'])
            # At a real field splice both pieces participate. Else a connection
            # binds to the shaft that physically passes through that elevation.
            if family in SPLICES:
                # Review splice recipes identify the upper selection first;
                # the pilot's original column-splice recipe uses lower first.
                ordered=sorted(matches,key=lambda p:p['axis'][0][2],reverse=family=='review_splice')
                new.extend(p['id'] for p in ordered)
            else:new.append(min(matches,key=lambda p:abs((p['axis'][0][2]+p['axis'][1][2])/2-z))['id'])
        c['member_ids']=list(dict.fromkeys(new));c['source_analysis_member_ids']=old
        if family=='review_column_continuity' and len(c['member_ids'])==1:
            dispositions.append(dict(id=c['id'],source=copy.deepcopy(c),reason='Analysis storey node lies inside one continuous physical column; no field joint or weld'))
        else:kept.append(c)
    builder.connections=kept
    builder.changes.append(dict(kind='source_splice_physical_pieces',replacements=replacements,
                               analysis_node_dispositions=dispositions,basis='Source splice elevations and selected sections, no analysis or capacity recalculation'))
    builder.note('PHYSICAL-PIECES','S: actual column pieces end at the source field-splice elevations. Intermediate analysis floor nodes are reference stations on continuous pieces. Analysis intervals remain mapped explicitly; source design checks are retained without a new capacity claim.')


def join_analysis_beam_nodes(builder):
    """Chevron workpoints split analysis beams, not the selected physical beam."""
    dispositions=[]
    for connection in list(builder.connections):
        if connection not in builder.connections or connection['detail_ref']['id']!='review_beam' or len(connection['member_ids'])!=2:continue
        members={m['id']:m for m in builder.members}
        left,right=[members[mid] for mid in connection['member_ids']]
        if any(m['kind'] not in ('beam','girder','moment_beam') or not (m.get('analysis_ids') or m.get('analysis_segments')) for m in (left,right)):continue
        # Restrict the inference to an explicit brace apex at the same workpoint.
        if not any(c['detail_ref']['id'] in ('review_brace','review_brb') and c.get('parameters',{}).get('joint')=='apex' and math.dist(c['point'],connection['point'])<1e-6 for c in builder.connections):continue
        try:piece=joined_piece(left['id']+':continuous',left,right)
        except ValueError:continue
        ids={left['id'],right['id']};builder.members=[m for m in builder.members if m['id'] not in ids]+[piece]
        kept=[]
        for c in builder.connections:
            original=list(c['member_ids'])
            if c['detail_ref']['id']=='review_beam' and set(original)==ids and math.dist(c['point'],connection['point'])<1e-6:
                dispositions.append(dict(source=copy.deepcopy(c),reason='Continuous selected beam at a brace-apex analysis subdivision; its brace connection is retained'))
                continue
            c['member_ids']=list(dict.fromkeys(piece['id'] if mid in ids else mid for mid in original));kept.append(c)
        builder.connections=kept
    if dispositions:builder.changes.append(dict(kind='continuous_analysis_beam_nodes',dispositions=dispositions))


def brace_receivers(builder):
    """Choose the beam in the actual brace bay, not the nearest adjacent bay."""
    from .pilots.model import sub,dot,unit
    members={m['id']:m for m in builder.members}
    beams=[m for m in builder.members if m['kind'] in ('beam','girder','moment_beam','link')]
    for c in builder.connections:
        if c['detail_ref']['id'] not in ('review_brace','review_brb'):continue
        primary=members[c['member_ids'][0]];point=c['point']
        far=max(primary['axis'],key=lambda q:math.dist(q,point));delta=sub(far,point)
        if math.hypot(*delta[:2])<1e-6:continue
        ray=unit([delta[0],delta[1],0]);candidates=[]
        column=next((members[mid] for mid in c['member_ids'] if members[mid]['kind']=='column'),None)
        if column:c.setdefault('parameters',{})['weak_axis_gusset']=abs(dot(column['local_y'],ray))>.99
        for m in beams:
            a,b=m['axis'];v=sub(b,a);length=math.dist(a,b)
            if not length or abs(dot(unit(v),ray))<.999999:continue
            t=dot(sub(point,a),v)/(length*length)
            if not -1e-6<=t<=1+1e-6:continue
            nearest=[q+t*d for q,d in zip(a,v)]
            if math.dist(nearest,point)>.01:continue
            reach=max(dot(sub(q,point),ray) for q in (a,b))
            if reach>.01:candidates.append((reach,m['id']))
        if not candidates:continue # A base may have no beam; preserve that case.
        chosen=members[max(candidates)[1]];old=list(c['member_ids'])
        c['member_ids']=[mid for mid in old if members[mid]['kind'] not in ('beam','girder','moment_beam','link')]+[chosen['id']]
        if old!=c['member_ids']:
            builder.changes.append(dict(kind='brace_support_binding',connection=c['id'],previous_member_ids=old,
                                        member_ids=list(c['member_ids']),basis='Actual checked beam extending into the brace bay at its workpoint'))


def opening_receivers(builder):
    """Bind opening end details to the perpendicular framing at that station."""
    from .pilots.model import sub,dot,unit
    members={m['id']:m for m in builder.members}
    beams=[m for m in builder.members if m['kind'] in ('beam','girder','moment_beam','infill','opening_header','opening_trimmer','link')]
    kept=[];seen={}
    for c in builder.connections:
        if c['detail_ref']['id']!='test_floor_opening':kept.append(c);continue
        primary=members[c['member_ids'][0]];point=c['point'];axis=unit(sub(*reversed(primary['axis'])))
        candidates=[]
        for m in beams:
            if m['id']==primary['id']:continue
            a,b=m['axis'];v=sub(b,a);length=math.dist(a,b)
            if not length or abs(dot(unit(v),axis))>.01:continue
            t=dot(sub(point,a),v)/(length*length)
            if not -1e-6<=t<=1+1e-6:continue
            nearest=[q+t*d for q,d in zip(a,v)]
            if math.dist(nearest[:2],point[:2])>.01 or abs(nearest[2]-point[2])>24:continue
            candidates.append((abs(nearest[2]-point[2]),m['id']))
        if candidates:
            receiver=min(candidates)[1];c['member_ids']=[primary['id'],receiver]
            token=(tuple(round(v,5) for v in point),tuple(sorted(c['member_ids'])))
            if token in seen:
                builder.changes.append(dict(kind='shared_opening_joint',source=copy.deepcopy(c),connection=seen[token],basis='Two member ends share one physical connection'))
                continue
            seen[token]=c['id']
        kept.append(c)
    builder.connections=kept
