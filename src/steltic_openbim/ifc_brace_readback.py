"""Intersect actual IFC brace bodies with their bound receiving steel members."""
from collections import defaultdict
from functools import lru_cache
import math

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.ifcopenshell_wrapper as wrapper
from ifcopenshell.util.element import get_psets
import numpy as np
from .ifc_readback_session import read_step


def verify_member_clearance(ifc_path,physical,crossings=(),source_records=None):
    members={m['id']:m for m in physical['members']}
    brace_ids={key for key,m in members.items() if any(token in m['kind'] for token in
              ('brace','truss_web','diagonal','lateral_strut'))}
    joints=defaultdict(list)
    for connection in physical['connections']:
        binds=set(connection.get('assembly_instance',{}).get('bindings',{}).values()) & members.keys()
        for brace in binds & brace_ids:
            for receiver in binds-brace_ids:
                joints[(brace,receiver)].append(connection['id'])
    result=dict(passed=False,brace_members=len(brace_ids),bound_pairs=len(joints),meshed_members=0,
                braces_with_bound_steel_receiver=len({k[0] for k in joints}),solid_pair_operations=0,findings=[])
    result['crossing_pairs']=len(crossings)
    result['crossings_checked']=0
    result['crossing_measurements']=[]
    if not joints and not crossings:
        result['passed']=True
        return result
    wanted={m for pair in joints for m in pair}
    crossing_ids={k for c in crossings for k in c['member_ids']}
    wanted.update(crossing_ids)
    model=read_step(ifc_path)
    objects={}
    for cls in ('IfcMember','IfcBeam','IfcColumn','IfcBuildingElementProxy'):
        for product in model.by_type(cls):
            key=get_psets(product,psets_only=True).get('Steltic_Coordination',{}).get('SourceId')
            if key in wanted:
                if key in objects:
                    result['findings'].append(dict(member=key,issue='duplicate IFC occurrence'))
                objects[key]=product
    for missing in sorted(wanted-objects.keys()):
        result['findings'].append(dict(member=missing,issue='IFC product absent'))
    if not objects:
        return result
    settings=ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS,True)
    ids={product.GlobalId:key for key,product in objects.items()}
    bounds={}
    crossing_meshes={}
    iterator=ifcopenshell.geom.iterator(settings,model,num_threads=1,include=list(objects.values()))
    seen=set()
    if iterator.initialize():
        while True:
            shape=iterator.get()
            key=ids[shape.guid]
            vertices=np.asarray(shape.geometry.verts,dtype=float).reshape(-1,3)
            if len(vertices) and np.isfinite(vertices).all():
                bounds[key]=(vertices.min(axis=0),vertices.max(axis=0))
                seen.add(key)
                if key in crossing_ids:
                    crossing_meshes[key]=(vertices/.0254,np.asarray(shape.geometry.faces,dtype=int).reshape(-1,3))
            if not iterator.next():
                break
    result['meshed_members']=len(seen)
    for missing in sorted(objects.keys()-seen):
        result['findings'].append(dict(member=missing,issue='IFC body could not be tessellated'))
    if crossings:
        from .ifc_crossing_readback import check_crossing
        for crossing in crossings:
            ids=crossing['member_ids']
            if len(ids)!=2 or any(k not in crossing_meshes or k not in members for k in ids):
                issue={'issue':'crossing has no pair of identifiable source and IFC bars'}
            else:
                selected={}
                if source_records is not None:
                    fields=source_records[crossing['record_id']]['fields']
                    selected={fields[i]['field']:fields[i]['value'] for i in crossing['selected']
                              if fields[i]['role']=='flat_bar_crossing_fillet'}
                issue=check_crossing(crossing,members,crossing_meshes,result['crossing_measurements'],selected)
                result['crossings_checked']+=1
            if issue:
                result['findings'].append(dict(crossing=crossing['id'],members=ids,**issue))
    native_settings=ifcopenshell.geom.settings()
    native_settings.set('use-world-coords',True)
    native_settings.set('iterator-output',wrapper.NATIVE)
    inch=.0254
    @lru_cache(maxsize=192)
    def solid(key,backend):
        product=ifcopenshell.geom.create_shape(native_settings,objects[key],geometry_library=backend)
        shape=product.geometry.as_compound(True)
        volume=shape.volume().to_double()
        if not math.isfinite(volume) or volume<=0:
            raise ValueError('IFC member lacks a positive-volume solid')
        return product,shape
    for (brace,receiver),connections in sorted(joints.items()):
        if brace not in seen or receiver not in seen:
            continue
        alo,ahi=bounds[brace]
        blo,bhi=bounds[receiver]
        if min(np.minimum(ahi,bhi)-np.maximum(alo,blo))<=.0001*inch:
            continue
        result['solid_pair_operations']+=1
        failures=[]
        for backend in ('manifold','cgal'):
            try:
                a=solid(brace,backend)
                b=solid(receiver,backend)
                common=a[1].intersect(b[1])
                volume=common.volume().to_double()/inch**3
                if not math.isfinite(volume) or volume < -1e-6:
                    raise ValueError('invalid common volume')
                if volume>1e-6:
                    result['findings'].append(dict(brace=brace,receiver=receiver,connections=connections,
                        issue='positive IFC solid intersection with bound member',intersection_in3=volume,kernel=backend))
                break
            except (ValueError,RuntimeError,AttributeError) as exc:
                failures.append(f'{backend}: {exc}')
        else:
            result['findings'].append(dict(brace=brace,receiver=receiver,connections=connections,
                issue='unable to establish solid clearance',detail=failures))
    solid.cache_clear()
    result['passed']=not result['findings']
    return result
