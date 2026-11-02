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
    faces=[];segments=[]
    for face in part['faces']:
        out=[];hits=[]
        for a,b in zip(face,face[1:]+face[:1]):
            da,db=dot(a,normal)-offset,dot(b,normal)-offset
            if da>=-1e-8:out.append(a)
            if da*db < -1e-14:
                p=add(a,mul(sub(b,a),da/(da-db)));out.append(p);hits.append(p)
        if len(out)>=3:faces.append(out)
        if len(hits)==2:segments.append(hits)
    while segments:
        chain=segments.pop();changed=True
        while changed:
            changed=False
            for i,(a,b) in enumerate(segments):
                if math.dist(chain[-1],a)<1e-6:chain.append(b)
                elif math.dist(chain[-1],b)<1e-6:chain.append(a)
                else:continue
                segments.pop(i);changed=True;break
        if len(chain)>=3:faces.append(chain)
    part['faces']=faces;part['bounds']=bounds(faces);part.setdefault('cut_planes',[]).append(dict(normal=normal,offset=offset))


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

    def member(self,label,pid,a,b,y=(0,1,0),basis='S',description=None,**extra):
        if pid.startswith('ASSEMBLY-'):basis='A'
        v=unit(sub(b,a));y=unit(sub(y,mul(v,dot(v,y))))
        m=dict(id=label,axis=[list(a),list(b)],end_offsets=[[0,0,0],[0,0,0]],profile_id=pid,local_y=y,**extra)
        return self.part(label,description or pid,member_faces(m,self.profiles),basis,'member',member=m,profile_id=pid)

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
                    bounds=bounds([f for p in self.parts for f in p['faces']]),section_axis=self.section_axis,section_at=self.section_at,front_axes=list(self.front_axes))


def section_polygons(part,axis,value):
    """Intersect each solid's faces with a cut plane; return ordered cut contours.

    Independent profile strips remain independent, preserving channel openings and
    hollow sections rather than drawing an enclosing rectangle.
    """
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
    # Stitch matching segment ends; separate strips/cylinders yield separate loops.
    loops=[]
    while segments:
        chain=segments.pop();changed=True
        while changed:
            changed=False
            for i,(a,b) in enumerate(segments):
                if math.dist(chain[-1],a)<1e-5:chain.append(b)
                elif math.dist(chain[-1],b)<1e-5:chain.append(a)
                else:continue
                segments.pop(i);changed=True;break
        if len(chain)>=3:loops.append([[p[i] for i in axes] for p in chain])
    return loops
