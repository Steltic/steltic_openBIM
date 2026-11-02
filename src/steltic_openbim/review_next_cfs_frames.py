"""The remaining portal/retrofit cases and their source secondary framing."""
import math
from .review_cfs import frange
from .review_model import MIL


def build(b):
    if b.key in ('cfs10','cfs18'):
        from .review_next_sbmf import build as sbmf
        sbmf(b);return
    c=b.cfg;key=b.key;span=c['span_ft']*12;length=c['length_ft']*12;step=c['spacing_ft']*12;frames=[i*step for i in range(c['n_frames'])];eave=c['eave_ft']*12;ridge=c['apex_ft']*12
    rz=lambda x:eave+(ridge-eave)*(1-abs(2*x/span-1))
    rec=lambda name:b.record('schedules','sched-'+name)
    col=b.profile(c['col_section'],gap=.375,pair_spacing=6.375);raf=b.profile(c['raf_section'],gap=.375,pair_spacing=6.375);primary={}
    context=key=='cfs25'
    for i,y in enumerate(frames):
        for side,x in enumerate((0,span)):
            m=b.member(f'F{i}-C{side}',col,'column',[x,y,0],[x,y,eave],1,'A' if context else 'S',local_y=[0,1,0]);primary[i,'C',side]=m
            b.connection(m['id']+'B','review_next_portal_base',m['axis'][0],[m],[b.record('anchorage','base-anchor')],parameters={'existing_context':context})
        for side,(a,d) in enumerate(((0,span/2),(span/2,span))):
            m=b.member(f'F{i}-R{side}',raf,'rafter',[a,y,rz(a)],[d,y,rz(d)],1,'A' if context else 'S',local_y=[0,1,0]);primary[i,'R',side]=m
            b.connection(m['id']+'K','review_next_portal_joint',[0 if side==0 else span,y,eave],[primary[i,'C',side],m],[b.record('connections','conn-knee')],parameters={'joint':'knee','rows':4,'existing_context':context})
        b.connection(f'F{i}-RIDGE','review_next_portal_joint',[span/2,y,ridge],[primary[i,'R',0],primary[i,'R',1]],[b.record('connections','conn-apex')],parameters={'joint':'ridge','rows':3,'existing_context':context})
    lap={'cfs25':30,'cfs27':12,'cfs28':18}[key]
    # Ex27 uses five equal slope spaces; its source spacing is 3.713 ft along slope.
    stations=[span*j/10 for j in range(11)] if key=='cfs27' else sorted(set(frange(0,span/2+.1,60))|{span/2}|{span-x for x in frange(0,span/2+.1,60)})
    for x in stations:
        for j,(ya,yb) in enumerate(zip(frames,frames[1:])):
            if key=='cfs25':pid='1000Z300-'+('97' if j in (0,len(frames)-2) or min(x,span-x)<=60 and j in (1,len(frames)-3) else '68')
            elif key=='cfs27':pid='800Z250-54'
            else:pid='1000Z250-'+('97' if j in (0,len(frames)-2) and min(x,span-x,abs(x-span/2))<=57.6 else '68')
            z=rz(x)+b.depth(raf)/2+b.depth(b.profile(pid))/2+.125;aa=ya-(lap if j else 0);dd=yb+(lap if j<len(frames)-2 else 0)
            m=b.member(f'P-{x:g}-{j}',pid,'purlin',[x,aa,z],[x,dd,z],1,'A',records=[rec('purlin')],local_y=[1,0,0],lap_in=lap)
            for end,y in enumerate((ya,yb)):b.connection(m['id']+str(end),'review_next_secondary',[x,y,z],[m,primary[j+end,'R',int(x>span/2)]],[rec('purlin')],parameters={'kind':'purlin','lap':lap,'support_bolts':4 if key=='cfs25' and min(x,span-x)<=60 and y not in (0,length) else 2,'clip_t':.375 if key=='cfs25' else .25})
            if context:b.connection(m['id']+'-SKIN','review_skin_fastener',[x,(ya+yb)/2,z+b.depth(pid)/2],[m],[rec('fastener')],parameters={'spacing':6 if j in (0,len(frames)-2) and min(x,span-x)<=96 else 12})
    for side,x in enumerate((0,span)):
        for j,(ya,yb) in enumerate(zip(frames,frames[1:])):
            pid='2X1200S250-97' if key=='cfs28' and side==0 else '800S250-97' if key=='cfs28' else '800S250-54' if key=='cfs27' else '1000Z300-97'
            m=b.member(f'EAVE-{side}-{j}',pid,'eave_strut',[x,ya,eave],[x,yb,eave],1,'A',records=[rec('strap')]);b.ends(m,'review_next_secondary',[rec('strap')],parameters={'kind':'eave_strut','lap':0,'support_bolts':2})
            if key=='cfs28' and side==0:continue
            for z in frange(24 if key=='cfs27' else 36,eave,60 if key=='cfs27' else 72):
                pid='800Z250-'+('54' if key=='cfs27' else '97' if key=='cfs28' or j in (0,len(frames)-2) else '68');outside=x+(-1 if side==0 else 1)*(b.depth(col)/2+b.depth(b.profile(pid))/2+.125)
                m=b.member(f'G-{side}-{j}-{z}',pid,'girt',[outside,ya-(lap if j else 0),z],[outside,yb+(lap if j<len(frames)-2 else 0),z],1,'A',records=[rec('girt')],local_y=[0,0,1]);b.ends(m,'review_next_secondary',[rec('girt')],parameters={'kind':'girt','lap':lap,'support_bolts':2,'clip_t':.375 if context else .25})
    def strap(mid,a,d,width,mil,count,host):
        pid=b.custom(f'STRAP-{width}-{mil}','flat',dict(width=width,thickness=MIL[mil]),basis='S');m=b.member(mid,pid,'strap',a,d,1,'A',records=[rec('strap')]);b.ends(m,'review_cfs_strap',[rec('strap')],parameters={'screws':count,'screw_size':12,'host_profile':host});return m
    if not context:
        for j in (0,len(frames)-3):
            ya,yb=frames[j],frames[j+2]
            for side,x in enumerate((0,span)):
                if key=='cfs28' and side==0:continue
                for flip in (0,1):strap(f'WALL-X-{j}-{side}-{flip}',[x,ya,eave*flip],[x,yb,eave*(1-flip)],5 if key=='cfs28' else 3.5,118 if key=='cfs28' else 68,33 if key=='cfs28' else 14,col)
        for j,n in ((0,3 if key=='cfs28' else 2),(len(frames)-(4 if key=='cfs28' else 3),3 if key=='cfs28' else 2)):
            for r,(aa,dd) in enumerate(zip(stations,stations[1:])):
                # Source Ex27 has eave-to-P3 and P3-to-ridge roof panels.
                if key=='cfs27':continue
                for flip in (0,1):strap(f'ROOF-X-{j}-{r}-{flip}',[aa,frames[j],rz(aa)+7] if flip else [dd,frames[j],rz(dd)+7],[dd,frames[j+n],rz(dd)+7] if flip else [aa,frames[j+n],rz(aa)+7],3,68,12,raf)
            if key=='cfs27':
                for r,(aa,dd) in enumerate(zip((0,span*.3,span*.5,span*.7),(span*.3,span*.5,span*.7,span))):
                    for flip in (0,1):strap(f'ROOF-X-{j}-{r}-{flip}',[aa,frames[j],rz(aa)+7] if flip else [dd,frames[j],rz(dd)+7],[dd,frames[j+n],rz(dd)+7] if flip else [aa,frames[j+n],rz(aa)+7],3,68,12,raf)
        if key=='cfs28':
            for j in (0,len(frames)-2):
                ya,yb=frames[j:j+2];z=171
                m=b.member(f'OPEN-STRUT-{j}','2X600S300-54','open_front_strut',[0,ya,z],[0,yb,z],1,'A',records=[rec('strap')]);b.ends(m,'review_screwed_flybrace',[rec('strap')],parameters={'screws':6})
                for flip in (0,1):strap(f'OPEN-X-{j}-{flip}',[0,ya,z if flip else eave],[0,yb,eave if flip else z],3,97,17,col)
        endwalls(b,frames,span,rz,primary,strap)
        flybraces(b,frames,stations,span,rz,primary)
    else:
        # Existing frame and braces remain explicitly assumed survey context.
        for y in (0,length):
            for x in (300,600,900):
                m=b.member(f'EXIST-POST-{y}-{x}','HSS8X8X1/4','endwall_post',[x,y,0],[x,y,rz(x)],1,'A');b.ends(m,'review_sliding_post',parameters={'existing_context':True})
            for x in range(0,1200,300):
                for z in (36,108,180):
                    pid='800Z250-'+('97' if x in (0,900) else '68');m=b.member(f'END-G-{y}-{x}-{z}',pid,'girt',[x,y,z],[x+300,y,z],1,'A',records=[rec('girt')]);b.ends(m,'review_next_secondary',[rec('girt')],parameters={'kind':'girt','lap':30,'support_bolts':2,'clip_t':.375})
        for x in (0,span):
            for j in (0,len(frames)-2):
                for flip in (0,1):
                    m=b.member(f'EXIST-X-{x}-{j}-{flip}','ROD1','rod_brace',[x,frames[j],eave*flip],[x,frames[j+1],eave*(1-flip)],1,'A');b.ends(m,'review_rod_clevis',parameters={'existing_context':True})
        for j in (0,len(frames)-2):
            for side,(xa,xb) in enumerate(((0,span/2),(span/2,span))):
                for flip in (0,1):
                    aa,dd=(xa,xb) if flip else (xb,xa)
                    m=b.member(f'EXIST-ROOF-X-{j}-{side}-{flip}','ROD1','rod_brace',[aa,frames[j],rz(aa)],[dd,frames[j+1],rz(dd)],1,'A',records=[rec('purlin')]);b.ends(m,'review_rod_clevis',[rec('purlin')],parameters={'existing_context':True,'supplier_hanger':True})
        b.note('RETROFIT-SURVEY','S: this design replaces purlins/girts and cladding attachments only. A: existing HSS frame/posts and joints are survey stand-ins, not source-designed replacement frames. Adopt the through-fastened roof option; the standing-seam alternate remains in the source register. Existing bracing and base verification remain outside the completed retrofit scope.')
    for side,(a,d) in enumerate(((0,span/2),(span/2,span))):b.panel('ROOF-'+str(side),'roof',[[a,0,rz(a)],[d,0,rz(d)],[d,length,rz(d)],[a,length,rz(a)]],.025,1,'A')
    b.levels=[(0,'BASE',0),(1,'EAVE',eave),(2,'RIDGE',ridge)];b.grids={'x':[('A',0),('R',span/2),('B',span)],'y':[(str(i+1),y) for i,y in enumerate(frames)]}
    b.views=[dict(title='TRANSVERSE FRAME',direction='X',station_in=y,range_in=[0,span]) for y in (0,frames[len(frames)//2])]
    b.note('FRAME-SOURCE','S: source portal profiles, bolt groups, secondary zones, laps and bracing arrangements. A: physical ply spacing, bracket outlines, receiving clips and local set-out. '+('North is -X; the open north side stays clear below the 14 ft header bracing.' if key=='cfs28' else 'Single-channel orientation and its torsion restraints are retained.' if key=='cfs27' else 'Existing primary framing is assumed context.'))


def endwalls(b,frames,span,rz,primary,strap):
    key=b.key;dw=192 if key=='cfs27' else 240;lo=(span-dw)/2;hi=lo+dw;rid=b.record('schedules','sched-endwall')
    for end,y in enumerate((frames[0],frames[-1])):
        jp='2X800S250-97' if key=='cfs27' else '2X1400S300-118';hp='HSS4X4X1/8' if key=='cfs27' else 'HSS6X6X3/16'
        for j,x in enumerate((lo,hi)):
            m=b.member(f'DOOR-JAMB-{end}-{j}',jp,'opening_jamb',[x,y,0],[x,y,rz(x)],1,'S',records=[rid]);b.connection(m['id']+'B','review_endpost_base',m['axis'][0],[m],[rid]);b.connection(m['id']+'T','review_endpost_top',m['axis'][1],[m,primary[0 if end==0 else len(frames)-1,'R',j]],[rid],parameters={'vertical_slip':1})
        m=b.member(f'DOOR-HEAD-{end}',hp,'opening_header',[lo,y,168],[hi,y,168],1,'S',records=[rid]);b.ends(m,'review_angle_clip',[rid],parameters={'count':2,'diameter':.5})
        m=b.member(f'CENTRE-POST-{end}','2X362S162-54' if key=='cfs27' else '2X600S162-54','endwall_post',[span/2,y,168],[span/2,y,rz(span/2)],1,'S',records=[rid]);b.ends(m,'review_endpost_top',[rid],parameters={'vertical_slip':1})
        for j,(aa,dd) in enumerate(((0,lo),(lo,span/2),(span/2,hi),(hi,span))):
            for z in frange(24 if key=='cfs27' else 36,min(rz(aa),rz(dd)),60 if key=='cfs27' else 72):
                if lo<=aa and dd<=hi and z<168:continue
                pid='800Z250-'+('54' if key=='cfs27' else '68' if lo<=aa and dd<=hi else '97');m=b.member(f'END-G-{end}-{j}-{z}',pid,'girt',[aa,y,z],[dd,y,z],1,'S',records=[rid]);b.ends(m,'review_next_secondary',[rid],parameters={'kind':'endwall_girt','lap':0,'support_bolts':2})
        if key=='cfs28':
            for j,(aa,dd) in enumerate(((0,lo),(hi,span))):
                for flip in (0,1):strap(f'END-X-{end}-{j}-{flip}',[aa,y,rz(aa)*flip],[dd,y,rz(dd)*(1-flip)],3.5,68,14,jp)
        b.openings.append(dict(id=f'DOOR-{end}',kind='door',plane='xz',x_ft=lo/12,y_ft=y/12,z_ft=0,width_ft=dw/12,height_ft=14,level=1,basis='S dimensions / A centred location',query_id=key.upper()+'-OPENINGS',confirmed=True))


def flybraces(b,frames,stations,span,rz,primary):
    key=b.key;rid=b.record('schedules','sched-torsion-brace' if key=='cfs27' else 'sched-strap')
    for i,y in enumerate(frames):
        for x in stations[1:-1]:
            if key=='cfs27' and x not in (stations[3],stations[5],stations[7]):continue
            for side in ((1,) if key=='cfs27' else (-1,1)):
                aa=[x,y,rz(x)-7];dd=[x,y+side*20,rz(x)+13];m=b.member(f'FB-R-{i}-{x}-{side}','L2X2X1/8','flange_brace',aa,dd,1,'A',records=[rid]);b.connection(m['id'],'review_screwed_flybrace',aa,[m,primary[i,'R',int(x>span/2)]],[rid],parameters={'screws':2 if key=='cfs27' else 4,'cross_plate':key=='cfs28'})
        for side,x in enumerate((0,span)):
            zs=(24,84,144) if key=='cfs27' else (171,) if side==0 else (36,108,180)
            for z in zs:
                for hand in ((1,) if key=='cfs27' else (-1,1)):
                    aa=[x+(7 if side==0 else -7),y,z];dd=[x+(-13 if side==0 else 13),y+hand*20,z];m=b.member(f'FB-C-{i}-{side}-{z}-{hand}','L2X2X1/8','flange_brace',aa,dd,1,'A',records=[rid]);b.connection(m['id'],'review_screwed_flybrace',aa,[m,primary[i,'C',side]],[rid],parameters={'screws':2 if key=='cfs27' or side==0 else 4})
