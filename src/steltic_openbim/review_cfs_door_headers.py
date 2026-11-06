"""Source HSS door headers fitted to the real outer frame-column webs."""
import copy,math
from .pilots.model import add,sub,mul,unit
from .pilots.geometry import strips
from .review_receiver_geometry import extract,point

AXES=([1,0,0],[0,1,0],[0,0,1])


def outside_web(column,profiles,side):
    # These vertical source portal columns have width along Y and depth along X.
    # Select an actual web crossing the centre of the frame depth, not a lip.
    if column['local_y']!=[0,1,0]:raise ValueError('Unexpected door-frame column roll')
    webs=[]
    for poly in strips(profiles[column['profile_id']],profiles):
        us=[q[0] for q in poly];vs=[q[1] for q in poly]
        if min(vs)<-3.5 and max(vs)>3.5 and max(us)-min(us)<.3:
            face=max(us) if side>0 else min(us)
            webs.append((side*face,column['axis'][0][1]+face,max(us)-min(us)))
    if not webs:raise ValueError('No real outer column web receives this door header')
    _,face,t=max(webs);return face,t


def apply(b):
    if b.key!='cfs17':return
    members={m['id']:m for m in b.members};columns=[m for m in b.members if m['kind']=='column']
    for c in b.connections:
        if not c['member_ids'][0].startswith('DOOR-HEADER-'):continue
        m=members[c['member_ids'][0]];end=0 if c['id'].endswith(':0') else 1;side=1 if end==0 else -1
        host=min(columns,key=lambda p:math.dist(p['axis'][0][:2],m['axis'][end][:2]))
        face,t=outside_web(host,b.profiles,side);previous=copy.deepcopy(m['end_offsets'][end])
        m['end_offsets'][end]=[0,face+side*.3125-m['axis'][end][1],0]
        c['point']=[m['axis'][end][0],face,m['axis'][end][2]];c['member_ids']=[m['id'],host['id']]
        c['parameters'].update(actual_cfs_door_header=True,end=end,side=side,receiver_web_in=t)
        b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],
            basis='Actual HSS end is carried by the source angle pair at the real frame-column web.'))
        b.changes.append(dict(kind='door_header_actual_column_web',member_id=m['id'],end=end,
            previous_offset=previous,actual_column=host['id'],basis='S HSS4x4x1/8 and L4x4x1/4 clips with two1/2in A325-N bolts. A exact end extensions, paired4in-long clips, through-HSS sleeves and column-leg bolt layout.'))
    b.note('DOOR-HEADER-WEB-FIT','S: HSS4x4x1/8 headers, L4x4x1/4 clips and two1/2in A325-N header bolts; the actual six-ply frame columns are the door jambs. A: exact header end fit to the outermost accessible web, paired4in-long clips, two additional1/2in bolts per column leg and through-HSS bolt sleeves. The10.4ft clear door opening remains unchanged; new local fit capacities are not verified.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;m,column=ctx.ms;sg=par['side'];rt=par['receiver_web_in'];t=.25
    extract(ctx,m,'HEADER',AXES,30);extract(ctx,column,'COLUMN',AXES,20)
    def q(u,v,z):return [v,sg*u,z]
    for side in (-1,1):
        tag='CLIP'+str(side)
        a.polygon(tag+'-COLUMN',[q(0,side*v,z) for v,z in ((2,-2),(6,-2),(6,2),(2,2))],t,
            normal=[0,sg,0],basis='S/A',description='S4in x1/4in column leg of L4x4x1/4; A4in clip length and actual web fit')
        a.polygon(tag+'-HEADER',[q(u,side*2,z) for u,z in ((.25,-2),(4.25,-2),(4.25,2),(.25,2))],t,
            normal=[side,0,0],basis='S/A',description='S4in x1/4in header leg; A exact fitted angle position')
        a.fastener(tag+'-COLUMN-BOLTS',[q(-rt,side*3.5,z) for z in (-1,1)],[0,sg,0],.5,rt+t,
            ['COLUMN',tag+'-COLUMN'],'A two1/2in A325-N column-leg bolts',basis='A')
        a.interfaces.append(dict(id=tag+'-FOLD',kind='continuous_angle',connects=[tag+'-COLUMN',tag+'-HEADER'],
            basis='S/A',description='S L4x4x1/4; A sharp-corner bend representation'))
    ht=p[m['profile_id']]['dimensions']['t'];sleeves=[]
    pid='GARAGE-HEADER-SLEEVE';a.profiles[pid]=dict(id=pid,family='chs',dimensions=dict(d=.875,t=.125),basis='A7/8in OD,1/8in wall,5/8in clear bore')
    for i,z in enumerate((-1,1)):
        label='SLEEVE'+str(i);sleeves.append(label)
        a.member(label,pid,q(1.75,-2+ht,z),q(1.75,2-ht,z),y=[0,1,0],basis='A',description='A hollow compression sleeve bears on both HSS inner walls;1/2in bolt passes through5/8in bore',representation_role='assembly_component')
    a.fastener('HEADER-BOLTS',[q(1.75,-2-t,z) for z in (-1,1)],[1,0,0],.5,4+2*t,
        ['HEADER','CLIP-1-HEADER','CLIP1-HEADER'],
        'S two1/2in A325-N header through-bolts; A hollow-section sleeves and exact set-out')
    a.interfaces.append(dict(id='SLEEVE-BEARING',kind='compression_sleeves',connects=['HEADER']+sleeves,
        basis='A',description='A sleeves bridge the internal HSS cavity at the two through-bolts'))
    a.dim(q(1.75,0,-1),q(1.75,0,1),'A2in bolt gauge',basis='A')
    a.front_axes=(1,2);a.section_axis=2;a.section_at=1
    a.notes.append('Actual six-ply frame columns serve as the door jambs. The source HSS header reaches the outer column web between the flanges; it is not connected to a remote generic stud. S angle/bolt selections; A exact clip length, receiver bolts, sleeves and end fit.')
