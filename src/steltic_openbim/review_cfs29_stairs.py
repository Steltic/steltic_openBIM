"""Explicit adopted stair and source guard interfaces for the mezzanine."""
import math
from .pilots.model import add,sub,mul,unit
from .review_cfs_occurrences import axis
from .review_cfs29_model import joint,link,TOP,STEEL


def build(b,posts,beams,joists):
    guards={};rails=[];caps={}
    gp=b.profile('2X362S162-54')
    # Long-edge guard posts are outside the source box beam. End-edge posts
    # stand clear of the grid columns; their single-C receiving bracket is A.
    for along,pos,limit,sg in ((0,0,720,-1),(0,384,720,1),(1,0,384,-1),(1,720,384,1)):
        stations=sorted(set(range(0,limit+1,48))|({312,360} if along==0 and pos==0 else set()))
        grids=range(0,limit+1,144 if along==0 else 192)
        stations=sorted((set(stations)-set(grids))|{g+d for g in grids for d in (-6,6) if 0<g+d<limit})
        if along==0 and pos==0:stations=[v for v in stations if not 312<v<360]
        if along==1:stations=[v for v in stations if v not in (0,384)]
        row=[]
        for u in stations:
            host=(beams[min(int(u//144),4)*144,pos] if along==0 else joists[pos,0 if u<192 else 192])
            # Posts directly at an X-grid joint use a finite adjacent beam
            # with a short A bridging bracket across the4.5in beam setback.
            normal=sg*(3.25 if along else (6+.1017)/2+.30)
            q=[u,pos+normal,132] if along==0 else [pos+normal,u,132]
            ly=[0,sg,0] if along==0 else [sg,0,0]
            m=b.member(f'MZ-GUARD-{along}-{pos}-{u}',gp,'guard_post',q,[q[0],q[1],182.25],1,'A',records=['connections/conn-guard-post'],local_y=ly)
            c=joint(b,m['id']+'-BASE','guard_base',[q[0],q[1],136],[m,host],['connections/conn-guard-post'],along=along,face=sg,source_box=along==0)
            link(b,m,c,0);guards[along,pos,u]=m;row.append((u,m))
            cp=b.custom('MEZZ29-GUARD-CAP','flat',dict(width=4,thickness=.125),basis='A4in square guard cap')
            cap=b.member(m['id']+'-CAP',cp,'guard_cap',[q[0],q[1]-2,182.3125],[q[0],q[1]+2,182.3125],1,'A',local_y=[1,0,0]);caps[m['id']]=cap
            cc=joint(b,m['id']+'-CAP-WELD','guard_cap',[q[0],q[1],182.375],[m,cap]);link(b,m,cc,1);link(b,cap,cc,0);link(b,cap,cc,1)
        # Continuous perimeter rails are segmented at actual posts. The source
        # specifies the guard-post design; rail/infill sections and joints are A.
        for j,((u,left),(v,right)) in enumerate(zip(row,row[1:])):
            if along==0 and pos==0 and u==312 and v==360:continue
            aa=[*left['axis'][1][:2],184.1875];dd=[*right['axis'][1][:2],184.1875]
            rail=b.member(f'MZ-RAIL-{along}-{pos}-{j}','362S162-54','guard_rail',aa,dd,1,'A',local_y=[0,sg,0] if along==0 else [sg,0,0])
            rails.append(rail)
            for end,post in enumerate((left,right)):
                c=joint(b,rail['id']+'-END'+str(end),'rail_post',axis(rail)[end],[rail,post,caps[post['id']]],along=along,end=end);link(b,rail,c,end)
    # Close the return-rail gap between the end-edge rows and the long-edge
    # corner posts, instead of displaying unconnected corner rail ends.
    for x in (0,720):
        for y,near in ((0,6),(384,378)):
            left=guards[0,y,6 if x==0 else 714];right=guards[1,x,near]
            aa=[*left['axis'][1][:2],184.1875];dd=[*right['axis'][1][:2],184.1875]
            m=b.member(f'MZ-RAIL-CORNER-{x}-{y}','362S162-54','guard_rail',aa,dd,1,'A')
            for end,post in enumerate((left,right)):
                c=joint(b,m['id']+'-END'+str(end),'rail_post',axis(m)[end],[m,post,caps[post['id']]],end=end,corner=True);link(b,m,c,end)
    strings=[]
    for i,x in enumerate((312,360)):
        m=b.member('MZ-STRINGER-'+str(i),'2X1000S250-97','stair_stringer',[x,-200,0],[x,0,140],1,'A',local_y=[1,0,0])
        u=unit(sub(*axis(m)[::-1]));m['end_offsets']=[mul(u,12),mul(u,-4.5)];strings.append(m)
        for end in (0,1):
            members=[m] if end==0 else [m,beams[288,0]]
            c=joint(b,m['id']+'-END'+str(end),'stair_end',axis(m)[end],members,['connections/conn-stair-stringer'],end=end)
            link(b,m,c,end)
    # Source stair reaction uses4ft width and16ft horizontal run. Eighteen
    # adopted8in risers give17 equal11.294in treads, with the floor as landing.
    treadpid=b.custom('MEZZ29-TREAD','flat',dict(width=192/17,thickness=1),basis='A1in steel-grating design envelope; supplier product to verify')
    for j in range(1,18):
        y=-192+(j-.5)*192/17;z=8*j
        tread=b.member('MZ-TREAD-'+str(j),treadpid,'stair_tread',[314.75,y,z-.5],[357.25,y,z-.5],1,'A',local_y=[0,1,0])
        for end,stringer in enumerate(strings):
            c=joint(b,tread['id']+'-END'+str(end),'tread_end',[312 if end==0 else 360,y,z-.5],[tread,stringer],end=end)
            link(b,tread,c,end)
        b.panel('MEZZ29-TREAD-'+str(j),'stair_tread',[[314.75,y-96/17,z],[357.25,y-96/17,z],[357.25,y+96/17,z],[314.75,y+96/17,z]],1,1,'A',physical_constituent_member_ids=[tread['id']],thickness_direction='negative_global_z')
    b.note('GUARD-STAIR','S:42in guard,paired362S16254 posts at4ft maximum,2x1/2in A325 bolts at4in vertical pitch and source crush tubes at boxed beams. Stair source interface L4x4x1/4 and2x1/2in bolts; source4ft nominal width/16ft run retained. A:guard posts shifted6in clear of beam/post joints, return/rail fittings, end-joist stand-off/backplate details, guard infill and stair side protection delegated to a proprietary system, paired1000S25097 stringers at48in centres with42.5in clear treads,18x8in rises,17equal treads and adopted tread product/attachments. No egress or supplier capacity certification is inferred.')
