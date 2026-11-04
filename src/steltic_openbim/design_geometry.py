"""Drawing geometry, marks and references for adopted fictional design scenarios."""
from __future__ import annotations
import copy
from collections import defaultdict
import math
from pathlib import Path
import json

from .design_scenarios import SCENARIOS, available_scenario
from .drawing_workflow import fingerprint
from .drawing_pdf import source_openings
from .pilots.model import add,sub,mul,dot,unit,cross


def length(member):
    return math.dist(*member['axis'])


def interval_in_rectangle(a,b,lo,hi,axes):
    """Open-interior intersection; a line on an opening edge is retained."""
    enter,leave=0.,1.
    for i in axes:
        d=b[i]-a[i]
        if abs(d)<1e-9:
            if not lo[i]+1e-6<a[i]<hi[i]-1e-6: return None
        else:
            u,v=(lo[i]-a[i])/d,(hi[i]-a[i])/d
            enter=max(enter,min(u,v));leave=min(leave,max(u,v))
    return (enter,leave) if leave-enter>1e-6 else None


def build_model(package,state):
    from .review_cases import CASES,build_model as build_review
    if state['design_scenario']['id'] in CASES:return build_review(package,state)
    pilot=state['design_scenario']['id']; spec=SCENARIOS[pilot]
    if available_scenario(package)!=pilot or state['design_scenario']['answers_sha256']!=fingerprint(spec['answers']):
        raise ValueError('Design test inputs do not match their source-bound scenario')
    ph=package['physical']; profiles={p['id']:copy.deepcopy(p) for p in ph['profiles']}
    catalog=json.loads(Path(__file__).with_name('pilots').joinpath('catalog.json').read_text())
    members=copy.deepcopy(ph['members']); panels=copy.deepcopy(ph['panels'])
    joints={j['id']:copy.deepcopy(j) for j in ph['joints']}
    connections=copy.deepcopy(ph['connections']); changes=[]
    for member in members: member.update(basis='S',source_member_id=member['id'])

    def profile(pid):
        if pid not in profiles: profiles[pid]=copy.deepcopy(catalog[pid]);profiles[pid]['id']=pid
        return pid

    def custom(pid,family,dimensions,**extra):
        profiles.setdefault(pid,dict(id=pid,family=family,dimensions=dimensions,status='declared',basis='A',**extra))
        return pid

    def pair(section,n=2):
        profile(section)
        return custom(f'TEST-{n}x{section}','built_up',{},components=[{'profile_id':section,'offset':[(i-(n-1)/2)*4,0],'rotation_deg':180 if i%2 else 0} for i in range(n)])

    def cfs(pid,d,b,t):
        return custom(pid,'channel',dict(d=d,b=b,t=t,lip=.625,r=1.5*t))

    def tube(pid,h,b,t): return custom(pid,'rhs',dict(h=h,b=b,t=t))

    def new_member(mid,a,b,pid,kind,level,assumption,detail,local_y=None):
        if math.dist(a,b)<.01: return None
        axis=unit(sub(b,a))
        if local_y is None: local_y=[1,0,0] if abs(axis[2])>.99 else unit(cross([0,0,1],axis))
        member=dict(id=mid,axis=[list(a),list(b)],profile_id=pid,kind=kind,level=level,basis='A',assumption_id=assumption,
            material_id='assumed_test_material',local_y=local_y,end_offsets=[[0,0,0],[0,0,0]],design_record_ids=[],source_member_id=None)
        members.append(member)
        for side,p in zip(('start','end'),(a,b)):
            jid=mid+':'+side
            joints[jid]=dict(id=jid,point=list(p),member_ends=[{'member_id':mid,'end':side}],attachments=[])
            connections.append(dict(id='TEST-C:'+jid,joint_id=jid,detail_ref={'id':detail},design_record_ids=[],parts=[],basis='A',assumption_id=assumption))
        return member

    # Reconcile nominal CFS floor datums with a single geometric transformation.
    if pilot=='cfs8':
        old=[0,107.256,120,223.26,236.004,339.264,352.008,468.012,537.012]
        new=[0,107.25,120,223.25,236,339.25,352,468,537]
        def zmap(z):
            for i in range(len(old)-1):
                if old[i]<=z<=old[i+1]: return new[i]+(z-old[i])*(new[i+1]-new[i])/(old[i+1]-old[i])
            return z+(new[-1]-old[-1] if z>old[-1] else 0)
        def point(p): return [p[0],p[1],zmap(p[2])]
        for m in members:
            m['axis']=[point(p) for p in m['axis']]
            if m['kind']=='squash_block': m['axis'][1][2]=m['axis'][0][2]+12
            m['datum_basis']='CFS8-FLOOR'
        for panel in panels: panel['vertices']=[point(p) for p in panel['vertices']]
        for joint in joints.values(): joint['point']=point(joint['point'])
        for connection in connections:
            for part in connection.get('parts',[]):
                if 'origin' in part['geometry']: part['geometry']['origin']=point(part['geometry']['origin'])
        changes.append({'kind':'datum_reconciliation','assumption_id':'CFS8-FLOOR','old_in':old,'adopted_in':new})

    features=copy.deepcopy(state['features'])+source_openings(package)
    # Clip affected secondary members; do not hide full members behind symbols.
    original_members={m['id']:copy.deepcopy(m) for m in members}; replacements={}
    for f in state['features']:
        axes=["xyz".index(c) for c in f['plane']];normal=next(i for i in range(3) if i not in axes)
        lo=[f[k]*12 for k in ('x_ft','y_ft','z_ft')];hi=lo.copy()
        hi[axes[0]]+=f['width_ft']*12;hi[axes[1]]+=f['height_ft']*12
        allowed={'joist'} if f['plane']=='xy' else {'stud','stud_bridging','bridging_anchor','bottom_track','girt'}
        after=[]
        for m in members:
            a,b=m['axis']
            if m['kind'] not in allowed or max(abs(a[normal]-lo[normal]),abs(b[normal]-lo[normal]))>15:
                after.append(m);continue
            cut=interval_in_rectangle(a,b,lo,hi,axes)
            if cut is None: after.append(m);continue
            t0,t1=cut; retained=[]
            for part,(u,v) in enumerate(((0,t0),(t1,1))):
                if (v-u)*length(m)<.5: continue
                segment=copy.deepcopy(m);segment['id']=m['id']+f'.{f["id"]}{part}'
                segment['axis']=[add(a,mul(sub(b,a),t)) for t in (u,v)]
                segment.update(basis='A',assumption_id=f['query_id'],opening_id=f['id'],end_offsets=[[0,0,0],[0,0,0]])
                retained.append(segment);after.append(segment)
            changes.append({'kind':'opening_trim','member_id':m['id'],'opening_id':f['id'],'retained_ids':[x['id'] for x in retained]})
        members=after

    if pilot=='hr22':
        angle=custom('TEST-L3X3X1/4','angle',dict(h=3,b=3,t=.25))
        for c in list(connections):
            family=c['detail_ref']['id'];joint=joints[c['joint_id']]
            if family=='hr_required_bottom_flange_brace':
                mid=joint.get('attachments',[{}])[0].get('member_id')
                member=original_members.get(mid)
                if member:
                    p=joint['point'];d=profiles[member['profile_id']]['dimensions']['d'];v=member['local_y']
                    new_member('TEST-KICK-'+c['id'],add(p,[0,0,-d]),add(p,mul(v,36)),angle,'flange_kicker',member['level'],'HR-DETAILS',family)
            if family=='hr_column_base' and any(p['id']=='end-plate' for p in c['parts']):
                x,y,_=joint['point']
                for side,(dx,dy,axis) in enumerate(((0,-17,[0,-1,0]),(0,17,[0,1,0]),(-9,0,[-1,0,0]),(9,0,[1,0,0]))):
                    for row in range(12):
                        c['parts'].append(dict(id=f'TEST-stud-{side}-{row}',kind='headed_stud',basis='A',assumption_id='HR-BASE-STUDS',
                            geometry=dict(type='cylinder',origin=[x+dx,y+dy,-90+row*6],axis=axis,radius=.4375,length=5)))
            related=[e['member_id'] for e in joint.get('member_ends',[])]+[a['member_id'] for a in joint.get('attachments',[])]
            if family=='hr_infill_shear_plate_cope' and any(original_members.get(mid,{}).get('profile_id')=='W18X40' for mid in related):
                c.update(parts=[],basis='A',assumption_id='HR-PENTHOUSE',detail_ref={'id':'test_floor_opening'})

    if pilot=='cfs16':
        angle=profile('L2x2x1/8')
        def roof(x):return 240+.2*min(x,720-x)
        for m in members:
            if m['kind']=='purlin_nested':
                x=m['axis'][0][0];normal=unit([-.2 if x<360 else .2,0,1])
                m['axis']=[add(p,mul(normal,.025)) for p in m['axis']]
                m.update(basis='A',assumption_id='CFS16-SECONDARY-SETOUT',nesting='1/8 in assumed normal separation')
        for frame in range(23):
            y=frame*150;sign=-1 if frame==22 else 1
            for x in (0,360,720):
                normal=unit([-.2 if x<=360 else .2,0,1])
                for pairno in (-1,1):
                    a=add([x,y+pairno*3.1875,roof(x)],mul(normal,-7));b=add(a,add(mul(normal,18),[0,sign*24,0]))
                    new_member(f'TEST-KICK-{frame}-{x}-{pairno}',a,b,angle,'flange_kicker',1,'CFS16-SECONDARY-SETOUT','cfs_scheduled_flange_kicker')
        for m in list(members):
            if m['kind']!='endwall_post':continue
            a=m['axis'][1];px=round(a[0]/60)*60;normal=unit([-.2 if px<=360 else .2,0,1]);b=add([px,a[1],roof(px)],mul(normal,11))
            # Jamb tops are farther from a purlin; their exact 31.5 in workline is explicit.
            target=max(30,math.ceil(math.dist(a,b)*2)/2);b[1]+= (1 if a[1]==0 else -1)*math.sqrt(max(0,target**2-math.dist(a,b)**2))
            new_member('TEST-TOP-'+m['id'],a,b,angle,'flange_kicker',1,'CFS16-SECONDARY-SETOUT','cfs_scheduled_flange_kicker')
        for c in connections:
            if c['detail_ref']['id']=='cfs_portal_pinned_base':
                x,y,_=joints[c['joint_id']]['point']
                for i,(dx,dy) in enumerate(((-5,-6),(5,-6),(5,6),(-5,6))):
                    c['parts'].append(dict(id=f'TEST-anchor-{i}',kind='anchor',basis='A',assumption_id='CFS16-BRACKETS',
                        geometry=dict(type='cylinder',origin=[x+dx,y+dy,-10],axis=[0,0,1],radius=.375,length=14)))

    # Explicit headers/jambs/trimmers at every newly located opening.
    for f in state['features']:
        x,y,z=[f[k]*12 for k in ('x_ft','y_ft','z_ft')];w,h=f['width_ft']*12,f['height_ft']*12
        level=f['level'];q=f['query_id'];pid=f['id']
        if f['plane']=='xy':
            if pilot=='hr22': shape=profile('W18X40'); half=profiles[shape]['dimensions']['bf']/2;zz=z-profiles[shape]['dimensions']['d']/2
            else:
                section=cfs('TEST-1200S300-97',12,3,.1017);shape=pair(section);half=3;zz=z-6.75
            for suffix,a,b in [('W',[x-half,y-half,zz],[x-half,y+h+half,zz]),('E',[x+w+half,y-half,zz],[x+w+half,y+h+half,zz]),
                               ('S',[x-half,y-half,zz],[x+w+half,y-half,zz]),('N',[x-half,y+h+half,zz],[x+w+half,y+h+half,zz])]:
                new_member('TEST-'+pid+'-'+suffix,a,b,shape,'opening_trimmer',level,q,'test_floor_opening')
            # Header extensions tie the frame to existing bearing lines.
            if pilot=='hr22':
                supports=[math.floor(x/120)*120,math.ceil((x+w)/120)*120]
                for sy in (y-half,y+h+half):
                    for aa,bb in ((supports[0],x-half),(x+w+half,supports[1])):
                        new_member(f'TEST-{pid}-EXT-{sy:g}-{aa:g}',[aa,sy,zz],[bb,sy,zz],shape,'opening_header',level,q,'test_floor_opening')
            else:
                if y>=1008:
                    supports=[math.floor(x/168)*168,math.ceil((x+w)/168)*168]
                    for sy in (y-half,y+h+half):
                        for aa,bb in ((supports[0],x-half),(x+w+half,supports[1])):
                            new_member(f'TEST-{pid}-EXT-{sy:g}-{aa:g}',[aa,sy,zz],[bb,sy,zz],shape,'opening_header',level,q,'test_floor_opening')
                else:
                    supports=[math.floor(y/168)*168,math.ceil((y+h)/168)*168]
                    for sx in (x-half,x+w+half):
                        for aa,bb in ((supports[0],y-half),(y+h+half,supports[1])):
                            new_member(f'TEST-{pid}-EXT-{sx:g}-{aa:g}',[sx,aa,zz],[sx,bb,zz],shape,'opening_header',level,q,'test_floor_opening')
        else:
            if pilot=='cfs16':
                jamb=pair('800S250-97');header=profile('HSS6X4X3/16');depth=6;half=4
            else:
                jamb=pair('600S200-68');header=pair(cfs('TEST-800S200-97',8,2,.1017));depth=8;half=3
            def loc(u,v): return [x+u,y,z+v] if f['plane']=='xz' else [x,y+u,z+v]
            floor_z=0 if pilot=='cfs16' else (0,120,236,352)[level-1]
            for side,u in [('L',-half),('R',w+half)]:
                new_member('TEST-'+pid+'-J'+side,loc(u,floor_z-z),loc(u,h+depth),jamb,'opening_jamb',level,q,'test_wall_opening',local_y=[0,1,0] if f['plane']=='xz' else [1,0,0])
            new_member('TEST-'+pid+'-H',loc(-half,h+depth/2),loc(w+half,h+depth/2),header,'opening_header',level,q,'test_wall_opening')
            if 'window' in f['kind']:
                new_member('TEST-'+pid+'-S',loc(-half,-depth/2),loc(w+half,-depth/2),header,'opening_sill',level,q,'test_wall_opening')

    if pilot=='cfs8':
        # Replace ordinary end studs with three-stud intersection packs.
        tracks=[m for m in members if m['kind']=='top_track']
        corner_points=defaultdict(list)
        for m in tracks:
            for p in m['axis']:corner_points[(m['level'],round(p[0],3),round(p[1],3))].append((p,m))
        for (level,x,y),at in corner_points.items():
            p,track=at[0];floor_z=(0,120,236,352)[level-1]
            shape=profile('600S200-68')
            for i,dx in enumerate((-2.5,2.5)):
                new_member(f'TEST-CORNER-{level}-{x}-{y}-{i}',[x+dx,y,floor_z],[x+dx,y,p[2]],shape,'intersection_stud',level,'CFS8-STUD-SETOUT','cfs_stud')
        # Source anchor count/diameter remains, with adopted 6 in end offsets.
        for c in connections:
            if c['detail_ref']['id']!='sill_anchor_group':continue
            anchors=[p for p in c['parts'] if p['kind']=='anchor'];n=len(anchors)
            if n<2:continue
            start=anchors[0]['geometry']['origin'];end=anchors[-1]['geometry']['origin'];axis=unit(sub(end,start))
            # Initial source centres were spaced at (k+1/2)/n across the full bay.
            step=math.dist(start,end)/(n-1);a=add(start,mul(axis,-step/2+6));b=add(end,mul(axis,step/2-6))
            for i,p in enumerate(anchors):
                old_origin=p['geometry']['origin'];p['geometry']['origin']=add(a,mul(sub(b,a),i/(n-1)));p.update(basis='A',assumption_id='CFS8-DETAILS')
                washer=next((w for w in c['parts'] if w['id']==f'washer-{i}'),None)
                if washer:washer['geometry']['origin']=add(washer['geometry']['origin'],sub(p['geometry']['origin'],old_origin))
        # New exterior support and guard geometry, all explicitly assumed.
        beam=tube('TEST-HSS8X4X1/4',8,4,.25);post=tube('TEST-HSS6X6X1/4',6,6,.25);rail=tube('TEST-HSS2X2X1/8',2,2,.125)
        for y in range(0,1009,168):
            new_member(f'TEST-WPOST-{y}',[492,y,0],[492,y,352],post,'walkway_post',1,'CFS8-WALKWAY-EDGE','test_walkway_support')
            panels.append(dict(id=f'TEST-PAD-{y}',kind='assumed_footing',level=0,basis='A',assumption_id='CFS8-WALKWAY-EDGE',
                vertices=[[456,y-36,-30],[528,y-36,-30],[528,y+36,-30],[456,y+36,-30]],thickness_in=30))
        for m in members:
            if m['kind']=='walkway_joist':
                target=(120,236,352)[m['level']-1]-4.75
                m['axis']=[[p[0],p[1],target] for p in m['axis']]
                m.update(basis='A',assumption_id='CFS8-FLOOR')
        for level,z in enumerate((120,236,352),1):
            # Joist and edge beam top flanges are aligned 3/4 in below FFL.
            for y in range(0,1008,168): new_member(f'TEST-WBEAM-{level}-{y}',[492,y,z-4.75],[492,y+168,z-4.75],beam,'walkway_edge_beam',level,'CFS8-WALKWAY-EDGE','test_walkway_support')
            new_member(f'TEST-RAIL-{level}',[492,0,z+42],[492,1008,z+42],rail,'guard_rail',level,'CFS8-WALKWAY-EDGE','test_guard')
            for y in range(0,1009,48): new_member(f'TEST-GUARD-{level}-{y}',[492,y,z],[492,y,z+42],rail,'guard_post',level,'CFS8-WALKWAY-EDGE','test_guard')
        # Fink trusses plus a girder and valley overframing; distinct physical members.
        chord=pair('600S162-68');web=profile('600S162-54');girder=pair(cfs('TEST-800S200-97',8,2,.1017),4)
        def truss(label,plane,station,start,span,base,rise,shape=chord,kind='truss_chord'):
            def p(u,v): return [station,start+u,base+v] if plane=='yz' else [start+u,station,base+v]
            nodes=[p(0,0),p(span/4,0),p(span/2,0),p(3*span/4,0),p(span,0),p(span/4,rise/2),p(span/2,rise),p(3*span/4,rise/2)]
            edges=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,4)]
            out_of_plane=[1,0,0] if plane=='yz' else [0,1,0]
            web_pack=pair(web,4 if kind=='girder_truss' else 2)
            for n,(a,b) in enumerate(edges): new_member(label+'-C'+str(n),nodes[a],nodes[b],shape,kind,4,'CFS8-ROOF-INTERFACE','test_roof_truss',local_y=out_of_plane)
            for n,(a,b) in enumerate([(1,5),(1,6),(2,6),(3,6),(3,7)]): new_member(label+'-W'+str(n),nodes[a],nodes[b],web_pack,'truss_web',4,'CFS8-ROOF-INTERFACE','test_roof_truss',local_y=out_of_plane)
        for x in range(0,1681,24): truss(f'TEST-HEAD-{x}','yz',x,1008,552,468,69)
        for y in range(0,1008,24): truss(f'TEST-STEM-{y}','xz',y,564,552,468,69)
        truss('TEST-GIRDER','xz',1008,564,552,468,69,girder,'girder_truss')
        for y in range(1032,1284,24):
            base=468+(y-1008)/4;rise=537-base;span=rise*8
            truss(f'TEST-VALLEY-{y}','xz',y,840-span/2,span,base,rise,chord,'valley_truss')
        panels=[p for p in panels if p['kind']!='truss_envelope']

    # Remap original end connections onto the retained portions of trimmed members.
    member_lookup={m['id']:m for m in members};source_segments=defaultdict(list)
    for m in members:
        if m.get('source_member_id'): source_segments[m['source_member_id']].append(m)
    kept_connections=[]
    for connection in connections:
        j=joints[connection['joint_id']]; related=[]
        for end in j.get('member_ends',[]):
            mid=end['member_id']
            if mid in member_lookup: related.append(mid);continue
            original=original_members.get(mid)
            if original:
                oldpoint=original['axis'][0 if end['end']=='start' else 1]
                related += [m['id'] for m in source_segments[mid] if any(math.dist(oldpoint,p)<.02 for p in m['axis'])]
        for attachment in j.get('attachments',[]):
            if attachment['member_id'] in member_lookup: related.append(attachment['member_id'])
        if not related: continue
        connection.update(member_ids=sorted(set(related)),point=j['point'])
        kept_connections.append(connection)
    connections=kept_connections
    # Every new cut end receives an explicit opening-frame interface reference.
    for m in members:
        if m.get('opening_id'):
            for end,p in enumerate(m['axis']):
                connections.append(dict(id=f'TRIM-C:{m["id"]}:{end}',point=p,member_ids=[m['id']],detail_ref={'id':'test_floor_opening' if m['kind']=='joist' else 'test_wall_opening'},
                    design_record_ids=[],parts=[],basis='A',assumption_id=m['assumption_id']))

    families=sorted({c['detail_ref']['id'] for c in connections})
    details={family:{'id':f'D{i+1:02}','family':family,'number':i%4+1,'sheet':f'S{501+i//4}',
        'reference':f'{i%4+1}/S{501+i//4}'} for i,family in enumerate(families)}
    member_connections=defaultdict(set)
    for c in connections:
        detail=details[c['detail_ref']['id']];c['drawing_ref']=detail['reference']
        for mid in c['member_ids']:member_connections[mid].add(detail['reference'])
    # Repeated marks mean identical profile/kind/workline length and joint references.
    groups=defaultdict(list)
    for m in members:
        key=(m['kind'],m['profile_id'],round(length(m)*16)/16,m['basis'],tuple(sorted(member_connections[m['id']])))
        groups[key].append(m)
    schedule=[]
    prefixes={'column':'C','stud':'S','chord':'CH','joist':'J','purlin':'P','girt':'G','rafter':'R','moment_beam':'M','girder':'B','infill':'B'}
    counts=defaultdict(int)
    for (kind,pid,reference_length,basis,refs),group in sorted(groups.items()):
        prefix=prefixes.get(kind,'A' if basis=='A' else 'T');counts[prefix]+=1;mark=f'{prefix}{counts[prefix]:03}'
        for m in group:m.update(mark=mark,connection_refs=list(refs))
        schedule.append(dict(mark=mark,kind=kind,profile_id=pid,length_in=reference_length,count=len(group),basis=basis,
            levels=sorted({m['level'] for m in group}),connection_refs=list(refs),member_ids=[m['id'] for m in group]))
    grids=copy.deepcopy(spec['grids'])
    grids['x']=[g for g in grids['x'] if g[0]!='W']
    for axis in grids:grids[axis].sort(key=lambda g:g[1])
    return dict(schema='steltic.design_drawing_model',version=1,pilot=pilot,title=spec['title'],fictional=True,
        source_sha256=fingerprint(package),scenario=copy.deepcopy(state['design_scenario']),
        members=members,profiles=list(profiles.values()),materials=copy.deepcopy(ph['materials'])+[
            dict(id='assumed_test_material',basis='A',specification='Fictional supplementary framing. Geometry and connection assumptions only; no newly verified strength or capacity.')],
        panels=panels,openings=features,connections=connections,
        member_schedule=schedule,details=list(details.values()),grids=grids,levels=spec['levels'],changes=changes,
        assumptions=[dict(id=r['id'],answer=r['resolution'] if r.get('confirmed') else 'TBD - resolve query: '+r['proposal'],
                          basis='A - user-authorized fictional test input' if r.get('confirmed') else 'Provisional information request',
                          confirmed=bool(r.get('confirmed'))) for r in state['requests']])
