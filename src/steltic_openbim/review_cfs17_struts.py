"""Actual garage eave/valley strut receivers and shared physical end fittings."""
import math
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .review_cfs_strut_ends import section_points
from .review_cfs_frame_straps import face_intervals
from .review_cfs25_cladding import top_flange
AXES=([1,0,0],[0,1,0],[0,0,1])
RID='schedules/sched-strap'


def apply(b):
    if b.key!='cfs17':return
    old={m['id'] for m in b.members if m['kind']=='eave_strut'}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old]
    lookup={m['id']:m for m in b.members}
    for line,x,z,out,pid in (('left',-10.75,216,-1,'800S250-68'),('right',1042.75,216,1,'800S250-68'),('valley',606.5,196.25,1,'2X800S250-68')):
        ms=[];valley=line=='valley';cut=4 if valley else 10
        if not valley:
            side=int(out>0);origin=[1032*side,0,0];axes=([0,0,1],[0,-out,0],[out,0,0])
            face=max(top_flange(b,m,origin,axes)[3] for m in b.members if m['id'].startswith(f'GAR-G-{side}-'))
            # Align the actual web with the source wall-sheet plane. The
            # bracket provides the bypass, not a deep panel screw spacer.
            x=origin[0]+out*(face-b.profiles[b.profile(pid)]['dimensions']['t']/2)
        for j in range(18):
            m=b.member(f'GAR-STRUT-{line}-{j}',pid,'eave_strut',[x,j*144,216],[x,(j+1)*144,216],1,'A',records=[RID],local_y=[1,0,0],physical_fit_basis='S eave/valley section and12ft span. A outward bypass and shared receiving bracket; valley member lowered19.75in to clear source continuous gussets/cap. Original strut checks remain separate from this local fitting.')
            m['end_offsets']=[[0,cut,z-216],[0,-cut,z-216]];ms.append(m)
            if valley:
                for k,yy in enumerate(range(16,138,24)):
                    b.connection(m['id']+'-STITCH'+str(k),'review_garage_strut',[x,j*144+yy,z],[m],[RID],parameters=dict(actual_garage_strut=True,purpose='stitch'))
        for i in range(19):
            members=[ms[j] for j in (i-1,i) if 0<=j<18];host=lookup[f'F{i+1}-PROP' if valley else f'F{i+1}-C{int(out>0)}']
            c=b.connection(f'GAR-STRUT-{line}-NODE{i}','review_garage_strut',[host['axis'][0][0],i*144,z],[host,*members],[RID],parameters=dict(actual_garage_strut=True,purpose='valley' if valley else 'eave',out=out))
            for m in members:
                end=0 if int(m['id'].rsplit('-',1)[-1])==i else 1
                b.endpoint_links.append(dict(member_id=m['id'],end='end' if end else 'start',connection_id=c['id'],basis='Both finite strut ends join one real shared bracket on the source column/prop.'))
    b.note('GARAGE-STRUT-RECEIVERS','S:800S25068 eave struts,2x800S25068 valley strut continuous through all18 bays and stitched at24in. A: eave10in and valley4in cuts; eave web aligned with real wall-sheet plane for direct panel bearing, with outward bypass bracket; valley centre lowered19.75in from its source workpoint to pass below the actual3/4in cap and6in gusset extensions; common3/16in brackets, actual paired-web packs and1/2in bolts. The retained source EA/L and strength checks do not verify these offsets or brackets.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params
    if par['purpose']=='stitch':
        from .review_cfs28_struts import draw as stitch
        stitch(ctx);a.title='GARAGE VALLEY / SOURCE24in PAIR STITCH';return
    host=ctx.ms[0];ms=ctx.ms[1:];out=par['out'];valley=par['purpose']=='valley';t=.1875;origin=ctx.c['point']
    extract(ctx,host,'COLUMN',AXES,34);ends=[]
    for i,m in enumerate(ms):
        extract(ctx,m,'STRUT'+str(i),AXES,32);aa,dd=axis(m);cut=min((aa,dd),key=lambda q:abs(q[1]-origin[1]))[1]-origin[1];sg=1 if (aa[1]+dd[1])/2>origin[1] else -1;ends.append((i,m,cut,sg))
    width=6 if valley else 19;low=min([-width/2]+[cut+sg*6 for _,_,cut,sg in ends]);high=max([width/2]+[cut+sg*6 for _,_,cut,sg in ends]);dx=axis(ms[0])[0][0]-origin[0]
    webs=sorted((min(q[0] for q in poly)+dx,max(q[0] for q in poly)+dx) for poly in section_points(ms[0],p) if max(q[0] for q in poly)-min(q[0] for q in poly)<.3 and max(q[2] for q in poly)-min(q[2] for q in poly)>4)
    face=webs[-1][1] if out>0 else webs[0][0];hf=3 if valley else 7;column_face=out*hf;outside=face+out*t
    bottom=-4 if valley else -5;top=4 if valley else 5;column_low=-4 if valley else -16
    a.polygon('STRUT-LEG',[[face,y,z] for y,z in ((low,bottom),(high,bottom),(high,top),(low,top))],t,normal=[out,0,0],basis='A',description='A common3/16in receiving leg on the real strut web')
    a.box('BRIDGE',[min(outside,column_face),-width/2,bottom],[abs(outside-column_face),width,t],'A','A continuous folded bridge to the actual column face')
    a.polygon('COLUMN-LEG',[[column_face,y,z] for y,z in ((-width/2,column_low),(width/2,column_low),(width/2,bottom),(-width/2,bottom))] if not valley else [[column_face,y,z] for y,z in ((-3,-4),(3,-4),(3,4),(-3,4))],t,normal=[out,0,0],basis='A',description='A actual HSS face receiver' if valley else 'A dropped receiver reaches all six actual column flanges below knee cut')
    a.interfaces.append(dict(id='FOLDS',kind='formed_bends',connects=['STRUT-LEG','BRIDGE','COLUMN-LEG'],basis='A',description='One connected folded bracket; radii omitted'))
    for i,m,cut,sg in ends:
        packs=[]
        for j,((_,lo),(hi,_)) in enumerate(zip(webs,webs[1:])):
            name=f'PACK{i}-{j}';a.box(name,[lo,min(cut,cut+sg*6),bottom],[hi-lo,6,top-bottom],'A','A solid pack between the actual paired webs');packs.append(name)
        a.fastener('STRUT-B'+str(i),[[outside,cut+sg*y,0] for y in (1.5,4.5)],[-out,0,0],.5,t+webs[-1][1]-webs[0][0],['STRUT'+str(i),'STRUT-LEG']+packs,'A two1/2in through-web bolts and actual gap pack',basis='A')
    _,bands=face_intervals(host,p,[out,0,0]);zs=(-1.5,1.5) if valley else (-14.5,-11.5)
    for i,(lo,hi,ht) in enumerate(bands):
        yy=(lo+hi)/2/out
        a.fastener('COLUMN-B'+str(i),[[column_face+out*t,yy,z] for z in zs],[-out,0,0],.5,t+ht,['COLUMN-LEG','COLUMN'],'A two1/2in bolts into this actual receiving flange/face',basis='A')
    assert len(bands)==(1 if valley else 6)
    a.title='GARAGE / SHARED '+('VALLEY' if valley else 'EAVE')+' STRUT SUPPORT';a.front_axes=(1,2);a.section_axis=2;a.section_at=zs[0]
    a.notes.append('Source sections and continuous collector line. A finite bypass/cuts, shared folded bracket and through-web hardware. Valley strut lies below the real cap; its adopted19.75in lowering requires local engineering verification. Source member capacities are not assigned to the bracket or offset.')
