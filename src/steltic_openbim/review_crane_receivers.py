"""Actual HR33 crane receivers and explicit fictional fitting proposals.

Source seat bolt counts and tie plate/bolt selections are retained. Receiver
plates and rail-clip geometry are A proposals, not fatigue/capacity approvals.
"""
import copy,math
from .pilots.model import sub,add,mul
from .review_receiver_geometry import extract,horizontal_frame,point

AXES=([1,0,0],[0,1,0],[0,0,1])


def ends(m):return [add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]


def apply(b):
    if b.key!='hr33':return
    b.endpoint_links=getattr(b,'endpoint_links',[])
    lookup={m['id']:m for m in b.members};remove=set()
    for c in b.connections:
        f=c['detail_ref']['id'];m=lookup[c['member_ids'][0]]
        if f=='review_crane_bracket':
            col=lookup[c['member_ids'][1]];sign=1 if m['axis'][1][1]>m['axis'][0][1] else -1
            face=b.depth(col['profile_id'])/2
            previous=copy.deepcopy(m['end_offsets'])
            m['end_offsets'][0][1]=col['axis'][0][1]+sign*face-m['axis'][0][1]
            for off in m['end_offsets']:off[2]-=1
            c.setdefault('parameters',{})['actual_crane_joint']='bracket'
            c['parameters']['sign']=sign
            c['coordination_requirements']=[
                'A: the accepted 30 in runway workline gives a reaction lever of '+str(30-face)+' in from the actual column flange. The saved bracket calculation uses 9 in. Its fatigue/capacity result does not verify this geometry; retain the source design and require bracket/crane coordination before construction.',
                'A: lower the bracket 1 in to receive the added 1 in bearing cap while retaining the source 28 ft rail-top datum.']
            c['engineering_status']='source_condition_mismatch_proposed_fit_not_verified'
            m['design_record_ids'].append(b.record('members','crane-bracket-W16X57'))
            for end in ('start','end'):
                b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],
                    basis='Actual cantilever bracket is welded to the column in this assembly; its outer cut is a free projection beyond the located girder bearing, not a separate field joint.'))
            b.changes.append(dict(kind='crane_actual_bracket_receiver',member_id=m['id'],previous_offsets=previous,
                offsets=copy.deepcopy(m['end_offsets']),source_record_ids=c['design_record_ids'],
                source_reaction_lever_in=9,adopted_reaction_lever_in=30-face,
                basis='S W16X57 and flange CJP/web fillets. A source-condition conflict retained explicitly; no new fatigue/capacity verification.'))
        elif f=='review_crane_seat' and m['kind']=='crane_bracket':
            # A runway end owns its real seat. The old bracket loop emitted a
            # second detached copy of each of those same connections.
            remove.add(c['id'])
    b.connections[:]=[c for c in b.connections if c['id'] not in remove]
    brackets=[m for m in b.members if m['kind']=='crane_bracket']
    for c in b.connections:
        f=c['detail_ref']['id'];m=lookup[c['member_ids'][0]]
        if f=='review_crane_seat':
            if m['kind']!='runway_beam':raise ValueError('Unexpected crane seat primary')
            bracket=min(brackets,key=lambda v:math.dist(v['axis'][0][:2],c['point'][:2]))
            side,index=m['id'].split('-')[1:];cap=lookup[f'RUNWAY-CAP-{side}-{index}']
            into=1 if abs(c['point'][0]-m['axis'][0][0])<.01 else -1
            c['member_ids']=[m['id'],bracket['id'],cap['id']]
            c.setdefault('parameters',{}).update(actual_crane_joint='seat',into=into,
                bracket_grid_x=bracket['axis'][0][0],bearing_cap_in=1.)
        elif f=='review_crane_tie':
            side,index=m['id'].split('-')[2:];run=lookup[f'RUNWAY-{side}-{index}']
            bracket=min(brackets,key=lambda v:math.dist(v['axis'][0][:2],c['point'][:2]))
            column=next(lookup[v['member_ids'][1]] for v in b.connections if v['id']==bracket['id'])
            into=1 if abs(c['point'][0]-m['axis'][0][0])<.01 else -1
            c['member_ids']=[m['id'],column['id'],run['id']]
            c.setdefault('parameters',{}).update(actual_crane_joint='tie',into=into,
                sign=1 if int(side)==0 else -1,column_grid_x=bracket['axis'][0][0])
        elif f=='review_rail_clip':
            # Replace two end-only generic clips by accepted supplier stations
            # on the actual cap. Each rail remains one continuous source piece.
            remove.add(c['id'])
    b.connections[:]=[c for c in b.connections if c['id'] not in remove]
    for rail in [m for m in b.members if m['kind']=='crane_rail']:
        side,index=rail['id'].split('-')[1:];cap=lookup[f'RUNWAY-CAP-{side}-{index}'];run=lookup[f'RUNWAY-{side}-{index}']
        start,end=rail['axis'][0][0],rail['axis'][1][0]
        stations=[start+1.5+i*24 for i in range(math.floor((end-start-3)/24)+1)]+[end-1.5]
        made=[]
        for i,x in enumerate(stations):
            c=b.connection(rail['id']+f':CLIP-{i}','review_rail_clip',[x,rail['axis'][0][1],rail['axis'][0][2]],
                [rail,cap,run],parameters=dict(actual_crane_joint='rail_clip',runway_profile=run['profile_id']),basis='A')
            made.append(c)
        for endname,c in zip(('start','end'),(made[0],made[-1])):
            b.endpoint_links.append(dict(member_id=rail['id'],end=endname,connection_id=c['id'],
                basis='A floating rail-clip pair at the adjacent 1.5 in end station. Supplier rail splice and longitudinal restraint verification remain explicit requirements.'))
    b.note('CRANE-RECEIVER-FIT','S: W16X57 brackets, four 7/8 in A325-SC seat bolts per girder end, 1/8 in steel bearing and 1/2 in unspliced girder gap; vertical 3/8 x 8 x 24 in tie plates with two 3/4 in A325-SC bolts each end and no plate welds. A: 1 in bearing cap, tie receiver lugs and floating rail clips at maximum24 in spacing. The accepted30 in runway inset gives a larger bracket lever than the source9 in check: the saved strength/fatigue results do not verify it. All added receiving plates, their welds, local column/cap effects, rail splices and supplier clip capacity require separate verification.')


