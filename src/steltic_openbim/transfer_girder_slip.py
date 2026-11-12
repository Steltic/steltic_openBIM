"""Build a longitudinal girder release between the actual plates of a transfer node."""
import math
from copy import deepcopy

from .connection_cuts import drill_plate, drill_receivers
from .pilots.model import add, dot, mul


def selection(package, connection):
    location = connection.get('parameters', {}).get('sliding_receiver')
    if not location:
        return None
    rid = location['record_id']
    records = [r for r in package['design_records'] if r['id'] == rid and rid in connection['design_record_ids']]
    if len(records) != 1 or records[0].get('waived'):
        raise ValueError('Sliding girder receiver needs its issued connection record')
    return location, records[0]['data']['sliding_receiver']


def place(package, model):
    members = {m['id']: m for m in model['members']}
    native = {m['id']: m for m in package['physical']['members']}
    for connection in package['physical']['connections']:
        selected = selection(package, connection)
        if not selected:
            continue
        loc, stock = selected
        mid = loc['girder_id']
        beam = members[mid]
        end = min(range(2), key=lambda i: math.dist(beam['axis'][i], connection['point']))
        if beam['profile_id'] != stock['beam'] or math.dist(beam['axis'][end], connection['point']) > .001:
            raise ValueError('The slotted receiver does not meet its selected girder end')
        ray = connection['assembly_instance']['x_axis']
        offset = beam['end_offsets'][end]
        beam['end_offsets'][end] = add(offset, mul(ray, stock['beam_gap_in'] - dot(offset, ray)))
        native[mid]['end_offsets'] = deepcopy(beam['end_offsets'])


