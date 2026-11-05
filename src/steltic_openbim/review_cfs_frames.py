"""Four distinct portal/canopy cases, including their scheduled secondary systems."""
import math,re
from .review_cfs import section,frange,opening
from .review_model import add,sub,mul,unit,MIL

def build(b):
    cfg=b.cfg;key=b.key;canopy=key=='cfs26';length=cfg['length_ft']*12;spacing=cfg['spacing_ft']*12
    frames=[i*spacing for i in range(cfg['n_frames'])];span=1032 if key=='cfs17' else cfg['span_ft']*12
    roof=[(0,216),(300,270),(600,216),(816,252),(1032,216)] if key=='cfs17' else ([( -48,163.2),(408,208.8)] if canopy else [(0,cfg['eave_ft']*12),(span/2,cfg['apex_ft']*12),(span,cfg['eave_ft']*12)])
    def rz(x):
        i=next((i for i,(a,d) in enumerate(zip(roof,roof[1:])) if a[0]-.01<=x<=d[0]+.01),0)
        a,d=roof[i:i+2];return a[1]+(d[1]-a[1])*(x-a[0])/(d[0]-a[0])
    schedules={r['id']:r for r in b.raw['schedules']}
    def rec(name):return b.record('schedules','sched-'+name)
    def pid(label):return b.profile(label,gap=.375,pair_spacing=6.375)
    col=pid(cfg['col_section']);raf=pid(cfg['raf_section']);primary={}
    for i,y in enumerate(frames):
        for j,x in enumerate((0,span)):
            m=b.member(f'F{i+1}-C{j}',col,'column',[x,y,0],[x,y,rz(x)],1,'S',local_y=[0,1,0]);primary[i,'C',j]=m
            b.connection(m['id']+'-BASE','review_portal_base',m['axis'][0],[m],[b.record('anchorage','base-anchor')],parameters={'fixed':canopy or key=='cfs30'})
        for j,(a,d) in enumerate(zip(roof,roof[1:])):
            m=b.member(f'F{i+1}-R{j}',raf,'rafter',[a[0],y,a[1]],[d[0],y,d[1]],1,'S',local_y=[0,1,0]);primary[i,'R',j]=m
        for j,x in enumerate((0,span)):
            r=primary[i,'R',0 if j==0 else len(roof)-2];c=primary[i,'C',j]
            b.connection(f'F{i+1}-K{j}','review_canopy_knee' if canopy else 'review_portal_joint',[x,y,rz(x)],[c,r],[b.record('connections','conn-knee')],parameters={'joint':'knee','across':4 if key=='cfs19' else 3,'rows':4})
        for j,(x,z) in enumerate(roof[1:-1],1):
            valley=key=='cfs17' and x==600;prop=valley or key=='cfs30';ms=[primary[i,'R',j-1],primary[i,'R',j]]
            if prop:
                pp=b.member(f'F{i+1}-PROP','HSS6X6X1/4' if valley else 'HSS8X8X1/4','prop',[x,y,0],[x,y,z-13],1,'A');ms.append(pp)
                b.connection(pp['id']+'-BASE','review_portal_base',pp['axis'][0],[pp],[b.record('anchorage','base-anchor')],parameters={'interior':True})
            b.connection(f'F{i+1}-J{j}','review_portal_joint',[x,y,z],ms,[b.record('connections','conn-valley' if valley else 'conn-apex')],parameters={'joint':'valley' if valley else 'apex','across':3 if key=='cfs19' else 4,'rows':4,'prop':prop,'hanger':key=='cfs19'})
        if canopy:
            for j,x in enumerate((0,span)):
                end=x+(48 if j==0 else -48);m=b.member(f'F{i+1}-KB{j}',cfg['knee_braces']['section'],'knee_brace',[x,y,rz(x)-36],[end,y,rz(end)],1,'S',local_y=[0,1,0]);b.ends(m,'review_canopy_brace',[b.record('connections','conn-knee-brace')],parameters={'count':4,'diameter':.625})
    def support_at(x,y):
        i=min(range(len(frames)),key=lambda j:abs(frames[j]-y));j=next((j for j,(a,d) in enumerate(zip(roof,roof[1:])) if a[0]-.1<=x<=d[0]+.1),0);return primary[i,'R',j]
    # Separate source section zones and actual lap extensions.
    xs=set(x for x,z in roof);ps=cfg.get('purlin_spacing_ft',5)*12
    for a,d in zip(roof,roof[1:]):xs.update(frange(a[0],d[0]+.1,ps))
    if key=='cfs30':xs.update((140,280,560,700))
    if key=='cfs17':xs.update((150,300,450,744,888))
    lap=15 if key=='cfs17' else (30 if key=='cfs19' else 24)
    for x in sorted(xs):
        for j,(ya,yb) in enumerate(zip(frames,frames[1:])):
            label='1200Z300-118' if canopy else ('1000Z250-68' if key=='cfs19' else ('800Z250-68' if key=='cfs30' or min(abs(x-t) for t in (300,600,816))<204 else '800Z250-54'))
            if key=='cfs30':label='800Z250-'+('118' if 6<=j<=10 else ('97' if abs(x-span/2)<=276 else '68'))
            pp=pid(label);z=rz(x)+7+b.depth(pp)/2+.125
            a=ya-(48 if canopy and j==0 else lap if j else 0);d=yb+(48 if canopy and j==len(frames)-2 else lap if j<len(frames)-2 else 0)
            m=b.member(f'P-{x:g}-{j}',pp,'purlin',[x,a,z],[x,d,z],1,'A',records=[rec('purlin')],local_y=[-1 if j%2 else 1,0,0],lap_in=lap)
            nested=not canopy and j in (0,len(frames)-2) and x in ([150,300,450,744,888] if key=='cfs17' else [120,240,360] if key=='cfs19' else [140,280,560,700])
            if nested:
                n=b.member(m['id']+'-NEST',pp,'purlin',[x+.2,a,z],[x+.2,d,z],1,'A',records=[rec('endwall')],local_y=m['local_y'],full_length_nested=True)
                for y in (ya,yb):b.connection(n['id']+str(y),'review_secondary',[x,y,z],[n,m,support_at(x,y)],[rec('purlin'),rec('endwall')],parameters={'lap':lap,'kind':'fully nested end-bay purlin','end':y in (0,length),'full_length_nested':True})
            for end,y in enumerate((ya,yb)):
                b.connection(m['id']+str(end),'review_secondary',[x,y,z],[m,support_at(x,y)],[rec('purlin')],parameters={'lap':0 if canopy else lap,'kind':'purlin','thermal':key=='cfs30','end':y in (0,length)})
            if key=='cfs30':b.connection(m['id']+'-SKIN','review_thermal_clip',[x,(ya+yb)/2,z+b.depth(pp)/2],[m],[rec('purlin')],parameters={'travel':.75,'fixed':j==8})
    # Eave struts and wall girts. Canopy deliberately has no enclosing walls.
    for side,x in enumerate((0,span)):
        strut='2X1000S250-97' if canopy else ('2X1200S350-97' if key=='cfs30' else '800S250-97' if key=='cfs19' else '800S250-68')
        for j,(ya,yb) in enumerate(zip(frames,frames[1:])):
            m=b.member(f'ES-{side}-{j}',strut,'eave_strut',[x,ya,rz(x)],[x,yb,rz(x)],1,'A',records=[rec('strap')]);b.ends(m,'review_secondary',[rec('strap')],parameters={'kind':'eave_strut','lap':0})
            if not canopy:
                gs=78 if key=='cfs30' else 84 if key=='cfs19' else 72
                for z in frange(30 if key=='cfs30' else 24 if key=='cfs17' else gs,rz(x),gs):
                    label='800Z250-'+('97' if key=='cfs19' and j in (0,len(frames)-2) else '68' if key=='cfs19' else '54')
                    gp=pid(label);outside=x+(-1 if side==0 else 1)*(7+b.depth(gp)/2+.125)
                    m=b.member(f'G-{side}-{j}-{z}',gp,'girt',[outside,ya-(lap if j else 0),z],[outside,yb+(lap if j<len(frames)-2 else 0),z],1,'A',local_y=[0,0,1],records=[rec('girt')]);b.ends(m,'review_secondary',[rec('girt')],parameters={'kind':'girt','lap':lap})
    # Actual scheduled strap planes and nodes; no diaphragm substituted for them.
    braced=range(6,10) if key=='cfs30' else (0,len(frames)-2)
    def strap(label,aa,dd,width,mil,count,supports,record):
        sp=b.custom(f'STRAP-{width}X{mil}','flat',dict(width=width,thickness=MIL[mil]),basis='S');m=b.member(label,sp,'strap',aa,dd,1,'A',records=[record]);b.ends(m,'review_cfs_strap',[record],parameters={'screws':count,'screw_size':14 if key=='cfs30' else 12,'host_profile':supports,'stainless':key=='cfs30'});return m
    for j in braced:
        ya,yb=frames[j:j+2]
        if not canopy:
            for side,x in enumerate((0,span)):
                for flip in (False,True):strap(f'SIDE-X-{j}-{side}-{flip}',[x,ya,rz(x) if flip else 0],[x,yb,0 if flip else rz(x)],5 if key in ('cfs17','cfs30') else 3.5,118 if key=='cfs30' else 97,44 if key=='cfs30' else 27 if key=='cfs17' else 19,col,rec('strap'))
        brace_roof=[(0,rz(0)),(span,rz(span))] if canopy else roof
        for r,(a,d) in enumerate(zip(brace_roof,brace_roof[1:])):
            count=3 if canopy else 2 if key=='cfs19' else 3
            for panel in range(count):
                x0=a[0]+(d[0]-a[0])*panel/count;x1=a[0]+(d[0]-a[0])*(panel+1)/count
                for flip in (False,True):strap(f'ROOF-X-{j}-{r}-{panel}-{flip}',[x0 if flip else x1,ya,rz(x0 if flip else x1)+7],[x1 if flip else x0,yb,rz(x1 if flip else x0)+7],3.5 if canopy or key=='cfs30' else 4 if key=='cfs17' else 3,97 if canopy or key in ('cfs17','cfs30') else 68,19 if canopy else 25 if key=='cfs30' else 22 if key=='cfs17' else 12,raf,rec('strap'))
    if canopy:canopy_extras(b,frames,span,rz,rec)
    else:endwalls(b,frames,span,rz,rec,support_at,key)
    if key=='cfs17':
        for j,(ya,yb) in enumerate(zip(frames,frames[1:])):
            m=b.member(f'VALLEY-STRUT-{j}','2X800S250-68','eave_strut',[600,ya,216],[600,yb,216],1,'A',records=[rec('strap')]);b.ends(m,'review_secondary',[rec('strap')],parameters={'kind':'valley_strut','lap':0})
            if j%2==0:
                for flip in (False,True):strap(f'VALLEY-X-{j}-{flip}',[600,ya,216 if flip else 0],[600,yb,0 if flip else 216],3,68,12,b.profile('HSS6X6X1/4'),rec('strap'))
    flange_braces(b,frames,rec)
    if key=='cfs19':monorail(b,frames,span,rec)
    if key=='cfs30':cold_storage(b,frames,span,rz,rec)
    b.levels=[(0,'BASE',0),(1,'LOW EAVE',min(rz(0),rz(span))),(2,'ROOF HIGH WORKPOINT',max(z for x,z in roof))]
    b.grids={'x':[(chr(65+i),x) for i,x in enumerate(sorted({0,span}|{x for x,z in roof if 0<=x<=span}))],'y':[(str(i+1),y) for i,y in enumerate(frames)]}
    b.views.extend([dict(title='TRANSVERSE FRAME',direction='X',station_in=y,range_in=[roof[0][0],roof[-1][0]]) for y in (frames[0],frames[len(frames)//2])])
    b.note('FRAME-FIT','A: workline-to-face set-out uses the actual source section depths and explicitly spaced channel plies. Bracket envelopes, member end cuts and secondary offsets are dimensioned assumptions. Source bolt counts, grades and plate thicknesses govern the detailed variants. End-wall post locations and door set-out use the completed schedules where available.')

def endwalls(b,frames,span,rz,rec,support_at,key):
    xs=[150,300,450,744,888] if key=='cfs17' else [120,240,360] if key=='cfs19' else [140,280,560,700]
    # Source Ex17 post stations are adopted from its unequal-span panel pattern.
    for end,y in enumerate((frames[0],frames[-1])):
        for j,x in enumerate(xs):
            label='2X1000S250-97' if key=='cfs30' or key=='cfs19' and j==1 else '2X800S250-97' if key=='cfs19' else '2X800S250-68' if j==1 else '2X800S200-68'
            m=b.member(f'END-{end}-POST-{j}',label,'endwall_post',[x,y,0],[x,y,rz(x)-8],1,'A',local_y=[1,0,0],records=[rec('endwall')])
            b.connection(m['id']+'B','review_endpost_base',m['axis'][0],[m],[rec('endwall')]);b.connection(m['id']+'T','review_endpost_top',m['axis'][1],[m,support_at(x,y)],[rec('endwall')],parameters={'vertical_slip':1})
        stations=sorted({0,span,*xs,600 if key=='cfs17' else span/2})
        for j,(a,d) in enumerate(zip(stations,stations[1:])):
            for z in frange(30 if key=='cfs30' else 24 if key=='cfs17' else 84, min(rz(a),rz(d)),78 if key=='cfs30' else 72 if key=='cfs17' else 84):
                label='600Z250-54' if key=='cfs30' else '800Z250-54';m=b.member(f'END-G-{end}-{j}-{z}',label,'girt',[a,y,z],[d,y,z],1,'A',local_y=[0,0,1],records=[rec('endwall')]);b.ends(m,'review_secondary',[rec('endwall')],parameters={'kind':'endwall_girt','lap':0})
        # A personnel opening in a clear outer post bay; all crossing girts cut below.
        u=(stations[0]+stations[1])/2-21;opening(b,f'ACCESS-{end}',0,y,u,0,42,84,1)
    if key=='cfs17':
        for j in (2,5,8,11,14):
            y=frames[j]+9.6;b.openings.append(dict(id=f'OH-{j+1}',kind='overhead door',plane='yz',x_ft=0,y_ft=y/12,z_ft=0,width_ft=10.4,height_ft=14,level=1,basis='S',query_id=b.key.upper()+'-OPENINGS',confirmed=True))
            m=b.member(f'DOOR-HEADER-{j+1}','HSS4X4X1/8','opening_header',[0,y,170],[0,y+124.8,170],1,'A',records=[rec('endwall')]);b.ends(m,'review_cfs_beam_clip',[rec('endwall')],parameters={'count':2,'diameter':.5})
    else:opening(b,'OH-1',0,frames[0],span/2-72,0,144,168,1)
    # Cut girts at clear openings, preserving end clips on both new pieces.
    for m in list(b.members):
        if m['kind']!='girt':continue
        a,d=m['axis'];axis=0 if abs(a[0]-d[0])>1 else 1;normal=1-axis;intervals=[(a[axis],d[axis])]
        for f in b.openings:
            if f['plane']!=('xz' if axis==0 else 'yz') or abs(a[normal]-f['xy'[normal]+'_ft']*12)>14:continue
            if not f['z_ft']*12<a[2]<(f['z_ft']+f['height_ft'])*12:continue
            lo=f['xy'[axis]+'_ft']*12-3;hi=lo+f['width_ft']*12+6;new=[]
            for x,z in intervals:
                if hi<=x or lo>=z:new.append((x,z))
                else:
                    if lo>x:new.append((x,lo))
                    if hi<z:new.append((hi,z))
            intervals=new
        if intervals==[(a[axis],d[axis])]:continue
        b.members.remove(m);b.connections[:]=[c for c in b.connections if m['id'] not in c['member_ids']]
        for j,(lo,hi) in enumerate(intervals):
            if hi-lo<1:continue
            aa=a.copy();dd=d.copy();aa[axis]=lo;dd[axis]=hi
            n=b.member(m['id']+'CUT'+str(j),m['profile_id'],'girt',aa,dd,1,'A',local_y=m['local_y'],records=m['design_record_ids']);b.ends(n,'review_secondary',m['design_record_ids'],parameters={'kind':'girt','lap':0})

def canopy_extras(b,frames,span,rz,rec):
    for side,x in enumerate((0,span)):
        for i,y in enumerate(frames):
            for sign in (-1,1):
                end=y+sign*72
                if end<0 or end>frames[-1]:continue
                m=b.member(f'LONG-KB-{side}-{i}-{sign}','2X600S162-54','knee_brace',[x,y,rz(x)-48],[x,end,rz(x)],1,'A');b.ends(m,'review_canopy_brace',[rec('strap')],parameters={'count':2,'diameter':.5})
    for x in (-48,span+48):
        for i,y in enumerate(frames):
            m=b.member(f'FASCIA-POST-{x}-{i}','2X600S200-68','fascia_post',[x,y,rz(x)],[x,y,rz(x)+36],1,'A');b.ends(m,'review_cfs_beam_clip',[rec('fascia')])
        for j,(a,d) in enumerate(zip(frames,frames[1:])):
            for h in (6,30):
                m=b.member(f'FASCIA-RAIL-{x}-{j}-{h}','800S200-54','fascia_rail',[x,a,rz(x)+h],[x,d,rz(x)+h],1,'A');b.ends(m,'review_cfs_beam_clip',[rec('fascia')])

def monorail(b,frames,span,rec):
    x=span/2;run='S10X25.4';wp='W12X26';b.profile(run);b.profile(wp)
    for j,(a,d) in enumerate(zip(frames,frames[1:])):
        m=b.member(f'HANGER-BEAM-{j}',wp,'hanger_beam',[x,a,300],[x,d,300],1,'A',records=[rec('crane')]);b.ends(m,'review_beam',[rec('crane')],parameters={'clip_angles':True})
    for i,y in enumerate(frange(0,frames[-1]+.1,120)):
        base=204+b.depth(run);top=300-b.depth(wp)/2 if i%2 else 304
        rods=[]
        for side in (-1,1):
            pid=b.custom('ROD7/8','round',{'d':.875},basis='S');rods.append(b.member(f'HANGER-{i}-{side}',pid,'hanger_rod',[x+side*4.5,y,base],[x+side*4.5,y,top],1,'A',records=[rec('crane')]))
        b.connection(f'HANGER-{i}-LOW','review_hanger_plate',[x,y,base],rods,[rec('crane')],parameters={'beam_profile':run,'gauge':2.75,'top':False,'tapered':True})
        b.connection(f'HANGER-{i}-HIGH','review_hanger_plate' if i%2 else 'review_hanger_pin',[x,y,top],rods,[rec('crane')],parameters={'beam_profile':wp,'gauge':3.5,'top':True})
        if i%2==0:
            for side in (-1,1):
                m=b.member(f'SWAY-{i}-{side}','L2X2X3/16','sway_brace',[x,y,base+6],[x+side*72,y,300],1,'A');b.ends(m,'review_angle_clip',[rec('crane')],parameters={'count':2,'diameter':.5})
    for j,(a,d) in enumerate(zip(frames,frames[1:])):
        m=b.member(f'MONORAIL-{j}',run,'monorail',[x,a,204+b.depth(run)/2],[x,d,204+b.depth(run)/2],1,'A',records=[rec('crane')]);b.ends(m,'review_hanger_plate',[rec('crane')],parameters={'beam_profile':run,'gauge':2.75,'top':False,'tapered':True})
    b.note('MONORAIL','S: lower-flange runway datum 17 ft; hanger spacing 10 ft; W12x26 intermediate hanger beams, S10x25.4 runway, 7/8 in rods and source pretensioned flange attachments. A: local rod cut lengths and sway-brace fit. Trolley and proprietary clevis geometry remain explicitly illustrative.')

def cold_storage(b,frames,span,rz,rec):
    # Four source evaporator hanger lines and a dimensioned fictional platform.
    for j,x in enumerate((180,660,348,492)):
        y=frames[7+j%3];m=b.member(f'EVAP-BEAM-{j}','2X800S250-118','hanger_beam',[x,y,rz(x)-20],[x,y+frames[1],rz(x)-20],1,'A');b.ends(m,'review_cfs_beam_clip',[rec('evaporator')],parameters={'count':2,'diameter':.5})
        for side in (-1,1):
            rp=b.custom('ROD1/2','round',{'d':.5},basis='S');rod=b.member(f'EVAP-ROD-{j}-{side}',rp,'hanger_rod',[x+side*3,y+60,rz(x)-60],[x+side*3,y+60,rz(x)-16],1,'A');b.ends(rod,'review_hanger_plate',[rec('evaporator')],parameters={'beam_profile':m['profile_id'],'diameter':.5,'gauge':3,'top':True})
    for i,x in enumerate((300,540)):
        for j,y in enumerate((frames[8],frames[9])):
            m=b.member(f'PLATFORM-LEG-{i}-{j}','HSS4X4X1/4','platform_leg',[x,y,rz(x)+7],[x,y,408],1,'A');b.ends(m,'review_platform_seat',[rec('platform')],parameters={'rafter_profile':b.profile(b.cfg['raf_section'],gap=.375,pair_spacing=6.375)})
    for j,y in enumerate((frames[8],frames[9])):
        m=b.member(f'PLATFORM-BEAM-{j}','W8X18','platform_beam',[300,y,404],[540,y,404],1,'A');b.ends(m,'review_beam',parameters={'moment':False})
    for x in frange(300,541,24):
        m=b.member(f'PLATFORM-J-{x}','800S200-68','platform_joist',[x,frames[8],404],[x,frames[9],404],1,'A');b.ends(m,'review_cfs_joist',parameters={'clip':True,'screws':4,'screw_size':10})
    # Vestibule 12 ft deep at the south end, source 16/14 ft bearing levels.
    led=b.member('VEST-LEDGER','HSS8X4X1/4','ledger',[0,0,192],[span,0,192],1,'A',records=[rec('endwall')]);b.ends(led,'review_ledger',[rec('endwall')])
    for x in frange(0,span+.1,48):
        m=b.member(f'VEST-R-{x}','1000S250-97','rafter',[x,-144,168],[x,0,192],1,'A');b.ends(m,'review_cfs_beam_clip',[rec('endwall')],parameters={'count':2,'diameter':.5})
        s=b.member(f'VEST-S-{x}','600S200-68','stud',[x,-144,0],[x,-144,168],1,'A');b.ends(s,'cfs_stud')
    # The 70 ft front wall is not a multiple of the 4 ft regular stud spacing.
    # Its actual end-bay straps require both end posts, not a nearby substitute.
    existing_stations={m['axis'][0][0] for m in b.members if m['id'].startswith('VEST-S-')}
    for x in sorted({span-48,span}-existing_stations):
        s=b.member(f'VEST-S-{x}','600S200-68','stud',[x,-144,0],[x,-144,168],1,'A',records=[rec('endwall')])
        b.ends(s,'cfs_stud')
    b.note('VEST-END-STUDS','A: vestibule end-bay chord stations include the front-wall corner and the point 4 ft from that corner, in addition to regular 4 ft studs. These actual members receive the source end-bay straps; no remote profile or nonexistent track substitutes for them.')
    for x in (0,span):
        m=b.member(f'VEST-RETURN-{x}','HSS4X4X3/16','girt',[x,-144,168],[x,0,192],1,'A');b.ends(m,'review_cfs_beam_clip',[rec('endwall')])
        for y in (-96,-48):
            m=b.member(f'VEST-STUD-{x}-{y}','800S200-68','stud',[x,y,0],[x,y,192+y/6],1,'A');b.ends(m,'cfs_stud')
    opening(b,'VEST-ACCESS',0,-144,span/2-21,0,42,84,1)
    # Cut the front-wall stud crossing the adopted access opening.
    for m in b.members:
        if m['id'].startswith('VEST-S-') and span/2-24<m['axis'][0][0]<span/2+24:
            m['axis'][0][2]=92
            for c in b.connections:
                if c['member_ids']==[m['id']] and c['point'][2]==0:c['point'][2]=92
    sp=b.custom('VEST-STRAP-3X68','flat',dict(width=3,thickness=.0713),basis='S: source vestibule end-bay strap')
    for bay,(lo,hi) in enumerate(((0,48),(span-48,span))):
        for flip in (False,True):
            m=b.member(f'VEST-X-{bay}-{flip}',sp,'strap',[lo,-146,168 if flip else 0],[hi,-146,0 if flip else 168],1,'A',records=[rec('endwall')])
            b.ends(m,'review_cfs_strap',[rec('endwall')],parameters={'screws':16,'screw_size':14,'stainless':True,'host_profile':'600S200-68'})
    for axis,pos,lo,hi,z in ((0,-144,0,span,84),(1,0,-144,0,90),(1,span,-144,0,90)):
        aa=[lo,pos,z] if axis==0 else [pos,lo,z];dd=[hi,pos,z] if axis==0 else [pos,hi,z]
        m=b.member(f'VEST-BRIDGE-{axis}-{pos}','150U050-54','bridging',aa,dd,1,'A',records=[rec('endwall')]);b.ends(m,'cfs_stud_bridging')
    b.note('COLD-STORAGE','S: cold structural steel with separate exterior skin; central braced zone retained. Thermal clips have +/-3/4 in travel. A: platform 20 ft x one frame bay at elevation 34 ft, coordinated evaporator locations and vestibule access. Source low-temperature material/fastener and fatigue requirements remain attached to the record register.')

def flange_braces(b,frames,rec):
    if b.key=='cfs26':return
    secondaries=[m for m in b.members if m['kind']=='purlin'];rafters=[m for m in b.members if m['kind']=='rafter']
    for j,m in enumerate(secondaries):
        x=m['axis'][0][0];z=m['axis'][0][2];ys=[y for y in frames if m['axis'][0][1]-.1<=y<=m['axis'][1][1]+.1]
        for y in ys:
            # One installed kicker at each purlin/frame interface; adjacent bay shares it.
            label=f'KICKER-{x:g}-{y:g}'
            if any(mm['id']==label+'-1' for mm in b.members):continue
            r=next((r for r in rafters if abs(r['axis'][0][1]-y)<.1 and min(q[0] for q in r['axis'])-.1<=x<=max(q[0] for q in r['axis'])+.1),None)
            if not r:continue
            aa,dd=r['axis'];rz=aa[2]+(dd[2]-aa[2])*(x-aa[0])/(dd[0]-aa[0]);lower=rz-b.depth(r['profile_id'])/2;rise=z-lower;run=math.sqrt(max(1,900-rise*rise));sign=-1 if y==frames[-1] else 1
            for side in (-1,1):
                # Both source rafter flange sides; end frames turn the outer brace inward.
                yy=y+side*6.375;direction=side if y not in (frames[0],frames[-1]) else sign
                q=b.member(label+str(side),'L2X2X1/8','flange_kicker',[x,yy,lower],[x,yy+direction*run,z],1,'A',records=[rec('strap')],local_y=[1,0,0]);b.connection(q['id'],'review_kicker',q['axis'][0],[q,r,m],[rec('strap')],parameters={'lower_count':3 if b.key=='cfs17' else 6 if b.key=='cfs30' else 4,'upper_count':6 if b.key=='cfs30' else 4,'stainless':b.key=='cfs30'})
    # Source end-wall post kickers carry reactions to the doubled end-bay purlins.
    for m in list(b.members):
        if m['kind']!='endwall_post':continue
        x,y,z=m['axis'][1];pp=min(secondaries,key=lambda q:abs(q['axis'][0][0]-x)+min(abs(q['axis'][0][1]-y),abs(q['axis'][1][1]-y)))
        end=[pp['axis'][0][0],y+(18 if y==frames[0] else -18),pp['axis'][0][2]]
        count={'cfs17':4,'cfs19':5,'cfs30':6}.get(b.key,2)
        q=b.member(m['id']+'-K','L2X2X1/8','flange_kicker',[x,y,z],end,1,'A',local_y=[1,0,0]);b.connection(q['id'],'review_kicker',q['axis'][0],[q,m,pp],[rec('endwall')],parameters={'lower_count':count,'upper_count':count,'post_top':True,'stainless':b.key=='cfs30'})
