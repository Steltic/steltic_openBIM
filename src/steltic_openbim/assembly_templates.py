"""Assembled joint recipes. Source choices and authored fit geometry stay distinct.

Each recipe draws connected members plus all load-path attachment groups. The
source-specific record and exact occurrence remain attached to the resulting scene.
"""
from __future__ import annotations
import copy
import math
import re
from .assembly_scene import Assembly
from .pilots.model import add,mul,sub,unit

NUMBER=r'(\d+(?:[ -]\d+/\d+|/\d+|\.\d+)?)'
MIL={33:.0346,43:.0451,54:.0566,68:.0713,97:.1017,118:.1242,137:.1438}

def number(s):
    s=str(s).strip().replace('-',' ')
    return sum(float(a.split('/')[0])/float(a.split('/')[1]) if '/' in a else float(a) for a in s.split())

def findnum(pattern,text,default):
    hit=re.search(pattern,text,re.I)
    return number(hit[1]) if hit else default

def group(text,default=(4,10)):
    found=re.search(r'(\d+)\s+No\.?\s*(\d+)',text,re.I)
    return tuple(map(int,found.groups())) if found else default

def screw_diameter(n):return {8:.164,10:.19,12:.216,14:.25}.get(n,.25)

def dim(profile,axis='depth'):
    d=profile['dimensions']
    if profile['family']=='built_up':return None
    if axis=='depth':return d.get('d',d.get('h',d.get('depth',d.get('width',6))))
    return d.get('bf',d.get('b',d.get('width',6)))

def effective(profiles,pid,key='depth'):
    p=profiles[pid]
    if p['family']=='built_up':
        from .pilots.geometry import strips
        axis=1 if key=='depth' else 0;values=[v[axis] for poly in strips(p,profiles) for v in poly]
        return max(values)-min(values)
    return dim(p,key)

def channel(profiles,pid,d=6,b=1.625,t=.0566,lip=.5):
    # Local recipes share a package. A friendly name such as TRACK600 is not
    # a section identity when different details specify different flange sizes.
    pid += f'-{d:g}x{b:g}x{t:g}x{lip:g}'
    profiles.setdefault(pid,dict(id=pid,family='channel',dimensions=dict(d=d,b=b,t=t,lip=lip)))
    return pid

def flat(profiles,w,t):
    pid=f'ASSEMBLY-PL{w:g}x{t:g}';profiles[pid]=dict(id=pid,family='flat',dimensions=dict(width=w,thickness=t));return pid

def rod(profiles,d):
    pid=f'ASSEMBLY-ROD{d:g}';profiles[pid]=dict(id=pid,family='round',dimensions={'d':d});return pid

def tube(profiles,d,b,t):
    pid=f'ASSEMBLY-HSS{d:g}x{b:g}x{t:g}';profiles[pid]=dict(id=pid,family='rhs',dimensions=dict(h=d,b=b,t=t));return pid

