"""Source longitudinal canopy system on finite columns and struts.

Cap-angle fit and bolted knife-plate receivers are explicit adopted details;
source brace/strut selections and source bolt groups remain distinguishable.
"""
import math
from .pilots.model import add,sub,mul,unit
from .review_cfs26_primary import GLOBAL,COL_HALF,RAF_HALF,through
from .review_cfs26_purlins import N,bolted
from .review_receiver_geometry import extract,point
from .review_cfs_occurrences import axis
from .review_assemblies import hull

RID='schedules/sched-longitudinal'


def roof_bottom(x):return 168+.1*x+19.5/N[2]


def apply(b):
    if b.key!='cfs26':return
    targets={m['id'] for m in b.members if m['id'].startswith(('ES-','LONG-KB-'))}
    b.connections[:]=[c for c in b.connections if not targets.intersection(c['member_ids'])]
    b.endpoint_links[:]=[v for v in b.endpoint_links if v['member_id'] not in targets]
    lookup={m['id']:m for m in b.members}
    for m in b.members:
        if m['id'] not in targets:continue
        m['design_record_ids']=[RID];m['basis']='A'
        if m['kind']=='eave_strut':
            _,side,bay=m['id'].split('-');side=int(side);bay=int(bay);z=roof_bottom(side*360)-7
            for end in (0,1):
                into=1 if end==0 else -1;y=(bay+end)*288;m['axis'][end]=[side*360,y,z];m['end_offsets'][end]=[0,into*(RAF_HALF+.375),0]
                c=b.connection(m['id']+'-CAP'+str(end),'review_canopy_longitudinal',[side*360,y,z],[m,lookup[f'F{bay+end+1}-C{side}'],lookup[f'F{bay+end+1}-R0']],[RID],
                    parameters=dict(actual_canopy_longitudinal=True,purpose='cap',into=into,axes=GLOBAL),title='CANOPY / SOURCE STRUT CAP ANGLES')
                b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Source cap-angle end on actual column/rafter plies; A finite clip fit and local receiving bolts.'))
            m['physical_fit_basis']='S selected2x1000S25097 strut with top2in below actual roof panel; A cap fit, end clearances and exact datum, no roof load assigned.'
        else:
            _,_,side,frame,sg=m['id'].split('-',4);side=int(side);frame=int(frame);sg=int(sg);x=side*360;y=frame*288;z=roof_bottom(x)-7
            m['axis']=[[x,y,z-48],[x,y+sg*72,z]];u=unit(sub(*m['axis'][::-1]));m['local_y']=[-1,0,0]
            m['end_offsets']=[mul(u,8),mul(u,-14)]
            m['physical_fit_basis']='S4ft down x6ft along and2x600S16254. A8in column-end and14in strut-end workline setbacks keep channels clear of finite receivers; knife plates bridge these explicit gaps.'
            bay=frame if sg>0 else frame-1
            for end,host in ((0,lookup[f'F{frame+1}-C{side}']),(1,lookup[f'ES-{side}-{bay}'])):
                c=b.connection(m['id']+'-END'+str(end),'review_canopy_longitudinal',m['axis'][end],[m,host],[RID],parameters=dict(actual_canopy_longitudinal=True,purpose='brace',end=end,into=sg,axes=GLOBAL),title='CANOPY / SOURCE LONGITUDINAL BRACE END')
                b.endpoint_links.append(dict(member_id=m['id'],end='start' if end==0 else 'end',connection_id=c['id'],basis='Source two brace bolts through both actual webs and adopted knife receiver.'))
    b.used_records.add(RID)
    b.note('CANOPY-LONGITUDINAL','S:2x1000S25097 struts, top2in below roof panels, no roof load;2x600S16254 braces,4ft down x6ft along, none outboard; four5/8in strut-cap bolts and two1/2in brace bolts per end. A: exact roof datum, channel end setbacks, tall bent cap angles, column/rafter receiving bolts, and knife-plate receivers with shop-welded end plates and bolted CFS attachments. These fit additions and revised clear lengths have no new capacity check. Source longitudinal analysis is retained separately.')


def draw(ctx):
    a=ctx.a;purpose=ctx.params['purpose']
    for i,m in enumerate(ctx.ms):extract(ctx,m,'M'+str(i),GLOBAL,40)
    if purpose=='cap':cap(ctx)
    else:brace(ctx)
    a.notes.append('S member sections and source fastener groups; A actual finite cap/knife-plate fit, receiving attachments, washer envelopes and clearances. No original capacity is assigned to the adopted local attachment geometry. All CFS attachments are bolted; the added plate subassembly welds are shop welds.')


