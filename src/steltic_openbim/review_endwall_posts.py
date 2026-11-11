"""Actual HR gable/end-wall posts, with explicit cuts and movement clips."""
import copy,math
from .pilots.model import add,sub,mul,unit,dot,cross
from .pilots.geometry import strips
from .review_cfs_frame_straps import closest
from .review_receiver_geometry import extract,point,vector


def lower_surface(member,profiles,xy):
    aa,bb=[add(q,o) for q,o in zip(member['axis'],member['end_offsets'])]
    u=unit(sub(bb,aa));y=member['local_y'];n=cross(u,y)
    if n[2]<0:n=mul(n,-1)
    if abs(n[2])<.5:raise ValueError('Roof member has no approximately horizontal flange')
    z=cross(u,y);offset=min(dot(add(mul(y,q[0]),mul(z,q[1])),n) for poly in strips(profiles[member['profile_id']],profiles) for q in poly)
    return (offset+dot(aa,n)-xy[0]*n[0]-xy[1]*n[1])/n[2]


def apply(b):
    if b.key not in ('hr31','hr33'):return
    lookup={m['id']:m for m in b.members};roof=[m for m in b.members if m['kind'] in ('beam','rafter','moment_beam')]
    for c in b.connections:
        if c['detail_ref']['id']!='review_sliding_post':continue
        post=lookup[c['member_ids'][0]];origin=c['point']
        if b.key=='hr33':
            rid=b.record('members','endwall-wind-column-W12X40')
            if rid not in post['design_record_ids']:post['design_record_ids'].append(rid)
            post['source_condition_status']='S W12X40 section retained. A four interior posts per end wall at14 ft spacing; source text instead states three per wall at23 ft4 in. Source count/spacing conflict requires coordination; saved checks do not verify the adopted layout.'
            record=b.record('connections','conn-endwall-wind-column-W12X40');text=b.records[record]['data']['components']
            if not text.startswith('top: ') or '; base: ' not in text:raise ValueError('Endwall source head/base clauses changed')
            top,base=text[5:].split('; base: ',1);label='base' if origin[2]<1 else 'top'
            c['source_record_selections']=[dict(record_id=record,field='components',clause=label,text=base if label=='base' else top,
                level=post['level'],basis='Actual endwall post '+label+' connection; both exact source clauses have located applications.')]
            c['source_connection_end']='start' if label=='base' else 'end'
        end=min(range(2),key=lambda i:math.dist(post['axis'][i],origin))
        if origin[2]<1:
            if b.key=='hr33':
                old=copy.deepcopy(post['end_offsets'][end]);post['end_offsets'][end][2]=2.75
                c.setdefault('parameters',{})['actual_endwall_base']=True
                b.changes.append(dict(kind='source_endwall_base_grout_datum',member_id=post['id'],previous_offset=old,
                    end_offset=copy.deepcopy(post['end_offsets'][end]),basis='S: 2 in grout plus 3/4 in base plate beneath the endwall post. Original base workpoint retained.'))
            continue
        candidates=[(closest(m,origin)[0],m['id'],m) for m in roof]
        distance,_,host=min(candidates)
        if distance>48:raise ValueError('No actual roof receiver for '+post['id'])
        aa,bb=post['axis'];u=unit(sub(bb,aa));y=post['local_y'];z=cross(u,y)
        polygons=strips(b.profiles[post['profile_id']],b.profiles)
        corners=[add(origin,add(mul(y,q[0]),mul(z,q[1]))) for poly in polygons for q in poly]
        top=min(lower_surface(host,b.profiles,q[:2]) for q in corners)-.5
        old=copy.deepcopy(post['end_offsets'][end]);post['end_offsets'][end][2]=top-origin[2]
        faces=[]
        for sign in (-1,1):
            n=mul(y,sign);face=max(dot(sub(q,origin),n) for q in corners)
            profile=b.profiles[post['profile_id']]
            if profile['family']=='i':face=profile['dimensions']['tw']/2
            q=add(origin,mul(n,face));distance,q0,hu,length,s=closest(host,q)
            # Roof ends cannot receive a clip beyond their actual span.
            if s<.001 or s>length-.001:continue
            faces.append((lower_surface(host,b.profiles,q[:2]),sign,n,face))
        if not faces:raise ValueError('No post face lies under the actual roof span')
        roofz,sign,n,face=min(faces,key=lambda r:r[:2]);c['member_ids']=[post['id'],host['id']]
        c.setdefault('parameters',{})['actual_endwall_head']=dict(normal=n,face_in=face,roof_z_in=roofz-origin[2],post_top_in=top-origin[2],
            plate_thickness_in=.375,plate_width_in=4,plate_height_in=8,bolt_diameter_in=.75,slot_length_in=1.875,slot_width_in=.8125)
        b.changes.append(dict(kind='actual_endwall_slip_head',member_id=post['id'],support_member_id=host['id'],
            previous_offset=old,end_offset=copy.deepcopy(post['end_offsets'][end]),basis='S: actual roof geometry and selected post; source HR33 clip/slot/bolt sizes retained. A: 1/2 in roof clearance, physical post cut and clip-face set-out; HR31 adopts the same explicit movement-clip proposal. Roof gravity is not carried by the post.'))
    if b.key=='hr33':b.note('ENDWALL-SOURCE-CONFLICT','S W12X40 endwall post selection and exact base/top attachment clauses retained. A saved layout has four interior posts at14 ft centres per end wall; source check text says three per wall at23 ft4 in. Neither text is silently replaced. The accepted coordination layout and source calculations require reconciliation before construction; data completeness is not approval of this change.')


