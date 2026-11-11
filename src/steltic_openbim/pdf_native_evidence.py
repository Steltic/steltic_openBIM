"""Source and IFC evidence for the ordinary HR physical-coordinate drawing layout."""
from collections import defaultdict
from functools import cached_property
import json

import ifcopenshell
import ifcopenshell.geom
from ifcopenshell.util.element import get_psets
import numpy as np
from .ifc_readback_session import read_step


class NativeEvidence:
    def __init__(self,directory,ifc_path=None):
        package=json.loads((directory/'source.json').read_bytes())
        state=json.loads((directory/'state.json').read_bytes())
        physical=package['physical']
        members=physical['members']
        vertical={'col','column','post','endwall_post','chord'}
        columns=[m for m in members if m['kind'] in vertical]
        grids={}
        for axis,key in enumerate('xy'):
            coords=sorted({round(p[axis],6) for m in columns or members for p in m['axis']})
            grids[key]=[(str(i+1) if axis==0 else chr(65+i) if i<26 else f'Y{i+1}',coord)
                        for i,coord in enumerate(coords)]
        levels=set(package.get('layout_evidence',{}).get('levels_in') or [])
        if not levels:
            levels={p['vertices'][0][2] for p in physical['panels'] if p.get('kind') in ('roof','floor')
                    and p.get('vertices') and len({round(v[2],6) for v in p['vertices']})==1}
            levels.add(min(p[2] for m in members for p in m['axis']))
        if len(levels)<2:
            levels.update(m['axis'][0][2] for m in members if abs(m['axis'][0][2]-m['axis'][1][2])<1e-5)
        openings=[]
        for opening in physical['openings']:
            lo,hi=np.min(opening['vertices'],axis=0),np.max(opening['vertices'],axis=0)
            normal=int(np.argmin(hi-lo))
            u,v=[i for i in range(3) if i!=normal]
            openings.append(dict(id='SRC-'+opening['id'],x_ft=lo[0]/12,y_ft=lo[1]/12,z_ft=lo[2]/12,
                width_ft=(hi[u]-lo[u])/12,height_ft=(hi[v]-lo[v])/12))
        openings.extend(f for f in state.get('features',[]) if f.get('confirmed'))
        self.drawing_model=dict(grids=grids,levels=[(i,None,round(z,6)) for i,z in enumerate(sorted(levels))],
                                openings=openings)
        self.physical=physical
        self.connections={c['id']:c for c in physical['connections']}
        self.templates={t['id']:t for t in physical.get('assemblies',[])}
        self.path=ifc_path or directory/'model.ifc'
        self.extents={}

    @cached_property
    def solids(self):
        # Keep the model alive for geometry conversion and retain exact occurrence associations.
        self.ifc=read_step(self.path)
        objects=defaultdict(list)
        for obj in self.ifc.by_type('IfcElement'):
            if obj.Representation is None:
                continue
            identity=get_psets(obj,psets_only=True).get('Steltic_Coordination',{})
            cid=identity.get('ConnectionId')
            if cid and identity.get('Geometry')=='design surfaces':
                objects[cid].append(obj)
        return objects

    def extent(self,connection):
        if connection in self.extents:
            return self.extents[connection]
        if not self.solids[connection]:
            raise ValueError('No actual IFC solid for PDF connection extent '+connection)
        settings=ifcopenshell.geom.settings()
        settings.set('use-world-coords',True)
        vertices=[]
        for product in self.solids[connection]:
            shape=ifcopenshell.geom.create_shape(settings,product)
            verts=np.asarray(shape.geometry.verts).reshape(-1,3)
            vertices.extend(verts[np.unique(shape.geometry.faces)]/.0254)
        self.extents[connection]=(np.min(vertices,axis=0),np.max(vertices,axis=0))
        return self.extents[connection]

    def bond_line(self,connection,index):
        frame=self.connections[connection]['assembly_instance']
        template=self.templates[frame['template_id']]
        bond=template['bond_interfaces'][index]
        receivers={r['id']:r for r in template['receivers']}
        axes=[np.asarray(receivers[r]['axis'],dtype=float) for r in bond['bar_receivers']]
        a,b=axes[0]
        if bond['kind']=='reinforcement_bond_lap':
            u=(b-a)/np.linalg.norm(b-a)
            stations=(axes[1]-a)@u
            lo=max(0,min(stations));hi=min(np.linalg.norm(b-a),max(stations))
            a,b=a+lo*u,a+hi*u
        x,y=np.asarray(frame['x_axis']),np.asarray(frame['y_axis'])
        basis=np.stack([x,y,np.cross(x,y)])
        return np.array([a,b])@basis + frame['origin']
