"""Source eave struts meet the wall skin through actual shared end supports."""
from .review_receiver_geometry import extract
from .review_cfs_occurrences import axis
AXES=([1,0,0],[0,1,0],[0,0,1])


def apply(b):
    if b.key!='cfs27':return
    lookup={m['id']:m for m in b.members};members=[m for m in b.members if m['id'].startswith('EAVE-')];ids={m['id'] for m in members}
    old={c['id'] for c in b.connections if ids.intersection(c['member_ids'])}
    b.connections[:]=[c for c in b.connections if c['id'] not in old]
    b.endpoint_links[:]=[r for r in b.endpoint_links if r['connection_id'] not in old]
    for m in members:
        _,side,bay=m['id'].split('-');side=int(side);bay=int(bay);out=-1 if side==0 else 1
        # Source wall-panel restraint requires the C's outside flange to meet
        # the same plane as the outermost nested girt flange.
        m['local_y']=[0,0,1];m['end_offsets']=[[out*11.8066,3.25,0],[out*11.8066,-3.25 if bay==29 else -.5,0]]
        m['physical_fit_basis']='S800S25054 eave strut restrained by wall skin. A horizontal-depth roll and outward placement make its flange meet the actual wall-sheet plane; shared dropped brackets reach the finite column. Source capacities are not assigned to this changed fit.'
    for side in (0,1):
        for frame in range(31):
            ms=[lookup[f'EAVE-{side}-{bay}'] for bay in (frame-1,frame) if 0<=bay<30];host=lookup[f'F{frame}-C{side}']
            c=b.connection(f'SC-EAVE-NODE-{side}-{frame}','review_single_strut',[432*side,78*frame,192],[host,*ms],['schedules/sched-strap'],parameters=dict(actual_single_strut=True,side=side,hand=-1 if frame==30 else 1),title='SINGLE CHANNEL / SHARED EAVE-STRUT SUPPORT')
            for m in ms:
                end=0 if int(m['id'].split('-')[-1])==frame else 1
                b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='One actual common column bracket serves incoming/outgoing eave struts; the source wall-sheet restraint has a physical flange interface.'))
    b.note('SINGLE-STRUT-ENDS','S800S25054 eave struts at6.5ft spans, wall-sheet restrained. A horizontal-depth orientation and outward fit align their outer flanges with the wall skin. Finite end cuts clear columns; one1/4in shared dropped support per column avoids overlapping independent clips, with two1/2in bolts per strut and four1/2in column-flange bolts. These geometry/attachment choices require verification; saved capacities remain separate.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;host=ctx.ms[0];ms=ctx.ms[1:];out=-1 if par['side']==0 else 1;hand=par['hand'];ct=.25;tw=.0566;ht=p[host['profile_id']]['dimensions']['t'];face=7*out
    extract(ctx,host,'COLUMN',AXES,32);points=[]
    for i,m in enumerate(ms):
        extract(ctx,m,'STRUT'+str(i),AXES,30)
        ends=axis(m);near=min(ends,key=lambda q:abs(q[1]-ctx.c['point'][1]));cut=near[1]-ctx.c['point'][1];into=1 if sum(q[1] for q in ends)/2>ctx.c['point'][1] else -1
        points.append((i,[[out*11.8066,cut+into*y,tw/2+ct] for y in (1.5,4.5)]))
    ys=[q[1] for _,pts in points for q in pts]+[0,hand*3];lo=min(ys)-1;hi=max(ys)+1
    a.polygon('STRUT-LEG',[[x,y,tw/2] for x,y in ((face,lo),(out*15.3,lo),(out*15.3,hi),(face,hi))],ct,normal=[0,0,1],basis='A',description='A common horizontal1/4in strut-web leg; one plate across the finite end gap')
    a.polygon('COLUMN-LEG',[[face,y,z] for y,z in ((0,-16),(hand*3,-16),(hand*3,tw/2),(0,tw/2))],ct,normal=[out,0,0],basis='A',description='A dropped receiving leg on the actual column outside flange, below the knee cut')
    a.interfaces.append(dict(id='BEND',kind='formed_bend',connects=['STRUT-LEG','COLUMN-LEG'],basis='A',description='One continuous folded support; exact developed outline and bend radius need verification'))
    for i,qs in points:a.fastener('STRUT-BOLTS'+str(i),qs,[0,0,-1],.5,ct+tw,['STRUT'+str(i),'STRUT-LEG'],'A two1/2in bolts through actual horizontal strut web',basis='A')
    qs=[[out*(7+ct),hand*y,z] for y in (.75,2.25) for z in (-14.5,-11.5)]
    a.fastener('COLUMN-BOLTS',qs,[-out,0,0],.5,ct+ht,['COLUMN','COLUMN-LEG'],'A four1/2in bolts into actual finite column outside flange',basis='A')
    a.title='SINGLE CHANNEL / SHARED EAVE-STRUT SUPPORT';a.front_axes=(1,2);a.section_axis=2;a.section_at=-14.5
    a.notes.append('The source C struts now have actual outer flanges at the wall-sheet plane. A offsets, roll, common folded support and receiving bolts are adopted fit; original local and member capacities are not extended to these changes. One shared bracket prevents coincident incoming/outgoing support plates.')