def head(ctx):
    a,p=ctx.a,ctx.p;post,host=ctx.ms;d=ctx.params['actual_endwall_head'];n=d['normal']
    axes=(cross(n,[0,0,1]),n,[0,0,1]);extract(ctx,post,'POST',axes,48);extract(ctx,host,'RAFTER',axes,36)
    y=d['face_in'];top=d['roof_z_in'];t=d['plate_thickness_in'];width=d['plate_width_in'];height=d['plate_height_in']
    source='S' if ctx.model['pilot']=='hr33' else 'A';pd=p[post['profile_id']];sheet=pd['dimensions'].get('tw',pd['dimensions'].get('t',.25))
    a.box('CLIP',[-width/2,y,top-height],[width,t,height],source,'Vertical slip clip; source HR33 3/8 x 4 x 8 in, explicit A proposal for HR31')
    a.fastener('B',[[0,y+t,top-q] for q in (2.5,5.5)],[0,-1,0],.75,t+sheet,['POST','CLIP'],
        source+' two 3/4 in A325-N bolts; A 3 in pitch; vertical 13/16 x 1-7/8 in slots',basis=source)
    a.fasteners[-1]['slot']=dict(direction=[0,0,1],length_in=1.875,width_in=.8125,travel_in=1.125,basis=source)
    a.weld('WR',[-width/2,y,top],[width/2,y,top],['RAFTER','CLIP'],.25,basis=source,description=source+' 1/4 in clip-to-rafter fillet at the actual bottom flange')
    a.interfaces.append(dict(id='SLIP',kind='vertical_slotted_connection',connects=['POST','CLIP','RAFTER'],travel_in=1.125,basis=source,
        description='Lateral restraint with vertical movement; no gravity bearing or moment fixity'))
    a.dim([3,y,top-height],[3,y,top],'8 in clip',basis=source);a.section_axis=2;a.section_at=top-2.5
    a.notes.append('The post ends below the actual roof underside, including its pitch. The plate is welded to that real flange and bolts pass through the actual post face. A bolt access/slot procurement and local roof/post capacity verification remain required; no roof gravity bearing is implied.')


def base(ctx):
    a,p=ctx.a,ctx.p;post=ctx.ms[0];y=post['local_y'];axes=(cross(y,[0,0,1]),y,[0,0,1]);part=extract(ctx,post,'POST',axes,32)
    a.box('CONC',[-15,-15,-18],[30,30,18],'A','A foundation envelope; source concrete 4 ksi',kind='concrete')
    a.box('GROUT',[-9,-7.5,0],[18,15,2],'S','Source 2 in non-shrink grout')
    plate=a.box('BASE',[-9,-7.5,2],[18,15,.75],'S','Source 3/4 x 15 x 18 in A572 Gr 50 base plate')
    plate['selected_material']='ASTM A572 Gr 50'
    from .review_base_selection import flange_rows
    from .connection_cuts import drill_plate
    layout=flange_rows(ctx.text)
    if not layout or layout[:2]!=(1,2):raise ValueError('Locate the selected pair of rods outside each end-post flange')
    offset=ctx.selected.get(('anchor_pattern','flange_offset_in')) or layout[3]
    pitch=ctx.selected.get(('anchor_pattern','spacing_in')) or layout[4]
    half=p[post['profile_id']]['dimensions']['d']/2+offset
    points=[[x,y,-12] for x in (-half,half) for y in (-pitch/2,pitch/2)]
    hole=ctx.selected.get(('anchor_hole','diameter_in')) or 1.3125
    drill_plate(plate,points,[0,0,1],hole,'S end-wall base anchor holes')
    for i,(x,y,_) in enumerate(points):
        name='WASHER'+str(i);washer=a.box(name,[x-1,y-1,2.75],[2,2,.25],'S','Source 1/4 x 2 x 2 in welded plate washer')
        washer_hole=ctx.selected.get(('washer_hole','diameter_in'))
        drill_plate(washer,[[x,y,0]],[0,0,1],washer_hole or .8125,'S selected washer bore' if washer_hole else 'A 1/16 in diametral clearance')
        anchor=a.fastener('ANCH'+str(i),[[x,y,-12]],[0,0,1],.75,15,['CONC','BASE',name],
            f'S 3/4 in F1554-36 anchor; {pitch:g} in transverse gauge, {offset:g} in beyond the flange; A 12 in embedment',basis='S count, diameter, grade and set-out; A embedment')
        anchor.update(functional_kind='anchor',selected_material='ASTM F1554-36')
        for j,(u,v) in enumerate((([-1,-1],[1,-1]),([1,-1],[1,1]),([1,1],[-1,1]),([-1,1],[-1,-1]))):
            a.weld(f'WW{i}-{j}',[x+u[0],y+u[1],2.75],[x+v[0],y+v[1],2.75],['BASE',name],.1875,description='Source all-round plate-washer fillet')
        a.cylinder('END-NUT'+str(i),[x,y,-12],[0,0,1],1.35,1,'A','A heavy hex anchor-end nut envelope; source embedded nut requirement')
    bounds=part['bounds']
    for sign in (-1,1):
        xx=bounds[0][0 if sign<0 else 1]
        a.weld('POST'+str(sign),[xx,bounds[1][0],2.75],[xx,bounds[1][1],2.75],['POST','BASE'],.25,basis='A',description='A 1/4 in post-end fillet; source pinned base arrangement')
    a.dim([-9,0,2],[9,0,2],'S 18 in plate');a.section_axis=2;a.section_at=2.375
    a.notes.append('The four source rods are located from the two actual W-shape flange faces and the transverse gauge. The plate, grout, rod holes, welded washers and embedded nuts retain the column-base selection. Embedment and post-end weld are adopted fit dimensions.')