def draw(ctx):
    kind=ctx.params['actual_crane_joint']
    return {'bracket':bracket,'seat':seat,'tie':tie,'rail_clip':rail_clip}[kind](ctx)


def bracket(ctx):
    a,p=ctx.a,ctx.p;m,col=ctx.ms;axes=horizontal_frame(sub(*m['axis'][::-1]))
    bm=extract(ctx,m,'BRACKET',axes,48);cm=extract(ctx,col,'COLUMN',axes,36)
    dims=p[m['profile_id']]['dimensions'];face=bm['member']['axis'][0][0];z=bm['member']['axis'][0][2]
    for sg in (-1,1):
        zz=z+sg*(dims['d']/2-dims['tf']/2)
        a.weld('FLANGE'+str(sg),[face,-dims['bf']/2,zz],[face,dims['bf']/2,zz],['BRACKET','COLUMN'],dims['tf'],'CJP',description='S bracket flange CJP; reinforcement left, source Category C')
        a.weld('WEB'+str(sg),[face,sg*dims['tw']/2,z-dims['d']/2+dims['tf']],
            [face,sg*dims['tw']/2,z+dims['d']/2-dims['tf']],['BRACKET','COLUMN'],.375,description='S 3/8 in web fillet, each side')
    # The member design explicitly requires full-depth bearing stiffeners.
    # Thickness/welds are A selections because the saved check gives no sizes.
    for sg in (-1,1):
        label='BEARING-STIFFENER'+str(sg);yy=dims['tw']/2 if sg>0 else -dims['bf']/2
        bottom=z-dims['d']/2+dims['tf'];top=z+dims['d']/2-dims['tf']
        a.box(label,[30-.25,yy,bottom],[.5,(dims['bf']-dims['tw'])/2,top-bottom],
            'S required stiffener; A thickness','S full-depth bearing stiffener beneath the runway; A1/2 in plate/local welds unverified')
        for zz in (bottom,top):a.weld(label+str(zz),[30,yy,zz],[30,yy+(dims['bf']-dims['tw'])/2,zz],['BRACKET',label],.25,basis='A')
        a.weld(label+'-WEB',[30,sg*dims['tw']/2,bottom],[30,sg*dims['tw']/2,top],['BRACKET',label],.25,basis='A')
    a.notes.extend(ctx.c['coordination_requirements']);a.section_axis=0;a.section_at=face+1
    a.dim([face,0,z],[30,0,z],'A reaction lever; source check is9 in',basis='A')


