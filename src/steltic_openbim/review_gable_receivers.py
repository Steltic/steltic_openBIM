"""Saved HR31 knee/cap selections at their actual physical member datums."""
import copy,math
from .pilots.model import add,sub,mul,unit,cross
from .review_receiver_geometry import horizontal_frame,extract,point
from .assembly_scene import clip_part


def apply(b):
    lookup={m['id']:m for m in b.members}
    for c in b.connections:
        if c['detail_ref']['id']=='review_hr_gable_knee':
            rafter,column=[lookup[mid] for mid in c['member_ids']]
            u=unit(sub(*rafter['axis'][::-1]));h=math.hypot(u[0],u[1]);slope=u[2]/h
            x=[u[0]/h,u[1]/h,0];y=cross([0,0,1],x)
            # The saved knee is explicitly bolted to a loaded column flange.
            # Its physical roll must present that flange to the hall rafter.
            old=copy.deepcopy(column['local_y']);column['local_y']=y
            d=b.profiles[column['profile_id']]['dimensions'];rd=b.depth(rafter['profile_id'])
            face=d['d']/2;ep=face+1;upper=slope*ep+rd*math.sqrt(1+slope*slope)/2
            end=max(range(2),key=lambda i:column['axis'][i][2]);previous=copy.deepcopy(column['end_offsets'][end])
            column['end_offsets'][end][2]=c['point'][2]+upper+3.625-column['axis'][end][2]
            c.setdefault('parameters',{})['actual_gable_knee']=dict(face_in=face,end_plate_face_in=ep,
                slope=slope,flange_upper_in=upper,flange_lower_in=slope*ep-rd*math.sqrt(1+slope*slope)/2)
            b.changes.append(dict(kind='source_gable_knee_column_fit',member_id=column['id'],source_record_ids=c['design_record_ids'],
                previous_local_y=old,local_y=list(y),previous_offset=previous,end_offset=copy.deepcopy(column['end_offsets'][end]),
                basis='S: loaded flange knee and column top 3.625 in above sloping rafter top flange. A: physical column roll aligned to that flange and slope-correct set-out. Original analysis axis and design evidence retained.'))
        elif c['detail_ref']['id']=='review_column_cap' and c.get('parameters',{}).get('bearing_girder'):
            column,beam=[lookup[mid] for mid in c['member_ids'][:2]]
            bottom=beam['axis'][0][2]+beam['end_offsets'][0][2]-b.depth(beam['profile_id'])/2
            end=max(range(2),key=lambda i:column['axis'][i][2]);old=copy.deepcopy(column['end_offsets'][end])
            column['end_offsets'][end][2]=bottom-.75-column['axis'][end][2]
            c['parameters']['actual_bearing_cap']=True
            b.changes.append(dict(kind='source_office_column_cap_bearing_datum',member_id=column['id'],
                previous_offset=old,end_offset=copy.deepcopy(column['end_offsets'][end]),beam_id=beam['id'],
                source_record_ids=c['design_record_ids'],basis='S: 3/4 in cap beneath the actual girder bottom flange. A physical column cut; the office roof TOS and analysis workline are unchanged.'))


