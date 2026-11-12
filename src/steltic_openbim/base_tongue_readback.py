"""Match integral plate extensions to the source brace's direction and actual sole contour."""
from collections import defaultdict
import re

import numpy as np
from shapely.geometry import Polygon,box
from shapely.ops import unary_union

from .assembly_templates import NUMBER,number
from .joint_mesh_readback import TOL,unit


def intended_tongues(physical,records):
    from .base_plate_extensions import frame_extension,base_edge_layout
    selected={}
    base_records=set()
    layouts=set()
    extensions={}
    for r in records:
        data=r.get('data',{})
        text=data.get('components','')
        if base_edge_layout(data) is not None:layouts.add(r['id'])
        if (spec:=frame_extension(data)) is not None:extensions[r['id']]=spec
        match=re.search(r'(?:plate\s+)?extended on the bay side by a\s+'+NUMBER+
                        r'\s+in wide tongue\s+'+NUMBER+r'\s+in long',text,re.I)
        if match:selected[r['id']]=tuple(number(v) for v in match.groups())
        if re.match(r'(?:base plate\s+|moment base:\s*)PL\b',text,re.I):base_records.add(r['id'])
    result=defaultdict(list);findings=[]
    if not selected and not (layouts and extensions):return result,findings
    members={m['id']:m for m in physical['members']}
    bases=defaultdict(list)
    for c in physical['connections']:
        if base_records.intersection(c.get('design_record_ids',[])):
            for mid in c.get('member_ids',[]):bases[mid].append(c)
    for c in physical['connections']:
        for record in (selected.keys() | layouts) & set(c.get('design_record_ids',[])):
            if record in layouts and c.get('parameters',{}).get('joint')!='base':continue
            try:
                inst=c['assembly_instance'];col=inst['bindings']['COLUMN'];brace=members[inst['bindings']['BRACE']]
                wp=np.array(c.get('point',inst['origin']),dtype=float)
                candidates=[b for b in bases[col] if np.linalg.norm(wp-b['assembly_instance']['origin'])<=TOL]
                if len(candidates)!=1:raise ValueError('No unique sole at the source brace workpoint')
                base=candidates[0];frame=base['assembly_instance'];ends=np.asarray(brace['axis'])
                end=int(np.argmin(np.linalg.norm(ends-wp,axis=1)))
                if np.linalg.norm(ends[end]-wp)>TOL:raise ValueError('Brace workpoint and bay-side base differ')
                v=ends[1-end]-ends[end];axes=np.array([frame['x_axis'],frame['y_axis']])
                projected=unit(axes@v);index=int(np.argmax(abs(projected)))
                if abs(projected[1-index])>TOL:raise ValueError('Bay direction is oblique to the rectangular stock')
                if record in layouts:
                    owner_record=next((rid for rid in base['design_record_ids'] if rid in extensions),None)
                    if owner_record is None:continue
                    world_axis,width,length=extensions[owner_record]
                    if abs(unit(v[:2])['XY'.index(world_axis)])<1-TOL:continue
                    record=owner_record
                else:width,length=selected[record]
                result[base['id']].append(dict(axis=index,sign=int(np.sign(projected[index])),width_in=width,
                    length_in=length,record=record,brace=c['id'],sheet=c.get('drawing_ref')))
            except (KeyError,ValueError) as error:
                findings.append(dict(code='selected_base_plate_tongue_unlocated',connection=c['id'],record=record,detail=str(error)))
    return result,findings


def measure_polygon(footprint,width,length,tongues):
    if footprint.geom_type!='Polygon' or not footprint.is_valid:
        raise ValueError('Integral base plate needs one continuous footprint')
    actual=Polygon(footprint.exterior)
    candidates=[]
    for sx,sy in {(width,length),(length,width)}:
        stock=box(-sx/2,-sy/2,sx/2,sy/2)
        additions=[]
        for row in tongues:
            i=row['axis'];sgn=row['sign'];w=row['width_in'];extent=row['length_in']
            face=sgn*(sx,sy)[i]/2
            lo,hi=sorted((face,face+sgn*extent))
            additions.append(box(lo,-w/2,hi,w/2) if i==0 else box(-w/2,lo,w/2,hi))
        wanted=unary_union([stock,*additions])
        candidates.append((actual.symmetric_difference(wanted).area,stock,additions))
    difference,stock,additions=min(candidates,key=lambda v:v[0])
    extra=actual.difference(stock)
    measured=[]
    for row,expected in zip(tongues,additions):
        i=row['axis'];sgn=row['sign']
        face=stock.bounds[(2 if sgn>0 else 0)+i]
        bx,by,tx,ty=actual.bounds
        if i==0:
            side=box(face,by-1,max(face,tx)+1,ty+1) if sgn>0 else box(min(face,bx)-1,by-1,face,ty+1)
        else:
            side=box(bx-1,face,tx+1,max(face,ty)+1) if sgn>0 else box(bx-1,min(face,by)-1,tx+1,face)
        part=extra.intersection(side)
        bounds=part.bounds
        span=[bounds[2]-bounds[0],bounds[3]-bounds[1]] if part.area>TOL**2 else [0.,0.]
        measured.append(dict(source=row,measured_projection_in=span[i],measured_width_in=span[1-i],
                             missing_or_excess_area_in2=float(part.symmetric_difference(expected).area)))
    return dict(nominal_stock_in=[stock.bounds[2]*2,stock.bounds[3]*2],tongues=measured,
                missing_or_excess_area_in2=float(difference)),difference<=TOL*max(1.,actual.length)


def measure_solid(mesh,width,length,tongues):
    low,high=np.min(mesh.vertices[:,2]),np.max(mesh.vertices[:,2])
    levels=sorted(set(np.round(mesh.vertices[:,2],6)))
    if not mesh.closed or high-low<=TOL:
        return {},['Actual sole is open or has zero thickness']
    data=[];issues=[]
    for a,b in zip(levels,levels[1:]):
        if b-a<=TOL:continue
        for fraction in (.15,.5,.85):
            z=a+(b-a)*fraction
            section=mesh.section([0.,0.,1.],z,([1.,0.,0.],[0.,1.,0.]))
            fact,valid=measure_polygon(section,width,length,tongues)
            if not valid:issues.append('Actual integral stock, signed tongue or width differs from HR')
            data.append(dict(fact,station_in=z))
    return dict(thickness_in=float(high-low),sections=data),list(dict.fromkeys(issues))
