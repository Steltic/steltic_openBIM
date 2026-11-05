"""Source 4 x 19 in cross plates tying all six braced rafter flanges.

Each plate is one located physical member shared by the paired kickers. Its
own screws connect every real flange; kicker details reference the same plate.
"""
import math
from .pilots.model import add,sub,mul,unit,cross,dot
from .review_receiver_geometry import extract,point
from .review_cfs_frame_straps import face_intervals
from .review_endwall_posts import lower_surface

AXES=([1,0,0],[0,1,0],[0,0,1])
THICKNESS=.1046


def apply(b):
    if b.key not in ('cfs17','cfs19','cfs30'):return
    members={m['id']:m for m in b.members};plates={}
    pid=b.custom('SOURCE-12GA-X4-CROSS-PLATE','flat',dict(width=4.,thickness=THICKNESS),
        basis='S: PL12ga x4 x19 in ASTM A1011 SS Gr50. A:0.1046in nominal sharp-edge drawing representation; gauge designation governs procurement.')
    for c in list(b.connections):
        data=c.get('parameters',{}).get('actual_cfs_kicker')
        if not data or c['parameters'].get('post_top'):continue
        roof=members[c['member_ids'][1]];u=unit(sub(*roof['axis'][::-1]));n=cross(u,roof['local_y'])
        if n[2]<0:n=mul(n,-1)
        sx=data['face_side'];x=data['foot_face_x']+sx*3
        q=[x,roof['axis'][0][1],lower_surface(roof,b.profiles,[x,roof['axis'][0][1]])]
        centre=add(q,mul(n,-THICKNESS/2))
        stamp=(roof['id'],round(x,6))
        if stamp not in plates:
            p=b.member('RAFTER-CROSS-'+str(len(plates)+1),pid,'flange_cross_plate',
                add(centre,[0,-9.5,0]),add(centre,[0,9.5,0]),1,'S',
                records=[b.record('schedules','sched-strap')],local_y=u,
                source_sheet_gauge='12 ga',source_plate_size_in=[4,19],
                fit_basis='A: located beneath actual braced flanges at the paired kicker foot; nominal0.1046in thickness.')
            plates[stamp]=p
            cc=b.connection(p['id']+'-SCREWS','review_kicker',centre,[p,roof],
                [b.record('schedules','sched-strap')],parameters=dict(actual_cfs_cross_plate=True,
                screws_per_flange=3 if b.key=='cfs30' else 2,stainless=b.key=='cfs30'))
            for end in ('start','end'):
                b.endpoint_links.append(dict(member_id=p['id'],end=end,connection_id=cc['id'],
                    basis='The single source cross plate is fastened to every actual braced flange by this complete assembly.'))
        c['member_ids'].append(plates[stamp]['id']);data['has_source_cross_plate']=True
    b.note('SOURCE-RAFTER-CROSS-PLATES','S: PL12ga x4 x19 in ASTM A1011 SS Gr50 across the braced rafter flanges at each paired kicker station; two No.12 screws into each flange (CFS17/19), or three1/4-14 stainless screws (CFS30). One physical plate is shared by the two kickers. A: exact set-out and nominal0.1046in drawing thickness. Source design requirements remain unchanged.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;plate,roof=ctx.ms;origin=ctx.c['point']
    u=unit(sub(*roof['axis'][::-1]));n=cross(u,roof['local_y'])
    if n[2]<0:n=mul(n,-1)
    extract(ctx,plate,'CROSS-PLATE',AXES,30);extract(ctx,roof,'RAFTER',AXES,12)
    face,intervals=face_intervals(roof,p,mul(n,-1));across=cross(u,mul(n,-1))
    count=par['screws_per_flange'];positions=(-1,0,1) if count==3 else (-1,1)
    centres=[]
    for lo,hi,rt in intervals:
        yy=(lo+hi)/2/across[1]
        if abs(yy)>9.5-.25:raise ValueError('Source19in cross plate misses a real rafter flange')
        if any(abs(yy-v)<.01 for v in centres):continue
        centres.append(yy)
        pts=[add(add(mul(u,x),[0,yy,0]),mul(n,-THICKNESS/2)) for x in positions]
        a.fastener('FLANGE'+str(len(centres)),pts,n,.25 if par['stainless'] else .216,THICKNESS+rt,
            ['CROSS-PLATE','RAFTER'],f'S {count} '+('1/4-14 stainless' if par['stainless'] else 'No.12')+' screws into this actual braced flange',screw=True)
    if len(centres)!=6:raise ValueError('Source six-ply frame cross plate must connect six actual flanges')
    a.dim([0,-9.5,0],[0,9.5,0],'S19in cross plate',basis='S')
    a.dim(mul(u,-2),mul(u,2),'S4in cross plate',basis='S')
    a.front_axes=(0,1);a.section_axis=0;a.section_at=u[0]
    a.notes.append('One source4x19in cross plate links all six actual braced flanges. Its own screw groups remain separate from the paired kicker foot screws; the same located plate is shown as a receiver in each kicker assembly.')
