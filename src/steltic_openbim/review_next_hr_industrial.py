"""Source equipment-platform and gable-hall geometry, with explicit test answers."""
import math
from .review_model import add,sub,mul,unit


def equipment(b,levels):
    from .review_hr import nearest
    def angle(mid,pid,a,d,k,rid,count=2):
        m=b.member(mid,pid,'plan_brace',a,d,k,records=[b.record('connections',rid)],local_y=[0,0,1])
        for end,point in enumerate((a,d)):
            support=nearest(b,point,('beam','girder','equipment_beam','column'))
            col=nearest(b,point,('column',))
            quadrant=col is not None and math.dist(point[:2],col['axis'][0][:2])<1
            hosts=[col] if quadrant else ([support] if support else [])
            if quadrant:
                for direction in (0,1):
                    beam=next((q for q in b.members if q['kind'] in ('beam','girder','moment_beam') and abs(q['axis'][1][direction]-q['axis'][0][direction])>1 and any(math.dist(v,point)<1 for v in q['axis'])),None)
                    if beam:hosts.append(beam)
            b.connection(mid+':'+str(end),'review_plan_angle',point,[m]+hosts,[b.record('connections',rid)],parameters={'count':count,'joint':'column_quadrant' if quadrant else 'leg_point'})
        return m
    rid='conn-diaphragm-plan-bracing-L3X3X1/4'
    for k,z in enumerate(levels[1:],1):
        for i in range(3):
            for j in range(2):
                x,y=i*240,j*240
                first=angle(f'PLAN-{k}-{i}-{j}-A','L3X3X1/4',[x,y,z],[x+240,y+240,z],k,rid)
                second=angle(f'PLAN-{k}-{i}-{j}-B','L3X3X1/4',[x,y+240,z+.25],[x+240,y,z+.25],k,rid)
                b.connection(f'PLAN-CROSS-{k}-{i}-{j}','review_angle_crossing',[x+120,y+120,z],[first,second],[b.record('connections',rid)])
    # Source vessel and skid support beams are not in the building analysis axes.
    offset=48/math.sqrt(2)
    specs=[('VESSEL',3,[(360+sg*offset,240+sy*offset) for sg in (-1,1) for sy in (-1,1)],'W18X60','L4X4X1/2',3),
           ('SKID',2,[(x,y) for x in (264,456) for y in (300,420)],'W16X26','L3X3X1/4',2)]
    for label,k,points,pid,diag,count in specs:
        z=levels[k];beams={}
        for j,y in enumerate(sorted({p[1] for p in points})):
            m=b.member(f'{label}-BEAM-{j}',pid,'equipment_beam',[240,y,z],[480,y,z],k,records=[b.record('connections',f'conn-{label.lower()}-beam-{pid}')]);m['end_offsets']=[[0,0,-b.depth(pid)/2]]*2;beams[y]=m
            for end,point in enumerate(m['axis']):
                support=nearest(b,point,('beam','girder'))
                b.connection(m['id']+':'+str(end),'review_beam',point,[m]+([support] if support else []),[b.record('connections',f'conn-{label.lower()}-beam-{pid}')])
        for j,(x,y) in enumerate(points):
            target=[240 if x<360 else 480,240 if label=='VESSEL' or y<360 else 480,z]
            angle(f'{label}-DIAG-{j}',diag,[x,y,z],target,k,f'conn-{label.lower()}-leg-diagonal-{diag}',count)
            leg=b.member(f'{label}-LEG-{j}','HSS4X4X1/4','equipment_leg',[x,y,z+.75],[x,y,z+48],k,'A')
            b.connection(leg['id']+'-FOOT','review_equipment_foot',[x,y,z],[leg,beams[y]],parameters={'equipment':label})
        if label=='VESSEL':
            for j,x in enumerate(sorted({p[0] for p in points})):
                angle('VESSEL-TIE-'+str(j),'L3X3X1/4',[x,240-offset,z],[x,240+offset,z],k,'conn-vessel-leg-tie-L3X3X1/4')
    # No pump positions/footprints were designed. Adopt three small frames over tier-1 girders.
    for j,x in enumerate((120,360,600)):
        z=levels[1];host=nearest(b,[x,240,z],('beam','girder'))
        for side in (-1,1):
            leg=b.member(f'PUMP-{j}-FOOT-{side}','HSS4X4X1/4','equipment_leg',[x+side*12,240,z+.75],[x+side*12,240,z+18],1,'A')
            b.connection(leg['id'],'review_equipment_foot',[x+side*12,240,z],[leg,host],parameters={'equipment':'PUMP'})
    b.note('EQUIPMENT','S: tier plan bracing in every bay; vessel beams and 8 ft leg circle; skid beams and leg load paths. A: supplier legs/foot plates/bolts, three 5 kip pump positions on the tier-1 centre girder, and local angle fit. The source 60/40/15 kip equipment loads and delegated attachment checks are retained; no equipment capacity is asserted by these drawings.')


