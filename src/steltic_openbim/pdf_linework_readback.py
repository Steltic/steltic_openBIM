"""Compare painted framing and native connection wires with projected source geometry."""
from collections import defaultdict
from bisect import bisect_left
from itertools import product
from math import dist,floor

from . import bim_assemblies
from .pilots.geometry import clip_axis,member_faces,part_faces
from .pdf_verification import POINT_TOL,transform


class WireInk:
    def __init__(self,tag,clipped=False):
        self.tag=tag
        self.segments=[]
        self.paths=[]
        self.errors={'linework is inside an unverified clipping path'} if clipped else set()

    def read(self,op,args,ctm,stroke,fill,width):
        if op==b'n':
            self.paths=[]
        elif op==b'm':
            self.paths.append([transform(ctm,args)])
        elif op==b'l' and self.paths:
            self.paths[-1].append(transform(ctm,args))
        elif op==b'h' and self.paths:
            self.paths[-1].append(self.paths[-1][0])
        elif op==b're':
            x,y,w,h=map(float,args)
            self.paths.append([transform(ctm,q) for q in ((x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y))])
        elif op in (b'S',b's',b'B',b'B*',b'b',b'b*'):
            if width<=0 or (len(stroke) in (1,3) and min(stroke)>.985):
                self.errors.add('linework uses an invisible stroke')
            for pts in self.paths:
                if op in (b's',b'b',b'b*') and pts[-1]!=pts[0]:pts.append(pts[0])
                self.segments.extend(zip(pts,pts[1:]))
            self.paths=[]
        elif op in (b'f',b'f*'):
            # White label backgrounds in a framing view use fill-only rectangles.
            self.paths=[]
        elif op in (b'W',b'W*',b'Do',b'gs',b'c',b'v',b'y'):
            self.errors.add('unsupported linework paint or clipping operator')


def unique_segments(lines):
    # Agree within the PDF's coordinate serialization, in either endpoint order.
    # Collapsed projected edges have no visible length.
    result={}
    for a,b in lines:
        if dist(a,b)<=.001:continue
        key=tuple(sorted((tuple(round(v,3) for v in a),tuple(round(v,3) for v in b))))
        result[key]=(a,b)
    return result


def differences(left,right):
    remaining=left.keys()-right.keys()
    if not remaining:return []
    def bucket(p):return tuple(floor(v/POINT_TOL) for v in p)
    index=defaultdict(list)
    for a,b in right.values():
        index[bucket(a)].append((a,b))
        index[bucket(b)].append((b,a))
    result=[]
    for key in remaining:
        a,b=left[key]
        x,y=bucket(a)
        nearby=(edge for dx,dy in product((-1,0,1),repeat=2) for edge in index.get((x+dx,y+dy),()))
        if not any(dist(a,p)<=POINT_TOL and dist(b,q)<=POINT_TOL for p,q in nearby):
            result.append(key)
    return result


def compare_lines(expected,group,crop):
    errors=list(group.errors)
    actual=unique_segments(group.segments)
    expected=unique_segments(expected)
    if any(not (crop[0]-.025<=x<=crop[2]+.025 and crop[1]-.025<=y<=crop[3]+.025)
           for segment in actual.values() for x,y in segment):
        errors.append('framing or connection linework is cropped by the PDF page')
    for left,right,label in [(expected,actual,'missing'),(actual,expected,'unexpected')]:
        delta=differences(left,right)
        if delta:
            errors.append(f'{len(delta)} {label} projected edges; first segment in PDF points {min(delta)}')
    return errors


def edges(points):
    return zip(points,points[1:]+points[:1])


def axis(member,offset):
    points=member['axis']
    if offset:
        return [[p[i]+d[i] for i in range(3)] for p,d in zip(points,member.get('end_offsets',[[0]*3]*2))]
    return points


