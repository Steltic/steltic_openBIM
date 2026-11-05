"""Source SPSW bays with field plates fitted to the actual boundary steel.

Gross analysis widths remain evidence. Clear plate extents, lap side and local
fishplate fits are explicit fictional decisions, not renewed capacity checks.
"""
import copy, math
from .pilots.model import add,sub,mul,dot,cross,unit
from .pilots.geometry import strips


def column_face(b,m,along,normal,side):
    from shapely.geometry import Polygon,box
    from shapely.ops import unary_union
    y=m['local_y'];z=cross(unit(sub(m['axis'][1],m['axis'][0])),y)
    polygons=[]
    for ring in strips(b.profiles[m['profile_id']],b.profiles):
        polygons.append(Polygon([(v*dot(y,along)+w*dot(z,along),v*dot(y,normal)+w*dot(z,normal)) for v,w in ring]))
    section=unary_union(polygons).intersection(box(-1000,-.1875,1000,.375))
    if section.is_empty:raise ValueError('SPSW boundary has no steel on the selected lap plane')
    return dot(m['axis'][0],along)+section.bounds[2 if side>0 else 0]


def apply(b):
    if b.key!='hr9':return
    old=[m for m in b.members if m['kind']=='plate_wall'];old_ids={m['id'] for m in old}
    steel=[m for m in b.members if m['kind'] in ('column','rocking_post','beam','moment_beam')]
    old_cons={c['member_ids'][0]:c for c in b.connections if c['detail_ref']['id']=='review_plate_wall'}
    base_cons={c['member_ids'][0]:c for c in b.connections if c['detail_ref']['id']=='review_plate_base'}
    b.members=[m for m in b.members if m['id'] not in old_ids]
    b.panels=[p for p in b.panels if p['id'] not in {v+'-PL' for v in old_ids}]
    b.connections=[c for c in b.connections if not any(i in old_ids for i in c['member_ids'])]
    b.changes=[c for c in b.changes if not (c.get('kind')=='plate_wall_base_clearance' and c.get('member_id') in old_ids)]
    for source in old:
        along=source['local_y'];normal=cross([0,0,1],along);axis=0 if abs(along[0])>.9 else 1
        width=b.profiles[source['profile_id']]['dimensions']['width'];t=b.profiles[source['profile_id']]['dimensions']['thickness']
        mid=dot(source['axis'][0],along);station=dot(source['axis'][0],normal)
        z0,z1=sorted(q[2] for q in source['axis']);count=round(width/168);fields=[]
        if abs(width-count*168)>.001:raise ValueError('SPSW source half-panel width changed')
        for bay in range(count):
            lo=mid-width/2+bay*168;hi=lo+168
            sides=[]
            for boundary,sign in ((lo,1),(hi,-1)):
                columns=[m for m in steel if m['kind'] in ('column','rocking_post') and abs(dot(m['axis'][0],along)-boundary)<.001
                    and abs(dot(m['axis'][0],normal)-station)<.001
                    and min(z1,max(q[2] for q in m['axis']))-max(z0,min(q[2] for q in m['axis']))>.1]
                if not columns:raise ValueError(f'{source["id"]}: missing actual VBE at {boundary:g}')
                sides.append([(m,column_face(b,m,along,normal,sign),sign) for m in columns])
            left=max(face for _,face,_ in sides[0])+2;right=min(face for _,face,_ in sides[1])-2
            beams=[];bottom=z0;top=z1
            for elevation,sign in ((z0,1),(z1,-1)):
                if elevation==0:continue
                candidates=[m for m in steel if m['kind'] in ('beam','moment_beam')
                    and abs(dot(unit(sub(m['axis'][1],m['axis'][0])),along))>.999
                    and all(abs(dot(q,normal)-station)<.001 for q in m['axis'])
                    and min(hi,max(dot(q,along) for q in m['axis']))-max(lo,min(dot(q,along) for q in m['axis']))>.1
                    and abs(sum(q[2] for q in m['axis'])/2-elevation)<50]
                if not candidates:raise ValueError(f'{source["id"]}: missing actual HBE at {elevation:g}')
                spans=sorted((max(lo,min(dot(q,along) for q in m['axis'])),min(hi,max(dot(q,along) for q in m['axis']))) for m in candidates)
                cursor=lo
                for start,end in spans:
                    if start>cursor+.001:raise ValueError('Missing HBE span inside source SPSW bay')
                    cursor=max(cursor,end)
                if cursor<hi-.001:raise ValueError('Incomplete HBE span inside source SPSW bay')
                faces=[]
                for beam in candidates:
                    physical=[add(q,o) for q,o in zip(beam['axis'],beam['end_offsets'])]
                    depth=b.depth(beam['profile_id']);face=sum(q[2] for q in physical)/2+sign*depth/2
                    faces.append(face);beams.append((beam,face,sign))
                if sign>0:bottom=max(faces)
                else:top=min(faces)
            bottom+=2;top-=2
            if right-left<12 or top-bottom<12:raise ValueError('SPSW clear field is too small')
            centre=(left+right)/2;point=add(mul(along,centre),mul(normal,station+.28125))
            pa=add(point,[0,0,bottom]);pb=add(point,[0,0,top]);pid=b.custom(source['profile_id']+f'-CLEAR-{right-left:.6f}',
                'flat',dict(width=right-left,thickness=t),basis='S thickness; A clear field width between actual VBE faces')
            records=list(dict.fromkeys(source['design_record_ids']+['members/brace-WEB3/16'+('P' if source.get('perforations') else '')]))
            wall=b.member(source['id']+f'-H{bay+1}',pid,'plate_wall',pa,pb,source['level'],'A',
                records=records,local_y=along,source_wall_id=source['id'],source_workline=copy.deepcopy(source['axis']),
                source_gross_width_in=width,perforations=copy.deepcopy(source.get('perforations')))
            fields.append(wall)
            receiver_ids=list(dict.fromkeys(m['id'] for rows in sides for m,_,_ in rows))+[m['id'] for m,_,_ in beams]
            for receiver in steel:
                if receiver['id'] in receiver_ids:
                    receiver['design_record_ids']=list(dict.fromkeys(receiver['design_record_ids']+['members/spsw-boundary-frame-25pct']))
            data=dict(along=along,normal=normal,field_left_in=left-centre,field_right_in=right-centre,
                height_in=top-bottom,source_bay_width_in=168,
                column_faces=[dict(member_id=m['id'],face_in=face-centre,side=sign) for rows in sides for m,face,sign in rows],
                beam_faces=[dict(member_id=m['id'],face_in=face-bottom,side=sign,
                    left_in=max(left,min(dot(add(q,o),along) for q,o in zip(m['axis'],m['end_offsets'])))-centre,
                    right_in=min(right,max(dot(add(q,o),along) for q,o in zip(m['axis'],m['end_offsets'])))-centre) for m,face,sign in beams])
            edge=b.connection(wall['id']+':edge','review_plate_wall',pa,[wall['id']]+receiver_ids,
                old_cons[source['id']]['design_record_ids'],parameters=dict(thickness=t,perforated=bool(source.get('perforations')),actual_plate_boundary=data))
            b.endpoint_links=getattr(b,'endpoint_links',[])
            for end in ('start','end'):
                b.endpoint_links.append(dict(member_id=wall['id'],end=end,connection_id=edge['id'],
                    basis='This complete field-plate boundary assembly contains the actual HBE/VBE fishplates at both ends of this same physical wall plate.'))
            if source['id'] in base_cons:
                wall['axis'][0][2]=0;wall['end_offsets'][0][2]=2
                b.changes.append(dict(kind='plate_wall_base_clearance',member_id=wall['id'],end_offset=[0,0,2],
                    basis=base_cons[source['id']]['parameters']['plate_base_fit']['basis']))
            b.changes.append(dict(kind='source_plate_wall_boundary_fit',source_member_id=source['id'],member_id=wall['id'],
                actual_receivers=receiver_ids,clear_axis=copy.deepcopy(wall['axis']),clear_width_in=right-left,gross_bay_width_in=168,
                basis='S: each 28 ft pier consists of two 14 ft half panels either side of the intermediate VBE; 3/16 in field plate and source 3/8 x 4 in fishplate/fillet selections. A: 2 in field clearance from actual boundary faces; one-sided lap at +9/32 in. At tier changes widen the local fishplate to reach the unchanged field edge. Local fits, modified widths and source capacity applicability require engineering verification.'))
        if source['id'] in base_cons:
            original=base_cons[source['id']];params=copy.deepcopy(original['parameters'])
            params['plate_base_fit'].update(embed_width_in=width,embed_offset_in=0)
            params['plate_base_fit']['half_panel_layout']=[dict(profile_id=m['profile_id'],offset_in=dot(m['axis'][0],along)-mid) for m in fields]
            origin=add(mul(along,mid),mul(normal,station+.28125))
            b.connection(source['id']+':base','review_plate_base',origin,fields,original['design_record_ids'],parameters=params)
    b.note('SPSW-FIELD-FIT','S: source gross bays, boundary steel, field thickness, perforation specification and weld selections retained. A: each actual VBE-to-VBE bay has its own clear field plate, with 2 in edge fit and one-sided fishplate lap. Fishplates follow actual column tiers; any width greater than the source 4 in is an explicitly unverified local fit. Perforation diameter/pitch remain design metadata; the design surface is not a punched fabrication solid. Companion gross-wall surfaces are removed to avoid duplicate plate geometry.')


