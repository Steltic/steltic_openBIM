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
    fields={key:member[key] for key in ("profile_id","local_y","end_offsets","extrusion_end_offsets","slots","rbs","cope","section_plies") if key in member}
    fields["axis"]=[[0.,0.,0.],(np.asarray(member["axis"][1])-origin).round(9).tolist()]
    if member.get("terminal_planes"):
        fields["terminal_planes"]=[dict(normal=p["normal"],offset_in=round(p["offset_in"]-float(origin@p["normal"]),9))
                                   for p in member["terminal_planes"]]
    if member.get('through_bores'):
        fields['through_bores']=[dict(h,point=(np.asarray(h['point'])-origin).tolist()) for h in member['through_bores']]
    return origin,fields,json.dumps(fields,sort_keys=True)


def opening_points(o):
    if o.get("vertices") is not None:
        return np.asarray(o["vertices"],dtype=float)
    ax,ay=["xyz".index(letter) for letter in o["plane"].lower()]
    p=np.tile([o["x_ft"]*12,o["y_ft"]*12,o["z_ft"]*12],(4,1)).astype(float)
    p[[1,2],ax]+=12*o["width_ft"]
    p[[2,3],ay]+=12*o["height_ft"]
    return p


def member_signature(faces,origin):
    if not faces:
        return [],np.empty((0,3))
    first=faces[0][0]
    # Match the precision of the native IFC coordinate list relative to its map origin.
    retained=[f for f in faces if len({tuple(round((v-a)*.0254,9) for v,a in zip(p,first)) for p in f})>=3]
    return [len(f) for f in retained],np.asarray([p for f in retained for p in f])-origin


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
            self.expected[key]=member_signature(member_faces(data,self.profiles),np.zeros(3))
        lengths=[len(r[0]) for r in faces]
        if any(len(rings)!=1 for rings in faces):
            return "unexpected void loop in the delivered section face"
        actual=points[np.concatenate([r[0] for r in faces])]-origin if faces else np.empty((0,3))
        def compare(expected):
            counts,coords=expected
            if lengths!=counts:
                return "delivered section faces or cut topology differ from the source member"
            if not len(coords) or np.abs(actual-coords).max()>INCH_TOL:
                return "delivered section or cut vertices differ from the numeric profile in its member frame"
            return None
        issue=compare(self.expected[key])
        if issue and any(member.get(k) for k in ("slots","terminal_planes","rbs","cope","through_bores")):
            # End stations within a few ULPs coalesce in the original world
            # coordinate frame. A translated replay can choose a different
            # coincident cap. Compare the exact input before flagging topology.
            issue=compare(member_signature(member_faces(member,self.profiles),origin))
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
