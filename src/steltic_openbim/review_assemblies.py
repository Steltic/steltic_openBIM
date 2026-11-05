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
            selected=next((s for s in c.get('source_record_selections',[]) if s['record_id']==rid and s['field']==key),None)
            if selected:
                from .bim_record_clauses import clauses
                if clauses(row.get(key)).get(selected['clause'])!=selected['text']:raise ValueError('Source clause changed')
                chunks.append(selected['text'])
            elif row.get(key):chunks.append(str(row[key]))
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
        receiver=self.receiver(kinds)
        if receiver:return receiver['profile_id']
        if default:return default
        # Receiving geometry absent from source is an explicit A part, never S.
        return self.default_w() if self.model['pilot'].startswith('hr') else channel(self.p,'ASSEMBLY-C600',6,1.625,.0566,.5)
    def receiver(self,kinds):
        direct=next((m for m in self.ms if m['kind'] in kinds),None)
        if direct:return direct
        point=self.c['point'];best=None;dd=1e30
        for m in self.model['members']:
            if m['kind'] not in kinds:continue
            a,b=m['axis'];v=sub(b,a);t=max(0,min(1,dot(sub(point,a),v)/dot(v,v)));distance=math.dist(point,add(a,mul(v,t)))
            if distance<dd:best=m;dd=distance
        return best if best and dd<60 else None
    def default_w(self):
        label='ASSEMBLY-W12';self.p[label]=dict(id=label,family='i',dimensions=dict(d=12,bf=6.5,tw=.3,tf=.5));return label
    def n(self,pattern,default):return findnum(pattern,self.text,default)
    def finish(self):
        a=self.a
        for part in a.parts:
            parameter=part.get('source_panel_parameter')
            if not parameter:continue
            host=self.params.get(parameter)
            if not host or not any(panel['id']==host for panel in self.model.get('panels',[])):
                raise ValueError('Assembly panel context has no actual declared host: '+str(host))
            part['bound_panel_id']=host
        a.notes=list(dict.fromkeys(a.notes))
        if self.params.get('released_connection_proposal'):
            for item in a.parts:
                if item['kind']!='member':item['basis']='A'
            for item in a.fasteners+a.welds+a.interfaces:item['basis']='A'
            a.notes.insert(0,'S: major-axis moment release at this end. A: simple-end plate, bolt and weld proposal; no source capacity verification for this attachment. The source RBS belongs to the fixed end and is not repeated here.')
        if not a.dimensions:
            bb=a.parts[0]['bounds'];a.dim([bb[0][0],0,bb[2][0]],[bb[0][1],0,bb[2][0]],basis='A',offset=-30)
        a.notes.insert(0,'A: local fit dimensions, plate outlines and procurement lengths not explicitly stated in the source are fictional test inputs. S values retain their source record; capacity checks have not been rerun.')
        result=a.result();result.update(family=self.family,subtype=self.params.get('joint',''),source_record_ids=self.c.get('design_record_ids',[]),source_text=self.text,
          representative_occurrence=self.c['id'],building_point=self.c['point'],source_member_ids=self.c['member_ids'],level=self.ms[0].get('level',1),
          coordinate_note='Inches. Local member worklines and source profiles; S source / A authored fit. World occurrence location retained in index.',source_context=dict(record_ids=self.c.get('source_context_records',[])))
        return result

