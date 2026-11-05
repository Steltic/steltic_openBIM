"""Continuous open-front strut line and actual shared column receivers."""
import math
from .review_cfs_occurrences import axis
from .review_receiver_geometry import extract
from .review_cfs_strut_ends import section_points
from .review_cfs_frame_straps import face_intervals

AXES=([1,0,0],[0,1,0],[0,0,1])
RID='schedules/sched-strap'


def apply(b):
    if b.key!='cfs28':return
    old={m['id'] for m in b.members if m['kind'] in ('open_front_strut','eave_strut')}
    b.members[:]=[m for m in b.members if m['id'] not in old]
    b.connections[:]=[c for c in b.connections if not old.intersection(c['member_ids'])]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['member_id'] not in old]
    lookup={m['id']:m for m in b.members}
    # Clear the real19in frame width; the shared bracket bridges both ends.
    for purpose,pid,x,z,roll in (('open','2X600S300-54',-10.75,171,[1,0,0]),('north','2X1200S250-97',-10.75,216,[1,0,0]),('south','800S250-97',588.2267,216,[0,0,1])):
        members=[]
        for j in range(10):
            m=b.member(f'AG-STRUT-{purpose}-{j}',pid,'open_front_strut' if purpose=='open' else 'eave_strut',[x,j*211.2,z],[x,(j+1)*211.2,z],1,'A',records=[RID],local_y=roll,physical_fit_basis='S section, full17.6ft grid span and source bracing duty. A physical bypass,10in end cut and shared folded receiver; saved capacities do not verify these local cuts/attachments.')
            m['end_offsets']=[[0,10,0],[0,-10,0]];members.append(m)
            if purpose!='south':
                for k,yy in enumerate(range(22,202,24)):
                    b.connection(m['id']+'-STITCH'+str(k),'review_ag_strut',[x,j*211.2+yy,z],[m],[RID],parameters=dict(actual_ag_strut=True,purpose='stitch'))
        for i in range(11):
            ms=[members[j] for j in (i-1,i) if 0<=j<10];host=lookup[f'F{i}-C{int(purpose=="south")}'];c=b.connection(f'AG-STRUT-NODE-{purpose}-{i}','review_ag_strut',[host['axis'][0][0],i*211.2,z],[host,*ms],[RID],parameters=dict(actual_ag_strut=True,purpose=purpose))
            for m in ms:
                end=0 if int(m['id'].rsplit('-',1)[-1])==i else 1
                b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='One shared receiver joins both finite strut ends to all three actual column pairs.'))
    b.note('AG-CONTINUOUS-STRUTS','S: the open-front2x600S30054 strut runs through all ten bays at14ft3in, maintaining14ft underside clearance; sixNo12 column-end screws. North2x1200S25097 and south800S25097 eave collectors; paired struts stitched at24in. A:10in end clearances, outward bypass, common3/16in folded brackets, through-web1/2in bolts/fit packs and local stitching groups. The source strut line is no longer limited to the two braced end bays. Exact collector receivers and capacity require verification; source member checks remain separate.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;purpose=par['purpose'];t=.1875
    if purpose=='stitch':
        m=ctx.ms[0];extract(ctx,m,'STRUT',AXES,14);webs=sorted((min(q[0] for q in poly),max(q[0] for q in poly)) for poly in section_points(m,p) if max(q[0] for q in poly)-min(q[0] for q in poly)<.3 and max(q[2] for q in poly)-min(q[2] for q in poly)>4)
        gap=round(webs[1][0]-webs[0][1],10);pid='A-AG-STRUT-STITCH-PACK';p[pid]=dict(id=pid,family='flat',dimensions=dict(width=5,thickness=gap),basis='A')
        centre=(webs[1][0]+webs[0][1])/2
        a.member('PACK',pid,[centre,-1,0],[centre,1,0],y=[0,0,1],representation_role='assembly_component',basis='A',description='A solid paired-web stitch pack')
        a.fastener('STITCH',[[webs[0][0],0,z] for z in (-1.5,1.5)],[1,0,0],.5,webs[-1][1]-webs[0][0],['STRUT','PACK'],'S24in stitch pitch / A two1/2in bolts and solid web pack',basis='S pitch / A group')
        a.title='AG STRUT / PAIRED-WEB STITCH';a.front_axes=(1,2);a.section_axis=1;a.section_at=0;return
    host=ctx.ms[0];ms=ctx.ms[1:];south=purpose=='south';out=1 if south else -1;ht=p[p[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t']
    extract(ctx,host,'COLUMN',AXES,32)
    bounds=[]
    for i,m in enumerate(ms):
        extract(ctx,m,'STRUT'+str(i),AXES,34);ends=axis(m);cut=min(ends,key=lambda q:abs(q[1]-ctx.c['point'][1]))[1]-ctx.c['point'][1];sg=1 if sum(q[1] for q in ends)/2>ctx.c['point'][1] else -1;bounds.append((i,m,cut,sg))
    low=min(cut+sg*6 for _,_,cut,sg in bounds);high=max(cut+sg*6 for _,_,cut,sg in bounds);low=min(low,-9.5);high=max(high,9.5)
    if south:
        tw=p[ms[0]['profile_id']]['dimensions']['t'];face=7;z=tw/2
        a.box('STRUT-LEG',[face,low,z],[9.2267,high-low,t],'A','A shared horizontal eave-strut web leg')
        a.box('COLUMN-LEG',[face,-9.5,-16],[t,19,16+z],'A','A dropped leg on all six actual outside flanges')
        a.interfaces.append(dict(id='FOLD',kind='formed_bend',connects=['STRUT-LEG','COLUMN-LEG'],basis='A',description='One continuous bent support'))
        for i,m,cut,sg in bounds:a.fastener('STRUT-BOLTS'+str(i),[[12.2267,cut+sg*y,z+t] for y in (1.5,4.5)],[0,0,-1],.5,t+tw,['STRUT'+str(i),'STRUT-LEG'],'A two1/2in strut-web bolts',basis='A')
        bolt_z=(-14.5,-11.5)
    else:
        webs=[]
        for poly in section_points(ms[0],p):
            if max(q[0] for q in poly)-min(q[0] for q in poly)<.3 and max(q[2] for q in poly)-min(q[2] for q in poly)>4:webs.append((min(q[0] for q in poly)-10.75,max(q[0] for q in poly)-10.75))
        webs.sort();face=webs[0][0];bottom=-2 if purpose=='open' else -5;top=2 if purpose=='open' else 5;column_bottom=-2 if purpose=='open' else -16
        a.box('STRUT-LEG',[face-t,low,bottom],[t,high-low,top-bottom],'A','A shared vertical web receiver for actual paired struts')
        a.box('BRIDGE',[face-t,-9.5,bottom],[(-7)-(face-t),19,t],'A','A continuous lower bridge reaches the column receiver above14ft clearance')
        a.box('COLUMN-LEG',[-7-t,-9.5,column_bottom],[t,19,top-column_bottom],'A','A source strut receiving face on all three real column pairs')
        a.interfaces.append(dict(id='FOLDS',kind='formed_bends',connects=['STRUT-LEG','BRIDGE','COLUMN-LEG'],basis='A',description='One continuous folded shared receiver, exact radii omitted'))
        for i,m,cut,sg in bounds:
            label='PACK'+str(i);gap=webs[1][0]-webs[0][1];a.box(label,[webs[0][1],min(cut,cut+sg*6),bottom],[gap,6,top-bottom],'A','A solid pack engages both source strut webs')
            a.fastener('STRUT-BOLTS'+str(i),[[face-t,cut+sg*y,0] for y in (1.5,4.5)],[1,0,0],.5,t+webs[-1][1]-face,['STRUT'+str(i),'STRUT-LEG',label],'A two1/2in bolts through actual paired webs and pack',basis='A')
        bolt_z=(0,) if purpose=='open' else (-14.5,-11.5)
    _,bands=face_intervals(host,p,[out,0,0])
    for i,(lo,hi,tt) in enumerate(bands):
        # For a vertical column, cross(axis,normal) = outward*Y.
        yy=(lo+hi)/2/out
        a.fastener('COLUMN'+str(i),[[out*(7+t),yy,z] for z in bolt_z],[-out,0,0],.216 if purpose=='open' else .5,t+ht,['COLUMN','COLUMN-LEG'],'S oneNo12 per actual outside flange, six total' if purpose=='open' else 'A two1/2in bolts per actual outside flange',basis='S count / A set-out' if purpose=='open' else 'A',screw=purpose=='open')
    assert len(bands)==6
    a.title='AG PORTAL / '+purpose.upper()+' SHARED STRUT SUPPORT';a.front_axes=(1,2);a.section_axis=2;a.section_at=bolt_z[0]
    a.notes.append('Source paired/open/south strut profiles and source sixNo12 open-strut column screws retained. A shared folded receiver, actual clearances, web bolts/packs and eave-column groups. Source calculations do not verify the adopted offset/cut/receiver geometry. The open-front underside remains at14ft.')
