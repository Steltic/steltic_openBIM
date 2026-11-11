"""Resolve one physical constituent shared by two checked connection occurrences."""
from collections import defaultdict
from copy import deepcopy
import json

import numpy as np

from .joint_mesh_readback import TOL,frame,transform,unit
from .pin_stack_readback import actual_materials,material_key


def linked_braces(connections):
    owners=defaultdict(set)
    for connection in connections.values():
        for ref in connection.get('parameters',{}).get('shared_constituents',[]):
            if ref.get('role')=='GUSSET':
                owners[ref.get('owner_connection_id')].update(connection.get('assembly_instance',{}).get('bindings',{}).values())
    return owners


def resolve_shared(check,connection,own_parts,instance):
    from .ifc_assembly_verification import brace_kind,property_value,selected
    refs=connection.get('parameters',{}).get('shared_constituents',[])
    virtual={};meshes={};curves=[]
    if not refs:return virtual,meshes,curves
    cid=connection['id'];inverse=np.linalg.inv(instance);local_bindings=connection['assembly_instance']['bindings']
    stored=json.loads(property_value(check.rb.assemblies[cid],'SourceEntity') or '{}')
    if refs!=stored.get('parameters',{}).get('shared_constituents'):
        raise ValueError('Shared-constituent references differ in the delivered IFC SourceEntity: '+cid)
    by_owner=defaultdict(list)
    for ref in refs:
        by_owner[ref['owner_connection_id']].append(ref)
    if len({ref['role'] for ref in refs})!=len(refs):
        raise ValueError('Duplicate secondary shared constituent role: '+cid)
    for owner_id,group in by_owner.items():
        if cid==owner_id or owner_id not in check.connections or owner_id not in check.rb.assemblies:
            raise ValueError('Missing or self-referential shared physical owner: '+owner_id)
        owner=check.connections[owner_id];oi=owner['assembly_instance'];tid=oi['template_id'];template=check.templates[tid]
        product=check.rb.assemblies[owner_id]
        if property_value(product,'SourceId')!=owner_id:
            raise ValueError('Shared owner IFC SourceId differs: '+owner_id)
        links=[r for r in check.rb.assemblies[cid].HasAssignments if r.is_a('IfcRelAssignsToProduct') and r.Name=='Shared assembly constituents' and r.RelatingProduct==product]
        if len(links)!=1 or json.loads(links[0].Description or '[]')!=group:
            raise ValueError('Shared IFC owner relationship missing or different: '+owner_id)
        owner_points=[connection['point'],owner['point']]
        if any(max(np.linalg.norm(np.asarray(p)-ref['point_in']) for p in owner_points)>TOL for ref in group):
            raise ValueError('Shared parts refer to a different physical joint: '+owner_id)
        map_roles={r['owner_part_id']:r['role'] for r in group}
        if len(map_roles)!=len(group):raise ValueError('One owner solid occupies multiple shared roles: '+owner_id)
        owner_parts={p['id']:p for p in template['parts']};ranges={p['id']:p for p in check.rb.ranges[tid]}
        _,raw,placed=check.rb.mesh(product);owner_frame=frame(oi['origin'],oi['x_axis'],oi['y_axis'])
        shift=inverse@owner_frame;actual_shift=inverse@placed
        materials=actual_materials(product);welds=set()
        for ref in group:
            role=ref['role'];pid=ref['owner_part_id']
            if (role in own_parts or pid not in owner_parts or ref['owner_template_id']!=tid
                    or ref['owner_template_revision']!=template['revision'] or oi['revision']!=template['revision']):
                raise ValueError('Shared solid is duplicated, missing or bound to a different revision: '+role)
            locator=ranges[pid];start,count=locator['face_start'],locator['face_count']
            if owner_parts[pid]['kind']=='weld':
                if count!=0:raise ValueError('Shared weld reference has unexpected solid faces: '+pid)
                welds.add(pid);welds.update(ref.get('owner_weld_roles',[]));continue
            if count<=0 or start<0 or start+count>len(raw.faces):
                raise ValueError('Shared constituent lacks real IFC faces: '+pid)
            original=owner_parts[pid];part=deepcopy(original);part['id']=role
            meshes[role]=raw.subset(start,count).transformed(actual_shift)
            # All bearing checks for this recipient use its assembly coordinate frame.
            for hole in part.get('parameters',{}).get('holes',[]):
                hole['point']=transform(np.asarray([hole['point']]),shift)[0].tolist()
                hole['axis']=unit(shift[:3,:3]@np.asarray(hole['axis'])).tolist()
            if role=='GUSSET':
                for owner_cid in (cid,owner_id):
                    fields=selected(check.handoff,owner_cid)
                    for thickness in fields.get(('gusset','thickness_in'),[]):
                        if abs(float(np.ptp(meshes[role].vertices@meshes[role].plate_normal))-float(thickness))>TOL:
                            raise ValueError('Shared actual gusset thickness differs at '+owner_cid)
                    for material in fields.get(('gusset','material'),[]):
                        if material_key(material) not in material_key(materials.get(pid,'')):
                            raise ValueError('Shared actual gusset lacks the selected material at '+owner_cid)
            virtual[role]=part
            welds.update(ref.get('owner_weld_roles',[]))
            check.counts['actual_shared_constituent_bindings']+=1
        receivers={r for r,m in oi.get('bindings',{}).items() if m in check.members and not brace_kind(check.members[m])}
        expected_welds={p['id'] for p in owner_parts.values() if p['kind']=='weld' and set(p.get('connects',[]))&map_roles.keys()
                        and set(p.get('connects',[]))<=receivers|map_roles.keys()}
        if all(ref.get('sharing_kind')=='column_base_support' for ref in group):
            # The secondary draws its own gusset weld to the primary's sole.
            # Column-to-sole and anchor attachments remain on the primary.
            mid=group[0].get('column_id')
            if (map_roles!={'P1':'BASE'} or not mid or local_bindings.get('COLUMN')!=mid or
                    mid not in oi['bindings'].values() or check.members.get(mid,{}).get('kind')!='column' or
                    owner.get('detail_ref',{}).get('legacy_family') not in ('review_base','review_wall_base')):
                raise ValueError('Secondary gusset sole does not share its actual column with the base owner')
            expected_welds=set()
        if welds!=expected_welds:
            raise ValueError('Shared support weld coverage differs for '+owner_id+': '+str(sorted(welds^expected_welds)))
        ref_lines=check.rb.curves(owner_id)
        for wid in sorted(welds):
            weld=owner_parts.get(wid,{})
            if weld.get('kind')!='weld' or weld.get('geometry',{}).get('type')!='polyline':
                raise ValueError('Shared support weld missing from its owner: '+wid)
            bound=[]
            for role in weld.get('connects',[]):
                if role in map_roles:bound.append(map_roles[role]);continue
                mid=oi.get('bindings',{}).get(role)
                equivalents=[r for r,m in local_bindings.items() if m==mid]
                if len(equivalents)!=1:
                    raise ValueError('Shared support weld has an unbound receiving part: '+wid+'/'+role)
                bound.append(equivalents[0])
            expected=transform(weld['geometry']['points'],owner_frame)
            matches=[line for line in ref_lines if line.shape==expected.shape and min(np.max(abs(line-expected)),np.max(abs(line[::-1]-expected)))<=TOL]
            if len(matches)!=1:
                raise ValueError('Shared support weld must resolve to one real IFC reference: '+wid)
            identity='shared:'+owner_id+':'+wid;copy=deepcopy(weld);copy['id']=identity;copy['connects']=bound
            copy.setdefault('parameters',{}).setdefault('source_weld_id',wid)
            copy['geometry']['points']=transform(expected,inverse).tolist()
            virtual[identity]=copy;curves.append(matches[0]);check.counts['actual_shared_support_weld_bindings']+=1
    return virtual,meshes,curves