def draw(ctx):
    from .review_receiver_geometry import point,vector
    a=ctx.a;data=ctx.params['actual_plate_boundary'];axes=(data['along'],data['normal'],[0,0,1])
    members={m['id']:m for m in ctx.ms};names={}
    a.title='SPSW FIELD PLATE / ACTUAL BOUNDARY FRAME'
    counts={'column':0,'beam':0}
    for i,m in enumerate(ctx.ms):
        group='column' if m['kind'] in ('column','rocking_post') else 'beam'
        if i:counts[group]+=1
        name='WALL' if i==0 else ('V' if group=='column' else 'H')+str(counts[group]);names[m['id']]=name
        ends=[point(add(q,o),ctx.c['point'],axes) for q,o in zip(m['axis'],m['end_offsets'])]
        u=sub(ends[1],ends[0]);lo,hi=0.,1.
        limits=((data['field_left_in']-24,data['field_right_in']+24),(-60,60),(-18,data['height_in']+18))
        for n,(lower,upper) in enumerate(limits):
            if abs(u[n])<1e-9:continue
            start,end=sorted(((lower-ends[0][n])/u[n],(upper-ends[0][n])/u[n]))
            lo=max(lo,start);hi=min(hi,end)
        if hi<=lo:raise ValueError('Boundary piece misses its actual field plate')
        a.member(name,m['profile_id'],add(ends[0],mul(u,lo)),add(ends[0],mul(u,hi)),y=vector(m['local_y'],axes),
                 basis=m['basis'],source_member_index=i,description='Actual '+m['kind']+' '+m['profile_id'])
    left,right=data['field_left_in'],data['field_right_in'];height=data['height_in'];fish_y=-.46875
    for i,row in enumerate(data['column_faces']):
        m=members[row['member_id']];face=row['face_in'];side=row['side'];edge=left if side>0 else right
        physical=[add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]
        lo=max(2,min(q[2] for q in physical)-ctx.c['point'][2]);hi=min(height-2,max(q[2] for q in physical)-ctx.c['point'][2])
        if hi<=lo:continue
        end=edge+side*2;xs=sorted((face,end));name='VF'+str(i+1)
        a.box(name,[xs[0],fish_y,lo],[xs[1]-xs[0],.375,hi-lo],
            'S 3/8 in thickness; A fitted width' if abs(xs[1]-xs[0]-4)>.001 else 'S size; A fit',
            'Actual VBE fishplate; source 4 in width where unchanged; tier-dependent extra width is A and unverified')
        for j,y in enumerate((fish_y,fish_y+.375)):
            a.weld(name+'S'+str(j),[face,y,lo],[face,y,hi],[names[m['id']],name],.25,description='Source two 1/4 in shop fillets to actual VBE')
        for j,x in enumerate((edge,end)):
            a.weld(name+'F'+str(j),[x,fish_y+.375,lo],[x,fish_y+.375,hi],['WALL',name],.1875,description='Source 3/16 in field fillets along both lap edges')
    for i,row in enumerate(data['beam_faces']):
        face=row['face_in'];side=row['side'];zs=sorted((face,face+side*4));name='HF'+str(i+1)
        lo,hi=row['left_in'],row['right_in']
        if hi<=lo:continue
        a.box(name,[lo,fish_y,zs[0]],[hi-lo,.375,4],'S size; A fitted length','Source 3/8 x 4 in fishplate on actual HBE flange')
        for j,y in enumerate((fish_y,fish_y+.375)):
            a.weld(name+'S'+str(j),[lo,y,face],[hi,y,face],[names[row['member_id']],name],.25,description='Source two 1/4 in shop fillets to actual HBE')
        for j,z in enumerate((face+side*2,face+side*4)):
            a.weld(name+'F'+str(j),[lo,fish_y+.375,z],[hi,fish_y+.375,z],['WALL',name],.1875,description='Source 3/16 in field fillets along both lap edges')
    a.section_axis=2;a.section_at=height/2
    a.dim([left,0,0],[right,0,0],'A clear field width',basis='A',offset=-45)
    a.dim([right,0,0],[right,0,height],'A clear field height',basis='A',offset=-85)
    a.notes.extend(['Source physical boundary members are shown at their actual sections, rolls and elevations. Clear field dimensions are accepted fictional fit proposals; source gross bay dimensions remain on the building grids.',
        'At a column tier change, the field stays clear of the larger selected face. Wider local fishplates are A and require verification. Original source weld sizes are retained; no new force-transfer check is implied.',
        'S: 6 in perforations at 10.75 in diagonal pitch; pattern origin, edge exclusions and punched fabrication geometry remain later detailing.' if ctx.params['perforated'] else 'S: solid plate selection. A: 2 in edge gap and local corner fit.'])