def build_scene(model,package,c,subtype=''):
    ctx=Context(model,package,c);family=ctx.family
    if family=='review_canopy_purlin':
        from .review_cfs26_purlins import draw
        draw(ctx);return ctx.finish()
    if family=='review_canopy_primary':
        from .review_cfs26_primary import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_sag':
        from .review_sbmf_sag_angles import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_stud_head':
        from .review_sbmf_stud_heads import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_wsp':
        from .review_sbmf_diaphragms import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_floor':
        from .review_sbmf_floor import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_deck':
        from .review_sbmf_deck import draw
        draw(ctx);return ctx.finish()
    if family=='review_mezz_bearing':
        from .review_sbmf_bearing import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_collector':
        from .review_sbmf_collectors import draw
        draw(ctx);return ctx.finish()
    if family in ('review_sbmf_chord_stitch','review_sbmf_chord_track','review_sbmf_track_anchor','review_sbmf_top_collector','review_sbmf_wall_bridging'):
        from .review_sbmf_wall_chords import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_rod_foundation' or (family=='review_sbmf_hold_down' and ctx.params.get('actual_sbmf_hold_down')):
        from .review_sbmf_hold_downs import draw
        draw(ctx);return ctx.finish()
    if family in ('review_sbmf_tier','review_sbmf_tier_seam'):
        from .review_sbmf_tiers import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_post_head':
        from .review_sbmf_post_heads import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_girt':
        from .review_sbmf_girts import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_restraint_cap' or (family=='review_sbmf_strut' and ctx.params.get('actual_sbmf_restraint')):
        from .review_sbmf_restraints import draw
        draw(ctx);return ctx.finish()
    if family in ('review_sbmf_roof_seat','review_sbmf_column_cap'):
        from .review_sbmf_roof_seats import draw
        draw(ctx);return ctx.finish()
    if family=='review_sbmf_cap' or (family=='review_sbmf_header' and ctx.params.get('actual_sbmf_header')):
        from .review_sbmf_headers import draw
        draw(ctx);return ctx.finish()
    if family=='review_roof_bottom_strap':
        from .review_cfs5_roof_restraint import draw
        draw(ctx);return ctx.finish()
    if family in ('review_wsp_block','review_wsp_screws'):
        from .review_cfs5_diaphragms import draw
        draw(ctx);return ctx.finish()
    if family=='review_retrofit_cladding':
        from .review_cfs25_cladding import draw
        draw(ctx);return ctx.finish()
    if family=='review_retrofit_existing':
        from .review_cfs25_existing import draw
        draw(ctx);return ctx.finish()
    if family in ('review_retrofit_z_support','review_retrofit_z_lap'):
        from .review_cfs25_secondary import draw
        draw(ctx);return ctx.finish()
    if family=='review_cfs5_drag_screws':
        from .review_cfs5_collectors import draw
        draw(ctx);return ctx.finish()
    if family=='review_cfs5_drag_end':
        from .review_cfs5_drag_ends import draw
        draw(ctx);return ctx.finish()
    if family=='review_parapet_roof':
        from .review_cfs5_parapets import draw
        draw(ctx);return ctx.finish()
    if family=='review_roof_distribution':
        from .review_cfs6_roof_distribution import draw
        draw(ctx);return ctx.finish()
    if family=='review_wallface_blocking':
        from .review_cfs6_wallface_blocking import draw
        draw(ctx);return ctx.finish()
    if family=='review_diaphragm_screws':
        from .review_cfs6_diaphragms import draw
        draw(ctx);return ctx.finish()
    if family in ('review_deck_screws','review_deck_block_link'):
        from .review_concrete_deck import draw
        draw(ctx);return ctx.finish()
    if family in ('review_chord_floor_pack','review_chord_floor_clip'):
        from .review_cfs6_chord_floors import draw
        draw(ctx);return ctx.finish()
    if family in ('review_source_floor_rim','review_source_floor_block'):
        from .review_cfs6_floor_framing import draw
        draw(ctx);return ctx.finish()
    if family=='review_double_top_track':
        from .review_double_top_tracks import draw
        draw(ctx);return ctx.finish()
    if family=='review_transition_splice':
        from .review_source_conflicts import draw_transition
        draw_transition(ctx);return ctx.finish()
    if family in ('review_collector_bond','review_collector_lap'):
        from .review_concrete_collectors import draw
        draw(ctx);return ctx.finish()
    if family=='review_edge_chord_corner':
        from .review_edge_chords import draw
        draw(ctx);return ctx.finish()
    if family=='review_track_corner':
        from .review_track_corners import draw
        draw(ctx);return ctx.finish()
    if family=='review_track_splice':
        from .review_track_splices import draw
        draw(ctx);return ctx.finish()
    if family=='review_rod_coupler':
        from .review_cfs_rods import draw
        draw(ctx);return ctx.finish()
    if family=='review_column_local_stiffeners':
        from .review_column_local_checks import draw
        draw(ctx);return ctx.finish()
    if family=='review_selected_studs':
        from .review_selected_details import draw
        draw(ctx);return ctx.finish()
    if family=='review_hr_strut_bracing':
        from .review_hr_strut_bracing import draw
        draw(ctx);return ctx.finish()
    from .review_final_details import FAMILIES as FINAL,draw as final
    if family in FINAL:final(ctx);return ctx.finish()
    from .review_final_cfs_details import FAMILIES as FINAL_CFS,draw as final_cfs
    if family in FINAL_CFS:final_cfs(ctx);return ctx.finish()
    from .review_next_hr_details import FAMILIES,draw as next_hr
    if family in FAMILIES:next_hr(ctx);return ctx.finish()
    from .review_next_cfs_details import FAMILIES as NEXT_CFS,draw as next_cfs
    if family in NEXT_CFS:next_cfs(ctx);return ctx.finish()
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
