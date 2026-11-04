"""Locate the selected RBS at its actual beam end and receiving column face."""
import math,re
from .assembly_templates import NUMBER,number
from .review_assemblies import source_text
from .pilots.model import add,sub,mul,unit,dot,cross


def selection(text):
    hit=re.search(r'RBS\s*\(?a\s*=\s*'+NUMBER+r'(?: in)?,\s*b\s*=\s*'+NUMBER+r'(?: in)?,\s*c\s*=\s*'+NUMBER,text,re.I)
    return dict(zip(('a_in','b_in','c_in'),map(number,hit.groups()))) if hit else None


def apply(builder):
    if not builder.key.startswith('hr'):return
    members={m['id']:m for m in builder.members};pending={};selections={}
    for member in builder.members:member.pop('rbs',None)
    for connection in builder.connections:
        if connection['detail_ref']['id']!='review_beam':continue
        token=tuple(connection.get('design_record_ids',[]))
        if token not in selections:selections[token]=selection(source_text(builder.package,connection))
        selected=selections[token]
        if not selected:continue
        beam=members[connection['member_ids'][0]]
        column=next((members[mid] for mid in connection['member_ids'][1:] if members[mid]['kind'] in ('column','rocking_post','transfer_vertical')),None)
        if column is None:raise ValueError('Selected RBS has no actual receiving column: '+connection['id'])
        ends=[add(q,o) for q,o in zip(beam['axis'],beam['end_offsets'])]
        end=min((0,1),key=lambda i:math.dist(beam['axis'][i],connection['point']))
        direction=unit(sub(ends[1-end],ends[end]));cu=unit(sub(*reversed(column['axis'])))
        cz=cross(cu,column['local_y']);profile=builder.profiles[column['profile_id']]
        dy,dz=abs(dot(direction,column['local_y'])),abs(dot(direction,cz));dims=profile['dimensions']
        if profile['family']=='i' and dz>.99999:half=dims['d']/2
        elif profile['family']=='i' and dy>.99999 and connection.get('parameters',{}).get('boxing_t'):
            half=dims['bf']/2+connection['parameters']['boxing_t']
        elif profile['family']=='rhs' and max(dy,dz)>.99999:half=(dims['b'] if dy>dz else dims['h'])/2
        else:raise ValueError('RBS face requires an explicit non-flange receiver definition: '+connection['id'])
        centre=add(column['axis'][0],column['end_offsets'][0])
        centre=add(centre,mul(cu,dot(sub(ends[end],centre),cu)))
        distance=dot(sub(centre,ends[end]),direction)+half
        cut=dict(selected,end=end,source_a_in=selected['a_in'],column_face_offset_in=distance,
                 a_in=selected['a_in']+distance,connection_id=connection['id'],
                 design_record_ids=connection.get('design_record_ids',[]),basis='S: source RBS dimensions measured from the actual column flange face')
        key=(beam['id'],end)
        if key in pending and any(abs(pending[key][k]-cut[k])>1e-6 for k in ('a_in','b_in','c_in')):
            raise ValueError('Conflicting RBS selections at one physical beam end: '+beam['id'])
        pending[key]=cut
    for (mid,end),cut in pending.items():
        beam=members[mid]
        old=beam.get('rbs',{}).get('cuts',[])
        beam['rbs']=dict(cuts=[c for c in old if c['end']!=end]+[cut])
        builder.changes.append(dict(kind='source_rbs_physical_cut',member_id=mid,**cut))