def seat(ctx):
    a,p=ctx.a,ctx.p;run,bm,cap=ctx.ms;origin=ctx.c['point'];into=ctx.params['into']
    rp=extract(ctx,run,'RUNWAY',AXES,24);bp=extract(ctx,bm,'BRACKET',AXES,36);extract(ctx,cap,'CAP-CHANNEL',AXES,24)
    rd=p[run['profile_id']]['dimensions'];bd=p[bm['profile_id']]['dimensions'];z=bp['bounds'][2][1];gx=ctx.params['bracket_grid_x']-origin[0]
    # Independent half caps preserve the source girder gap. They are welded
    # only to the bracket, never across the two simple-span girder ends.
    x0=gx+.25 if into>0 else gx-7;length=6.75
    a.box('BEARING-CAP',[x0,-6,z],[length,12,1],'A','A 1 in cap half: four source seat bolts fit inside actual steel')
    a.box('BEARING',[x0,-rd['bf']/2,z+1],[length,rd['bf'],.125],'S thickness; A length','S 1/8 in elastomeric-free steel bearing')
    xx=[gx+into*v for v in (1.75,4.75)]
    a.fastener('SEAT-BOLTS',[[x,y,z] for x in xx for y in (-2.5,2.5)],[0,0,1],.875,1+.125+rd['tf'],
        ['BEARING-CAP','BEARING','RUNWAY'],'S four 7/8 in A325-SC, Class A; source 2.5 in each side of web; A3 in longitudinal pitch')
    for sg in (-1,1):
        x=gx+sg*bd['bf']/2
        if x0<=x<=x0+length:
            ya=max(-6,bp['bounds'][1][0]);yb=min(6,bp['bounds'][1][1])
            a.weld('CW'+str(sg),[x,ya,z],[x,yb,z],['BRACKET','BEARING-CAP'],.25,basis='A',description='A cap-to-bracket edge fillet; cap/local flange capacity unverified')
    a.interfaces.extend([
        dict(id='CAP-BEARING',kind='compression_bearing',connects=['BRACKET','BEARING-CAP'],basis='A',description='A cap half bears on actual bracket top flange'),
        dict(id='GIRDER-BEARING',kind='compression_bearing',connects=['BEARING','RUNWAY'],basis='S',description='Actual girder bottom flange bears on source steel bearing')])
    a.front_axes=(0,2);a.section_axis=0;a.section_at=xx[0]
    a.dim([gx,0,z],[gx+into*7,0,z],'A half cap extent',basis='A')
    a.notes.append('The actual W16 flange cannot accommodate two longitudinal bolt rows beneath each side of the1/2 in girder gap. A separate1 in cap half provides that receiving steel; all four source bolts and source gauge retained. Cap, welds, local flange bending and fatigue are unverified. The two runway girders remain unspliced.')


