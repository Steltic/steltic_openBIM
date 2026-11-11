"""Locate source-selected crossing fillets on the actual two flat-bar edges."""
import math

from .assembly_scene import Assembly
from .drawing_workflow import fingerprint
from .pilots.model import add, sub, mul, dot, cross, unit
from .stmf_fit import local


def crossing_scene(rows,profiles,selected):
    if selected['count'] != 4:
        raise ValueError('The selected crossing requires a different weld layout')
    a=Assembly('WELDED FLAT-BAR CROSSING | '+ ' / '.join(r['pid'] for r in rows),profiles)
    for r in rows:
        a.member(r['role'],r['pid'],sub(r['centre'],mul(r['ray'],8)),
                 add(r['centre'],mul(r['ray'],8)),y=r['width_axis'])
    centres=[r['centre'][1] for r in rows]
    low,high=sorted(range(2),key=lambda i:centres[i])
    contact=centres[low]+rows[low]['thickness']/2
    opposite=centres[high]-rows[high]['thickness']/2
    if abs(contact-opposite)>1e-5:
        raise ValueError('Selected crossing flat bars do not meet face to face')
    weld_length=selected['length_in']
    for i,r in enumerate(rows):
        other=rows[1-i]
        projection=dot(r['ray'],other['width_axis'])
        if abs(projection)<1e-6:
            raise ValueError('Selected crossing bars are parallel')
        available=other['width']/abs(projection)
        for side in (-1,1):
            edge=add(r['centre'],mul(r['width_axis'],side*r['width']/2))
            station=dot(sub(other['centre'],edge),other['width_axis'])/projection
            centre=add(edge,mul(r['ray'],station))
            centre[1]=contact
            p=sub(centre,mul(r['ray'],weld_length/2))
            q=add(centre,mul(r['ray'],weld_length/2))
            a.weld(f'XW{i+1}'+('A' if side<0 else 'B'),p,q,[r['role'],other['role']],
                   selected['size_in'],description='Selected crossing fillet on the exposed flat-bar edge')
            a.welds[-1].update(attachment_role='flat_bar_crossing_fillet',
                               available_edge_length_in=available,selected_total_length_in=weld_length)
        if available+1e-4<weld_length:
            a.notes.append(f"{r['role']} has {available:.4f} in of straight lap edge for each selected {weld_length:g} in fillet. Review this source geometry conflict.")
    a.dim(a.welds[0]['a'],a.welds[0]['b'],'Selected crossing fillet length')
    return a.result()