def gable(b):
    from .review_hr import nearest,connect_primary
    from .review_cfs import simple_truss
    b.levels=[(0,'BASE',0),(1,'OFFICE ROOF TOS',192),(2,'HALL EAVE',312),(3,'HALL RIDGE',432)]
    # Use saved source axes for the office and column segments, remapping mean roof height.
    for src in b.package['physical']['members']:
        pid=src['profile_id'];kind='column' if src['kind'] in ('col','column') else src['kind']
        if pid in ('W27X94','ROD1'):
            b.excluded.append(dict(id=src['id'],profile_id=pid,reason='Mean-height analysis rafter / single tension idealization replaced by sloping rafters / physical crossed rods'));continue
        axis=[[p[0],p[1],312 if abs(p[2]-372)<.01 else p[2]] for p in src['axis']]
        k=1 if max(p[2] for p in axis)<=192 else 2
        m=b.member(src['id'],pid,kind,*axis,k,local_y=src.get('local_y'),source=src['id'])
    connect_primary(b,[0,192,312])
    # Replace source column continuity interpretations with one-piece columns.
    b.connections[:]=[c for c in b.connections if c['detail_ref']['id'] not in ('review_splice','review_column_continuity')]
    lookup={m['id']:m for m in b.members}
    for con in b.connections:
        ms=[lookup[i] for i in con['member_ids']]
        if con['detail_ref']['id']=='review_base' and ms[0]['profile_id']=='W8X31':
            con['design_record_ids'].append(b.record('connections','conn-base-lateral_col-W8X31'))
        if con['detail_ref']['id']=='review_beam' and con['point'][2]==192 and con['point'][1]==480:
            con['design_record_ids'] += [b.record('connections','conn-lateral_col-W24X84'),b.record('connections','collector-irregularity-lines')]
    for m in b.members:
        if m['kind']=='column' and m['profile_id']=='W8X31':
            point=max(m['axis'],key=lambda q:q[2]);support=nearest(b,point,('beam','girder'))
            b.connection(m['id']+'-CAP','review_column_cap',point,[m]+([support] if support else []),[b.record('connections','conn-gravity_col-W8X31'),b.record('connections','conn-lateral_col-W8X31')],parameters={'bearing_girder':True})
    roof=lambda y:312+min(y-480,1440-y)/4
    for i,x in enumerate(range(0,2401,300)):
        halves=[]
        for side,(y0,y1) in enumerate(((480,960),(1440,960))):
            m=b.member(f'RAFTER-{i}-{side}','W27X94','rafter',[x,y0,roof(y0)],[x,y1,roof(y1)],2,records=[b.record('members','roof-W27X94')],local_y=[1,0,0]);halves.append(m)
            col=nearest(b,[x,y0,312],('column',))
            b.connection(m['id']+'-KNEE','review_hr_gable_knee',[x,y0,312],[m,col],[b.record('connections','conn-roof-W27X94')])
        b.connection(f'RIDGE-{i}','review_hr_gable_ridge',[x,960,432],halves,parameters={'slope':.25})
    # Source delegated secondary products: explicit fictional sections and fit.
    for x in range(0,2400,300):
        for y in range(480,1441,60):
            m=b.member(f'PURLIN-{x}-{y}','1200Z300-97','purlin',[x,y,roof(y)+6],[x+300,y,roof(y)+6],2,'A');b.ends(m,'review_angle_clip',parameters={'count':2,'diameter':.625})
        for y in (480,1440):
            for z in (84,168,252):
                if y==480 and 600<=x<1800 and z<192:continue
                m=b.member(f'GIRT-{x}-{y}-{z}','1000Z250-97','girt',[x,y,z],[x+300,y,z],2,'A');b.ends(m,'review_angle_clip',parameters={'count':2,'diameter':.625})
    for x in (0,2400):
        for y in range(480,1440,240):
            for z in (84,168,252):
                m=b.member(f'END-GIRT-{x}-{y}-{z}','1000Z250-97','girt',[x,y,z],[x,y+240,z],2,'A');b.ends(m,'review_angle_clip',parameters={'count':2,'diameter':.625})
        for y in (720,960,1200):
            m=b.member(f'END-POST-{x}-{y}','HSS8X8X1/4','endwall_post',[x,y,0],[x,y,roof(y)],2,'A');b.ends(m,'review_sliding_post')
    for x in range(600,1801,60):simple_truss(b,'OFFICE-JOIST-'+str(x),1,x,0,480,168,22,1,'2X362S162-97','2X250S162-68',48,flat=True)
    for i,x in enumerate(range(600,1800,300)):b.panel('OFFICE-ROOF-'+str(i),'roof',[[x,0,192],[x+300,0,192],[x+300,480,192],[x,480,192]],1.5,1,'S')
    for side,(lo,hi) in enumerate(((480,960),(960,1440))):b.panel('HALL-ROOF-'+str(side),'roof',[[0,lo,roof(lo)],[2400,lo,roof(lo)],[2400,hi,roof(hi)],[0,hi,roof(hi)]],.05,2,'A')
    def rod_pair(mid,a,d,c,e,level):
        for j,(aa,bb) in enumerate(((a,d),(c,e))):
            m=b.member(mid+'-'+str(j),'ROD1','rod_brace',aa,bb,level,records=[b.record('members','brace-ROD1')])
            for end,point in enumerate((aa,bb)):
                host=nearest(b,point,('column','rafter','beam'))
                b.connection(m['id']+':'+str(end),'review_rod_clevis',point,[m]+([host] if host else []),[b.record('connections','conn-brace-ROD1')])
            b.connection(m['id']+'-TURNBUCKLE','review_rod_clevis',[(u+v)/2 for u,v in zip(aa,bb)],[m],parameters={'joint':'turnbuckle'})
    for y in (480,1440):
        for x in (300,1800):rod_pair(f'WALL-X-{x}-{y}',[x,y,0],[x+300,y,312],[x+300,y,0],[x,y,312],2)
    rod_pair('OFFICE-X',[900,0,0],[1200,0,192],[1200,0,0],[900,0,192],1)
    for x in (0,2100):
        for y in (480,720,960,1200):rod_pair(f'ROOF-X-{x}-{y}',[x,y,roof(y)],[x+300,y+240,roof(y+240)],[x+300,y,roof(y)],[x,y+240,roof(y+240)],2)
    # Paired flange braces, one on each side of the web at each prescribed station.
    for i,x in enumerate(range(0,2401,300)):
        for side,y0 in enumerate((480,1440)):
            sign=1 if side==0 else -1
            for j,run in enumerate((0,120/math.sqrt(1.0625),240/math.sqrt(1.0625),360/math.sqrt(1.0625),480/math.sqrt(1.0625))):
                y=y0+sign*run;z=roof(y);host=next(m for m in b.members if m['id']==f'RAFTER-{i}-{side}')
                for s in (-1,1):
                    aa=[x,y,z-13.5];bb=[x+s*29.56,y,z+16.06];m=b.member(f'RAFTER-FB-{i}-{side}-{j}-{s}','L2-1/2X2-1/2X1/4','flange_brace',aa,bb,2,'A')
                    b.connection(m['id'],'review_angle_clip',aa,[m,host],[b.record('connections','conn-flange-braces')],parameters={'count':2,'diameter':.75})
            for z in (84,168,252,312):
                host=nearest(b,[x,y0,z],('column',))
                for s in (-1,1):
                    aa=[x,y0+sign*12,z];bb=[x+s*26.73,y0-sign*14.73,z];m=b.member(f'COLUMN-FB-{i}-{side}-{z}-{s}','L2-1/2X2-1/2X1/4','flange_brace',aa,bb,2,'A');b.connection(m['id'],'review_angle_clip',aa,[m,host],[b.record('connections','conn-flange-braces')],parameters={'count':2,'diameter':.75})
    for m in b.members:
        if m['kind'] in ('beam','girder'):m['end_offsets']=[[0,0,-b.depth(m['profile_id'])/2]]*2
    b.grids={'x':[(str(i+1),x) for i,x in enumerate(range(0,2401,300))],'y':[('A',0),('B',480),('R',960),('C',1440)]}
    b.note('GABLE','S: actual 26 ft eaves and 36 ft ridge replace the 31 ft mean-height analysis beam; W27X94 rafters and source end-plate knees retained. S rod crosses and source paired flange braces; A secondary purlin/girt products, office joist internals, endwall posts, ridge splice and clevis/turnbuckle supplier envelopes. Office roof is a roof, not an occupied floor. Adopted geometry does not certify supplier capacity.')


