"""Read the numeric member faces, panel boundaries and voids from delivered IFC."""
from collections import defaultdict
import json

import ifcopenshell.util.placement
import numpy as np
from shapely import union_all
from shapely.geometry import Polygon

from .pilots.geometry import member_faces


INCH_TOL=1e-4


def mapped_body(obj):
    if not obj.Representation:
        raise ValueError("missing IFC body")
    reps=[item for rep in obj.Representation.Representations if rep.RepresentationIdentifier=="Body" for item in rep.Items]
    if len(reps)!=1 or not reps[0].is_a("IfcMappedItem"):
        raise ValueError("expected one native mapped body")
    item=reps[0]
    meshes=item.MappingSource.MappedRepresentation.Items
    if len(meshes)!=1 or not meshes[0].is_a("IfcPolygonalFaceSet"):
        raise ValueError("expected polygonal face set")
    placement=(ifcopenshell.util.placement.get_local_placement(obj.ObjectPlacement)
               @ifcopenshell.util.placement.get_mappeditem_transformation(item))
    return meshes[0],placement


def unpack(mesh):
    points=np.asarray(mesh.Coordinates.CoordList,dtype=float)
    faces=[]
    for face in mesh.Faces:
        rings=[np.array(face.CoordIndex,dtype=int)-1]
        if face.is_a("IfcIndexedPolygonalFaceWithVoids"):
            rings.extend(np.array(row,dtype=int)-1 for row in face.InnerCoordIndices)
        faces.append(rings)
    return points,faces


def member_key(member):
    origin=np.asarray(member["axis"][0])
    fields={key:member[key] for key in ("profile_id","local_y","end_offsets","extrusion_end_offsets","slots","rbs","cope") if key in member}
    fields["axis"]=[[0.,0.,0.],(np.asarray(member["axis"][1])-origin).round(9).tolist()]
    if member.get("terminal_planes"):
        fields["terminal_planes"]=[dict(normal=p["normal"],offset_in=round(p["offset_in"]-float(origin@p["normal"]),9))
                                   for p in member["terminal_planes"]]
    return origin,fields,json.dumps(fields,sort_keys=True)


def opening_points(o):
    if o.get("vertices") is not None:
        return np.asarray(o["vertices"],dtype=float)
    ax,ay=["xyz".index(letter) for letter in o["plane"].lower()]
    p=np.tile([o["x_ft"]*12,o["y_ft"]*12,o["z_ft"]*12],(4,1)).astype(float)
    p[[1,2],ax]+=12*o["width_ft"]
    p[[2,3],ay]+=12*o["height_ft"]
    return p


class ShapeReadback:
    def __init__(self,physical,unit_in):
        self.unit_in=unit_in
        self.profiles={p["id"]:p for p in physical["profiles"]}
        self.panels={p["id"]:p for p in physical.get("panels",[])}
        self.openings=defaultdict(list)
        without_host={}
        for o in physical.get("openings",[]):
            if o.get("host_id"):
                self.openings[o["host_id"]].append(o)
            else:
                without_host[o["id"]]=o
        for panel in self.panels.values():
            self.openings[panel["id"]].extend(without_host[k] for k in panel.get("openings",[]) if k in without_host)
        self.meshes={}
        self.expected={}
        self.verified={}

    def read(self,obj):
        mesh,placement=mapped_body(obj)
        if mesh.id() not in self.meshes:
            self.meshes[mesh.id()]=unpack(mesh)
        local,faces=self.meshes[mesh.id()]
        return mesh.id(),placement,(local@placement[:3,:3].T+placement[:3,3])*self.unit_in,faces

    def check_member(self,obj,member):
        origin,data,key=member_key(member)
        mesh_id,placement,points,faces=self.read(obj)
        # Include actual world placement relative to this occurrence's source workline.
        cache_key=(mesh_id,key,tuple(placement[:3,:3].round(9).flat),
                   tuple((placement[:3,3]*self.unit_in-origin).round(8)))
        if cache_key in self.verified:
            return self.verified[cache_key]
        if key not in self.expected:
            source=member_faces(data,self.profiles)
            expected=[f for f in source if len(set(tuple(round(x*.0254,9) for x in p) for p in f))>=3]
            self.expected[key]=([len(f) for f in expected],np.array([p for f in expected for p in f]))
        counts,coords=self.expected[key]
        issue=None
        if any(len(rings)!=1 for rings in faces) or [len(r[0]) for r in faces]!=counts:
            issue="delivered section faces, voids or cut topology differ from the source member"
        elif not len(coords) or np.abs(points[np.concatenate([r[0] for r in faces])]-origin-coords).max()>INCH_TOL:
            issue="delivered section or cut vertices differ from the numeric profile in its member frame"
        self.verified[cache_key]=issue
        return issue

    def check_panel(self,obj,panel):
        _,_,coords,faces=self.read(obj)
        expected=np.asarray(panel["vertices"],dtype=float)
        origin=expected[0]
        normal=np.sum(np.cross(expected-origin,np.roll(expected,-1,axis=0)-origin),axis=0)
        normal/=np.linalg.norm(normal)
        if not np.isfinite(normal).all() or np.max(abs((coords-origin)@normal))>INCH_TOL:
            return "actual IFC panel has a displaced or invalid source plane"
        # Dropping the axis normal's largest component gives a stable, independent planar chart.
        axes=[i for i in range(3) if i!=int(np.argmax(abs(normal)))]
        expected_area=Polygon(expected[:,axes])
        for o in self.openings[panel["id"]]:
            ring=opening_points(o)
            if np.max(abs((ring-origin)@normal))>INCH_TOL:
                return "declared opening misses its host plane"
            cut=Polygon(ring[:,axes])
            if not expected_area.buffer(INCH_TOL).covers(cut):
                return "declared opening falls outside or overlaps another opening in its host"
            expected_area=expected_area.difference(cut)
        actual=union_all([Polygon(coords[r[0]][:,axes],[coords[h][:,axes] for h in r[1:]]) for r in faces])
        if not actual.is_valid or not (
                actual.buffer(INCH_TOL).covers(expected_area) and expected_area.buffer(INCH_TOL).covers(actual)):
            return "actual IFC panel edge or opening differs from the declared host and opening boundaries"
        return None