def knee(ctx):
    a,p=ctx.a,ctx.p;rafter,column=ctx.ms;data=ctx.params['actual_gable_knee']
    axes=horizontal_frame(sub(*rafter['axis'][::-1]));origin=ctx.c['point']
    col=extract(ctx,column,'COLUMN',axes,60);rf=extract(ctx,rafter,'RAFTER',axes,60)
    cp=p[column['profile_id']]['dimensions'];rp=p[rafter['profile_id']]['dimensions']
    face,ep=data['face_in'],data['end_plate_face_in'];lo,hi=data['flange_lower_in'],data['flange_upper_in'];top=hi+3.625
    clip_part(rf,[1,0,0],ep)
    a.box('CAP',[-cp['d']/2,-cp['bf']/2,top],[cp['d'],cp['bf'],.5],'S','Separate source 1/2 in column cap; not a transverse stiffener')
    a.box('EP',[face,-5.5,lo-3.625],[1,11,hi-lo+7.25],'S','Source 1 x 11 in 4E end plate; A slope-correct height and mitre fit')
    a.fastener('B1',[[face-cp['tf'],y,z] for y in (-3.25,3.25) for z in (lo-2,lo+2,hi-2,hi+2)],
        [1,0,0],1.25,cp['tf']+1,['COLUMN','EP'],'S eight 1-1/4 in A490 bolts; A 6.5 in gauge and slope-correct flange stations')
    for j,(z,t) in enumerate(((hi,.875),(lo,.625))):
        for sign in (-1,1):
            y=cp['tw']/2 if sign>0 else -cp['tw']/2-4.25;name=f'S{j}{sign}'
            a.box(name,[-cp['d']/2+cp['tf'],y,z-t/2],[cp['d']-2*cp['tf'],4.25,t],'S','Source full-depth transverse stiffener; A corner clip development')
            a.weld('WF'+name,[face-cp['tf'],y,z],[face-cp['tf'],y+4.25,z],['COLUMN',name],t,'CJP')
            a.weld('WW'+name,[-cp['d']/2+cp['tf'],sign*cp['tw']/2,z],[face-cp['tf'],sign*cp['tw']/2,z],['COLUMN',name],.1875)
    a.box('DOUBLER',[-cp['d']/2+cp['tf'],cp['tw']/2,lo+.3125],
        [cp['d']-2*cp['tf'],.25,hi-lo-.75],'S','Source 1/4 in web doubler between actual flange stiffeners')
    a.weld('WD',[face-cp['tf'],cp['tw']/2,lo],[face-cp['tf'],cp['tw']/2,hi],['COLUMN','DOUBLER'],.25,'CJP')
    for tag,z in [('LOW',lo),('HIGH',hi)]:a.weld('RF'+tag,[ep,-rp['bf']/2,z],[ep,rp['bf']/2,z],['RAFTER','EP'],rp['tf'],'CJP')
    a.weld('RW',[ep,0,lo+rp['tf']],[ep,0,hi-rp['tf']],['RAFTER','EP'],.375)
    for sign in (-1,1):a.weld('CAP'+str(sign),[-cp['d']/2,sign*cp['bf']/2,top],[cp['d']/2,sign*cp['bf']/2,top],['COLUMN','CAP'],.25,basis='A',description='Source cap perimeter fillet; A 1/4 in size')
    a.dim([face,0,lo-3.625],[face,0,top],'A slope-correct plate height',basis='A');a.section_axis=2;a.section_at=hi
    a.notes.append('S: 3:12 source rafter, loaded column flange, eight A490 bolts, separate 1/2 in cap, 7/8 in upper / 5/8 in lower stiffeners and 1/4 in doubler. A: actual column roll, flange/bolt set-out and local plate fit. Mitre and stiffener corner clips remain design-detail geometry, not issued fabrication cuts; no new capacity verification.')


def bearing_cap(ctx):
    a,p=ctx.a,ctx.p;column,beam=ctx.ms[:2];axes=horizontal_frame(sub(*beam['axis'][::-1]))
    col=extract(ctx,column,'COLUMN',axes,45);girder=extract(ctx,beam,'GIRDER',axes,30)
    top=max(q[2] for q in col['member']['axis']);t=.75
    a.box('CAP',[-6,-5,top],[12,10,t],'S','Source 3/4 x 10 x 12 in cap beneath the actual girder')
    cp=p[column['profile_id']]['dimensions'];bounds=col['bounds'];tf=p[beam['profile_id']]['dimensions']['tf']
    # Both bolts lie on the actual end extract; a second adjacent span owns
    # its separate connection if present.
    xs=girder['bounds'][0];x=max(xs[0]+1.5,min(xs[1]-1.5,0))
    gauge=min(2.,p[beam['profile_id']]['dimensions']['bf']/2-.75)
    a.fastener('BG',[[x,y,top+t+tf] for y in (-gauge,gauge)],[0,0,-1],.75,t+tf,['GIRDER','CAP'],'S two 3/4 in A325 bolts; A gauge within the actual flange')
    for sign in (-1,1):
        yy=bounds[1][0 if sign<0 else 1]
        a.weld('WC'+str(sign),[bounds[0][0],yy,top],[bounds[0][1],yy,top],['COLUMN','CAP'],.25,description='Source cap perimeter fillet')
    a.interfaces.append(dict(id='BEARING',kind='compression_bearing',connects=['GIRDER','CAP'],basis='S',description='Actual girder bottom flange on source cap plate'))
    a.dim([-6,0,top],[6,0,top],'S 12 in cap');a.section_axis=2;a.section_at=top+t/2
    a.notes.append('Source office roof TOS is retained. The column physically stops beneath its 3/4 in cap and the actual girder bottom flange; it no longer runs through the girder. A bolt gauge and cut datum; original analysis axis retained.')
