"""Fit transverse floor tabs and deck boundaries to their located transfer panel."""
from copy import deepcopy
from math import dist
from .pilots.model import dot,add,mul
from .bim_assemblies import transformed

def draw(ctx):
    from .connection_cuts import drill_receivers
    from .review_hr_details import support
    a=ctx.a;spec=ctx.params['transfer_floor_tab_design'];face=spec['outer_face']
    a.title='TRANSVERSE FLOOR TAB | '+ctx.pid
    loc=next(c['assembly_instance'] for c in ctx.package['physical']['connections'] if c['id']==ctx.c['id'])
    stock=spec['selected_components']['transfer_floor_tab_receiver'];ray=loc['x_axis']
    if dot(face['plane_normal'],ray)<.99999:raise ValueError('Transfer tab faces away from its floor beam')
    x=(face['face_plane_y']-loc['origin'][1])*ray[1]
    yl,yh=sorted(dx*loc['y_axis'][0] for dx in face['weld_root_x_rel'])
    lo,hi=face['weld_root_z_rel'];length=hi-lo
    if abs(length-stock['weld_length_in'])>.001 or x<=0:raise ValueError('Transfer tab weld does not match its checked receiver')
    support(ctx,ctx.pid);dims=ctx.p[ctx.pid]['dimensions']
    reach=stock['end_setback_in'];line=stock['bolt_line_from_face_in']
    a.member('M2',ctx.pid,[x+reach,0,-dims['d']/2],[x+reach+42,0,-dims['d']/2])
    bolt=ctx.selected;dia=bolt[('bolt','diameter_in')];count=int(bolt[('bolt','count')]);pitch=bolt[('bolt','pitch_in')]
    edge=bolt[('bolt','horizontal_edge_in')]
    plate=a.box('P1',[x,yl,lo],[line+edge,yh-yl,length],'S','Selected floor shear tab on transfer stock')
    plate.update(thickness=yh-yl,selected_material=bolt[('shear_plate','material')])
    receiver=a.box('PANEL',[x-stock['thickness_in'],yl-3,lo-1],[stock['thickness_in'],yh-yl+6,length+2],
                   'S face; local section','Local view of the parent transfer panel')
    receiver.update(selected_material=stock['material'],representation_role='context_only')
    edge=(length-(count-1)*pitch)/2;points=[[x+line,-dims['tw']/2,lo+edge+i*pitch] for i in range(count)]
    bore=bolt.get(('bolt','hole_diameter_in')) or dia+(0.125 if dia>=1 else 0.0625)
    bolts=a.fastener('F1',points,[0,1,0],dia,dims['tw']+yh-yl,['M2','P1'],'Selected bolt through the web and tab')
    bolts.update(functional_kind='bolt',selected_material=bolt[('bolt','material')])
    drill_receivers(a,bolts,bore)
    for label,y in (('W1',yl),('W1-B',yh)):
        a.weld(label,[x,y,lo],[x,y,hi],['PANEL','P1'],stock['weld_size_in'],basis='S',description='Fillet on the physical post-panel face')
        a.welds[-1]['selected_material']=stock['weld_material']
    a.dim([x,yl,lo],[x+reach,yl,lo],'Beam-end setback',basis='S')
    a.dim([x,yl,hi],[x+line,yl,hi],'Receiver face to bolt line',basis='S')
    a.section_at=x+line;a.section_axis=0

def place(package,model):
    native={m['id']:m for m in package['physical']['members']};drawn={m['id']:m for m in model['members']}
    for c in package['physical']['connections']:
        s=c.get('parameters',{}).get('transfer_floor_tab_design')
        if not s:continue
        face=s['outer_face'];mid=s['receiver_member_ids']['beam'];frame=c['assembly_instance'];ray=frame['x_axis']
        m=drawn[mid];end=min(range(2),key=lambda i:dist(m['axis'][i],c['point']))
        if dist(m['axis'][end],c['point'])>.001:raise ValueError('Selected floor tab is detached from its beam')
        cut=(face['face_plane_y']-frame['origin'][1])*ray[1]+face['end_setback_from_face_in']
        off=m['end_offsets'][end];m['end_offsets'][end]=add(off,mul(ray,cut-dot(off,ray)))
        native[mid]['end_offsets']=deepcopy(m['end_offsets'])

def bind(package,model):
    ph=package['physical'];connections={c['id']:c for c in ph['connections']};templates={t['id']:t for t in ph['assemblies']}
    owners={}
    for c in ph['connections']:
        s=c.get('parameters',{}).get('transfer_floor_tab_design')
        if not s:continue
        owner=connections[s['parent_connection_id']];frame=owner['assembly_instance'];tpl=templates[frame['template_id']]
        if s['receiver_plate'] not in {p['id'] for p in tpl['parts']}:raise ValueError('Missing checked transverse tab receiver')
        c['parameters'].setdefault('shared_constituents',[]).append(dict(role='PANEL',sharing_kind='transfer_floor_tab',
            owner_part_id=s['receiver_plate'],owner_connection_id=owner['id'],owner_template_id=tpl['id'],
            owner_template_revision=tpl['revision'],point_in=c['point']))
        owners[owner['id']]=owner
    if owners:fit_floor_boundaries(ph,model,templates,owners)

def fit_floor_boundaries(physical,model,templates,owners):
    import numpy as np
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    from .joint_mesh_readback import Mesh
    sections={}
    for owner in owners.values():
        frame=owner['assembly_instance'];z=owner['point'][2]
        template=templates[frame['template_id']]
        for part in template['parts']:
            if part.get('parameters',{}).get('source_role')!='transfer_post_gusset':continue
            points=[];faces=[]
            for face in part['geometry']['faces']:
                faces.append(tuple(range(len(points),len(points)+len(face))))
                points.extend(transformed(q,frame) for q in face)
            mesh=Mesh(np.asarray(points),tuple(faces))
            section=mesh.section([0.,0.,1.],z,(np.array([1.,0.,0.]),np.array([0.,1.,0.])))
            if section.is_empty:raise ValueError('Selected transfer panel misses the floor datum')
            sections.setdefault(z,[]).append(section)
    outlines={z:unary_union(shapes) for z,shapes in sections.items()}
    drawn={p['id']:p for p in model['panels']}
    for panel in physical['panels']:
        z=panel['vertices'][0][2]
        if panel['kind']!='floor' or z not in outlines:continue
        polygon=Polygon([p[:2] for p in panel['vertices']]);inside=polygon.intersection(outlines[z])
        if inside.area<1e-5:continue
        cut=polygon.difference(outlines[z])
        if cut.geom_type!='Polygon' or cut.interiors:raise ValueError('Transfer fan requires a separate interior opening or split floor')
        points=[[x,y,z] for x,y in list(orient(cut,sign=1).exterior.coords)[:-1]]
        panel['vertices']=points;drawn[panel['id']]['vertices']=deepcopy(points)
        drawn[panel['id']]['transfer_panel_notch_area_in2']=inside.area