def tie(ctx):
    a,p=ctx.a,ctx.p;cap,col,run=ctx.ms;sg=ctx.params['sign'];into=ctx.params['into'];origin=ctx.c['point']
    extract(ctx,cap,'CAP-CHANNEL',AXES,32);cp=extract(ctx,col,'COLUMN',AXES,42);extract(ctx,run,'RUNWAY',AXES,32)
    cd=p[col['profile_id']]['dimensions'];gridx=ctx.params['column_grid_x']-origin[0]
    # Outside the column flange width, the plate clears the real flange and
    # reaches the cap underside without intersecting the rail above the cap.
    lugx=gridx+into*(cd['bf']/2);tieface=lugx+into*.375
    cy=col['axis'][0][1]-origin[1];face=cy+sg*cd['d']/2
    web_bottom=cap['axis'][0][2]+cap['end_offsets'][0][2]-p[cap['profile_id']]['dimensions']['t']/2-origin[2]
    low=web_bottom-8;near=face-sg*3;far=face+sg*21
    a.box('TIE',[min(tieface,tieface+into*.375),min(near,far),low],[.375,24,8],'S','S vertical3/8 x8 x24 plate; thin direction along runway; no welds')
    for index,(ya,yb) in enumerate(((near,face),(face+sg*18,far))):
        label='LUG'+str(index);a.box(label,[min(lugx,tieface),min(ya,yb),low],[.375,3,8],'A','A3/8 in receiver lug; source tie plate remains unwelded')
        yy=(ya+yb)/2
        a.fastener('TB'+str(index),[[tieface+into*.375,yy,low+zz] for zz in (2,6)],[-into,0,0],.75,.75,[label,'TIE'],
            'S two3/4 in A325-SC bolts at each end; A4 in vertical pitch and fitted receiver lug')
        if index==0:
            for y in (face,face-sg*cd['tf']):
                a.weld('LC'+str(y),[lugx,y,low],[lugx,y,web_bottom],['COLUMN',label],.25,basis='A',description='A lug fillet at actual outer column-flange edge; local/fatigue capacity unverified')
        else:
            a.weld('LR',[lugx,ya,web_bottom],[lugx,yb,web_bottom],['CAP-CHANNEL',label],.25,basis='A',description='A lug fillet to actual cap-channel web underside')
    a.front_axes=(1,2);a.section_axis=2;a.section_at=low+4
    a.dim([tieface,near,low],[tieface,far,low],'S24 in plate /18 in between lugs',basis='S')
    a.notes.append('Source flexible vertical tie plate, four source bolts and18 in clear length between receiving lugs are retained. A outboard receiver lugs fit the real column flange edge and cap underside. No weld is placed on the tie plate; added lug welds/local effects/fatigue remain unverified.')


def rail_clip(ctx):
    a,p=ctx.a,ctx.p;rail,cap,run=ctx.ms
    rr=extract(ctx,rail,'RAIL',AXES,18);cc=extract(ctx,cap,'CAP-CHANNEL',AXES,18);extract(ctx,run,'RUNWAY',AXES,18)
    rd=p[rail['profile_id']]['dimensions'];ct=p[cap['profile_id']]['dimensions']['t'];top=cc['bounds'][2][1]
    for sg in (-1,1):
        toe=sg*(rd['bf']/2-.5);outer=sg*(rd['bf']/2+2.5);label='CLIP'+str(sg);bolt_y=sg*(rd['bf']/2+1.5)
        # Separate toe and heel make the actual clearance and support visible.
        # It is a fictional floating clip envelope, not a supplier approval.
        a.box(label,[ -2,min(toe,outer),top+rd['tf']+.0625],[4,3,.5],'A','A floating clip with1/16 in rail-toe clearance')
        a.box('HEEL'+str(sg),[-2,min(sg*(rd['bf']/2+.5),outer),top],[4,2,rd['tf']+.0625],'A','A clip heel bearing on actual cap web')
        a.fastener('CB'+str(sg),[[0,bolt_y,top-ct]],[0,0,1],.625,ct+rd['tf']+.0625+.5,
            ['CAP-CHANNEL','HEEL'+str(sg),label],'A5/8 in supplier clip bolt; actual cap web/heel/clip grip',basis='A')
        a.interfaces.append(dict(id='FLOAT'+str(sg),kind='floating_rail_clip',connects=['RAIL',label],basis='A',
            description='A1/16 in toe clearance permits longitudinal rail movement; supplier clip capacity and rail splice verification remain required'))
    a.section_axis=0;a.section_at=0
    a.notes.append('Actual source cap-channel location and adopted85 lb rail envelope. A floating clip pairs at maximum24 in spacing,1/16 in toe clearance and5/8 in clip bolts. No longitudinal fixity or verified supplier product is implied.')
