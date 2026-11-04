"""Explicit fixture rod continuations and actual floor coupling locations."""
import copy,math
from collections import defaultdict


def apply(b):
    if not b.key.startswith('cfs'):return
    rods=[m for m in b.members if m['kind']=='hold_down_rod']
    if not rods:return
    b.endpoint_links=getattr(b,'endpoint_links',[]);groups=defaultdict(list)
    def link(m,end,c,reason):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis=reason))
    for rod in rods:groups[tuple(round(v,6) for v in rod['axis'][0][:2])].append(rod)
    for rod in rods:
        hd=next((c for c in b.connections if c['detail_ref']['id']=='review_cfs_hold_down' and rod['id'] in c['member_ids']),None)
        foundation=next((c for c in b.connections if c['detail_ref']['id']=='review_rod_foundation' and rod['id'] in c['member_ids']),None)
        if hd:
            hd.setdefault('parameters',{})['separate_coupler']=True
            chord=next(m for m in b.members if m['id']==hd['member_ids'][0])
            link(chord,'end',hd,'Actual chord head is served by its own located hold-down bracket')
            # Bottom chord clips are a separate physical fastening operation;
            # neither the tie rod nor a top bracket stands for these screws.
            if not any(c['detail_ref']['id']=='cfs_stud' and chord['id'] in c['member_ids'] and math.dist(c['point'],chord['axis'][0])<.01 for c in b.connections):
                b.connection(chord['id']+':foot-clips','cfs_stud',chord['axis'][0],[chord],parameters=dict(each_ply_end_screws=True),basis='A: one positional No.10 at each exposed ply flange; verify local grip and attachment capacity')
        if foundation:
            old=copy.deepcopy(rod['axis']);rod['axis'][0][2]=foundation['point'][2]-foundation['parameters']['embedment']
            b.changes.append(dict(kind='rod_to_actual_foundation_plate',member_id=rod['id'],previous_axis=old,axis=copy.deepcopy(rod['axis']),basis='A: adopted anchorage depth extends the actual rod to its drawn end plate; foundation design remains delegated'))
            foundation['source_context_records']=foundation['design_record_ids'];foundation['design_record_ids']=[]
            foundation['basis']='A: illustrative foundation anchorage; source tie-rod design remains on the rod and hold-down bracket, sill anchorage belongs to the bottom track'
            link(rod,'start',foundation,'Actual rod end terminates at its own drawn foundation end plate and nut')
    coupled=set()
    for group in groups.values():
        group.sort(key=lambda m:m['level'])
        for lower,upper in zip(group,group[1:]):
            if upper['level']!=lower['level']+1:continue
            gap=upper['axis'][0][2]-lower['axis'][1][2]
            if not -2<=gap<=30:continue
            z=(upper['axis'][0][2]+lower['axis'][1][2])/2;old=[copy.deepcopy(m['axis']) for m in (lower,upper)]
            lower['axis'][1][2]=z-.0625;upper['axis'][0][2]=z+.0625
            point=[*lower['axis'][1][:2],z]
            c=b.connection(lower['id']+':coupler','review_rod_coupler',point,[lower,upper],parameters=dict(gap_in=.125),basis='A: actual story rod ends with supplier coupling envelope; no new coupling capacity approval')
            c['source_context_records']=sorted(set(lower['design_record_ids']+upper['design_record_ids']))
            link(lower,'end',c,'Actual lower rod end engages this located floor coupler');link(upper,'start',c,'Actual upper rod end engages this located floor coupler')
            coupled.add(lower['id'])
            b.changes.append(dict(kind='located_story_rod_coupler',member_ids=[lower['id'],upper['id']],previous_axes=old,axes=[copy.deepcopy(m['axis']) for m in (lower,upper)],point=point,basis=c['basis']))
        last=group[-1]
        hd=next((c for c in b.connections if c['detail_ref']['id']=='review_cfs_hold_down' and last['id'] in c['member_ids']),None)
        if hd:link(last,'end',hd,'The top rod projection is retained above its own take-up nut and bearing plate')
    b.note('ROD-JOINTS','A: actual tie-rod extents now reach their own foundation plates and explicitly located floor couplers. Source story diameters and design forces are unchanged. Coupler/thread geometry and rod extension lengths are accepted fit proposals; supplier/foundation capacity and installation remain delegated.')


def draw(ctx):
    from .review_receiver_geometry import extract
    a,p=ctx.a,ctx.p;axes=([1,0,0],[0,1,0],[0,0,1]);parts=[]
    for index,m in enumerate(ctx.ms[:2]):parts.append(extract(ctx,m,'ROD'+str(index),axes,12))
    diameters=[p[m['profile_id']]['dimensions']['d'] for m in ctx.ms[:2]];dia=max(diameters);length=4*dia
    pid='A-COUPLER-'+str(dia);p[pid]=dict(id=pid,family='chs',dimensions=dict(d=2*dia,t=.2),basis='A: hollow proprietary coupling envelope; actual internal threads delegated')
    a.member('COUPLER',pid,[0,0,-length/2],[0,0,length/2],basis='A',representation_role='assembly_component',description='A proprietary threaded rod coupler; supplier selects actual threads/body')
    for index,sign in enumerate((-1,1)):
        a.weld('THREAD'+str(index),[0,0,sign*.0625],[0,0,sign*length/2],['ROD'+str(index),'COUPLER'],kind='THREADED',basis='A',description='Thread engagement interface, not a weld')
    a.section_axis=2;a.section_at=-length/4;a.dim([dia,0,-length/2],[dia,0,length/2],basis='A')
    a.notes.append('Two actual story rods retain their source diameters. Their ends lie within this explicitly located coupling envelope. Body, thread forms, engagement and transition capacity remain delegated; envelope is A.')
