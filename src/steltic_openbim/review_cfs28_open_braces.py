"""Located open-front diagonal flange restraints and their real folded feet."""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_receiver_geometry import extract
from .review_cfs28_braces import CT
from .review_cfs_frame_straps import face_intervals
from .review_assemblies import hull

AXES=([1,0,0],[0,1,0],[0,0,1])
RID='schedules/sched-strap'


def apply(b):
    if b.key!='cfs28':return
    lookup={m['id']:m for m in b.members};pid=b.custom('AG-SOURCE-CROSS-PLATE','flat',dict(width=4,thickness=CT),basis='S12ga nominal0.1046in representation')
    for i in range(11):
        y=i*211.2;host=lookup[f'F{i}-C0'];plate=b.member(f'AG-OPEN-CROSS-{i}',pid,'flange_cross_plate',[7+CT/2,y-9.5,162],[7+CT/2,y+9.5,162],1,'S',records=[RID],local_y=[0,0,1],source_plate_size_in=[4,19])
        c=b.connection(plate['id'],'review_ag_open_brace',[0,y,162],[plate,host],[RID],parameters=dict(actual_ag_open_brace=True,purpose='plate'))
        for end in ('start','end'):b.endpoint_links.append(dict(member_id=plate['id'],end=end,connection_id=c['id'],basis='Source12ga4x19in cross plate at13ft6in with twoNo12 screws in each actual inside flange.'))
        for hand in (-1,1):
            direction=1 if i==0 else -1 if i==10 else hand;bay=i if direction>0 else i-1;strut=lookup[f'AG-STRUT-open-{bay}']
            aa=[8.3546,y+hand*8,162];dx=-10.0-aa[0];run=math.sqrt(30.9**2-dx**2-9**2);dd=[-10,y+hand*8+direction*run,171];along=unit(sub(dd,aa));normal=unit(cross(along,[0,0,1]));wy=cross(normal,along)
            m=b.member(f'AG-OPEN-FLY-{i}-{hand}','L2X2X1/8','flange_brace',aa,dd,1,'A',records=[RID],local_y=wy,source_kicker_length_in=30.9,
                physical_fit_basis='S30.9in L2x2x1/8 and twoNo12 per end, source inside-flange station162in/open strut171in. A exact3D roll, inward last-frame hand and two folded feet; source direction-cosine/stiffness checks not reassigned.')
            cc=b.connection(m['id'],'review_ag_open_brace',[0,y,162],[m,host,strut,plate],[RID],parameters=dict(actual_ag_open_brace=True,purpose='brace',normal=normal,hand=hand,direction=direction))
            for end in ('start','end'):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=cc['id'],basis='Actual finite30.9in brace, folded feet, inside-flange cross plate and real open-strut web.'))
    b.note('AG-OPEN-FLANGE-BRACES','S:two L2x2x1/8 braces per open-side column,30.9in source length and twoNo12 screws each end;12ga4x19in plate at13ft6in joins all six inside flanges with twoNo12 each. Strut axis14ft3in retains14ft clear underside. A:outward strut bypass,3D angle roll, exact feet, end-frame hands and local screw gauges; source0.78 direction cosine and stiffness are retained as source requirements and not claimed for this changed fitting.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;origin=ctx.c['point']
    if par['purpose']=='plate':
        plate,host=ctx.ms;extract(ctx,plate,'PLATE',AXES,30);extract(ctx,host,'COLUMN',AXES,20);ht=p[p[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];_,bands=face_intervals(host,p,[1,0,0])
        for i,(lo,hi,t) in enumerate(bands):a.fastener('FLANGE'+str(i),[[7+CT,(lo+hi)/2,z] for z in (-1,1)],[-1,0,0],.216,CT+ht,['PLATE','COLUMN'],'S twoNo12 into this real inside flange',basis='S count / A gauge',screw=True)
        assert len(bands)==6
        a.title='AG OPEN FRONT / SOURCE INSIDE CROSS PLATE';a.front_axes=(1,2);a.section_axis=2;a.section_at=1;return
    angle,host,strut,plate=ctx.ms
    for label,m in zip(('ANGLE','COLUMN','STRUT','CROSS-PLATE'),ctx.ms):extract(ctx,m,label,AXES,48)
    aa,dd=[sub(q,origin) for q in angle['axis']];along=unit(sub(dd,aa));wy=angle['local_y'];normal=par['normal'];ct=.125;at=.125
    ht=p[p[host['profile_id']]['components'][0]['profile_id']]['dimensions']['t'];sp=p[strut['profile_id']];st=p[sp['components'][0]['profile_id']]['dimensions']['t'];web=.0625+st
    for name,end,face,thickness,receivers in (('LOW',0,7+CT,CT+ht,['CROSS-PLATE','COLUMN']),('HIGH',1,-10.75+web,st,['STRUT'])):
        near=aa if end==0 else dd;direction=1 if end==0 else -1
        qs=[add(near,add(mul(along,direction*s),wy)) for s in (1,2.5)]
        # A bent clip follows the exact angle-leg plane and the actual
        # vertical receiver plane. Their intersection is a vertical fold.
        scalar=dot(aa,normal)-ct;fold_y=(scalar-normal[0]*(face+ct))/normal[1];tangent=[-normal[1],normal[0],0]
        fold=[face+ct,fold_y,0];fold_s=dot(fold,tangent);data=[(fold_s,min(q[2] for q in qs)-.5),(fold_s,max(q[2] for q in qs)+.5)]
        data += [(dot(q,tangent)+ds,q[2]+dz) for q in qs for ds,dz in ((-.35,-.35),(-.35,.35),(.35,-.35),(.35,.35))]
        vertices=[add(mul(normal,scalar),add(mul(tangent,s),[0,0,z])) for s,z in hull(data)]
        a.polygon(name+'-ANGLE',vertices,ct,normal=normal,basis='A',description='A1/8in actual-angle-plane leg of one folded foot')
        receive_y=par['hand']*8 if end==0 else sum(q[1] for q in qs)/2
        receive_z=(-1,1) if end==0 else (8,10)
        lo,hi=sorted((fold_y,receive_y));lo-=.4;hi+=.4;z0=min(min(q[2] for q in qs)-.5,min(receive_z)-.5);z1=max(max(q[2] for q in qs)+.5,max(receive_z)+.5)
        a.polygon(name+'-HOST',[[face,y,z] for y,z in ((lo,z0),(hi,z0),(hi,z1),(lo,z1))],ct,normal=[1,0,0],basis='A',description='A folded receiver leg on the real column cross plate or open-strut web')
        a.interfaces.append(dict(id=name+'-FOLD',kind='formed_bend',connects=[name+'-ANGLE',name+'-HOST'],basis='A',description='Continuous bent foot along the vertical intersection; bend radius omitted'))
        a.fastener(name+'-ANGLE-S',[sub(q,mul(normal,ct)) for q in qs],normal,.216,ct+at,['ANGLE',name+'-ANGLE'],'S twoNo12 at brace end / A folded foot',basis='S group / A fit',screw=True)
        a.fastener(name+'-HOST-S',[[face+ct,receive_y,z] for z in receive_z],[-1,0,0],.216,ct+thickness,[name+'-HOST',*receivers],'A twoNo12 from folded foot into actual receiver',basis='A',screw=True)
    a.title='AG OPEN FRONT / SOURCE30.9in FLANGE BRACE';a.front_axes=(1,2);a.section_axis=2;a.section_at=1
    a.dim(aa,dd,'S30.9in angle',basis='S');a.notes.append('Source twoNo12 per brace end, L2x2x1/8 and30.9in length retained. A exact3D roll and folded feet connect the actual inside-flange cross plate at13ft6in to the actual open strut at14ft3in. Source stiffness/direction-cosine and local receiving capacities require verification for this adopted fit.')