def draw(ctx):
    from .review_hr_details import support
    _, s = selection(ctx.package, ctx.c)
    a = ctx.a
    a.title = 'LONGITUDINAL GIRDER SLIDING CONNECTION | '+ctx.pid
    support(ctx, ctx.pid)
    next(p for p in a.parts if p['id']=='M1')['description'] = 'Adjacent transverse beam at its installed setback'
    dimensions = ctx.p[ctx.pid]['dimensions']
    tw, depth = dimensions['tw'], dimensions['d']
    if abs(tw-s['web_in'])>.001 or abs(depth-s['beam_depth_in'])>.001:
        raise ValueError('Girder web or depth differs from its sliding connection design')
    gap, line = s['beam_gap_in'], s['bolt_line_in']
    a.member('M2',ctx.pid,[gap,0,-depth/2],[gap+38,0,-depth/2])
    material = s['material']
    def plate(name, origin, size, description):
        part = a.box(name,origin,size,'S',description)
        part['selected_material'] = material
        return part

    centre = -depth/2
    span, height, thickness = s['inner_fan_gap_in'], s['diaphragm_height_in'], s['diaphragm_thickness_in']
    low = centre-height/2
    plate('DIAPHRAGM',[-thickness,-span/2,low],[thickness,span,height],'Transverse diaphragm between both transfer fans')
    a.notes.append('The two fan portions are local sections of the transfer-node plates. The diaphragm bears the slotted tabs.')
    for side, name in ((-1,'FAN-L'),(1,'FAN-R')):
        y = side*span/2
        part = plate(name,[-4,y-s['fan_stock_in'] if side<0 else y,low-1],[16,s['fan_stock_in'],height+2],'Local part of the installed transfer fan')
        part['representation_role']='context_only'
        a.weld(name+'-CJP',[-thickness/2,y,low],[-thickness/2,y,low+height],['DIAPHRAGM',name],
               0,kind='CJP',description='Full-penetration diaphragm-to-fan groove')
        a.welds[-1]['selected_material']=s['weld_material']

    tab_depth, tab_t = s['tab_depth_in'], s['tab_thickness_in']
    count, pitch = s['bolt_count'], s['pitch_in']
    clear, sleeve = s['running_gap_in'], s['sleeve_length_in']
    if abs(sleeve-tab_t-2*clear)>.001 or (s['slot_length_in']-s['sleeve_od_in'])/2<s['travel_each_in']:
        raise ValueError('Selected sleeves do not provide the required sliding clearances')
    zlo = centre-tab_depth/2
    plate('BACKING',[0,-tw/2-clear,zlo],[s['backing_projection_in'],tw+2*clear,tab_depth],
          'Fitted continuous backing bar for the two outside-bevel tab grooves')
    points = [[line,0,centre+(i-(count-1)/2)*pitch] for i in range(count)]
    for side, name in ((-1,'P1'),(1,'P2')):
        inner = side*(tw/2+clear)
        ylo = min(inner,inner+side*tab_t)
        part = plate(name,[0,ylo,zlo],[s['tab_length_in'],tab_t,tab_depth],'Fixed shear tab with longitudinal slots')
        part['thickness']=tab_t
        drill_plate(part,points,[0,1,0],s['slot_width_in'],'S machined sleeve slot',[1,0,0],
                    slot_travel=s['slot_length_in']-s['slot_width_in'])
        y=ylo+tab_t/2
        a.weld(name+'-CJP',[0,y,zlo],[0,y,zlo+tab_depth],['DIAPHRAGM',name],0,kind='CJP',
               description='Full-penetration tab groove from the outer face on continuous backing')
        a.welds[-1]['selected_material']=s['weld_material']
        for j,(x,_,z) in enumerate(points):
            axis=[0,side,0];q=[x,side*tw/2,z]
            bush=a.cylinder(name+'-BUSH'+str(j),q,axis,s['sleeve_od_in'],sleeve,'S','Machined pretension spacer',kind='plate')
            bush['selected_material']=s['sleeve_material']
            drill_plate(bush,[q],axis,s['sleeve_bore_in'],'S bolt clearance in the sleeve')
            y=side*(tw/2+sleeve);kt=s['keeper_thickness_in']
            keeper=plate(name+'-KEEP'+str(j),[x-s['keeper_length_in']/2,min(y,y+side*kt),z-s['keeper_height_in']/2],
                         [s['keeper_length_in'],kt,s['keeper_height_in']],'Bored keeper washer seated on the moving sleeve')
            drill_plate(keeper,[q],axis,s['sleeve_bore_in'],'S keeper bore')
    near=-(tw/2+sleeve+s['keeper_thickness_in'])
    fastener=a.fastener('F1',[[x,near,z] for x,_,z in points],[0,1,0],s['bolt_in'],-2*near,
                        ['M2','P1','P2'],'Through bolt clamping the two sleeves, web and keepers')
    fastener.update(selected_material=s['bolt_material'],functional_kind='bolt')
    drill_receivers(a,dict(fastener,connects=['M2']),s['beam_bore_in'])
    a.interfaces.append(dict(id='SLIP',kind='horizontal_slotted_connection',connects=['M2','P1','P2'],
                             travel_in=2*s['travel_each_in'],basis='S',description='Sleeves move in both fixed tabs'))
    a.dim([0,0,zlo],[gap,0,zlo],'Girder end to diaphragm')
    a.dim([0,0,zlo+tab_depth],[line,0,zlo+tab_depth],'Diaphragm face to bolt line')
    a.notes.append('Centre sleeves within 1/8 in. Verify 1 in travel both ways. Tighten through the sleeves to 64–80 kip. Keepers clear both fixed tabs.')
    a.section_at=line;a.section_axis=0


def bind(package):
    physical = package['physical']
    connections = {c['id']: c for c in physical['connections']}
    templates = {t['id']: t for t in physical['assemblies']}
    for connection in connections.values():
        selected = selection(package,connection)
        if not selected:
            continue
        loc, _ = selected
        parent = connections[loc['parent_connection_id']]
        template = templates[parent['assembly_instance']['template_id']]
        names = {p['id'] for p in template['parts'] if p.get('parameters',{}).get('source_role')=='transfer_post_gusset'}
        if names!={loc['negative_fan'],loc['positive_fan']} or parent['point']!=connection['point']:
            raise ValueError('Sliding diaphragm requires both installed post fans at its own node')
        refs=connection['parameters'].setdefault('shared_constituents',[])
        for role,key in (('FAN-L','negative_fan'),('FAN-R','positive_fan')):
            refs.append(dict(role=role,sharing_kind='transfer_girder_slip',owner_part_id=loc[key],
                             owner_connection_id=parent['id'],owner_template_id=template['id'],
                             owner_template_revision=template['revision'],point_in=parent['point']))
