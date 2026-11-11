"""Author one finite pin and the ordered, independently bored HR-selected plies."""
import math

from .connection_cuts import drill_joined_plates
from .pilots.model import add,sub,mul,dot
from .review_assemblies import hull


def selected_stack(ctx):
    candidate=ctx.params.get('pin_stack')
    records=ctx.package.get('source_handoff',{}).get('records',{})
    apps=ctx.package.get('source_handoff',{}).get('occurrences',{}).get(ctx.c['id'],{}).get('applications',[])
    active={a['record_id'] for a in apps if a.get('selected')}
    rows=[(rid,records[rid].get('data',{}).get('pin_stack')) for rid in ctx.c['design_record_ids'] if rid in records and rid in active]
    rows=[(rid,stack) for rid,stack in rows if stack]
    if not rows and candidate is None:return None
    if len(rows)!=1:raise ValueError('Pin stack needs one applicable authenticated source record at '+ctx.c['id'])
    rid,source=rows[0]
    # Connection parameters may repeat the selected values and their source link.
    if candidate is not None and any(source.get(k)!=v for k,v in candidate.items() if k!='source_record_id'):
        raise ValueError('Physical pin stack differs from its authenticated source at '+ctx.c['id'])
    if candidate and candidate.get('source_record_id',rid)!=rid:
        raise ValueError('Pin stack source record mismatch at '+ctx.c['id'])
    return rid,source


def stack_positions(source):
    grip=source['grip_in'];gap=source['clearance_between_moving_groups_in']
    pin=source['pin_diameter_in'];hole=source['pin_hole_diameter_in']
    if not 0<pin<=hole or gap<0:raise ValueError('Invalid selected pin or moving clearance')
    seen=set();rows=[];previous=None;y=-grip/2
    for index,ply in enumerate(source['selected_stack']):
        role=ply['role'];thickness=ply['thickness_in']
        if role in seen or thickness<=0:raise ValueError('Invalid selected pin ply '+role)
        seen.add(role)
        group=role if ply['connected_to']=='host' else ply['connected_to']
        if previous and group!=previous:y+=gap
        part_id=role.upper().replace('_','-')
        rows.append(dict(ply,index=index,id=part_id,start=y,finish=y+thickness))
        y+=thickness;previous=group
    if abs(y-grip/2)>1e-6:raise ValueError('Actual ply and clearance sum differs from selected common-pin grip')
    if sum(p['connected_to']=='host' for p in rows)!=source['receiving_leaves']:
        raise ValueError('Pin stack does not contain each selected primary gusset')
    return rows


def selected_receiver(ctx,selection):
    rid,_=selection
    data=ctx.package['source_handoff']['records'][rid]['data'].get('receiver_selection',{})
    if not data:return {}
    binding={m['id'] for m in ctx.ms}
    required={data['brace_member_id'],data['column_id']}
    if data['beam_id']:required.add(data['beam_id'])
    if data['native_connection_id']!=ctx.c['id'] or not required<=binding or math.dist(ctx.c['point'],data['point_in'])>1e-5:
        raise ValueError('Selected pin stack does not belong to these named brace and host workpoints')
    return data


