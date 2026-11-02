"""Source-bound assembled details for the twenty varied fictional review cases."""
import copy,math,re
from .assembly_scene import Assembly,clip_part
from .assembly_templates import NUMBER,number,findnum,grid,effective,web_faces,channel,flat,tube,rod,screw_diameter
from .pilots.model import add,sub,mul,unit,dot,cross

def source_text(package,c):
    lookup={r['id']:r['data'] for r in package['design_records']};chunks=[]
    for rid in c.get('design_record_ids',[]):
        # Governing-line summaries retain applicability in the source register;
        # their example bolt group must not override a member-specific detail.
        if rid.endswith('/collector-irregularity-lines'):continue
        row=lookup.get(rid,{})
        for key in ('components','selection','detail','design_note','type','note'):
            if row.get(key):chunks.append(str(row[key]))
        for r in row.get('rows',[]):
            chunks.append(str(r.get('item',r.get('zone','')))+': '+str(r.get('selection',r.get('section',''))))
    return '\n'.join(chunks)

def hull(points):
    q=sorted(set((round(x,7),round(z,7)) for x,z in points))
    def turn(o,b,d):return (b[0]-o[0])*(d[1]-o[1])-(b[1]-o[1])*(d[0]-o[0])
    lo=[];hi=[]
    for v in q:
        while len(lo)>1 and turn(lo[-2],lo[-1],v)<=0:lo.pop()
        lo.append(v)
    for v in reversed(q):
        while len(hi)>1 and turn(hi[-2],hi[-1],v)<=0:hi.pop()
        hi.append(v)
    return lo[:-1]+hi[:-1]

class Context:
    def __init__(self,model,package,c):
        self.model=model;self.package=package;self.c=c;self.text=source_text(package,c);self.params=c.get('parameters',{})
        lookup={m['id']:m for m in model['members']};self.ms=[lookup[i] for i in c['member_ids']];self.pid=self.ms[0]['profile_id'];self.family=c['detail_ref']['id']
        self.a=Assembly(c.get('title',self.family.removeprefix('review_').replace('_',' ').upper()),{p['id']:p for p in model['profiles']});self.p=self.a.profiles
        profiles=' / '.join(dict.fromkeys(m['profile_id'] for m in self.ms))
        self.a.title+=' | '+profiles[:95]
    def select(self,kinds,default=None):
        direct=next((m for m in self.ms if m['kind'] in kinds),None)
        if direct:return direct['profile_id']
        point=self.c['point'];best=None;dd=1e30
        for m in self.model['members']:
            if m['kind'] not in kinds:continue
            a,b=m['axis'];v=sub(b,a);t=max(0,min(1,dot(sub(point,a),v)/dot(v,v)));distance=math.dist(point,add(a,mul(v,t)))
            if distance<dd:best=m;dd=distance
        if best and dd<60:return best['profile_id']
        if default:return default
        # Receiving geometry absent from source is an explicit A part, never S.
        return self.default_w() if self.model['pilot'].startswith('hr') else channel(self.p,'ASSEMBLY-C600',6,1.625,.0566,.5)
    def default_w(self):
        label='ASSEMBLY-W12';self.p[label]=dict(id=label,family='i',dimensions=dict(d=12,bf=6.5,tw=.3,tf=.5));return label
    def n(self,pattern,default):return findnum(pattern,self.text,default)
    def finish(self):
        a=self.a
        if not a.dimensions:
            bb=a.parts[0]['bounds'];a.dim([bb[0][0],0,bb[2][0]],[bb[0][1],0,bb[2][0]],basis='A',offset=-30)
        a.notes.insert(0,'A: local fit dimensions, plate outlines and procurement lengths not explicitly stated in the source are fictional test inputs. S values retain their source record; capacity checks have not been rerun.')
        result=a.result();result.update(family=self.family,subtype=self.params.get('joint',''),source_record_ids=self.c.get('design_record_ids',[]),source_text=self.text,
          representative_occurrence=self.c['id'],building_point=self.c['point'],source_member_ids=self.c['member_ids'],level=self.ms[0].get('level',1),
          coordinate_note='Inches. Local member worklines and source profiles; S source / A authored fit. World occurrence location retained in index.',source_context={})
        return result

def build_scene(model,package,c,subtype=''):
    ctx=Context(model,package,c);family=ctx.family
    if family in ('review_truss_node','review_truss_heel'):
        from .assembly_templates import build_scene as pilot_scene
        cc=copy.deepcopy(c);cc['detail_ref']['id']='test_roof_truss'
        # The node itself and the heel support are separate, fully assembled variants.
        result=pilot_scene(model,package,cc,'');result['family']=family
        result['title']='DELEGATED TRUSS '+('HEEL NODE' if 'heel' in family else 'PANEL NODE')+' / A'
        return result
    if family in HR_FAMILIES:
        from .review_hr_details import draw
    elif family in CFS_FAMILIES:
        from .review_cfs_details import draw
    else:raise ValueError('No explicit review connection recipe '+family)
    draw(ctx);return ctx.finish()

HR_FAMILIES={
 'review_base','review_beam','review_pin_beam','review_splice','review_column_continuity','review_brace','review_brb','review_ebf_link',
 'review_plate_wall','review_wall_base','review_core_wall','review_coupling','review_stmf_node','review_stmf_end',
 'review_retrofit_beam','review_retrofit_column','review_existing_joint','review_crane_bracket','review_crane_seat','review_crane_tie','review_rail_clip','review_sliding_post','review_joist_seat',
 'review_rocker','review_core_base','review_plate_base','review_chamfer','review_column_box','review_deck_studs','review_edge_bars'}
CFS_FAMILIES={
 'review_portal_base','review_portal_joint','review_canopy_knee','review_canopy_brace','review_secondary','review_thermal_clip','review_endpost_base','review_endpost_top',
 'review_cfs_sill','review_cfs_floor','review_cfs_hold_down','review_cfs_post','review_cfs_strap','review_sheathing','review_cfs_joist','review_cfs_beam_clip',
 'review_hanger_plate','review_hanger_pin','review_angle_clip','review_platform_seat','review_ledger','review_roof_seat','review_rod_foundation',
 'review_kicker','review_guard_connection','review_stair_clip','review_pack_stitch','review_floor_strap','review_post_collector','review_rod_transfer','review_roof_edge','review_post_edge'}