def add_crossings(package,model):
    handoff=package.get('source_handoff',{})
    required=handoff.get('crossing_interfaces',[])
    if not required:
        return 0
    physical=package['physical']
    members={m['id']:m for m in physical['members']}
    profiles={p['id']:p for p in physical['profiles']}
    templates={t['id']:t for t in physical['assemblies']}
    existing={c['id']:c for c in physical['connections']}
    catalogue={m['id']:m for m in physical['materials']}
    next_sheet=max(int(s['sheet'][1:]) for s in model['connection_assemblies'])
    variants={}
    count=0
    for source in required:
        if source['kind']!='flat_bar_crossing' or source.get('native_connection_ids'):
            continue
        rid=source['record_id']
        fields=handoff['records'][rid]['fields']
        selected={fields[i]['field']:fields[i]['value'] for i in source['selected']
                  if fields[i]['role']=='flat_bar_crossing_fillet'}
        ids=source['member_ids'];origin=source['point_in'];bars=[members[mid] for mid in ids]
        world_ray=unit(sub(bars[0]['axis'][1],bars[0]['axis'][0]))
        x=unit([world_ray[0],world_ray[1],0.])
        frame=dict(origin=origin,x_axis=x,y_axis=cross([0.,0.,1.],x))
        rows=[]
        for i,m in enumerate(bars):
            if profiles[m['profile_id']]['family']!='flat':
                raise ValueError('Selected crossing receiver is not a flat bar: '+m['id'])
            dims=profiles[m['profile_id']]['dimensions']
            ends=[add(p,o) for p,o in zip(m['axis'],m['end_offsets'])]
            ray=unit(sub(ends[1],ends[0]))
            centre=add(ends[0],mul(ray,dot(sub(origin,ends[0]),ray)))
            rows.append(dict(role=f'BAR{i+1}',pid=m['profile_id'],width=dims['width'],thickness=dims['thickness'],
                             centre=local(centre,frame,True),ray=local(ray,frame),width_axis=local(m['local_y'],frame)))
        key=(rid,tuple(sorted(selected.items())),tuple((r['pid'],*(round(v,6) for k in ('centre','ray','width_axis') for v in r[k])) for r in rows))
        if key not in variants:
            from .saved_assemblies import native_parts
            scene=crossing_scene(rows,profiles,selected)
            next_sheet+=1;sid=f'CD{next_sheet:03}';sheet=f'C{next_sheet:03}'
            scene.update(id=sid,sheet=sheet,reference='1/'+sheet,family='flat_bar_crossing',subtype='',
                         source_text=fields[source['selected'][0]]['source']['literal'],source_record_ids=[rid],
                         representative_occurrence=source['id'],source_member_ids=ids,building_point=origin,
                         source_context={'record_ids':[rid]},level=bars[0]['level'],occurrences=[],occurrence_count=0)
            scene['geometry_sha256']=fingerprint([scene['parts'],scene['welds'],scene['interfaces']])
            # The source fixes dimensions and count. Use the accepted weld
            # material from the connection on these exact bars for its grade.
            end=existing[source['source_end_connection_ids'][0]]
            inherited=templates[end['assembly_instance']['template_id']]
            parts=native_parts(scene,inherited,catalogue)
            for p in parts:
                p['parameters']['source_field_indices']=source['selected']
                p['parameters']['source_record_id']=rid
            receivers=[dict(id=p['id'],kind='member',profile_id=p['profile_id'],axis=p['member']['axis'],
                            local_y=p['member']['local_y']) for p in scene['parts']]
            template=dict(id='crossing-'+fingerprint(key)[:16],basis='HR crossing fillets on the actual flat-bar lap',
                          source_detail=sid,source_record_ids=[rid],parts=parts,receivers=receivers)
            template['revision']=fingerprint(template)
            physical['assemblies'].append(template)
            model['connection_assemblies'].append(scene)
            variants[key]=(scene,template)
        scene,template=variants[key]
        cid=source['id'];jid=cid+':joint'
        scene['occurrences'].append(cid);scene['occurrence_count']+=1
        bindings={r['role']:mid for r,mid in zip(rows,ids)}
        frame.update(template_id=template['id'],revision=template['revision'],bindings=bindings)
        attachments=[dict(member_id=mid,station=t,offset=[0.,0.,0.]) for mid,t in zip(ids,source['member_stations'])]
        physical['joints'].append(dict(id=jid,point=origin,member_ends=[],attachments=attachments,status='declared',
                                       basis='Intersection of the selected source member worklines'))
        drawing=dict(id=cid,point=origin,member_ids=ids,parts=[],basis='S',parameters={'source_crossing_id':cid},
                     design_record_ids=[rid],detail_ref={'id':'flat_bar_crossing'},source_analysis_member_ids=[],
                     drawing_ref=scene['reference'],assembly_id=scene['id'])
        model['connections'].append(drawing)
        detail=dict(id=model['pilot']+'/'+scene['id'],legacy_family='flat_bar_crossing',
                    revision=scene['geometry_sha256'],source_drawing=scene['reference'])
        physical['connections'].append(dict(drawing,joint_id=jid,assembly_instance=frame,status='declared',
                                            scope='designed',detail_ref=detail))
        count+=1
    return count