def gable_detail(ctx):
    from .review_assemblies import effective
    from .assembly_scene import clip_part
    a,p=ctx.a,ctx.p;rp='W27X94';rd=effective(p,rp);rw=effective(p,rp,'width');tf=p[rp]['dimensions']['tf'];slope=.25
    if ctx.family=='review_hr_gable_ridge':
        for j,sg in enumerate((-1,1)):
            rafter=a.member('RAFTER'+str(j),rp,[-sg*5,0,1.25],[sg*42,0,-10.5]);clip_part(rafter,[sg,0,0],1);a.box('EP'+str(j),[-1 if sg<0 else 0,-5.5,-rd/2-3.625],[1,11,rd+7.25],'A','A ridge end plate 1 in, source knee arrangement adopted')
            a.weld('WF'+str(j),[sg,-rw/2,rd/2],[sg,rw/2,rd/2],['RAFTER'+str(j),'EP'+str(j)],tf,'CJP',basis='A')
        a.fastener('B1',[[ -1,y,z] for y in (-3.25,3.25) for z in (-rd/2-2,-rd/2+2,rd/2-2,rd/2+2)],[1,0,0],1.25,2,['EP0','EP1'],'A eight 1-1/4 in A490 ridge bolts','A');a.notes.append('A ridge splice: source knee plate/bolt family adopted for this fictional test. Ridge design was not resolved in the completed source. Source roof slopes and rafter profile retained.');a.section_axis=2;a.section_at=0;return
    cp=ctx.select(('column',),ctx.default_w());cd=effective(p,cp);cw=effective(p,cp,'width');ctw=p[cp]['dimensions']['tw'];ctf=p[cp]['dimensions']['tf'];face=cd/2;ep=face+1;top=rd/2+3.625
    a.member('COLUMN',cp,[0,0,-50],[0,0,top]);a.box('CAP',[-cd/2,-cw/2,top],[cd,cw,.5],'S','Source separate 1/2 in cap');a.box('EP',[face,-5.5,-rd/2-3.625],[1,11,rd+7.25],'S','Source 1 x 11 in extended end plate; A vertical fit');rafter=a.member('RAFTER',rp,[ep-6,0,-1.5],[ep+48,0,12]);clip_part(rafter,[1,0,0],ep)
    a.fastener('B1',[[face-ctf,y,z] for y in (-3.25,3.25) for z in (-rd/2-2,-rd/2+2,rd/2-2,rd/2+2)],[1,0,0],1.25,ctf+1,['COLUMN','EP'],'S eight 1-1/4 in A490; A 6.5 in gauge')
    for j,(z,t) in enumerate(((rd/2,.875),(-rd/2,.625))):
        for s in (-1,1):
            name=f'S{j}{s}';y=ctw/2 if s>0 else -ctw/2-4.25;a.box(name,[-cd/2+ctf,y,z-t/2],[cd-2*ctf,4.25,t],'S','Source transverse stiffener; A corner clip envelope');a.weld('WF'+name,[face-ctf,y,z],[face-ctf,y+4.25,z],['COLUMN',name],t,'CJP');a.weld('WW'+name,[-cd/2+ctf,s*ctw/2,z],[face-ctf,s*ctw/2,z],['COLUMN',name],.1875)
    a.box('DOUBLER',[-cd/2+ctf,ctw/2,-rd/2+.3125],[cd-2*ctf,.25,rd-.75],'S','Source 1/4 in web doubler');a.weld('WD',[face-ctf,ctw/2,-rd/2],[face-ctf,ctw/2,rd/2],['COLUMN','DOUBLER'],.25,'CJP')
    for s in (-1,1):a.weld('RF'+str(s),[ep,-rw/2,s*rd/2],[ep,rw/2,s*rd/2],['RAFTER','EP'],tf,'CJP')
    a.weld('RW',[ep,0,-rd/2+tf],[ep,0,rd/2-tf],['RAFTER','EP'],.375);a.dim([face,0,-rd/2-3.625],[face,0,top],'A fitted plate height',basis='A');a.section_axis=2;a.section_at=rd/2
    a.notes.append('S: column projects 3.625 in above the rafter upper flange; separate cap, 7/8 in upper and 5/8 in lower stiffeners, 1/4 in doubler, no haunch. Source 3:12 slope. A local gauge and plate fit; mitre/corner cuts require fabrication development.')