def make_stack(ctx,selection,v,station,depth,width):
    a=ctx.a;rid,source=selection;rows=stack_positions(source);receiver=selected_receiver(ctx,selection)
    n=[-v[2],0,v[0]]
    def at(s,d,y):return add(add(mul(v,s),mul(n,d)),[0.,y,0.])
    def rectangle(s0,s1,d0,d1,y):
        return [at(s,d,y) for s,d in ((s0,d0),(s0,d1),(s1,d1),(s1,d0))]
    support=next(p for p in a.parts if p['id']=='GUSSET')
    a.parts.remove(support)
    support_welds=[w for w in a.welds if 'GUSSET' in w['connects']]
    a.welds[:]=[w for w in a.welds if w not in support_welds]
    edges=[pt for weld in support_welds for pt in (weld['a'],weld['b'])]
    if not edges:raise ValueError('Selected primary gusset has no located host attachment')
    cheek=source['cheek_side_in'];half=source['primary_width_at_pin_in']/2
    extension=source['extension_in'];grip=source['grip_in'];hole=source['pin_hole_diameter_in']
    # Position the bore after the actual host contacts. The parallel free edges
    # give the selected width across the bore and the specified end extension.
    pin_s=max(station,max(dot(p,v) for p in edges)+cheek/2+2,
              max((abs(dot(p,n))+half)*abs(v[2])+dot(p,v) for p in edges))
    fit_start=pin_s-cheek/2-1
    pin=mul(v,pin_s);end=pin_s+extension;cap_s=end+2
    hull_pts=[(dot(p,v),dot(p,n)) for p in edges]
    hull_pts.extend([(fit_start,-half),(fit_start,half),(end,-half),(end,half)])
    outline=hull(hull_pts)
    if abs(4*cheek-source['cheek_weld_perimeter_in'])>1e-6:
        raise ValueError('Selected cheek perimeter and side are inconsistent')
    by_role={r['role']:r for r in rows}
    midplanes=[(r['start']+r['finish'])/2 for r in rows if r['connected_to']=='host']
    if receiver and (len(midplanes)!=receiver['number_of_primary_leaves'] or
        any(abs(x-y)>1e-6 for x,y in zip(midplanes,receiver['gusset_leaf_offsets_in'],strict=True))):
        raise ValueError('Selected gusset support offsets differ from the common-pin stack')
    for row in rows:
        role=row['role'];pid=row['id'];y=row['start'];t=row['thickness_in']
        if row['connected_to']=='host':
            primary=a.polygon(pid,[at(s,d,y) for s,d in reversed(outline)],t,basis='S',
                              description=f'Selected primary gusset {t:g} in; fitted contour around the selected bearing width')
            for w in support_welds:
                edge=receiver.get('column_edge' if 'COLUMN' in w['connects'] else 'horizontal_edge',{})
                if edge and (edge['count_per_leaf']!=2 or abs(math.dist(w['a'],w['b'])-edge['length_in'])>1e-5):
                    raise ValueError('Selected per-leaf support weld setout differs at '+ctx.c['id'])
                for i,face in enumerate((y,y+t)):
                    connect=[pid if x=='GUSSET' else x for x in w['connects']]
                    a.weld(w['id']+'-'+pid+'-'+str(i+1),[w['a'][0],face,w['a'][2]],
                           [w['b'][0],face,w['b'][2]],connect,edge.get('size_in',w['size']),
                           kind=edge.get('weld_type',w['kind']),basis=w['basis'],
                           description='Selected primary gusset attachment to actual '+connect[0])
                    a.welds[-1].update(attachment_role='gusset_column_weld' if 'COLUMN' in connect else
                                       'gusset_base_weld' if 'BASE' in connect else 'gusset_beam_weld')
                    a.welds[-1].update(source_weld_id=w['id'],source_weld_side=(-1,1)[i],source_weld_leaf=pid)
                    if edge:a.welds[-1]['selected_material']=edge['material']
            part=primary
        elif row['connected_to']=='brace_end':
            tongue_half=max(hole/2+2,cheek/2)
            part=a.polygon(pid,rectangle(pin_s-hole/2-2,cap_s,-tongue_half,tongue_half,y),t,basis='S',
                           description=f'Selected supplier tongue {t:g} in with adopted end-cap fit')
            a.weld('W-'+pid,at(cap_s,-tongue_half,y+t/2),at(cap_s,tongue_half,y+t/2),
                   [pid,'END-CAP'],basis='A',description='Supplier tongue-to-cap reference line')
        else:
            primary=by_role[row['connected_to']]
            if abs(y+t-primary['start'])<1e-6:face=y+t
            elif abs(y-primary['finish'])<1e-6:face=y
            else:raise ValueError('Cheek does not abut its selected primary gusset: '+pid)
            ring=rectangle(pin_s-cheek/2,pin_s+cheek/2,-cheek/2,cheek/2,y)
            part=a.polygon(pid,ring,t,basis='S',description=f'Selected {cheek:g} in square pin cheek, t={t:g}')
            for i,(u,z) in enumerate(zip(ring,ring[1:]+ring[:1]),1):
                a.weld('W-'+pid+'-'+str(i),[u[0],face,u[2]],[z[0],face,z[2]],
                       [pid,primary['id']],source['cheek_weld_leg_in'],description='Selected cheek perimeter fillet to primary gusset')
                a.welds[-1]['attachment_role']='cheek_perimeter_fillet'
        part.update(selected_material=row['material'],parameters=dict(source_stack_role=role,
                    source_stack_index=row['index'],source_record_id=rid))
    cap_t=1.;cap_half=max(width/2,grip/2+1);cap_depth=max(depth/2,cheek/2+1)
    a.polygon('END-CAP',[at(cap_s,side*cap_depth,face*cap_half) for side,face in
              ((-1,-1),(-1,1),(1,1),(1,-1))],cap_t,normal=v,basis='A',
              description='Fitted supplier casing end cap on the common clevis stack')
    start=mul(v,cap_s+cap_t)
    a.member('BRACE',ctx.pid,start,add(start,mul(v,24)),description='Actual BRB casing trimmed to its supplier end cap')
    for suffix,side in (('A',-1),('B',1)):
        a.weld('CAP-W'+suffix,at(cap_s+cap_t,side*depth/2,-width/2),at(cap_s+cap_t,side*depth/2,width/2),
               ['BRACE','END-CAP'],.375,basis='A',description='Supplier casing/end-cap reference line')
    pin_part=a.fastener('PIN',[at(pin_s,0,-grip/2)],[0,1,0],source['pin_diameter_in'],grip,
                        [r['id'] for r in rows],'Selected common pin, diameter and complete grip')
    pin_part.update(functional_kind='pin',selected_material=source['pin_material'],
                    parameters=dict(source_record_id=rid,source_stack_roles=[r['role'] for r in rows]))
    drill_joined_plates(a,pin_part,hole,'Selected common pin-hole diameter')
    a.dim(at(pin_s,0,-grip/2),at(pin_s,0,grip/2),'Selected common-pin grip',view='section')
    a.dim(at(pin_s,-half,0),at(pin_s,half,0),'Selected primary width at pin')
    a.section_at=pin[0]
    return start
