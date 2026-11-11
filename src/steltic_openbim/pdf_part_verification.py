"""Compare the marked, painted PDF part outlines to the projected connection solids."""
from collections import defaultdict
from math import dist, isfinite

from shapely import make_valid, union_all
from shapely.geometry import LineString, Polygon

from .pdf_verification import transform


# ReportLab emits six decimal places or significant digits, depending on magnitude.
INK_TOL_PT = 0.01


class FaceInk:
    def __init__(self, number, clipped=False):
        self.number=number
        self.errors={"part is inside a clipping path"} if clipped else set()
        self.path=[]
        self.fills=[]
        self.strokes=[]

    def read(self,op,args,ctm,stroke,fill,width):
        if op==b"n":
            self.path=[]
        elif op==b"m":
            self.path.append([transform(ctm,args)])
        elif op==b"l" and self.path:
            self.path[-1].append(transform(ctm,args))
        elif op==b"h" and self.path:
            self.path[-1].append(self.path[-1][0])
        elif op in (b"S",b"s",b"f",b"f*",b"B",b"B*",b"b",b"b*"):
            if op not in (b"S",b"s"):
                if len(fill) in (1,3) and min(fill)>.985:
                    self.errors.add("part uses an invisible fill")
                self.fills.extend(self.path)
            if op not in (b"f",b"f*"):
                if width<=0 or (len(stroke) in (1,3) and min(stroke)>.985):
                    self.errors.add("part uses an invisible stroke")
                self.strokes.extend(self.path)
            self.path=[]
        elif op in (b"W",b"W*",b"Do",b"gs",b"re",b"c",b"v",b"y"):
            self.errors.add("part contains an unsupported paint or clipping operation")


def shapes(rings):
    areas=[]
    lines=[]
    for points in rings:
        if len(points)<2:
            continue
        if len(points)>2:
            face=Polygon(points)
            if face.area>1e-8:
                areas.append(face if face.is_valid else make_valid(face))
                continue
        if len(set(points))>1:
            lines.append(LineString(points))
    # Edge-on facets of a closed solid lie within its projected polygon.
    return union_all(areas or lines,grid_size=.00001)


def check_parts(scene,view,ink,crop):
    parts=scene["parts"]
    axes=scene["front_axes"]
    x,y,w,h=map(float,view["rect_pt"])
    den=float(view["scale_denominator"])
    if (not all(isfinite(v) for v in (x,y,w,h,den)) or min(w,h,den)<=0
            or x<crop[0] or y<crop[1] or x+w>crop[2] or y+h>crop[3]):
        return 0,[(scene["id"],"invalid part view scale or crop")]
    scale=72/den
    all_points=[p for part in parts for face in part["faces"] for p in face]
    centres=[(min(p[a] for p in all_points)+max(p[a] for p in all_points))/2 for a in axes]
    origin=(x+w/2-centres[0]*scale,y+h/2-10-centres[1]*scale)
    def project(p):
        return tuple(origin[j]+scale*p[a] for j,a in enumerate(axes))
    painted=defaultdict(list)
    for face in ink:
        painted[face.number].append(face)
    issues=[]
    count=0
    for i,part in enumerate(parts):
        if part["kind"]=="concrete":
            continue
        count+=1
        groups=painted.pop(i,[])
        errors=set()
        rings=[]
        for group in groups:
            errors.update(group.errors)
            if part.get("drawing_style")=="outline":
                vertices=[]
                for chain in group.strokes:
                    if vertices and dist(vertices[-1],chain[0])>INK_TOL_PT:
                        errors.add("disconnected outline strokes")
                    vertices.extend(chain if not vertices else chain[1:])
                if len(vertices)<3 or dist(vertices[0],vertices[-1])>INK_TOL_PT:
                    errors.add("incomplete outline strokes")
                else:
                    rings.append(vertices)
            else:
                rings.extend(group.fills)
        actual=shapes(rings)
        if actual.is_empty:
            errors.add("no painted part silhouette")
        else:
            expected=shapes([[project(p) for p in face] for face in part["faces"]])
            if expected.is_empty or not (
                    actual.buffer(INK_TOL_PT).covers(expected)
                    and expected.buffer(INK_TOL_PT).covers(actual)):
                errors.add("painted part silhouette differs from projected solid")
            if (actual.bounds[0]<x-INK_TOL_PT or actual.bounds[1]<y-INK_TOL_PT
                    or actual.bounds[2]>x+w+INK_TOL_PT or actual.bounds[3]>y+h+INK_TOL_PT):
                errors.add("part extends beyond its drawing window")
        issues.extend((part["id"],error) for error in sorted(errors))
    issues.extend((str(i),"painted part has no source solid") for i in painted)
    return count,issues
