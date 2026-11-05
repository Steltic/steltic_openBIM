"""Physical connection assemblies shared by drawings, audits and future exporters.

Coordinates are inches in an explicitly named local joint frame. Meshes are derived
from the same member profiles, plates and fastener axes used by the dimensions.
No library rectangle is allowed to stand in for a connected member.
"""
from __future__ import annotations
import copy
import math
from .pilots.model import add, sub, mul, dot, cross, unit
from .pilots.geometry import member_faces, extrude, part_faces


def bounds(faces):
    pts=[p for f in faces for p in f]
    return [[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]


def clip_part(part,normal,offset):
    """Keep dot(point,normal)>=offset; used for physically separated mitre ends."""
    faces=[]
    for face in part['faces']:
        out=[]
        for a,b in zip(face,face[1:]+face[:1]):
            da,db=dot(a,normal)-offset,dot(b,normal)-offset
            if da>=-1e-8:out.append(a)
            if da*db < -1e-14:
                p=add(a,mul(sub(b,a),da/(da-db)));out.append(p)
        if len(out)>=3:faces.append(out)
    # A stitched cap commonly closes by repeating its first point. Mesh faces
    # close implicitly, so retaining that point creates a zero-length edge.
    clean=[]
    for face in faces:
        ring=[]
        for q in face:
            if not ring or math.dist(ring[-1],q)>1e-7:ring.append(q)
        if len(ring)>1 and math.dist(ring[0],ring[-1])<1e-7:ring.pop()
        if len(ring)>=3 and any(sum(v*v for v in cross(sub(ring[i],ring[0]),sub(ring[i+1],ring[0])))>1e-16 for i in range(1,len(ring)-1)):clean.append(ring)
    # Build the cap from the resulting boundary, including original edges that
    # lie on the cutting plane. Counting only two strict crossing points misses
    # the cap when a skew cut passes through an existing vertical plate edge.
    from collections import defaultdict
    edges=defaultdict(list)
    key=lambda q:tuple(round(v,7) for v in q)
    for face in clean:
        for a,b in zip(face,face[1:]+face[:1]):
            if abs(dot(a,normal)-offset)<1e-6 and abs(dot(b,normal)-offset)<1e-6:
                edges[tuple(sorted((key(a),key(b))))].append((a,b))
    segments=[rows[0] for rows in edges.values() if len(rows)==1]
    while segments:
        a,b=segments.pop();chain=[b,a]
        while math.dist(chain[-1],chain[0])>1e-6:
            found=False
            for i,(a,b) in enumerate(segments):
                if math.dist(chain[-1],b)<1e-6:chain.append(a)
                elif math.dist(chain[-1],a)<1e-6:chain.append(b)
                else:continue
                segments.pop(i);found=True;break
            if not found:break
        if len(chain)>=4 and math.dist(chain[-1],chain[0])<1e-6:clean.append(chain[:-1])
    part['faces']=clean;part['bounds']=bounds(clean);part.setdefault('cut_planes',[]).append(dict(normal=normal,offset=offset))


def reflect_z(assembly):
    """Reflect geometry AND receiver/fastener metadata for a mirrored detail."""
    def point(p):return [p[0],p[1],-p[2]]
    for part in assembly.parts:
        # A reflection reverses handedness; reverse face winding as well.
        part['faces']=[[point(p) for p in reversed(face)] for face in part['faces']]
        part['bounds']=bounds(part['faces'])
        if 'geometry' in part:
            part['geometry']=dict(type='mesh',faces=copy.deepcopy(part['faces']))
        if 'member' in part:
            member=part['member'];member['axis']=[point(p) for p in member['axis']]
            member['local_y']=point(member['local_y'])
            member['end_offsets']=[point(p) for p in member.get('end_offsets',[[0,0,0],[0,0,0]])]
        if 'points' in part:part['points']=[point(p) for p in part['points']]
        if 'axis' in part:part['axis']=point(part['axis'])
        if 'polygon' in part:part['polygon']=[point(p) for p in part['polygon']]
        if 'normal' in part:part['normal']=point(part['normal'])
        for cut in part.get('cut_planes',[]):cut['normal']=point(cut['normal'])
    for fastener in assembly.fasteners:
        fastener['points']=[point(p) for p in fastener['points']];fastener['axis']=point(fastener['axis'])
    for item in assembly.welds+assembly.dimensions:
        item['a']=point(item['a']);item['b']=point(item['b'])
    if assembly.section_axis==2:assembly.section_at=-assembly.section_at


def upright_receiver(assembly):
    """Rotate a vertical receiver from local X into drawing Z, including metadata."""
    rotate=lambda p:[-p[2],p[1],p[0]]
    for part in assembly.parts:
        part['faces']=[[rotate(p) for p in face] for face in part['faces']]
        part['bounds']=bounds(part['faces'])
        if 'geometry' in part:part['geometry']=dict(type='mesh',faces=copy.deepcopy(part['faces']))
        if 'member' in part:
            m=part['member'];m['axis']=[rotate(p) for p in m['axis']]
            m['local_y']=rotate(m['local_y']);m['end_offsets']=[rotate(p) for p in m['end_offsets']]
        for field in ('points','polygon'):
            if field in part:part[field]=[rotate(p) for p in part[field]]
        for field in ('axis','normal'):
            if field in part:part[field]=rotate(part[field])
        if 'pattern' in part:part['pattern']['axes']=[rotate(v) for v in part['pattern']['axes']]
        for cut in part.get('cut_planes',[]):cut['normal']=rotate(cut['normal'])
    for f in assembly.fasteners:f['points']=[rotate(p) for p in f['points']];f['axis']=rotate(f['axis'])
    for item in assembly.welds+assembly.dimensions:item['a']=rotate(item['a']);item['b']=rotate(item['b'])
    if assembly.section_axis==0:assembly.section_axis=2
    elif assembly.section_axis==2:assembly.section_axis=0;assembly.section_at=-assembly.section_at


class Assembly:
    def __init__(self, title, profiles):
        self.title=title;self.profiles=copy.deepcopy(profiles)
        self.parts=[];self.fasteners=[];self.welds=[];self.interfaces=[];self.dimensions=[];self.notes=[]
        self.section_axis=0;self.section_at=0.;self.front_axes=(0,2)

    def part(self, label, description, faces, basis='S', kind='plate', **data):
        if not faces:raise ValueError('Empty assembly part '+label)
        if any(p['id']==label for p in self.parts):raise ValueError('Duplicate assembly part '+label)
        item=dict(id=label,description=description,basis=basis,kind=kind,faces=faces,**data)
        item['bounds']=bounds(faces);self.parts.append(item);return item

    def member(self,label,pid,a,b,y=(0,1,0),basis='S',description=None,representation_role=None,**extra):
        if pid.startswith('ASSEMBLY-'):basis='A'
        v=unit(sub(b,a));y=unit(sub(y,mul(v,dot(v,y))))
        m=dict(id=label,axis=[list(a),list(b)],end_offsets=[[0,0,0],[0,0,0]],profile_id=pid,local_y=y,**extra)
        part=self.part(label,description or pid,member_faces(m,self.profiles),basis,'member',member=m,profile_id=pid)
        if representation_role:
            part['representation_role']=representation_role
        needed={pid};pending=[pid]
        while pending:
            for component in self.profiles[pending.pop()].get('components',[]):
                child=component['profile_id']
                if child not in needed:needed.add(child);pending.append(child)
        part['section_definitions']=[copy.deepcopy(self.profiles[key]) for key in sorted(needed)]
        return part

    def translate(self,delta):
        """Translate the whole local detail, including all attachment metadata."""
        from .bim_assemblies import transform_geometry
        frame=dict(origin=delta,x_axis=[1,0,0],y_axis=[0,1,0])
        for part in self.parts:
            part['faces']=[[add(p,delta) for p in face] for face in part['faces']]
            part['bounds']=bounds(part['faces'])
            if 'geometry' in part:part['geometry']=transform_geometry(part['geometry'],frame)
            if 'member' in part:part['member']['axis']=[add(p,delta) for p in part['member']['axis']]
            if 'points' in part:part['points']=[add(p,delta) for p in part['points']]
            if 'polygon' in part:part['polygon']=[add(p,delta) for p in part['polygon']]
            for cut in part.get('cut_planes',[]):cut['offset']+=dot(delta,cut['normal'])
        for fastener in self.fasteners:fastener['points']=[add(p,delta) for p in fastener['points']]
        for item in self.welds+self.dimensions:item['a']=add(item['a'],delta);item['b']=add(item['b'],delta)
        self.section_at+=delta[self.section_axis]

    def box(self,label,origin,size,basis='A',description=None,x=(1,0,0),y=(0,1,0),kind='plate'):
        g=dict(type='box',origin=list(origin),size=list(size),x_axis=list(x),y_axis=list(y))
        return self.part(label,description or 'PL '+' x '.join(f'{v:g}' for v in size),part_faces({'geometry':g},self.profiles),basis,kind,geometry=g)

    def polygon(self,label,vertices,thickness,normal=(0,1,0),basis='A',description=None):
        n=unit(normal);back=[add(p,mul(n,thickness)) for p in vertices]
        faces=[list(reversed(vertices)),back]+[[vertices[i],vertices[(i+1)%len(vertices)],back[(i+1)%len(vertices)],back[i]] for i in range(len(vertices))]
        return self.part(label,description or f'Gusset PL t={thickness:g}',faces,basis,polygon=vertices,thickness=thickness,normal=n)

    def cylinder(self,label,origin,axis,diameter,length,basis='A',description='',kind='rod'):
        g=dict(type='cylinder',origin=list(origin),axis=unit(axis),radius=diameter/2,length=length)
        return self.part(label,description or f'Rod dia {diameter:g}',part_faces({'geometry':g},self.profiles),basis,kind,geometry=g)

    def fastener(self,label,points,axis,diameter,grip,connects,description,basis='S',screw=False):
        """Points locate the near grip face; grip is the actual joined-ply envelope.

        Head/nut envelopes are illustrative; grip is not a procurement length.
        Every group declares exactly which assembly parts it joins.
        """
        if not points or not connects:raise ValueError('Unattached fastener group '+label)
        n=unit(axis);faces=[];centres=[]
        for p in points:
            g=dict(type='cylinder',origin=list(p),axis=n,radius=diameter/2,length=grip)
            faces+=part_faces({'geometry':g},self.profiles)
            # Hex head, and a nut on through bolts; screw tips are shown beyond grip.
            yy=unit(cross([0,0,1],n)) if abs(n[2])<.99 else [1,0,0]
            poly=[[diameter*.9*math.cos(i*math.pi/3),diameter*.9*math.sin(i*math.pi/3)] for i in range(6)]
            head=mul(n,diameter*.6)
            faces+=extrude(poly,sub(p,head),p,yy)
            if not screw:faces+=extrude(poly,add(p,mul(n,grip)),add(p,mul(n,grip+diameter*.65)),yy)
            centres.append(add(p,mul(n,grip/2)))
        item=self.part(label,description,faces,basis,'fastener',count=len(points),diameter=diameter,grip=grip,axis=n,points=[list(p) for p in points],connects=list(connects),screw=screw)
        if len(points)>1:
            pairs=[(math.dist(a,b),sub(b,a)) for i,a in enumerate(points) for b in points[i+1:] if math.dist(a,b)>1e-6]
            spacing,u=min(pairs,key=lambda row:row[0]);u=unit(u);v=unit(cross(n,u))
            coords=[[dot(sub(p,points[0]),direction) for p in points] for direction in (u,v)]
            values=[sorted({round(t,6) for t in row}) for row in coords]
            regular=[]
            for vals in values:
                steps=[b-a for a,b in zip(vals,vals[1:])]
                regular.append((len(vals),steps[0] if steps and max(steps)-min(steps)<1e-5 else None))
            if all(count==1 or pitch is not None for count,pitch in regular):
                item['pattern']=dict(axes=[u,v],counts=[r[0] for r in regular],spacing=[r[1] for r in regular])
        self.fasteners.append({k:copy.deepcopy(item[k]) for k in ('id','count','diameter','grip','axis','points','connects','basis','screw')})
        return item

    def weld(self,label,a,b,connects,size=.25,kind='fillet',basis='S',description=None):
        self.welds.append(dict(id=label,a=list(a),b=list(b),connects=list(connects),size=size,kind=kind,basis=basis,
                               description=description or f'{size:g} in {kind}; E70XX'))

    def dim(self,a,b,label=None,basis='S',view='front',offset=24):
        value=math.dist(a,b)
        self.dimensions.append(dict(a=list(a),b=list(b),value_in=value,label=label,basis=basis,view=view,offset=offset))

    def result(self):
        # At least one useful graphic set-out dimension accompanies the parts
        # schedule. Local fastener stations remain A unless explicitly dimensioned
        # by the source-specific recipe above.
        front=[d for d in self.dimensions if d['view']=='front' and any(abs(d['a'][i]-d['b'][i])>.01 for i in self.front_axes)]
        if not front:
            for f in self.fasteners:
                pairs=[(math.dist(a,b),a,b) for j,a in enumerate(f['points']) for b in f['points'][j+1:]
                       if sum(abs(a[i]-b[i])>.01 for i in self.front_axes)==1 and abs(a[next(i for i in range(3) if i not in self.front_axes)]-b[next(i for i in range(3) if i not in self.front_axes)])<.01]
                if pairs:
                    _,a,b=min(pairs,key=lambda row:row[0]);self.dim(a,b,f['id']+' local pitch',basis='A',offset=-38);break
            else:
                plates=[p for p in self.parts if p['kind']=='plate']
                part=max(plates or self.parts,key=lambda p:max(p['bounds'][i][1]-p['bounds'][i][0] for i in self.front_axes))
                axis=max(self.front_axes,key=lambda i:part['bounds'][i][1]-part['bounds'][i][0]);a=[(lo+hi)/2 for lo,hi in part['bounds']];b=list(a)
                a[axis],b[axis]=part['bounds'][axis];self.dim(a,b,part['id']+' local extent',basis='A',offset=-38)
        if not any(section_polygons(part,self.section_axis,self.section_at) for part in self.parts if part['kind']!='concrete'):
            # Some mirrored nodes extend only to the negative side of the origin.
            # Place the explicitly labelled cut through actual joined material.
            candidates={(lo+hi)/2 for part in self.parts if part['kind']!='concrete' for lo,hi in [part['bounds'][self.section_axis]]}
            self.section_at=max(candidates,key=lambda at:(sum(bool(section_polygons(part,self.section_axis,at)) for part in self.parts if part['kind']!='concrete'),-abs(at-self.section_at)))
        ids={p['id'] for p in self.parts}
        for f in self.fasteners:
            if len(f['connects'])<2 or not set(f['connects'])<=ids:raise ValueError('Invalid joined plies '+str(f))
        for w in self.welds:
            if len(w['connects'])<2 or not set(w['connects'])<=ids:raise ValueError('Invalid weld attachments '+str(w))
        if len([p for p in self.parts if p['kind']=='member'])<2 and not any(p['kind']=='concrete' for p in self.parts):
            raise ValueError('Assembly lacks its receiving member/support: '+self.title)
        for interface in self.interfaces:
            if len(interface['connects'])<2 or not set(interface['connects'])<=ids:raise ValueError('Invalid bearing/bond interface')
        if not self.fasteners and not self.welds and not self.interfaces:raise ValueError('Assembly has no attachment: '+self.title)
        return dict(title=self.title,parts=self.parts,fasteners=self.fasteners,welds=self.welds,interfaces=self.interfaces,dimensions=self.dimensions,notes=self.notes,
                    bounds=bounds([f for p in self.parts for f in p['faces']]),section_axis=self.section_axis,section_at=self.section_at,front_axes=list(self.front_axes),
                    **({'front_depth_sign':self.front_depth_sign} if hasattr(self,'front_depth_sign') else {}))


def section_polygons(part,axis,value):
    """Intersect each solid's faces with a cut plane; return ordered cut contours.

    Independent profile strips remain independent, preserving channel openings and
    hollow sections rather than drawing an enclosing rectangle.
    """
    # Slot cuts subdivide a strip into adjacent closed solids. Intersect each
    # solid independently: stitching their shared vertices together can fill a
    # web opening or turn a continuous flange into a self-intersecting outline.
    # Use the actual mesh faces (including rigid transforms), checking that
    # every proposed group is closed. Other edited/mitred meshes still follow
    # their explicit faces below.
    if part.get('member',{}).get('slots') and not part.get('cut_planes'):
        from .pilots.geometry import member_solids
        profiles={p['id']:p for p in part.get('section_definitions',[])}
        if profiles:
            counts=[len(solid) for solid in member_solids(part['member'],profiles)]
            if sum(counts)==len(part['faces']):
                from collections import Counter
                solids=[];start=0
                for count in counts:
                    solid=part['faces'][start:start+count];start+=count
                    key=lambda q:tuple(round(v,7) for v in q)
                    edges=Counter(tuple(sorted((key(a),key(b)))) for face in solid for a,b in zip(face,face[1:]+face[:1]))
                    if any(n!=2 for n in edges.values()):break
                    solids.append(solid)
                if len(solids)==len(counts):
                    return [loop for solid in solids for loop in section_polygons({'faces':solid},axis,value)]
    axes=[i for i in range(3) if i!=axis];segments=[]
    for face in part['faces']:
        hits=[]
        for a,b in zip(face,face[1:]+face[:1]):
            da,db=a[axis]-value,b[axis]-value
            if abs(da)<1e-7:hits.append(a)
            if da*db < -1e-12:hits.append(add(a,mul(sub(b,a),-da/(db-da))))
        unique={tuple(round(p[i],7) for i in range(3)):p for p in hits}
        points=list(unique.values())
        if len(points)==2 and math.dist(*points)>1e-6:segments.append(points)
        elif len(points)>2:
            # A cap across adjacent web/flange strips may contain an interior
            # vertex on the section line. Dropping that whole face loses the
            # diagonal closure. Keep its actual intervals, including the shared
            # vertex, rather than enclosing a concave face across empty space.
            direction=max(range(3),key=lambda i:max(q[i] for q in points)-min(q[i] for q in points))
            points.sort(key=lambda q:q[direction]);ray=sub(points[-1],points[0])
            if dot(ray,ray)<1e-12 or any(dot(cross(sub(q,points[0]),ray),cross(sub(q,points[0]),ray))>1e-10*dot(ray,ray) for q in points):continue
            normal=next((cross(sub(q,face[0]),sub(r,face[0])) for q,r in zip(face[1:],face[2:]) if dot(cross(sub(q,face[0]),sub(r,face[0])),cross(sub(q,face[0]),sub(r,face[0])))>1e-12),None)
            if normal is None:continue
            plane=[i for i in range(3) if i!=max(range(3),key=lambda i:abs(normal[i]))]
            def inside(q):
                x,y=[q[i] for i in plane];hit=False
                for v,w in zip(face,face[1:]+face[:1]):
                    ax,ay=[v[i] for i in plane];bx,by=[w[i] for i in plane]
                    if abs((x-ax)*(by-ay)-(y-ay)*(bx-ax))<1e-8 and min(ax,bx)-1e-8<=x<=max(ax,bx)+1e-8 and min(ay,by)-1e-8<=y<=max(ay,by)+1e-8:return True
                    if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:hit=not hit
                return hit
            for a,b in zip(points,points[1:]):
                if math.dist(a,b)>1e-6 and inside(mul(add(a,b),.5)):segments.append([a,b])
    # Stitch matching segment ends; separate strips/cylinders yield separate loops.
    loops=[]
    while segments:
        chain=segments.pop();changed=True
        while changed:
            # A slotted member is extruded in several adjacent intervals.
            # Once one contour closes, do not walk through its shared corner
            # into the next interval and create a self-intersecting outline.
            if len(chain)>2 and math.dist(chain[-1],chain[0])<1e-5:break
            changed=False
            for i,(a,b) in enumerate(segments):
                if math.dist(chain[-1],a)<1e-5:chain.append(b)
                elif math.dist(chain[-1],b)<1e-5:chain.append(a)
                else:continue
                segments.pop(i);changed=True;break
        if len(chain)>=3:loops.append([[p[i] for i in axes] for p in chain])
    return loops