class DrawingLinework:
    def __init__(self,model,manifest,native):
        self.native=native
        self.model=model
        physical=native.physical if native else model
        self.members={m['id']:m for m in physical.get('members',[])}
        self.profiles={p['id']:p for p in physical.get('profiles',[])}
        self.views=defaultdict(list)
        self.ordinary=manifest.get('representation')=='source_physical_geometry'
        self.required_frames=set()
        for v in manifest['views']:
            if self.members and v.get('grid_axes'):
                self.required_frames.add(v['sheet'])
            if v.get('linework') or v.get('kind')=='source_connection_assembly':
                self.views[v['sheet']].append(v)

    def framing(self,view):
        mode=view['linework']
        axes=view['axes']
        scale=view['points_per_inch']
        base=view['origin_pt']
        lows=[b[0] for b in view['bounds_in']]
        def project_point(p):
            return tuple(base[j]+(p[k]-lows[j])*scale for j,k in enumerate(axes))
        selected=view['member_ids']
        if not selected or len(selected)!=len(set(selected)) or any(i not in self.members for i in selected):
            raise ValueError('Framing view has empty, unknown or duplicate source member IDs')
        if mode=='physical_section':
            limits=view['limits_in']
            applicable={i for i,m in self.members.items() if clip_axis(*axis(m,True),limits)}
            if set(selected)!=applicable:
                raise ValueError('Section member list differs from its cut through the physical model')
        if mode=='source_axes' and self.native:
            if len(axes)!=2:raise ValueError('Native framing view has no plane')
            if 2 in axes:
                normal=next(i for i in (0,1) if i not in axes)
                station=view['source_plane_in']
                required={m['id'] for m in self.members.values() if all(abs(p[normal]-station)<1e-5 for p in m['axis'])}
            else:
                z=view['source_elevation_in']
                cols={m['id'] for m in self.members.values() if m['kind'] in ('col','column','post','endwall_post','chord')}
                levels=sorted(v[2] for v in self.model['levels'])
                k=next(i for i,v in enumerate(levels) if abs(z-v)<1e-5)
                if view['base_plan']:
                    required={i for i in cols if min(p[2] for p in self.members[i]['axis'])<=z+1e-5} or set(self.members)
                else:
                    required=set()
                    for i,m in self.members.items():
                        lo,hi=sorted(p[2] for p in m['axis'])
                        fallback=max(1,min(len(levels)-1,bisect_left(levels,hi-1e-5)))
                        level=m.get('level')
                        if level is None:level=m.get('storey') if type(m.get('storey')) in (int,float) else fallback
                        if (i in cols and lo-1e-5<=z<=hi+1e-5) or (i not in cols and (abs(hi-z)<1e-5 or level==k)):
                            required.add(i)
            if set(selected)!=required:
                raise ValueError('Framing view omits or adds members at the source plane or story')
        segments=[]
        seen=set()
        for ident in selected:
            m=self.members[ident]
            endpoints=axis(m,mode!='source_axes')
            a,b=map(project_point,endpoints)
            if mode=='physical_section':
                for face in member_faces(m,self.profiles,limits):
                    segments.extend(edges([project_point(p) for p in face]))
                continue
            if mode=='physical_plan':
                key=tuple(round(v,2) for v in (*a,*b))
                if key in seen:continue
                seen.add(key)
                if tuple(axes)==(0,1) and m['kind'] in ('composite_wall','wall_closure') and dist(endpoints[0][:2],endpoints[1][:2])<=.001:
                    # The ends of the real wall profiles form their plan footprint.
                    from .design_pdf import wall_plan_sections
                    rings=wall_plan_sections(m,self.profiles)
                    if not rings:raise ValueError('Cannot project the physical wall section')
                    for poly in rings:segments.extend(edges([project_point(p) for p in poly]))
                    continue
            elif mode!='source_axes':
                raise ValueError('Unrecognized framing view '+str(mode))
            segments.append((a,b))
            if dist(a,b)<2:
                h=3 if mode=='source_axes' else 2.5
                segments.extend(edges([(a[0]+dx*h,a[1]+dy*h) for dx,dy in ((-1,-1),(1,-1),(1,1),(-1,1))]))
        return len(selected),segments

    def connection(self,view):
        c=self.native.connections[view['connection_id']]
        parts=bim_assemblies.parts(c,self.native.templates,world=True)
        if [p['id'] for p in parts]!=view['part_ids']:
            raise ValueError('Native view part list differs from the located source assembly')
        s=view['points_per_inch']
        ox,oy=view['origin_pt']
        if not s>0:raise ValueError('Invalid native part projection scale')
        axes=view['axes']
        def project_point(p):
            u,v=((p[axes[0]],p[axes[1]]) if axes else (.8*p[0]-.6*p[1],.9*p[2]-.26*p[0]-.35*p[1]))
            return (ox+s*u,oy+s*v)
        segments=[]
        for p in parts:
            for face in part_faces(p,self.profiles):
                segments.extend(edges([project_point(q) for q in face]))
        return len(parts),segments

    def check(self,sheet,wires,crop):
        issues=[]
        frames=parts=0
        views=self.views.get(sheet,[])
        wanted=[v for v in views if v.get('linework') or v.get('kind')=='source_connection_assembly']
        if sheet in self.required_frames and not any(v.get('linework') for v in wanted):
            return 0,0,['Framing grid view has no source-bound member linework']
        if not wanted and not wires:return 0,0,[]
        if len(wanted)!=len(wires):
            return 0,0,['Missing or extra marked framing or native connection views']
        for view,wire in zip(wanted,wires):
            frame=bool(view.get('linework'))
            if wire.tag!=('/StelticFrame' if frame else '/StelticPartWire'):
                issues.append('Physical linework was painted in the wrong view')
                continue
            try:
                measured,segments=self.framing(view) if frame else self.connection(view)
                if frame:frames+=measured
                else:parts+=measured
                view_crop=crop
                if not frame and view.get('rect_pt'):
                    x,y,w,h=view['rect_pt']
                    view_crop=(max(crop[0],x),max(crop[1],y),min(crop[2],x+w),min(crop[3],y+h))
                issues.extend(compare_lines(segments,wire,view_crop))
            except (ValueError,KeyError,TypeError,IndexError,StopIteration) as e:
                issues.append('Cannot read physical linework: '+str(e))
        return frames,parts,issues
