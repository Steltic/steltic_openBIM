"""SBMF lateral beams, independent gravity roofs and separated office/mezzanine."""
import math,re
from .review_cfs import frange,simple_truss,section,opening
from .review_model import MIL

def build(b):
    office=b.key=='cfs10';length=1200 if office else 2400;width=960 if office else 600;c=b.cfg;cp=b.profile(c['col_section']);single=b.profile('1800S350-118' if office else '1600S350-118')
    bp=b.pack(single,2,'back_to_back',label='SBMF-'+single,gap=b.depth(cp));cols={};frames=list(range(0,length+1,150));roofbase=302 if office else 300
    for i,x in enumerate(frames):
        for side,y in enumerate((0,600)):
            col=b.member(f'FRAME-{i}-C{side}',cp,'column',[x,y,0],[x,y,300],1,'S');cols[i,side]=col;b.connection(col['id']+'B','review_next_portal_base',[x,y,0],[col],[b.record('anchorage','base-anchor')])
        m=b.member(f'FRAME-{i}-BEAM',bp,'moment_beam',[x,-b.depth(cp)/2,288],[x,600+b.depth(cp)/2,288],1,'S',local_y=[1,0,0],records=[b.record('members','frame-raf')])
        for side,y in enumerate((0,600)):b.connection(m['id']+'J'+str(side),'review_sbmf_joint',[x,y,288],[m,cols[i,side]],[b.record('connections','conn-knee')],parameters={'bearing_plates':office})
        # Independent truss restrains the beam flange through vertically slotted struts only.
        face=b.depth(cp)/2
        near=[face+v for v in frange(18,73,18)]
        stations=sorted(set(near+[600-v for v in near]+list(frange(96,505,96))))
        for j,y in enumerate(stations):
            for hand in (-1,1):
                st=b.member(f'FLANGE-STRUT-{i}-{j}-{hand}','362S162-54','flange_strut',[x+hand*b.depth(cp)/2,y,288-b.depth(bp)/2],[x+hand*(b.depth(cp)/2+24),y,288-b.depth(bp)/2],1,'S')
                b.connection(st['id'],'review_sbmf_strut',st['axis'][0],[st,m],[b.record('connections','conn-sbmf-bottom-flange-struts'),b.record('schedules','sched-purlin')],parameters={'vertical_slot':2})
    for side,y in enumerate((0,600)):
        hp='2X1200S250-97' if office and side==0 else '2X1200S300-118' if office else '2X1000S250-97';hr='header-storefront' if office and side==0 else 'header-interior' if office else 'header-eave';headerpid=b.profile(hp,gap=.375)
        for i,(xa,xb) in enumerate(zip(frames,frames[1:])):
            m=b.member(f'HEADER-{side}-{i}',headerpid,'girder',[xa,y,roofbase-b.depth(headerpid)/2],[xb,y,roofbase-b.depth(headerpid)/2],1,'S',records=[b.record('headers',hr)])
            for end,point in enumerate(m['axis']):b.connection(m['id']+str(end),'review_sbmf_header',point,[m,cols[i+end,side]],[b.record('headers',hr),b.record('connections','conn-'+hr+'-to-column')])
            if office and side==0:
                ep=b.pack(b.profile('1600S350-118'),2,'back_to_back',label='SBMF-STOREFRONT',gap=12);ew=b.member(f'EW-BEAM-{i}',ep,'moment_beam',[xa-6,0,246],[xb+6,0,246],1,'S',local_y=[0,1,0],records=[b.record('frames','frame-EW-storefront')])
                for end,x in enumerate((xa,xb)):b.connection(ew['id']+str(end),'review_sbmf_joint',[x,0,246],[ew,cols[i+end,0]],[b.record('frames','frame-EW-storefront')],parameters={'bearing_plates':False,'joint':'storefront'})
                hg=b.member(f'STOREFRONT-GIRT-{i}','2X800S200-68/BOX','girt',[xa,0,192],[xb,0,192],1,'S',local_y=[0,0,1],records=[b.record('framing','girt-storefront-head')]);b.ends(hg,'review_next_secondary',[b.record('framing','girt-storefront-head')],parameters={'kind':'girt','lap':0,'support_bolts':2})
    for x in frange(0,length+.1,48):
        simple_truss(b,f'ROOF-{x}',1,x,0,600,roofbase,12.5 if not office else 0,1,'2X600S162-68','2X362S162-54',60,heel=24 if not office else 36)
        if office:simple_truss(b,f'ROOF-NORTH-{x}',1,x,600,960,roofbase,0,1,'2X600S162-68','2X362S162-54',60,heel=30)
    if office:
        wall(b,'NORTH',0,960,0,1200,0,288,1,'800S200-68','2X800S250-118',[(60,180),(360,480),(720,840),(1020,1140)],3,10,.875,continuous=True)
        # Tier strut/catwalk ledger and source drag struts are discrete members.
        m=b.member('NORTH-TIER','2X600S162-54/BOX','tier_strut',[0,960,144],[1200,960,144],1,'S',records=[b.record('framing','strut-north-tier')]);b.ends(m,'review_next_secondary',[b.record('framing','strut-north-tier')],parameters={'kind':'tier_strut','lap':0,'support_bolts':2})
        for i,x in enumerate(frames):
            m=b.member(f'NORTH-DRAG-{i}','600S162-54','collector',[x,600,roofbase+30],[x,960,roofbase+30],1,'S',records=[b.record('framing','collector-frame-line')]);b.ends(m,'review_next_secondary',[b.record('framing','collector-frame-line')],parameters={'kind':'collector','lap':0,'support_bolts':2})
        catwalk(b,roofbase)
    else:
        for side,y in enumerate((0,600)):
            for j,xa in enumerate((7.5,length-142.5)):
                wall(b,f'SIDE-{side}-{j}',0,y,xa,xa+135,0,288,1,'800S200-54','2X800S200-68',[(xa,xa+135)],3.5,12,.75,continuous=True)
            # Remaining wall stud framing and girts, with columns kept independent of straps.
            for x in frange(150,length-150+.1,16):
                for tier in (0,1):
                    m=b.member(f'SIDE-STUD-{side}-{x}-{tier}','800S200-54','stud',[x,y,tier*144+.1],[x,y,(tier+1)*144-.1],1,'A');b.ends(m,'cfs_stud')
            for i,(xa,xb) in enumerate(zip(frames,frames[1:])):
                for z in (72,144,216):
                    m=b.member(f'SIDE-GIRT-{side}-{i}-{z}','800S200-54','girt',[xa,y,z],[xb,y,z],1,'S');b.ends(m,'review_next_secondary',[b.record('framing','girt-side-walls')],parameters={'kind':'girt','lap':0,'support_bolts':2})
    for end,x in enumerate((0,length)):
        for y in frange(0,width+.1,16) if office else ():
            m=b.member(f'END-STUD-{end}-{y}','800S200-68' if office else '800S200-54','stud',[x,y,0],[x,y,roofbase-1],1,'A');b.connection(m['id']+'B','cfs_stud',m['axis'][0],[m]);b.connection(m['id']+'T','review_sbmf_wall_slide',m['axis'][1],[m],[b.record('framing','stud-end-walls' if office else 'post-end-walls')])
        if not office:
            for y in (150,300,450):
                m=b.member(f'END-POST-{end}-{y}','2X1000S250-97/BOX','endwall_post',[x,y,0],[x,y,288],1,'S',records=[b.record('framing','post-end-walls')]);b.connection(m['id']+'B','review_cfs_post',m['axis'][0],[m],parameters={'slab_thickness':10,'embedment':6});b.connection(m['id']+'T','review_sbmf_wall_slide',m['axis'][1],[m],[b.record('framing','post-end-walls')])
            for y in (0,150,300,450):
                for z in (72,144,216):
                    m=b.member(f'END-GIRT-{end}-{y}-{z}','800S200-54','girt',[x,y,z],[x,y+150,z],1,'S');b.ends(m,'review_next_secondary',[b.record('framing','post-end-walls')],parameters={'kind':'girt','lap':0,'support_bolts':2})
    # Main hall has its own roof level; it must not appear on the office floor plan.
    for m in b.members:m['level']=3
    for w in b.walls:w['level']=3
    for p in b.panels:p['level']=3
    for side,(ya,yb) in enumerate(((0,300),(300,600)) if not office else ((0,600),(600,960))):
        roof_z=lambda y:roofbase+(36 if side==0 else 30) if office else roofbase+24+12.5*(1-abs(2*y/600-1))
        b.panel('MAIN-ROOF-'+str(side),'roof',[[0,ya,roof_z(ya)],[length,ya,roof_z(ya)],[length,yb,roof_z(yb)],[0,yb,roof_z(yb)]],.025,3,'A')
    wing(b,office)
    b.levels=[(0,'BASE',0),(1,'OFFICE L2' if office else 'MEZZ L2',132 if office else 120),(2,'OFFICE ROOF' if office else 'MEZZ TOP',264 if office else 240),(3,'MAIN ROOF / SBMF WORKLINE',288)]
    b.grids={'x':[(str(i+1),x) for i,x in enumerate(frames)],'y':[('A',0),('B',600)]+([('C',960)] if office else [])};b.views=[dict(title='SBMF TRANSVERSE FRAME',direction='Y',station_in=frames[len(frames)//2],range_in=[0,width])]
    b.note('SBMF-GRAVITY','S: paired channels lie outside the HSS faces, with the source eight 1 in snug-tight bolts. The source SBMF beam is a lateral member; independent trusses carry the roof. Vertically slotted flange struts transfer restraint without importing gravity load. A: raised truss heels/internals and supplier clips; source roof slope retained. Source stiffness/ductility and supplier certification requirements are unchanged.')


def wall(b,label,axis,pos,lo,hi,base,top,k,sp,cp,bays,width,count,rod,continuous=False):
    def pt(u,z):return [u,pos,z] if axis==0 else [pos,u,z]
    d=b.depth(b.profile(sp));tp=b.profile(('800' if d>=8 else '600')+'T200-68');cp=b.profile(cp);sp=b.profile(sp)
    for suffix,z,ly in (('BT',base,[0,0,1]),('TT',top,[0,0,-1])):
        m=b.member(label+suffix,tp,'bottom_track' if suffix=='BT' else 'top_track',pt(lo,z),pt(hi,z),k,'S',local_y=ly);b.connection(m['id'],'review_cfs_sill' if suffix=='BT' else 'review_cfs_floor',pt(lo,z),[m],parameters={'floor_depth':12,'level':k})
    for u in frange(lo,hi+.1,12 if b.key=='cfs10' and label.startswith('OFF') else 16):
        if any(abs(u-end)<4 for bay in bays for end in bay):continue
        for tier,(aa,dd) in enumerate(((base,(base+top)/2),((base+top)/2,top)) if continuous else ((base,top),)):
            m=b.member(f'{label}-ST-{u}-{tier}',sp,'stud',pt(u,aa+.1),pt(u,dd-.1),k,'A',local_y=[1,0,0] if axis==0 else [0,1,0]);b.ends(m,'cfs_stud')
    if continuous:
        for face in (-1,1):
            tr=b.member(label+'-TIER'+str(face),tp,'tier_track',pt(lo,(base+top)/2+face*.08),pt(hi,(base+top)/2+face*.08),k,'S',local_y=[0,0,face]);b.ends(tr,'review_sbmf_wall_slide',[b.record('framing','sidewall-tier-track')],parameters={'joint':'tier'})
    for j,(aa,dd) in enumerate(bays):
        chords=[]
        chord_stations=(aa,dd) if b.key=='cfs18' and continuous else (aa+3,dd-3)
        for side,u in enumerate(chord_stations):
            m=b.member(f'{label}-CH-{j}-{side}',cp,'chord',pt(u,base),pt(u,top),k,'S',local_y=[1,0,0] if axis==0 else [0,1,0]);chords.append(m)
            rp=b.custom('ROD-'+str(rod),'round',dict(d=rod),basis='S');r=b.member(m['id']+'R',rp,'hold_down_rod',pt(u,base-2),pt(u,top+4),k,'A')
            rid='base-north-panels' if b.key=='cfs10' and label=='NORTH' else 'hd-side-wall' if continuous else ('office' if b.key=='cfs10' else 'mezz')+'-rod-s'+str(k)
            b.connection(m['id']+'HD','review_sbmf_hold_down',pt(u,base if continuous else top),[m,r],[b.record('bases',rid)],parameters={'rod_diameter':rod,'foundation':continuous or k==1,'continuous':continuous})
        for tier,(z0,z1) in enumerate(((base,(base+top)/2),((base+top)/2,top)) if continuous else ((base,top),)):
            for face in (-1,1):
                for flip in (0,1):
                    a=pt(aa,z0 if flip else z1);dend=pt(dd,z1 if flip else z0);a[1-axis]+=face*d/2;dend[1-axis]+=face*d/2;pid=b.custom(f'STRAP-{width}-54','flat',dict(width=width,thickness=.0566),basis='S');m=b.member(f'{label}-X-{j}-{tier}-{face}-{flip}',pid,'strap',a,dend,k,'A',records=[b.record('schedules','sched-strap')]);b.ends(m,'review_cfs_strap',[b.record('schedules','sched-strap')],parameters={'screws':count,'screw_size':12,'host_profile':cp})
    b.walls.append(dict(id=label,line=label,direction='XY'[axis],level=k,base_z_in=base,top_z_in=top,runs=[dict(start_in=a,end_in=d,position_in=pos) for a,d in bays],basis='A source bay sizes / adopted locations',source_record=b.record('schedules','sched-strap')))


def wing(b,office):
    x0,x1,y0,y1=(1208,2168,480,960) if office else (1818,2382,24,576);h=132 if office else 120
    for k in (1,2):
        pid='1200S250-68' if office and k==1 else '1000S200-68' if office else '1000S250-97' if k==1 else '800S162-54'
        # The roof uses 19/32 WSP, not the floor's WSP + gypsum stack.
        # One exact top-of-finish datum sets the joist, bearing track and panel.
        finish=23/32+(1 if office else 1.5) if k==1 else 19/32
        z0=(k-1)*h;zt=k*h;floor_depth=b.depth(b.profile(pid))+finish;top=zt-floor_depth
        sp='600S162-54' if office else '600S162-43';cp=('2X600S250-97' if k==1 else '2X600S162-54') if office else ('2X600S200-68' if k==1 else '2X600S162-54');rod=1.25 if office and k==1 else .75 if k==1 or office else .625
        for name,axis,pos,lo,hi in [('S',0,y0,x0,x1),('N',0,y1,x0,x1),('W',1,x0,y0,y1),('E',1,x1,y0,y1)]:
            margin=(hi-lo-240)/3;bays=[(lo+margin,lo+margin+120),(hi-margin-120,hi-margin)]
            wall(b,('OFF-' if office else 'MEZZ-')+name+str(k),axis,pos,lo,hi,z0,top,k,sp,cp,bays,(6 if office else 5) if k==1 else 3 if office else 2,(20 if office else 16) if k==1 else 10 if office else 8,rod)
        bearing=[y0,(y0+y1)/2,y1] if office else [y0,y0+184,y0+368,y1]
        for j,y in enumerate(bearing[1:-1]):wall(b,f'BEARING-{k}-{j}',0,y,x0,x1,z0,top,k,sp,cp,[],0,0,rod)
        spacing=12 if office and k==1 else 16 if k==1 else 24;rid=('office-joist-floor' if k==1 else 'office-joist-roof') if office else 'mezz-joist-storage' if k==1 else 'mezz-joist-ceiling'
        for x in sorted(set([*frange(x0,x1+.1,spacing),x1])):
            for j,(aa,dd) in enumerate(zip(bearing,bearing[1:])):
                z=zt-finish-b.depth(b.profile(pid))/2;m=b.member(f'WING-J-{k}-{x}-{j}',pid,'joist',[x,aa,z],[x,dd,z],k,'S',records=[b.record('joists',rid)]);b.ends(m,'review_cfs_joist',[b.record('joists',rid)],parameters={'floor_depth':floor_depth,'spacing':spacing})
        panel=b.panel('WING-FLOOR-'+str(k),'floor' if k==1 else 'roof',[[x0,y0,zt],[x1,y0,zt],[x1,y1,zt],[x0,y1,zt]],finish,k,'S')
        panel['thickness_direction']='negative_global_z'
        panel['datum_basis']='Source finish thickness below top of finish; joist top meets panel underside and bottom flange meets top-track web.'
    # Door is in the middle gap, clear of both source-sized strap panels.
    opening(b,'WING-ACCESS',0,y0,(x0+x1)/2-18,0,36,84,1)
    # Remove the threshold and shorten ordinary studs at the adopted access door.
    cut=[]
    for m in list(b.members):
        if m['level']!=1 or m['kind'] not in ('stud','bottom_track') or not all(abs(q[1]-y0)<.01 for q in m['axis']):continue
        aa,dd=m['axis'];lo,hi=(x0+x1)/2-18,(x0+x1)/2+18
        if m['kind']=='stud' and lo-4<aa[0]<hi+4:
            m['axis'][0][2]=92
            for c in b.connections:
                if c['id']==m['id']+':0':c['point']=list(m['axis'][0])
            continue
        if m['kind']=='bottom_track' and min(aa[0],dd[0])<lo and max(aa[0],dd[0])>hi:
            b.members.remove(m);cut.append(m['id'])
            for j,(a,d) in enumerate(((aa,[lo,y0,0]),([hi,y0,0],dd))):
                piece=b.member(m['id']+'-DOOR'+str(j),m['profile_id'],'bottom_track',a,d,1,'A',local_y=m['local_y']);b.ends(piece,'review_cfs_sill')
    b.connections[:]=[c for c in b.connections if not set(c['member_ids'])&set(cut)]
    b.note('SEPARATION','S: '+('office west wall is 8 in beyond the high-bay east line; 80 x 40 ft wing, 11 + 11 ft stories.' if office else 'mezzanine x=151.5..198.5 ft, y=2..48 ft, two 10 ft levels. 19 in clear to HSS faces and 12 in clear to rear wind posts.')+' No framing crosses the seismic separation. A: wall panel positions, ordinary infills and access opening. Source rod/chord schedules remain story-specific.')


def catwalk(b,roofbase):
    # Source north catwalk at +12 ft, 4 ft wide, suspended from the roof trusses.
    for x in frange(0,1200+.1,48):
        m=b.member('CATWALK-J-'+str(x),'800S162-54','joist',[x,912,140],[x,960,140],1,'A');b.ends(m,'review_cfs_joist',parameters={'floor_depth':8,'spacing':48})
        rod=b.member('CATWALK-H-'+str(x),'ROD1/2','hanger_rod',[x,912,144],[x,912,roofbase],1,'A');b.ends(rod,'review_rod_clevis',parameters={'supplier_hanger':True})
    b.panel('CATWALK','walkway',[[0,912,144],[1200,912,144],[1200,960,144],[0,960,144]],1.5,1,'A')
    for y in (912,960):
        edge=b.member('CATWALK-EDGE-'+str(y),'2X800S200-68','walkway_edge_beam',[0,y,140],[1200,y,140],1,'A');b.ends(edge,'review_cfs_joist',parameters={'floor_depth':8,'spacing':48})
    for x in frange(0,1200+.1,48):
        post=b.member('CATWALK-GUARD-'+str(x),'HSS2X2X1/8','guard_post',[x,912,144],[x,912,186],1,'A');b.ends(post,'test_guard')
    for z in (165,186):
        rail=b.member('CATWALK-RAIL-'+str(z),'HSS2X2X1/8','guard_rail',[0,912,z],[1200,912,z],1,'A');b.ends(rail,'test_guard')
    b.note('CATWALK','S: north catwalk load enters the 30 ft roof trusses 4 ft from the north wall. A: pictured +12 ft walkway, 800S162-54 joists at 4 ft, 1/2 in hangers and supplier interfaces; source hanger reactions retained, supplier members unverified.')