def grid(count,cols,pitch=1,gauge=1,origin=(0,0,0),along=(1,0,0),up=(0,0,1)):
    return [add(origin,add(mul(along,(i%cols)*gauge),mul(up,(i//cols)*pitch))) for i in range(count)]


def web_faces(profiles,pid):
    """Outward web faces of the actual channel plies, in profile coordinates."""
    profile=profiles[pid]
    if profile['family']=='built_up':
        result=[]
        for comp in profile['components']:
            base=profiles[comp['profile_id']];t=base['dimensions'].get('t',.1017)
            sign=-1 if comp['rotation_deg']%360==0 else 1
            result.append((comp['offset'][0]+sign*t/2,sign,t))
        return result
    return [(-profile['dimensions'].get('t',.1017)/2,-1,profile['dimensions'].get('t',.1017))]

def clip(a,label,origin,height,leg=2,t=.125,basis='A'):
    x,y,z=origin
    a.box(label+'a',[x,y,z],[leg,t,height],basis,description=f'{label} angle {leg:g} x {leg:g} x {t:g}, length {height:g}')
    a.box(label+'b',[x,y,z],[t,leg,height],basis,description=f'{label} return leg (same angle)')
    return [label+'a',label+'b']

def source_text(package,c):
    refs={r['id']:r['data'] for r in package['design_records']}
    chunks=[]
    for rid in c.get('design_record_ids',[]):
        d=refs.get(rid,{})
        for k in ('components','selection','design_note','type'):
            if d.get(k):chunks.append(str(d[k]));break
    return '\n'.join(chunks)

def build_scene(model,package,c,subtype=''):
    par=c.get('parameters',{});family=c['detail_ref']['id']
    if par.get('physical_hr_kicker'):
        from .review_assemblies import Context
        from .review_hr_kickers import draw
        ctx=Context(model,package,c);draw(ctx);return ctx.finish()
    located=None
    if par.get('physical_opening_joint'):located='header'
    elif par.get('physical_jamb_base'):located='jamb_base'
    elif par.get('physical_wall_attachment') and family=='cfs_stud_bridging':located='bridging'
    elif par.get('physical_wall_attachment') and family=='review_sheathing':located='sheathing'
    elif par.get('physical_floor_stack'):located='floor'
    if located:
        from .review_assemblies import Context
        from . import review_located_wall_details
        ctx=Context(model,package,c);getattr(review_located_wall_details,located)(ctx);return ctx.finish()
    if c['detail_ref']['id'].startswith('review_'):
        from .review_assemblies import build_scene as review_scene
        return review_scene(model,package,c,subtype)
    if c['detail_ref']['id']=='cfs_scheduled_endwall_post':
        from .review_assemblies import Context
        from .review_cfs_details import endpost
        context=Context(model,package,c);endpost(context,subtype=='post-base');return context.finish()
    profiles={p['id']:copy.deepcopy(p) for p in model['profiles']};lookup={m['id']:m for m in model['members']}
    ms=[lookup[i] for i in c['member_ids']];family=c['detail_ref']['id'];text=source_text(package,c)
    primary=ms[0];pid=primary['profile_id'];level=primary.get('level',1)
    a=Assembly(family.replace('_',' ').upper()+(' / '+subtype if subtype else ''),profiles)
    p=a.profiles
    context={}
    def pick(kinds,default=None):
        direct=next((m for m in ms if m['kind'] in kinds),None)
        if direct:return direct['profile_id']
        point=c['point'];best=None;distance=float('inf')
        for m in model['members']:
            if m['kind'] not in kinds:continue
            aa,bb=m['axis'];v=sub(bb,aa);ln=sum(x*x for x in v)
            at=max(0,min(1,sum(x*y for x,y in zip(sub(point,aa),v))/ln))
            dd=math.dist(point,add(aa,mul(v,at)))
            if dd<distance:best=m;distance=dd
        if best is not None and distance<=18:
            context[best['id']]=dict(profile_id=best['profile_id'],kind=best['kind'],distance_to_joint_in=distance)
            return best['profile_id']
        return default or pid
    def receiver(kinds,default):
        point=c['point'];best=None;distance=1e30;pv=unit(sub(primary['axis'][1],primary['axis'][0]))
        for m in model['members']:
            if m['id']==primary['id'] or m['kind'] not in kinds:continue
            aa,bb=m['axis'];v=sub(bb,aa);ln=sum(x*x for x in v);uv=unit(v)
            if abs(sum(x*y for x,y in zip(pv,uv)))>.98:continue
            at=max(0,min(1,sum(x*y for x,y in zip(sub(point,aa),v))/ln));dd=math.dist(point,add(aa,mul(v,at)))
            if dd<distance:best=m;distance=dd
        if best is not None and distance<=18:
            context[best['id']]=dict(profile_id=best['profile_id'],kind=best['kind'],distance_to_joint_in=distance)
            return best['profile_id']
        return default
    def default_c(d=6,b=1.625,t=.0566):return channel(p,f'ASSEMBLY-C{d:g}x{b:g}x{t:g}',d,b,t)
    def default_w():
        name=next((q for q in p if p[q]['family']=='i'),None)
        if name:return name
        name='ASSEMBLY-W12';p[name]=dict(id=name,family='i',dimensions=dict(d=12,bf=6.5,tf=.5,tw=.3));return name
    def note(t):a.notes.append(t)
    def fast(label,pts,axis,d,grip,connects,desc,basis='S',screw=False):a.fastener(label,pts,axis,d,grip,connects,desc,basis,screw)

    # HR beam-to-column/beam: member solids, support face, plate, bolt grip, welds.
    if family in ('hr_simple_shear_plate','hr_infill_shear_plate_cope','hr_rbs_joint','hr_shear','hr_moment','hr_link_end') or (family=='test_floor_opening' and model['pilot'].startswith('hr')):
        floor_opening=family=='test_floor_opening'
        bp=primary['profile_id'] if floor_opening else pick(('girder','infill','moment_beam','opening_header','opening_trimmer','beam','link'))
        if floor_opening:
            support=next((m for m in ms if m['id']!=primary['id']),None)
            if support is None:raise ValueError('Opening detail needs its actual perpendicular receiving member: '+c['id'])
            cp=support['profile_id']
        else:cp=pick(('column',),next((m['profile_id'] for m in ms if m['profile_id']!=bp),default_w()))
        bd=effective(p,bp);cd=effective(p,cp);bf=effective(p,bp,'width');beam=next((m for m in ms if m['profile_id']==bp),primary)
        support_is_column=any(m['kind']=='column' for m in ms) or family in ('hr_simple_shear_plate','hr_rbs_joint','hr_moment')
        beam_z=-bd/2;support_z=-cd/2
        if floor_opening:
            def physical_z(m):
                aa,bb=m['axis'];v=sub(bb,aa);s=max(0,min(1,sum(x*y for x,y in zip(sub(c['point'],aa),v))/sum(x*x for x in v)))
                offsets=m.get('end_offsets',[[0,0,0],[0,0,0]])
                return aa[2]+s*v[2]+offsets[0][2]+s*(offsets[1][2]-offsets[0][2])-c['point'][2]
            beam_z=physical_z(primary);support_z=physical_z(support)
        if support_is_column:
            column=next((m for m in ms if m['kind']=='column'),None)
            weak=False
            if family=='hr_simple_shear_plate' and column:
                ray=unit(sub(beam['axis'][1],beam['axis'][0]))
                weak=abs(sum(x*y for x,y in zip(ray,column['local_y'])))>.7
            a.member('M1',cp,[0,0,-bd-12],[0,0,15],y=[1,0,0] if weak else [0,1,0],description='Supporting column '+cp)
            face=p[cp]['dimensions']['tw']/2 if weak else cd/2
        else:
            a.member('M1',cp,[0,-22,support_z],[0,22,support_z],y=(1,0,0),description='Supporting girder '+cp)
            face=p[cp]['dimensions'].get('tw',.375)/2
        gap=0 if family in ('hr_rbs_joint','hr_moment') else 1.25
        rbs=dict(beam['rbs'],ends=[0]) if beam.get('rbs') else None
        if rbs:rbs.pop('cuts',None)
        extra={'rbs':rbs} if rbs else {}
        if not support_is_column and p[bp]['family']=='i' and p[cp]['family']=='i':
            extra['cope']=dict(length_in=max(1,p[cp]['dimensions']['bf']/2+.5-face-gap),depth_in=p[cp]['dimensions']['tf']+.5)
        length=max(40,(rbs['a_in']+rbs['b_in']+8) if rbs else 40)
        a.member('M2',bp,[face+gap,0,beam_z],[face+gap+length,0,beam_z],description='Connected beam '+bp,**extra)
        moment=family in ('hr_rbs_joint','hr_moment')
        plate_t=.375 if moment or family=='test_floor_opening' else (.25 if 'infill' in family else .5)
        n=4 if moment else (3 if family=='test_floor_opening' else (5 if 'infill' in family else 6))
        dia=.75 if moment or 'infill' in family or family=='test_floor_opening' else .875
        pitch=3;edge=1.5 if 'infill' in family else 1.125;ph=(n-1)*pitch+2*edge;pw=6 if moment else 5
        actual=next((q['geometry'] for q in c.get('parts',[]) if q['id']=='shear-plate'),None)
        if actual and not moment:pw,plate_t,ph=actual['size']
        if not moment and text:
            hit=re.search(r'(?<![\d.])(\d+)\s*x\s*'+NUMBER+r'\s*in\.?\s+(?:ASTM\s+F3125\s+)?A(?:325|490)',text,re.I)
            if hit:n=int(hit[1]);dia=number(hit[2]);ph=(n-1)*pitch+2*edge
        ph=min(ph,bd-2.0);edge=(ph-(n-1)*pitch)/2
        if edge<dia: # Explicit test alternative when a source family does not fit the smaller beam.
            pitch=max(2.5*dia,(bd-4)/(n-1));ph=(n-1)*pitch+2;edge=1
            note('A: pitch fitted to this member web; retained source count. This variant has no new capacity verification.')
        tw=p[bp]['dimensions'].get('tw',.375);z=beam_z-ph/2
        a.box('P1',[face,tw/2,z],[pw,plate_t,ph],'A' if moment or family=='test_floor_opening' else 'S',description=f'Shear/erection plate {pw:g} x {ph:g} x {plate_t:g}')
        bolt_x=face+pw-1.75
        fast('F1',grid(n,1,pitch,origin=(bolt_x,-tw/2,z+edge)),(0,1,0),dia,tw+plate_t,['M2','P1'],f'{n} x {dia:g} in '+('A325' if dia==.75 else 'A490')+' through beam web and P1','A' if moment or family=='test_floor_opening' else 'S')
        a.weld('W1',[face,tw/2,z],[face,tw/2,z+ph],['M1','P1'],.25 if family=='test_floor_opening' else .3125,description='Fillet weld both sides of P1 to support; E70XX')
        a.section_at=bolt_x;a.dim([bolt_x,0,z+edge],[bolt_x,0,z+edge+(n-1)*pitch],f'{n-1} @ {pitch:g} in',offset=-34)
        a.dim([face,0,z],[face+pw,0,z],basis='A' if moment else 'S',offset=-35)
        if gap:a.dim([face,0,4],[face+gap,0,4],'1-1/4 in end gap (A)',basis='A',offset=20)
        if moment:
            a.weld('W2',[face,-bf/2,0],[face,bf/2,0],['M1','M2'],kind='CJP',description='CJP beam flange to column flange; source demand-critical requirements')
            a.weld('W3',[face,-bf/2,-bd],[face,bf/2,-bd],['M1','M2'],kind='CJP',description='Bottom-flange CJP; source access-hole requirements')
            a.weld('W4',[face,0,-bd+1],[face,0,-1],['M1','M2'],kind='CJP',description='Web CJP between weld access holes')
            source_plates=[q for q in c.get('parts',[]) if q['kind']=='plate' and 'continuity' in q['id']]
            ct=source_plates[0]['geometry']['size'][-1] if source_plates else .5
            cb=effective(p,cp,'width');cw=p[cp]['dimensions'].get('tw',.5)
            for i,zz in enumerate((-p[bp]['dimensions'].get('tf',.5),-bd)):
                for j,yy in enumerate((-cb/2,cw/2)):
                    label=f'CP{i+1}{j+1}'
                    a.box(label,[-cd/2,yy,zz],[cd,(cb-cw)/2,ct],'S' if source_plates else 'A',description=f'Continuity half-plate at beam flange, t={ct:g}')
                    a.weld(f'WC{i+1}{j+1}',[-cd/2,yy,zz],[cd/2,yy,zz],['M1',label],kind='CJP',basis='S' if source_plates else 'A',description='Continuity-to-column weld per joint schedule')
            doubles=[q for q in c.get('parts',[]) if 'doubler' in q['id']]
            if doubles:
                dt=min(doubles[0]['geometry']['size']);a.box('DP',[-cd/2,cw/2,-bd],[cd,dt,bd],'S',description=f'Panel-zone doubler, t={dt:g}')
                a.weld('WD',[-cd/2,cw/2,-bd],[cd/2,cw/2,-bd],['M1','DP'],.25,description='Doubler boundary weld per source joint schedule')
            if rbs:
                a.dim([face+rbs['a_in'],0,0],[face+rbs['a_in']+rbs['b_in'],0,0],'RBS b',offset=45)
                a.dim([face,0,0],[face+rbs['a_in'],0,0],'RBS a',offset=25)
                note(f"S: RBS reduction c={rbs['c_in']:g} in from EACH flange edge; applied to M2 geometry. Protected zone per source record.")
        note('Bolt head/nut envelopes are illustrative. The transverse cut shows the joined web and plate; grip is not a shop bolt length.')

    elif family=='test_guard' and subtype=='post-base':
        cp=pid;bp=pick(('walkway_edge_beam',),tube(p,8,4,.25));bd=effective(p,bp)
        a.member('M1',cp,[0,0,.875],[0,0,20],basis='A',description='Guard post '+cp)
        a.member('M2',bp,[-20,0,-bd/2],[20,0,-bd/2],basis='A',description='Walkway edge beam '+bp)
        a.box('CAP',[-4,-4,0],[8,8,.5],'A','8 x 8 x 1/2 beam cap plate')
        a.box('BASE',[-3,-3,.5],[6,6,.375],'A','6 x 6 x 3/8 post base plate')
        fast('F1',[[x,y,0] for x in (-2,2) for y in (-2,2)],[0,0,1],.5,.875,['CAP','BASE'],'4 x 1/2 in A325 bolts; 4 x 4 gauge (A)','A')
        a.weld('W1',[-1,-1,.875],[1,-1,.875],['M1','BASE'],.1875,basis='A',description='3/16 in post/base fillet all around (A)')
        a.weld('W2',[-4,-2,0],[4,-2,0],['M2','CAP'],.25,basis='A',description='1/4 in cap-to-beam weld both longitudinal edges (A)')
        a.section_axis=0;a.section_at=0
        note('Guard load path: post/base bolts/cap weld/walkway edge beam. All fitting dimensions are A test inputs.')

    elif family in ('hr_column_base','cfs_portal_pinned_base','test_walkway_support','hr_base','cfs_moment_base') and subtype not in ('beam-seat','rail-joint'):
        cp=pick(('column','walkway_post','guard_post'));cd=effective(p,cp);cw=effective(p,cp,'width')
        embedded=family=='hr_column_base' and cp.startswith('W36')
        if embedded:
            thick=3.25 if cp=='W36X395' else 2;side=47 if cp=='W36X395' else 46
            a.member('M1',cp,[0,0,-96],[0,0,18]);a.box('P1',[-side/2,-side/2,-96-thick],[side,side,thick],'S','Embedded column end plate')
            for i,sign in enumerate((-1,1)):
                a.box(f'P{i+2}',[-17,sign*cw/2-(.75 if sign>0 else 0),-96],[34,.75,96],'S','Source column boxing plate 3/4 x 34 in; local edge preparation required')
                for edge in (-1,1):a.weld(f'W{i+1}-{edge}',[17*edge,sign*cw/2,-96],[17*edge,sign*cw/2,0],['M1',f'P{i+2}'],kind='CJP',description='Source CJP boxing-plate weld to flange tips over full embedment')
            a.box('CONC',[-cd/2-18,-cw/2-18,-114],[cd+36,cw+36,114],'A','Source minimum concrete extent: Le+18 deep and 18 beyond boxed column; reinforcement by foundation engineer',kind='concrete')
            for i,sign in enumerate((-1,1)):
                pts=[[x,sign*cw/2,-90+j*6] for x in (-14,14) for j in range(12)]
                fast('ST'+str(i+1),pts,[0,sign,0],.875,5,[f'P{i+2}','CONC'],'24 headed studs, 7/8 x 5 in; four rows overall','A',True)
            from .review_base_selection import erection_rods
            erection=erection_rods(text)
            if erection:
                if erection['count']!=4:raise ValueError('Pilot embedded base requires an explicit erection-anchor layout')
                edge=erection['edge_min'];dia=erection['diameter']
                pts=[[x,y,-96-thick-12] for x in (-side/2+edge,side/2-edge) for y in (-side/2+edge,side/2-edge)]
                fast('ERECTION-ANCHORS',pts,[0,0,1],dia,12+thick,['P1','CONC'],f'S: four erection-only anchors. A: {dia:g} in F1554 Grade 36, 12 in embedment and corner set-out; no contribution to source base capacity','S count; A diameter, grade, length and set-out')
            a.weld('W3',[-cd/2,0,-96],[cd/2,0,-96],['M1','P1'],.5,basis='A',description='A: continuous 1/2 in end-plate weld')
            a.section_axis=2;a.section_at=-60;a.dim([side/2,0,-96],[side/2,0,0],'96 in embedment');a.dim([0,0,-90],[0,0,-24],'11 @ 6 in stud pitch','A',offset=45)
            note('CONC is a context envelope shown transparent in views; no invented reinforcement is implied.')
        else:
            guard=family=='test_guard';cfs=family.startswith('cfs_');walk=family=='test_walkway_support'
            side_x,side_y,t=(6,6,.375) if guard else ((14,16,.75) if cfs else ((12,12,.75) if walk else (23,23,1.625)))
            gauge,pitch,diam=(4,4,.5) if guard else ((10,12,.75) if cfs else ((8,8,.75) if walk else (16,16,1.25)))
            grout=0 if guard else 2;embed=7 if cfs else (12 if walk else 18)
            a.member('M1',cp,[0,0,grout+t],[0,0,grout+t+max(cd*2,18)])
            a.box('P1',[-side_x/2,-side_y/2,grout],[side_x,side_y,t],'A' if guard or walk else 'S','Base plate')
            a.box('SUPPORT',[-side_x/2-4,-side_y/2-4,-embed-3],[side_x+8,side_y+8,embed+3],'A','Supporting concrete / host context',kind='concrete')
            if grout:a.box('GROUT',[-side_x/2,-side_y/2,0],[side_x,side_y,grout],'A','Non-shrink grout layer',kind='grout')
            pts=[[x,y,-embed] for x in (-gauge/2,gauge/2) for y in (-pitch/2,pitch/2)]
            fast('F1',pts,[0,0,1],diam,embed+grout+t,['P1','SUPPORT'],f'4 x {diam:g} in anchors; A embedment {embed:g} in','A')
            a.weld('W1',[-cd/2,-cw/2,grout+t],[cd/2,-cw/2,grout+t],['M1','P1'],.1875 if guard else .25,basis='A',description='A: continuous fillet around member/base interface')
            if cfs:
                # Paired vertical shoes join all channel webs to the horizontal base plate.
                pair=p[cp].get('pair_spacing_in',6.375) or 6.375
                for i,yy in enumerate((-pair/2,pair/2)):
                    a.box('G'+str(i),[-5,yy-.1875,grout+t],[10,.375,8],'A','Vertical base shoe between channel webs')
                    fast('B'+str(i),[[x,yy-.4,grout+t+z] for x in (-1.5,1.5) for z in (2,5)],[0,1,0],.75,.8,['M1','G'+str(i)],'4 web bolts per channel pair, 3 in gauge/pitch','A')
                    a.weld('WG'+str(i),[-5,yy,grout+t],[5,yy,grout+t],['P1','G'+str(i)],.25,basis='A',description='A: shoe-to-base fillet both sides')
            a.section_axis=2;a.section_at=grout+t/2
            a.dim([-side_x/2,0,grout],[side_x/2,0,grout],'Base width',offset=-35)
            a.dim([-gauge/2,0,grout],[gauge/2,0,grout],'Anchor gauge','A',offset=-60)
            note('Anchor diameter/count from source where stated. A identifies the adopted embedment, set-out and grout values; no foundation capacity calculation is added.')

    elif family in ('hr_column_splice_48in_above_floor','hr_splice'):
        cp=pid;above=ms[1]['profile_id'] if len(ms)>1 else cp;d=max(effective(p,cp),effective(p,above));b=effective(p,cp,'width')
        a.member('M1',cp,[0,0,-24],[0,0,0]);a.member('M2',above,[0,0,0],[0,0,24])
        cjp='complete-joint' in text.lower() or 'CJP' in text or 'lateral' in text.lower()
        if cjp:
            a.weld('W1',[-d/2,-b/2,0],[-d/2,b/2,0],['M1','M2'],kind='CJP',description='CJP column flanges; source splice grade/inspection requirements')
            a.weld('W2',[d/2,-b/2,0],[d/2,b/2,0],['M1','M2'],kind='CJP',description='Opposite flange CJP')
            a.weld('W3',[-d/2,0,0],[d/2,0,0],['M1','M2'],kind='CJP',description='Column web CJP')
        flange=re.search(r'flange plates?\s+PL\s+'+NUMBER+r'\s*x\s*'+NUMBER,text,re.I)
        ft,fw=(number(flange[1]),number(flange[2])) if flange and not cjp else (.75,min(b,12))
        for i,sign in enumerate((-1,1)):
            lab='P'+str(i+1);a.box(lab,[sign*d/2-(ft if sign<0 else 0),-fw/2,-12],[ft,fw,24],'A' if cjp else 'S',f'Splice flange/erection plate t={ft:g}, width {fw:g}; A length 24')
            pts=[[sign*(d/2+ft),yy,zz] for yy in (-fw/2+3,fw/2-3) for zz in ((-9,-3,3,9) if cjp else (-6,6))]
            fast('F'+str(i+1),pts,[-sign,0,0],.75 if cjp else .875,ft+p[cp]['dimensions'].get('tf',1),['M1','M2',lab],'8 x 3/4 in erection bolts (A)' if cjp else '4 x 7/8 in A325; 2 per flange each side of splice','A' if cjp else 'S')
        if not cjp:
            hit=re.search(r'web plates?\s+2\s+PL\s+'+NUMBER+r'\s*x\s*'+NUMBER,text,re.I)
            wpt,wpw=(number(hit[1]),number(hit[2])) if hit else (.375,9)
            wt=p[cp]['dimensions'].get('tw',.5)
            for i,sign in enumerate((-1,1)):a.box('WP'+str(i+1),[-wpw/2,sign*wt/2-(wpt if sign<0 else 0),-9],[wpw,wpt,18],'S','Web splice cover; A overall vertical length 18')
            fast('FW',[[xx,-wt/2-wpt,zz] for xx in (-1.5,1.5) for zz in (-6,6)],[0,1,0],.875,wt+2*wpt,['M1','M2','WP1','WP2'],'4 x 7/8 in through both web covers; two each side of splice','S')
            for j,(member,name,lo,hi) in enumerate(((cp,'M1',-12,0),(above,'M2',0,12))):
                filler=(d-effective(p,member))/2
                if filler>.005:
                    for i,sign in enumerate((-1,1)):
                        xx=-d/2 if sign<0 else d/2-filler
                        a.box(f'FL{j}{i}',[xx,-fw/2,lo],[filler,fw,hi-lo],'A',f'Fit filler between {name} and flange cover, t={filler:g}; source filler specification retained')
        a.section_axis=2;a.section_at=6;a.dim([d/2+4,0,-12],[d/2+4,0,12],'24 in erection plate','A');note('Splice datum: 48 in above the floor. Source CJP or bearing-splice classification is retained; A erection fittings are explicit.')

    elif family in ('cfs_knee_3x4','cfs_apex_3x3','cfs_portal_knee','cfs_portal_apex'):
        apex='apex' in family;cp=pick(('column',));rp=pick(('rafter',),pid);slope=.2
        rm=next((m for m in ms if m['kind']=='rafter'),None)
        if rm:
            v=sub(rm['axis'][1],rm['axis'][0]);slope=abs(v[2])/max(math.hypot(v[0],v[1]),1e-9)
        slope=max(slope,.001);theta=math.atan(slope);co,si=math.cos(theta),math.sin(theta)
        dirs=[[-co,0,-si],[co,0,-si]] if apex else [[0,0,-1],[co,0,si]]
        gap=.375;rows=3 if apex else 4;leg=(rows-1)*3+4;pair=p[rp].get('pair_spacing_in',6.375) or 6.375
        from .assembly_scene import clip_part
        bisector=unit(sub(dirs[0],dirs[1]))
        for i,v in enumerate(dirs):
            part=a.member('M'+str(i+1),rp if apex or i else cp,[0,0,0],mul(v,34),description=('Rafter' if apex or i else 'Column')+' '+(rp if apex or i else cp))
            clip_part(part,mul(bisector,1 if i==0 else -1),gap/2)
        # A continuous polygon bridges both legs, instead of two disconnected rectangles.
        for j,yy in enumerate((-pair/2,pair/2)):
            points=[]
            for v in dirs:
                across=[-v[2],0,v[0]]
                points += [add(mul(v,end),add(mul(across,side),[0,yy-.1875,0])) for end in (0,leg) for side in (-6,6)]
            # Convex hull of each joined pair of leg envelopes; deliberately no re-entrant notch.
            q=sorted(set((round(v[0],7),round(v[2],7)) for v in points))
            def turn(o,b,c):return (b[0]-o[0])*(c[1]-o[1])-(b[1]-o[1])*(c[0]-o[0])
            lo=[]
            for v in q:
                while len(lo)>=2 and turn(lo[-2],lo[-1],v)<=0:lo.pop()
                lo.append(v)
            hi=[]
            for v in reversed(q):
                while len(hi)>=2 and turn(hi[-2],hi[-1],v)<=0:hi.pop()
                hi.append(v)
            poly=[[x,yy-.1875,z] for x,z in lo[:-1]+hi[:-1]];label='P'+str(j+1)
            a.polygon(label,poly,.375,basis='A',description='Continuous 3/8 in bracket, both legs joined (A outline)')
            for i,v in enumerate(dirs):
                across=[-v[2],0,v[0]];pts=[add(mul(v,2+r*3),add(mul(across,g),[0,yy-.35,0])) for r in range(rows) for g in (-4,0,4)]
                fast(f'F{j+1}{i+1}',pts,[0,1,0],.75,.7,['M'+str(i+1),label],f'{rows*3} x 3/4 in A325, leg {i+1}, pair {j+1}','S')
        a.section_axis=0;a.section_at=6;a.dim([-6,0,-leg],[6,0,-leg],'12 in leg envelope','A',offset=-35)
        a.dim([0,0,-2],[0,0,-(2+3*(rows-1))],f'{rows-1} @ 3 in',offset=45)
        note('S: source bolt count, pitch/gauge and 3/8 in plate. A: continuous convex boundary joins both leg groups; 3/8 in assembly gap. Two bracket planes match the paired-channel webs.')

    elif family in ('cfs_chord','cfs_hold_down_rod','cfs_holddown'):
        suffix=next((rid.split('conn-rod-bracket-')[-1] for rid in c.get('design_record_ids',[]) if 'conn-rod-bracket-' in rid),'')
        matching=[m for m in model['members'] if m['kind']=='chord' and m.get('level')==level and any(rid.endswith(suffix) for rid in m.get('design_record_ids',[]))]
        cp=pick(('chord',),matching[0]['profile_id'] if matching else next((m['profile_id'] for m in model['members'] if m['kind']=='chord'),default_c()))
        h=20;gap=findnum(NUMBER+r'\s*in\.\s*clear',text,4.25);t=findnum(r'^'+NUMBER+r'\s*in',text,.25)
        hit=re.search(NUMBER+r'\s*x\s*'+NUMBER+r'\s*in\.\s*A572.*?bearing plate',text,re.I)
        bt,bw=(number(hit[1]),number(hit[2])) if hit else (.875,5.5)
        n,no=group(text,(28,14));cols=4;rows=math.ceil(n/cols);ph=max(10,rows+2)
        rod_member=next((m for m in ms if m['kind']=='hold_down_rod'),None)
        rd=p[rod_member['profile_id']]['dimensions']['d'] if rod_member else None
        if rd is None:
            candidates=[m for m in model['members'] if m['kind']=='hold_down_rod' and m.get('level')==level and any(rid.endswith(suffix) for rid in m.get('design_record_ids',[]))]
            rd=p[candidates[0]['profile_id']]['dimensions']['d'] if candidates else 1.75
        a.member('M1',cp,[0,0,-h],[0,0,10],y=(1,0,0),description='Source spaced chord pack '+cp)
        a.member('M2',rod(p,rd),[0,0,-h],[0,0,14],description=f'Continuous tie rod dia {rd:g}, story {level}')
        for i,sign in enumerate((-1,1)):
            lab='P'+str(i+1);xx=sign*gap/2-(t if sign<0 else 0)
            a.box(lab,[xx,-bw/2,-ph],[t,bw,ph],'S','Rod bracket side plate')
        a.box('BP',[-gap/2,-bw/2,-bt],[gap,bw,bt],'S','Bearing plate between side plates')
        a.cylinder('NUT',[0,0,0],[0,0,1],rd*1.8,rd*.8,'A','Heavy nut / take-up envelope; actual supplier outline follows')
        a.weld('W1',[-gap/2,-bw/2,-bt],[-gap/2,bw/2,-bt],['BP','P1'],.1875,description='3/16 fillets top and bottom of bearing plate')
        a.weld('W2',[gap/2,-bw/2,-bt],[gap/2,bw/2,-bt],['BP','P2'],.1875,description='Opposite bearing-plate fillets')
        a.section_axis=2;a.section_at=-3;a.dim([-gap/2,0,0],[gap/2,0,0],'Clear bracket gap',offset=35);a.dim([gap/2+1,0,-ph],[gap/2+1,0,0],'Side plate height (A)','A')
        note(f'S: {n} No.{no} screws total. A: the side plates have welded 2 in returns over both chord flanges; the source screw total is divided between four returns. This resolves the physical attachment without placing screws across the empty pack gap.')
        for i,(sx,sy) in enumerate(((-1,-1),(-1,1),(1,-1),(1,1))):
            count=n//4+(1 if i<n%4 else 0);xx=-gap/2-2 if sx<0 else gap/2;yy=sy*3-(t if sy<0 else 0)
            label='R'+str(i+1);a.box(label,[xx,yy,-ph],[2,t,ph],'A','2 in welded return over chord flange')
            pts=[[xx+1,sy*(3+t),-ph+1+j*(ph-2)/max(1,count-1)] for j in range(count)]
            fast('F'+str(i+1),pts,[0,-sy,0],screw_diameter(no),t+.15,['M1',label],f'{count} No.{no}; total four returns {n}','S',True)
            side='P1' if sx<0 else 'P2';a.weld('WR'+str(i+1),[sx*gap/2,yy,-ph],[sx*gap/2,yy,0],[side,label],.1875,basis='A',description='A: return-to-side-plate fillet both sides')

    elif family in ('cfs_strap','cfs_scheduled_strap','hr_brace_gusset','hr_brb_gusset','hr_ebf_brace'):
        hr=family.startswith('hr');sp=pick(('strap','brace','brb'),pid)
        cp=pick(('chord','column'),default_w() if hr else default_c());tp=default_w() if hr else channel(p,'ASSEMBLY-TRACK6',6,1.25,.1017,0)
        a.member('M1',cp,[0,0,-4],[0,0,30],description='Receiving chord/column '+cp)
        a.member('M2',tp,[0,0,0],[36,0,0],description='Receiving track/beam '+tp)
        n,no=group(text,(8,14) if hr else (40,12));n=min(n,80)
        cols=5 if n>20 else (3 if n>10 else 2);rows=math.ceil(n/cols);gw=max(12,rows+6);gh=max(12,cols+7);gt=.5 if hr else .1017
        if '137 mil' in text:gt=.1438
        angle=math.radians(45);v=[math.cos(angle),0,math.sin(angle)];along=[-v[2],0,v[0]]
        strap_t=p[sp]['dimensions'].get('thickness',.125);surface=effective(p,cp,'width')/2
        a.member('M3',sp,[5,surface+gt+strap_t/2,5],[32,surface+gt+strap_t/2,32],y=along,description='Brace / strap '+sp)
        a.polygon('P1',[[0,surface,0],[gw,surface,0],[gw,surface,gh*.6],[gw*.6,surface,gh],[0,surface,gh]],gt,basis='S' if not hr else 'A',description=f'Gusset t={gt:g}; A boundary fitted to all three attachment groups')
        pts=[add([6,surface,6],add(mul(v,i//cols),mul(along,i%cols-(cols-1)/2))) for i in range(n)]
        fast('F1',pts,[0,1,0],.75 if hr else screw_diameter(no),gt+strap_t,['M3','P1'],f'{n} '+('3/4 in bolts (A)' if hr else f'No.{no} strap-to-gusset screws'),'A' if hr else 'S',not hr)
        if hr:
            a.weld('W1',[0,surface,0],[0,surface,gh],['M1','P1'],.3125,basis='A',description='A: gusset-to-column fillet both sides')
            a.weld('W2',[0,surface,0],[gw,surface,0],['M2','P1'],.3125,basis='A',description='A: gusset-to-beam fillet both sides')
        else:
            m=re.search(r'gusset to chord pack (\d+)\s+No\.?\s*(\d+).*?track (\d+)\s+No\.?\s*(\d+)',text,re.I)
            nc,cc,nt,ct=map(int,m.groups()) if m else (8,14,8,14)
            fast('F2',grid(nc,2,1,1,origin=(.75,surface,.75)),[0,1,0],screw_diameter(cc),gt+.2,['M1','P1'],f'{nc} No.{cc} gusset-to-chord screws','S' if m else 'A',True)
            fast('F3',grid(nt,math.ceil(nt/2),1,1,origin=(3,surface,.75)),[0,1,0],screw_diameter(ct),gt+.15,['M2','P1'],f'{nt} No.{ct} gusset-to-track screws','S' if m else 'A',True)
        a.section_axis=0;a.section_at=6;a.dim([0,0,0],[gw,0,0],'Gusset extent (A)','A',offset=-30)
        note('Three independent load-path attachments are drawn: brace to gusset, gusset to vertical member, gusset to horizontal member. Source attachment counts remain separate.')

    elif family in ('cfs_stud','cfs_top_track','cfs_bottom_track','cfs_stud_bridging','cfs_bridging_anchor'):
        if c.get('parameters',{}).get('physical_stud_support'):
            from .review_assemblies import Context
            from .review_wall_occurrence_details import cripple
            ctx=Context(model,package,c);cripple(ctx);return ctx.finish()
        fitted=c.get('parameters',{}).get('physical_track')
        sp=pid if fitted else pick(('stud',),next((m['profile_id'] for m in model['members'] if m['kind']=='stud'),default_c()));sd=effective(p,sp)
        tp=pick(('top_track','bottom_track'),channel(p,f'ASSEMBLY-T{sd:g}',sd,1.25,.0566,0))
        bridging=family in ('cfs_stud_bridging','cfs_bridging_anchor')
        direction=c.get('parameters',{}).get('stud_end_direction',1)
        ends=([0,0,0],[0,0,18]) if direction>0 else ([0,0,-18],[0,0,0])
        a.member('M1',sp,*ends,y=(1,0,0),description='Stud '+sp) if fitted else a.member('M1',sp,[0,0,-12 if bridging else 0],[0,0,18],description='Stud '+sp)
        if bridging:
            bp=pick(('stud_bridging',),channel(p,'ASSEMBLY-U1.5',1.5,.5,.0566,0));a.member('M2',bp,[-18,0,6],[18,0,6],description='Continuous bridging '+bp)
            clip(a,'L1',[-1,0,4],4,2,.0566)
            fast('F1',[[-.5,0,5],[-.5,0,7]],[0,1,0],.19,.12,['M1','L1a'],'2 No.10 to stud (A set-out)','S',True)
            fast('F2',[[0,.75,5],[0,.75,7]],[1,0,0],.19,.12,['M2','L1b'],'2 No.10 to bridging (A set-out)','S',True)
            if family=='cfs_bridging_anchor':
                a.member('M3',pid,[-6,0,6],[6,0,6],description='Source bridging anchor strap '+pid)
                fast('F3',[[-1,0,6],[1,0,6]],[0,1,0],.19,.2,['M3','M1'],'2 No.10 anchor strap to stud','S',True)
            a.section_at=0
        else:
            # Rotate track to open upward; stud flanges engage the two track legs.
            if fitted:a.member('M2',fitted['profile_id'],*fitted['axis'],y=fitted['local_y'],description='Actual receiving track '+fitted['profile_id'])
            else:a.member('M2',tp,[-15,0,0],[15,0,0],y=(0,0,1),description='Receiving track '+tp)
            for i,sign in enumerate((-1,1)):
                if c.get('parameters',{}).get('each_ply_end_screws'):
                    from .pilots.geometry import strips
                    positions=set()
                    for poly in strips(p[sp],p):
                        for aa,bb in zip(poly,poly[1:]+poly[:1]):
                            if abs(aa[1]-sign*sd/2)<1e-6 and abs(bb[1]-aa[1])<1e-6 and abs(bb[0]-aa[0])>.3:positions.add(round((aa[0]+bb[0])/2,6))
                    if not positions:raise ValueError('No exposed chord flange at track attachment')
                    trackpart=next(part for part in a.parts if part['id']=='M2');surface=trackpart['bounds'][1][i]
                    grip=abs(surface-sign*sd/2)+.125
                    fast('F'+str(i+1),[[x,surface,direction*.65] for x in sorted(positions)],[0,-sign,0],.19,grip,['M1','M2'],'A one No.10 at each exposed chord-ply flange; verify grip/attachment capacity','A',True)
                else:fast('F'+str(i+1),[[.75 if fitted else 0,sign*sd/2,direction*.65]],[0,-sign,0],.19,.12,['M1','M2'],'1 No.10 through track leg and stud flange; A local station','S',True)
            a.dim([0,-sd/2,0],[0,sd/2,0],'Stud/track nominal depth',view='section');note('Stud seated on track web. One screw through EACH flange; top condition mirrors this bottom condition. Track size follows the stud depth/mil variant.')
        a.section_axis=2;a.section_at=direction*.65 if not bridging else 6

    elif family in ('cfs_joist','cfs_bearing_stiffener','cfs_squash_block','cfs_rim_track','cfs_collector','cfs_collector_blocking','cfs_junction_collector','cfs_floor_stack'):
        jp=pick(('joist',),next((m['profile_id'] for m in model['members'] if m['kind']=='joist'),default_c(12,2,.0713)))
        jd=effective(p,jp);sp=next((m['profile_id'] for m in model['members'] if m['kind']=='stud'),default_c());sd=effective(p,sp)
        tp=channel(p,f'ASSEMBLY-T{sd:g}',sd,1.25,.1017,0);st=channel(p,'ASSEMBLY-STIFFENER',3.625,1.625,.0451)
        a.member('M1',sp,[0,0,-20],[0,0,0]);a.member('M2',tp,[0,-18,0],[0,18,0],y=(0,0,1),description='Top track of lower wall')
        a.member('M3',jp,[-2.5,0,jd/2],[28,0,jd/2],description='Floor joist '+jp)
        a.member('M4',st,[0,.15,0],[0,.15,jd],y=(1,0,0),description='Full-depth bearing stiffener 362S162-43')
        a.member('M5',tp,[0,-18,jd+.1017],[0,18,jd+.1017],y=(0,0,1),description='Bottom track of upper wall')
        a.member('M6',sp,[0,0,jd+.1017],[0,0,jd+18],description='Aligned upper stud')
        a.box('DECK',[sd/2,-12,jd],[25,24,.75],'A','3/4 in subfloor; held clear of bearing-wall stack',kind='panel')
        fast('F1',grid(3,1,(jd-3)/2,origin=(0,-.1,1.5)),[0,1,0],.19,.2,['M3','M4'],'3 No.10 stiffener-to-joist web screws','S',True)
        # Both interfaces in the floor shear transfer are explicit; counts belong to a complete bay.
        a.box('CLIP',[sd/2-.1,-4,jd-3],[.0566,8,4],'A','54 mil shear-transfer clip at track/rim interface')
        fast('F2',[[sd/2,-2,jd+.5],[sd/2,2,jd+.5]],[-1,0,0],.216,.2,['M5','CLIP'],'Upper shear group: distribute source screws over full bay','S',True)
        fast('F3',[[sd/2,-2,jd-1],[sd/2,2,jd-1]],[-1,0,0],.216,.2,['M3','CLIP'],'Lower clip group: distribute source screws over full bay','S',True)
        fast('F4',[[-1,0,.05],[1,0,.05]],[0,0,1],.216,.2,['M3','M2'],'Joist/rim bottom flange to lower top track; bay schedule governs','S',True)
        if family=='cfs_squash_block':
            a.member('SB',pid,[0,0,0],[0,0,jd],y=(1,0,0),description='Actual chord squash pack '+pid)
            fast('FS',[[0,-.1,2],[0,-.1,jd-2]],[0,1,0],.216,.3,['SB','M3'],'A: 2 No.12 positional screws; compression bears through the full pack','A',True)
        elif family in ('cfs_rim_track','cfs_collector','cfs_collector_blocking','cfs_junction_collector'):
            if p[pid]['family']=='flat':
                a.member('COL',pid,[-sd/2,-18,jd+.2],[-sd/2,18,jd+.2],y=(1,0,0),description='Source collector strap '+pid)
                axis=[0,0,1];pts=[[-sd/2,yy,jd] for yy in (-8,0,8)]
            else:
                a.member('COL',pid,[-sd/2,-18,jd/2],[-sd/2,18,jd/2],y=(1,0,0),description='Source rim/collector/blocking '+pid)
                axis=[1,0,0];pts=[[-sd/2,yy,jd/2] for yy in (-8,0,8)]
            fast('FC',pts,axis,.216,.3,['COL','M3'],'Source distributed collector/rim group; three stations shown in this extract','S',True)
        a.section_axis=0;a.section_at=0;a.dim([28,0,0],[28,0,jd],'Joist depth');a.dim([-2.5,0,-3],[0,0,-3],'2-1/2 in bearing',offset=-35)
        note('All six steel components shown in the floor stack. The upper wall bears steel-to-steel through the stiffened joist; subfloor stops at the wall. Source bay screw counts are distributed along the full bay, not concentrated into this cut segment.')
        story=re.search(r'story\s+'+str(level)+r'\s+(\d+)',text,re.I)
        if story:note(f'S: story {level}: {story[1]} No.12 screws PER BAY AND GROUP at each floor-shear interface. The two shown are a local extract of the continuous group.')

    elif family=='cfs_scheduled_endwall_post' and subtype=='post-base':
        cp=pid;cd=effective(p,cp);a.member('M1',cp,[0,0,0],[0,0,24])
        a.box('CONC',[-12,-12,-10],[24,24,10],'A','Local foundation context',kind='concrete')
        for i,sign in enumerate((-1,1)):
            yy=sign*2
            a.box('L'+str(i)+'v',[-2,yy,0],[4,.25,7],'S','L4 x 4 x 1/4 vertical leg; A cut length 7')
            a.box('L'+str(i)+'h',[-2,yy if sign>0 else yy-4,0],[4,4,.25],'S','Angle foot on concrete')
            fast('B'+str(i),[[0,yy,2],[0,yy,5]],[0,-sign,0],.5,.6,['M1','L'+str(i)+'v'],'2 x 1/2 in A325-N web bolts per clip','S')
            fast('A'+str(i),[[0,yy+sign*2,-7]],[0,0,1],.625,7.25,['CONC','L'+str(i)+'h'],'1 x 5/8 in F1554 Gr36 anchor per clip; A 7 in embedment','A')
        a.section_axis=2;a.section_at=2;a.dim([0,0,2],[0,0,5],'3 in bolt pitch (A)','A');note('Two source clip angles and two source anchors are shown as a complete base. A: clip length, bolt pitch and anchor embedment; keep source grade/count.')

    elif family=='test_walkway_support' and subtype=='beam-seat':
        cp=pick(('walkway_post',),tube(p,6,6,.25));bp=pick(('walkway_edge_beam',),tube(p,8,4,.25));cd=effective(p,cp)
        a.member('M1',cp,[0,0,-20],[0,0,12],basis='A',description='Walkway post '+cp)
        a.member('M2',bp,[cd/2+.125,0,4.5],[cd/2+28,0,4.5],basis='A',description='Walkway edge beam '+bp)
        a.box('P1',[cd/2,-4,0],[10,8,.5],'A','Beam seat 1/2 x 8 x 10 in')
        fast('F1',[[cd/2+x,y,0] for x in (2,8) for y in (-1,1)],[0,0,1],.625,.75,['M2','P1'],'4 x 5/8 in seat bolts on 6 x 2 in grid (A)','A')
        a.weld('W1',[cd/2,-4,.25],[cd/2,4,.25],['M1','P1'],.25,basis='A',description='A: 1/4 in seat-to-post fillet both sides')
        for i,yy in enumerate((-2,2)):
            label='ST'+str(i);a.polygon(label,[[cd/2,yy,-6],[cd/2,yy,0],[cd/2+8,yy,0]],.375,basis='A',description='Seat stiffener 3/8 in, 6 x 8 triangular envelope')
            a.weld('WS'+str(i),[cd/2,yy,-6],[cd/2,yy,0],['M1',label],.25,basis='A',description='A: stiffener-to-post weld')
            a.weld('WT'+str(i),[cd/2,yy,0],[cd/2+8,yy,0],['P1',label],.25,basis='A',description='A: stiffener-to-seat weld')
        a.section_axis=0;a.section_at=cd/2+5;a.dim([cd/2,0,0],[cd/2+10,0,0],'10 in seat projection (A)','A',offset=-35)

    elif family=='test_wall_opening' and subtype=='jamb-base':
        cp=pid;cd=effective(p,cp);ground=c['point'][2]<1
        a.member('M1',cp,[0,0,.125],[0,0,24],basis='A',description='Opening jamb '+cp)
        if ground:
            a.box('CONC',[-12,-10,-10],[24,20,10],'A','Foundation context',kind='concrete')
            host='CONC'
        else:
            jp=pick(('joist',),next((m['profile_id'] for m in model['members'] if m['kind']=='joist'),default_c(12,2,.0713)))
            jd=effective(p,jp);a.member('M2',jp,[-18,0,-jd/2],[18,0,-jd/2],basis='A',description='Floor joist / rim support below jamb '+jp)
            a.box('CAP',[-6,-6,-.25],[12,12,.25],'A','Floor spreader plate under jamb shoes 12 x 12 x 1/4')
            fast('FC',[[x,1,-.25] for x in (-4,-2,2,4)],[0,0,-1],.25,.4,['CAP','M2'],'4 No.14 spreader-to-joist flange screws (A)','A',True)
            host='CAP'
        tp=channel(p,'ASSEMBLY-JAMB-SILL',cd+.125,2,.1017,0)
        a.member('TRACK',tp,[0,-12,.05],[0,12,.05],y=(0,0,1),basis='A',description='97 mil jamb sill, fitted to pack (A)')
        for i,(yy,sign,t) in enumerate(web_faces(p,cp)):
            lab='L'+str(i);oy=yy if sign>0 else yy-.125
            a.box(lab+'V',[-2,oy,.125],[4,.125,6],'A','Jamb shoe vertical leg 4 x 6 x 1/8')
            a.box(lab+'H',[-2,yy if sign>0 else yy-3,0],[4,3,.125],'A','Shoe foot 3 in projection')
            fast('B'+str(i),[[xx,yy+sign*.125,z] for xx in (-1,1) for z in (1.5,4.5)],[0,-sign,0],.25,.125+t,[lab+'V','M1'],'4 No.14 shoe-to-jamb screws per ply (A)','A',True)
            anchor=[0,yy+sign*1.5,-7 if ground else -.25]
            fast('A'+str(i),[anchor],[0,0,1],.5 if ground else .25,7.125 if ground else .5,[lab+'H',host],'1 x 1/2 in anchor, 7 in embedment (A)' if ground else '1 No.14 shoe-to-floor support screw (A)','A',not ground)
            a.weld('W'+str(i),[-2,yy,.125],[2,yy,.125],[lab+'V',lab+'H'],.125,basis='A',description='1/8 in shoe corner fillet (A)')
        a.section_axis=2;a.section_at=2
        note('A: complete opening-jamb base fitting. Ground bases bear on foundation context; upper-storey bases connect to floor framing. No header is substituted for this base.')

    elif family in ('cfs_ledger','cfs_walkway_joist','cfs_scheduled_door_header','cfs_scheduled_endwall_post','test_floor_opening','test_wall_opening','cfs_clip'):
        jp=pick(('walkway_joist','opening_header','opening_trimmer','door_header','joist','walkway_edge_beam'),pid)
        horizontal_support=family=='test_floor_opening'
        cp=receiver(('opening_trimmer','opening_header','joist','girder'),jp) if horizontal_support else pick(('opening_jamb','endwall_post','walkway_post','stud'),next((m['profile_id'] for m in model['members'] if m['kind']=='endwall_post'),default_c()))
        jd=effective(p,jp);cd=effective(p,cp)
        if horizontal_support:
            a.member('M1',cp,[0,-20,-cd/2],[0,20,-cd/2],y=(1,0,0),description='Receiving opening frame '+cp)
            face=.15
        else:
            a.member('M1',cp,[0,0,-jd-14],[0,0,0 if subtype=='jamb-head' else 12],description='Receiving post/jamb/stud '+cp);face=cd/2
        a.member('M2',jp,[face+.125,0,-jd/2],[face+28,0,-jd/2],description='Supported header/joist '+jp)
        bolted=family in ('cfs_scheduled_door_header','cfs_scheduled_endwall_post')
        height=7 if bolted else min(jd-1,8);leg=4 if bolted else (3 if family.startswith('test') else 2);t=.25 if bolted else (.125 if family.startswith('test') else .0566)
        faces=web_faces(p,jp) if p[jp]['family'] in ('channel','built_up') else [(-effective(p,jp,'width')/2,-1,.1875),(effective(p,jp,'width')/2,1,.1875)]
        for i,(web,sign,web_t) in enumerate(faces):
            yy=web+(-t if sign<0 else 0);inward=-sign;labels=['L'+str(i+1)+'a','L'+str(i+1)+'b']
            a.box(labels[0],[face,yy,-height-1],[leg,t,height],'A',f'Clip angle {leg:g} x {leg:g} x {t:g}; height {height:g}, at web ply {i+1}')
            a.box(labels[1],[face,web if inward>0 else web-leg,-height-1],[t,leg,height],'A','Clip return against supporting member')
            n=2 if bolted else (6 if family=='test_wall_opening' else (8 if family=='test_floor_opening' else 3));cols=2 if n>3 else 1;rows=math.ceil(n/cols);pitch=3 if bolted else (height-2)/max(1,rows-1)
            fast('F'+str(i+1)+'a',grid(n,cols,pitch,1,origin=(face+.75,web+sign*t,-height+1),along=(1,0,0)),[0,-sign,0],.5 if bolted else (.25 if n>3 else .19),t+web_t,['M2',labels[0]],f'{n} '+('1/2 in A325-N bolts' if bolted else 'screws')+' to supported web ply','A' if n>3 else 'S',not bolted)
            fast('F'+str(i+1)+'b',grid(n,cols,pitch,1,origin=(face+t,web+inward*.75,-height+1),along=(0,inward,0)),[-1,0,0],.5 if bolted else (.25 if n>3 else .19),t+.15,['M1',labels[1]],f'{n} '+('1/2 in A325-N bolts' if bolted else 'screws')+' to supporting flange','A' if n>3 else 'S',not bolted)
        a.section_axis=0;a.section_at=face+1;a.dim([face,0,-height-1],[face,0,-1],'Clip height (A)','A',offset=35)
        if family in ('cfs_ledger','cfs_walkway_joist'):
            lp=pick(('ledger',),next((m['profile_id'] for m in model['members'] if m['kind']=='ledger'),default_c(12,2,.0566)))
            a.member('LEDGER',lp,[face,-15,-jd/2],[face,15,-jd/2],y=(1,0,0),description='Wall-face ledger '+lp)
            fast('FL',[[face,0,-jd/2-2],[face,0,-jd/2+2]],[-1,0,0],.216,.3,['M1','LEDGER'],'2 No.12 ledger screws at EVERY stud','S',True)
        note('Both legs and both attachment groups are shown. Paired opening members receive a clip at each load-carrying ply. A clip extents and screw set-out are adopted test geometry.')

    elif family in ('cfs_scheduled_purlin','cfs_scheduled_purlin_nested','cfs_scheduled_girt','cfs_scheduled_endwall_girt','cfs_scheduled_eave_strut','cfs_secondary_lap'):
        zp=pid;zp=pick(('purlin','girt','purlin_nested','endwall_girt','eave_strut'),zp);zd=effective(p,zp)
        rp=next((m['profile_id'] for m in model['members'] if m['kind']=='rafter'),default_c(14,3,.1242));rd=effective(p,rp)
        a.member('M1',rp,[0,-20,-rd/2],[0,20,-rd/2],y=(1,0,0),description='Rafter / column supporting secondary steel')
        a.member('M2',zp,[-35,0,zd/2],[12,0,zd/2],description='Left purlin/girt with 24 in lap')
        a.member('M3',zp,[-12,.125,zd/2],[35,.125,zd/2],description='Right purlin/girt; 1/8 in nest offset (A)')
        clip(a,'L1',[-2,0,0],4,3,.125)
        fast('F1',[[-1,0,1],[-1,0,3]],[0,1,0],.25,.4,['M2','M3','L1a'],'2 x 1/4 in screws through nested webs and clip (A)','A',True)
        fast('F2',[[-1,1,0],[-1,2,0]],[0,0,-1],.25,.4,['M1','L1b'],'2 x 1/4 in clip-to-rafter fasteners (A)','A',True)
        fast('F3',[[x,0,z] for x in (-9,9) for z in (2,zd-2)],[0,1,0],.25,.3,['M2','M3'],'4 lap stitch screws; A layout, source selection retained','A',True)
        a.section_axis=0;a.section_at=0;a.dim([-12,0,zd+1],[12,0,zd+1],'24 in lap','S',offset=35)
        note('Lap webs, nested offset, support member and both clip legs are drawn. This local detail uses the actual section variant; source fastener selection and zone schedule accompany it.')

    elif family in ('hr_required_bottom_flange_brace','cfs_scheduled_flange_kicker','hr_kicker'):
        hr=family.startswith('hr');bp=pick(('moment_beam','girder','rafter'),default_w() if hr else default_c(14,3,.1242));bd=effective(p,bp)
        kp=pick(('flange_kicker',),None);kp=kp if p[kp]['family']=='angle' else 'ASSEMBLY-L3'
        p.setdefault(kp,dict(id=kp,family='angle',dimensions=dict(h=3 if hr else 2,b=3 if hr else 2,t=.25 if hr else .125)))
        pp=next((m['profile_id'] for m in model['members'] if m['kind']==('infill' if hr else 'purlin')),default_w() if hr else default_c(8,2.5,.0713))
        pd=effective(p,pp);pz=-pd/2 if hr else pd/2
        a.member('M1',bp,[-20,0,-bd/2],[20,0,-bd/2]);a.member('M2',pp,[0,-12,pz],[0,34,pz],y=(1,0,0))
        start=[0,0,-bd+1];length=30 if not hr else max(30,bd)
        rise=pz-start[2];run=math.sqrt(max(1,length*length-rise*rise))
        end=[0,run,pz]
        a.member('M3',kp,start,end,y=(1,0,0),basis='A')
        for i,(pt,host) in enumerate(((start,'M1'),(end,'M2'))):
            a.box('P'+str(i),[pt[0]-.375,pt[1]-2,pt[2]-1],[.375,4,4],'A','Brace end tab / angle leg')
            fast('F'+str(i),[[pt[0]-.375,pt[1],pt[2]+z] for z in (0,1,2)],[1,0,0],.75 if hr else .216,.625,['M3','P'+str(i)],'3 brace-end fasteners, adopted local set-out','A',not hr)
            if hr:a.weld('W'+str(i),[pt[0]-.375,pt[1],pt[2]-1],[pt[0]-.375,pt[1],pt[2]+3],[host,'P'+str(i)],.25,basis='A',description='A: tab-to-receiving web fillet both sides')
            elif i==0:
                a.box('FOOT',[-2,-2,-bd],[4,4,.125],'A','Lower clip return against rafter bottom flange')
                fast('FH0',[[x,y,-bd] for x in (-1,1) for y in (-1,1)],[0,0,1],.216,.3,['FOOT','M1'],'4 No.12 lower clip-to-rafter flange screws (A)','A',True)
                a.weld('WC',[-.375,-2,-bd],[-.375,2,-bd],['FOOT','P0'],.125,basis='A',description='A: formed/fabricated lower clip corner')
            else:fast('FH1',[[pt[0]-.375,pt[1]+y,pt[2]+z] for y in (-1,1) for z in (-.5,2.5)],[1,0,0],.216,.5,['P1','M2'],'4 No.12 upper tab-to-purlin web screws (A)','A',True)
        a.front_axes=(1,2);a.section_axis=1;a.section_at=run/2;a.dim(start,end,'Brace workline length','A' if hr else 'S',offset=25)
        note('Source 30 in CFS brace length retained. A: local brace angle and end tabs fit the shown receiving members; all added attachment groups are labelled A.')

    elif family=='test_roof_hanger':
        gp=pick(('girder_truss',));rp=pick(('truss_chord',));gd=effective(p,gp);rd=effective(p,rp)
        face=max(c['offset'][0] for c in p[gp].get('components',[{'offset':[0,0]}]))
        a.member('M1',gp,[0,-22,-gd/2],[0,22,-gd/2],y=(1,0,0),basis='A',description='Receiving four-ply girder chord '+gp)
        a.member('M2',rp,[face+.3,0,-rd/2],[face+28,0,-rd/2],basis='A',description='Supported head-roof truss chord '+rp)
        a.box('BACK',[face+.1,-3,-rd],[.125,6,rd],'A','Hanger back plate 1/8 in')
        a.box('SEAT',[face+.1,-3,-rd-.125],[12,6,.125],'A','Hanger seat 1/8 in')
        fast('FB',grid(12,3,(rd-2)/3,1.5,origin=(face,-1.5,-rd+1),along=(0,1,0)),[1,0,0],.25,.3,['M1','BACK'],'12 No.14 hanger-back screws to girder chord (A)','A',True)
        for i,yy in enumerate((-2.125,2)):
            lab='SIDE'+str(i);a.box(lab,[face+.1,yy,-rd],[12,.125,rd],'A','Hanger side plate 1/8 in')
            fast('F'+str(i),grid(6,2,1.5,3,origin=(face+2,yy,-rd+1)),[0,1,0],.25,.3,['M2',lab],'6 No.14 per side to supported chord (A)','A',True)
            a.weld('W'+str(i),[face+.1,yy,-rd],[face+12.1,yy,-rd],['SEAT',lab],.125,basis='A',description='A: continuous hanger seat-to-side weld')
            a.weld('WB'+str(i),[face+.1,yy,-rd],[face+.1,yy,0],['BACK',lab],.125,basis='A',description='A: continuous hanger back-to-side weld')
        a.section_axis=0;a.section_at=face+5;a.dim([face+.1,0,-rd],[face+12.1,0,-rd],'12 in hanger seat (A)','A',offset=-35)
        note('Actual head-roof heel to girder-chord occurrence at Grid G. A: fabricated hanger and fastener arrangement; source/delegated roof reactions remain unverified test inputs.')

    elif family=='test_roof_truss':
        point=c['point'];extent=[max(abs(q[i]-point[i]) for m in ms for q in m['axis']) for i in (0,1)];horizontal=0 if extent[0]>=extent[1] else 1;other=1-horizontal
        def local(q):return [q[horizontal]-point[horizontal],q[other]-point[other],q[2]-point[2]]
        ends=[]
        for i,m in enumerate(ms):
            aa,bb=[local(q) for q in m['axis']];far=max((aa,bb),key=lambda q:sum(v*v for v in q));v=unit(far);far=mul(v,min(24,math.sqrt(sum(t*t for t in far))))
            ly=m['local_y'];local_y=[ly[horizontal],ly[other],ly[2]]
            a.member('M'+str(i+1),m['profile_id'],[0,0,0],far,y=local_y,basis='A',description=m['kind'].replace('_',' ')+' '+m['profile_id'])
            ends.append((i+1,v,m))
        if len(ends)<2:raise ValueError('Truss node has no adjoining chord/web')
        # Mitred ends share a workpoint but do not occupy the same steel volume.
        from .assembly_scene import clip_part
        bolt_starts={}
        for n,v,m in ends:
            part=next(q for q in a.parts if q['id']=='M'+str(n))
            across=[-v[2],0,v[0]];bolt_start=5
            for _,other,_ in ends:
                delta=sub(v,other)
                if math.sqrt(sum(x*x for x in delta))>.01:
                    normal=unit(delta);clip_part(part,normal,.125)
                    along=sum(x*y for x,y in zip(normal,v));crossing=abs(sum(x*y for x,y in zip(normal,across)))
                    bolt_start=max(bolt_start,(.75*crossing+.75)/max(along,.01))
            bolt_starts[n]=math.ceil(bolt_start*2)/2
        # One node plate for EVERY actual load-carrying web plane, including all
        # four girder plies. Plate offsets are fitted to the thickest joined web.
        planes={}
        for _,_,m in ends:
            for yy,sign,t in web_faces(p,m['profile_id']):
                centre=round(yy-sign*t/2,5)
                old=planes.get((centre,sign),0);planes[centre,sign]=max(old,t)
        for face,((centre,sign),thick) in enumerate(sorted(planes.items())):
            yy=centre+sign*thick/2+(-.125 if sign<0 else 0)
            coords=[(-4,-4),(4,-4),(-4,4),(4,4)]
            for n,v,_ in ends:
                across=[-v[2],0,v[0]]
                coords.extend((q[0],q[2]) for q in [add(mul(v,bolt_starts[n]+5),mul(across,3)),add(mul(v,bolt_starts[n]+5),mul(across,-3))])
            coords=sorted(set(coords));lower=[];upper=[]
            def turn(o,b,d):return (b[0]-o[0])*(d[1]-o[1])-(b[1]-o[1])*(d[0]-o[0])
            for q in coords:
                while len(lower)>1 and turn(lower[-2],lower[-1],q)<=0:lower.pop()
                lower.append(q)
            for q in reversed(coords):
                while len(upper)>1 and turn(upper[-2],upper[-1],q)<=0:upper.pop()
                upper.append(q)
            label='P'+str(face+1);a.polygon(label,[[x,yy,z] for x,z in lower[:-1]+upper[:-1]],.125,basis='A',description='1/8 in continuous node gusset, A boundary')
            for n,v,m in ends:
                matches=[t for at,ss,t in web_faces(p,m['profile_id']) if abs(at-ss*t/2-centre)<.01]
                if not matches:continue
                across=[-v[2],0,v[0]];pts=[add(mul(v,bolt_starts[n]+r*1.5),add(mul(across,s),[0,yy,0])) for r in range(3) for s in (-.75,.75)]
                if sign>0:pts=[add(q,[0,.125,0]) for q in pts]
                fast(f'F{face+1}-{n}',pts,[0,-sign,0],.25,.125+thick,['M'+str(n),label],'6 No.14 per actual web ply at this member end (A)','A',True)
        direction=ends[0][1];a.section_axis=0 if abs(direction[0])>.1 else 2;a.section_at=direction[a.section_axis]*8
        note('The node includes actual adjoining members and every built-up web ply. A: 1/8 in gussets, six No.14 per web ply, mitre fit with 1/4 in nominal gap, and matching paired/four-ply webs. No supplier capacity approval is inferred.')

    elif family in ('cfs_delegated_truss_heel_clip','hr_truss_node','hr_stmf_node'):
        cp=pick(('truss_chord','girder_truss','valley_truss'),default_c());wp=pick(('truss_web',),default_c());tp=channel(p,'ASSEMBLY-TRUSS-TRACK',6,2,.1017,0)
        a.member('M1',cp,[0,0,0],[35,0,0],basis='A',description='Bottom chord '+cp)
        a.member('M2',cp,[0,0,0],[35,0,8.75],basis='A',description='Top chord '+cp)
        a.member('M3',wp,[12,0,0],[24,0,6],basis='A',description='Web '+wp)
        a.member('M4',tp,[-3,-14,-3],[-3,14,-3],y=(0,0,1),description='Bearing wall top track')
        for i,yy in enumerate((-.25,.125)):
            label='P'+str(i);a.polygon(label,[[-2,yy,-3],[18,yy,-3],[24,yy,9],[0,yy,6]],.125,basis='A',description='Truss node gusset 1/8 in; A outline')
            for k,(mid,z) in enumerate((('M1',-1),('M2',3),('M3',2))):
                pts=grid(6,3,1.5,1.5,origin=(4+k*5,yy,z))
                fast(f'F{i}{k}',pts,[0,1,0],.25,.35,[mid,label],'6 No.14 per face; 12 total per attached member (A)','A',True)
        labels=clip(a,'HEEL',[-1,0,-3],5,2,.0566)
        fast('FH1',grid(4,2,1,1,origin=(0,0,-1)),[0,1,0],.19,.15,['M1',labels[0]],'4 No.10 heel-clip screws to truss','S',True)
        fast('FH2',grid(4,2,1,1,origin=(-1,1,-2),along=(0,1,0)),[1,0,0],.19,.15,['M4',labels[1]],'4 No.10 heel-clip screws to track','S',True)
        a.section_axis=0;a.section_at=8;a.dim([0,0,-4],[18,0,-4],'Gusset length (A)','A',offset=-30)
        note('A: internal truss gussets and member-end screw layout are test details. Heel clip retains source 4+4 screw groups. Delegated capacity/reactions are not converted into verified design.')

    elif family=='test_guard' and subtype=='rail-joint':
        rp=pid;pp=next((m['profile_id'] for m in model['members'] if m['kind']=='guard_post'),rp)
        a.member('M1',pp,[0,0,-20],[0,0,0],basis='A',description='Guard post '+pp)
        a.member('M2',rp,[-20,0,1],[20,0,1],basis='A',description='Top rail '+rp)
        a.weld('W1',[-1,-1,0],[1,-1,0],['M1','M2'],.1875,basis='A',description='A: 3/16 in fillet all around post/rail interface')
        a.section_axis=0;a.section_at=0
        note('Guard height 42 in above finished floor; post spacing 4 ft maximum. Welded rail/post joint is A test geometry, without new guard-load verification.')

    elif family=='sill_anchor_group':
        tp=channel(p,'ASSEMBLY-SILL97',6,1.25,.1017,0);sp=next((m['profile_id'] for m in model['members'] if m['kind']=='stud'),default_c())
        d=findnum(r'\d+\s*x\s*'+NUMBER+r'\s*in',text,.875);n=int(findnum(r'(\d+)\s*x',text,6));length=48
        a.member('M1',tp,[-24,0,0],[24,0,0],y=(0,0,1));a.member('M2',sp,[0,0,.1017],[0,0,18])
        a.box('CONC',[-28,-8,-10],[56,16,10],'A','Foundation context',kind='concrete')
        for i,x in enumerate((-18,18)):
            a.box('P'+str(i),[x-1.5,-1.5,.1017],[3,3,.25],'S','3 x 3 x 1/4 in anchor plate washer')
            fast('F'+str(i),[[x,0,-7]],[0,0,1],d,7+.3517,['M1','P'+str(i),'CONC'],f'{d:g} in F1554 Gr36 anchor; 7 in effective embedment','S')
        a.section_axis=0;a.section_at=18;a.dim([-24,0,0],[-18,0,0],'6 in end offset (A)','A',offset=-30);note(f'S: {n} anchors per FULL braced bay, diameter {d:g} in. This end-zone extract shows the end-offset arrangement; distribute the remaining anchors along the scheduled bay, retaining bay-end tie rods separately.')

    else:
        raise ValueError('No assembled detail recipe for '+family+' / '+subtype)

    result=a.result();result.update(family=family,subtype=subtype,source_record_ids=c.get('design_record_ids',[]),source_text=text,
        representative_occurrence=c['id'],building_point=c['point'],source_member_ids=c['member_ids'],level=level,
        coordinate_note='Local assembly axes X/Y horizontal, Z up; profiles and design parameters from the referenced occurrence. A marks authored fit/layout geometry.',source_context=context)
    return result
