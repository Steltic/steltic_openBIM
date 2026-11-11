"""Reject common material between separate delivered IFC gusset occurrences."""
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from shapely import STRtree
from shapely.geometry import box

from .joint_mesh_readback import TOL,plane_axes


@dataclass
class PlacedGusset:
    connection:str
    sheet:str
    part:str
    mesh:object
    placement:object

    @cached_property
    def bounds(self):
        vertices=self.mesh.vertices@self.placement[:3,:3].T+self.placement[:3,3]
        return vertices.min(0),vertices.max(0)

    @cached_property
    def world(self):
        return self.mesh.transformed(self.placement)

    @cached_property
    def prism(self):
        mesh=self.mesh
        n=mesh.plate_normal
        stations=mesh.vertices@n
        lo,hi=float(min(stations)),float(max(stations))
        if not mesh.closed or hi-lo<=TOL:return None
        if np.any(np.minimum(np.abs(stations-lo),np.abs(stations-hi))>TOL):return None
        for f in mesh.polygons:
            if np.ptp(f@n)<=TOL:continue
            perpendicular=np.cross(f,np.roll(f,-1,axis=0)).sum(axis=0)
            size=np.linalg.norm(perpendicular)
            if size<1e-9 or abs(perpendicular@n)>1e-6*size:return None
        return self.placement[:3,:3]@n


def solid_volume(a,b):
    """Read the exact constituent face sets into native IFC solid operations."""
    import ifcopenshell
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.root
    import ifcopenshell.api.unit
    import ifcopenshell.geom
    import ifcopenshell.ifcopenshell_wrapper as wrapper
    model=ifcopenshell.file(schema='IFC4')
    ifcopenshell.api.root.create_entity(model,ifc_class='IfcProject')
    ifcopenshell.api.unit.assign_unit(model)
    context=ifcopenshell.api.context.add_context(model,context_type='Model')
    body=ifcopenshell.api.context.add_context(model,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=context)
    origin=a.vertices[0]
    entities=[]
    for mesh in (a,b):
        obj=ifcopenshell.api.root.create_entity(model,ifc_class='IfcPlate')
        shape=ifcopenshell.api.geometry.add_mesh_representation(model,context=body,
            vertices=[((mesh.vertices-origin)*.0254).tolist()],faces=[list(mesh.faces)])
        ifcopenshell.api.geometry.assign_representation(model,product=obj,representation=shape)
        ifcopenshell.api.geometry.edit_object_placement(model,product=obj)
        entities.append(obj)
    settings=ifcopenshell.geom.settings()
    settings.set('iterator-output',wrapper.NATIVE)
    failures=[]
    for backend in ('manifold','cgal'):
        try:
            handles=[ifcopenshell.geom.create_shape(settings,obj,geometry_library=backend) for obj in entities]
            solids=[s.geometry.as_compound(True) for s in handles]
            if any(s.volume().to_double()<=0 for s in solids):raise ValueError('non-positive plate solid')
            volume=solids[0].intersect(solids[1]).volume().to_double()/.0254**3
            if not np.isfinite(volume) or volume< -1e-6:raise ValueError('invalid intersection')
            return float(volume),backend
        except (ValueError,RuntimeError,AttributeError) as exc:
            failures.append(backend+' '+str(exc))
    raise ValueError('Unable to establish solid clearance: '+', '.join(failures))


def check_shared_gussets(rows,connections):
    owned={(r.connection,r.part) for r in rows}
    findings=[]
    declared=0
    for c in connections:
        for link in c.get('parameters',{}).get('shared_constituents',[]):
            role,owner=link['role'],(link['owner_connection_id'],link['owner_part_id'])
            if 'gusset' not in (role+' '+owner[1]).lower():continue
            declared+=1
            if owner not in owned or owner[0]==c['id'] or (c['id'],role) in owned:
                findings.append(dict(code='shared_gusset_owner_inconsistent',connection=c['id'],role=role,
                                     owner_connection=owner[0],owner_part=owner[1]))
    boxes=[box(*r.bounds[0][:2],*r.bounds[1][:2]) for r in rows]
    pairs=STRtree(boxes).query(boxes) if rows else ([],[])
    tested=0
    for i,j in zip(*pairs):
        if j<=i:continue
        a,b=rows[i],rows[j]
        if a.connection==b.connection:continue
        if min(np.minimum(a.bounds[1],b.bounds[1])-np.maximum(a.bounds[0],b.bounds[0]))<=TOL:continue
        tested+=1
        detail=dict(connections=[a.connection,b.connection],parts=[a.part,b.part],sheets=[a.sheet,b.sheet])
        try:
            if a.prism is not None and b.prism is not None and np.linalg.norm(np.cross(a.prism,b.prism))<1e-9:
                n=a.prism
                first,second=a.world.vertices@n,b.world.vertices@n
                lo,hi=max(min(first),min(second)),min(max(first),max(second))
                if hi-lo<=TOL:continue
                uv=plane_axes(n)
                station=float((lo+hi)/2)
                p,q=(r.world.section(n,station,uv) for r in (a,b))
                if p.is_empty or q.is_empty:raise ValueError('Unable to read both occupied plate sections')
                area=float(p.intersection(q).area)
                volume=area*(hi-lo)
                detail.update(common_section_in2=area,common_thickness_in=float(hi-lo),method='parallel plate sections')
            else:
                volume,backend=solid_volume(a.world,b.world)
                detail['method']=backend
            if volume>1e-6:findings.append(dict(detail,code='distinct_assembly_gussets_occupy_common_material',volume_in3=float(volume)))
        except (ValueError,RuntimeError,AttributeError) as exc:
            findings.append(dict(detail,code='interassembly_gusset_clearance_unverified',error=str(exc)))
    return dict(actual_gusset_occurrences=len(rows),shared_gusset_references=declared,
                interassembly_gusset_pairs_tested=tested),findings