def cap(ctx):
    a=ctx.a;into=ctx.params['into'];zwork=168+.1*ctx.c['point'][0]-ctx.c['point'][2];face=RAF_HALF;web=.125/2+.1017
    a.title='CANOPY / FOUR SOURCE STRUT-CAP BOLTS'
    for sign in (-1,1):
        x=sign*web;label='CAP'+str(sign)
        a.polygon(label+'-S',[[x,into*y,z] for y,z in ((face,-2+zwork),(face+5,-2+zwork),(face+5,4),(face,4))],.25,normal=[sign,0,0],basis='A',description='A1/4in tall bent cap-angle strut leg')
        outline=((web+.25,-2+zwork),(web+3.75,-2+zwork),(web+3.75,zwork+6.5),(.7,zwork+6.5),(.7,zwork+8.2),(web+3.75,zwork+8.2),(web+3.75,4),(web+.25,4))
        a.polygon(label+'-R',[[sign*xx,into*face,z] for xx,z in outline],.25,normal=[0,into,0],basis='A',description='A receiving leg outside actual rafter web; relief clears continuous roof gusset. Bolts also pass through actual column web.')
        a.interfaces.append(dict(id=label+'-BEND',kind='formed_bend',connects=[label+'-S',label+'-R'],basis='A',description='One tall bent cap angle; bend radius and local capacity unverified'))
        cap_bolts(a,label,sign,into,web,face)
        from .review_cfs26_primary import washers
        for i,z in enumerate((zwork,zwork+3)):
            q=[sign*(web+2),into*(face+.25),z];n=[0,-into,0];grip=.25+.1017+.1242
            wa=label+'-RA'+str(i);wb=label+'-RB'+str(i)
            washers(a,wa,sub(q,mul(n,.125)),n,.5);washers(a,wb,add(q,mul(n,grip)),n,.5)
            a.fastener(label+'-RECEIVER'+str(i),[sub(q,mul(n,.125))],n,.5,grip+.25,[label+'-R','M1','M2',wa,wb],'A1/2in receiving bolt through cap, actual rafter web and column web; local capacity unverified',basis='A')
    a.front_axes=(1,2);a.section_axis=2;a.section_at=2.5
    for part in a.parts:
        if part['kind']=='rod':part['annotation_group']='F436-WASHERS'
        elif part['kind']=='fastener':part['annotation_group']='STRUT-BOLTS' if 'SOURCE' in part['id'] else 'RECEIVING-BOLTS'
    a.notes.append('A cap receiving-leg relief clears the continuous roof gusset; cap bend and strut leg stay continuous. Relief dimensions and resulting angle capacity require verification.')
    a.dim([0,0,-2.5],[0,0,2.5],'A5in source-bolt gauge',basis='A')


def cap_bolts(a,label,sign,into,web,face):
    # The general purlin helper is fixed at1/2in; caps retain source5/8in.
    from .review_cfs26_primary import washers
    for i,z in enumerate((-2.5,2.5)):
        q=[sign*(web+.25),into*(face+2.5),z];n=[-sign,0,0];grip=.25+.1017
        start=sub(q,mul(n,.125));end=add(q,mul(n,grip));wa=label+'-WA'+str(i);wb=label+'-WB'+str(i)
        washers(a,wa,start,n,.625);washers(a,wb,end,n,.625)
        a.fastener(label+'-SOURCE'+str(i),[start],n,.625,grip+.25,[label+'-S','M0',wa,wb],'S5/8in A325 strut-cap bolt; four per end; A exact gauge/grip')


def brace(ctx):
    a=ctx.a;m,h=ctx.ms;end=ctx.params['end'];sg=ctx.params['into'];origin=ctx.c['point'];ends=axis(m);u=unit(sub(ends[1-end],ends[end]));start=point(ends[end],origin,GLOBAL)
    pts=[add(start,mul(u,s)) for s in (1.5,4.5)];g=.125;t=.0566;host=[]
    if end==0:
        yy=sg*(COL_HALF+.25);host=[[0,yy,z] for z in (-4,4)]
    else:
        host=[[0,y,0] for y in (-3,3)]
    outline=hull([(p[1]+dy,p[2]+dz) for p in pts+host for dy,dz in ((-1,-1),(-1,1),(1,-1),(1,1))])
    if end==0:
        # Exact edge at the end plate; do not extend a hull into the column.
        outline=[(sg*max(abs(yy),sg*y),z) for y,z in outline]
        outline=hull(outline)
    a.polygon('KNIFE',[[-g/2,y,z] for y,z in outline],g,normal=[1,0,0],basis='A',description='A1/8in knife plate within actual back-to-back channel gap')
    through(a,'BRACE',pts,[1,0,0],.5,-g/2-t,g/2+t,['M0','KNIFE'])
    if end==1:
        through(a,'STRUT',host,[1,0,0],.5,-g/2-.1017,g/2+.1017,['M1','KNIFE'])
        for f in a.fasteners:
            if f['id'].startswith('STRUT'):f.update(basis='A',description='A two1/2in knife-to-strut bolts through actual strut webs; additional local capacity unverified')
        for part in a.parts:
            if part['id'].startswith('STRUT'):
                part['basis']='A'
                if part['kind']=='fastener':part['description']='A1/2in knife-to-strut bolt through actual strut webs; additional local capacity unverified'
    else:
        lo=sg*COL_HALF if sg>0 else -COL_HALF-.25
        a.box('ENDPLATE',[-4,lo,-5],[8,.25,10],'A','A shop-welded end plate, bolted to actual column face')
        for x in (-g/2,g/2):a.weld('KNIFE-W'+str(x),[x,yy,-4],[x,yy,4],['KNIFE','ENDPLATE'],.125,basis='A',description='A1/8in shop fillet; adopted local connection requires verification')
        bolted(a,'COLUMN',[[x,yy,z] for x in (-2.5,2.5) for z in (-3,3)],[0,-sg,0],.25+.1242,['ENDPLATE','M1'],'A four1/2in receiving bolts into actual column web','A')
    a.title='CANOPY / TWO SOURCE LONGITUDINAL BRACE BOLTS';a.front_axes=(1,2);a.section_axis=2;a.section_at=pts[0][2]
    a.dim(pts[0],pts[1],'A3in source-bolt pitch',basis='A')
