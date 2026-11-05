"""CFS18 source bearing-wall gypsum and adopted mid-height CRC restraint."""
import math
from .pilots.model import add
from .review_crossings import slot
from .review_receiver_geometry import extract
from .review_cfs_source_bindings import attach

RID='framing/mezz-stud-L1-bearing'
T=.0566


def apply(b):
    if b.key!='cfs18':return
    b.material_selections=getattr(b,'material_selections',[])+[dict(id='CFS18-WALL-GYPSUM',basis='S',specification='5/8in gypsum board on both faces of the source interior bearing wall; product and local fastener selection require verification')]
    lookup={m['id']:m for m in b.members}
    for label in ('BEARING-1-0','BEARING-1-1'):
        studs=sorted([m for m in b.members if m['id'].startswith(label+'-ST-')],key=lambda m:m['axis'][0][0])
        assert studs and all(m['profile_id']=='600S162-43' for m in studs)
        bottom,top=lookup[label+'BT'],lookup[label+'TT'];lo,hi=sorted(q[0] for q in top['axis']);y=top['axis'][0][1]
        z0,z1=bottom['axis'][0][2],top['axis'][0][2];z=(z0+z1)/2
        panels={}
        for side in (-1,1):
            face=y+side*(3+.625/2)
            p=b.panel(label+'-GYP'+str(side),'wall_sheathing',[[lo,face,z0],[hi,face,z0],[hi,face,z1],[lo,face,z1]],.625,1,'S',records=[RID],material_id='CFS18-WALL-GYPSUM')
            p.update(reference_line='Mid-surface; gypsum inner face meets the actual6in stud flange',
                attachment_schedule=dict(screw='A No8 self-drilling gypsum screw',maximum_spacing_in=12,basis='A exact product and stations; S5/8in gypsum each face, no new strength/stiffness verification'))
            panels[side]=p
        pid=b.custom('A-MEZZ-CRC1.5X.5-54','channel',dict(d=1.5,b=.5,t=T,lip=0),basis='A selected CRC for source-required mid-height bridging')
        crc=b.member(label+'-MID-CRC',pid,'stud_bridging',[lo-.5,y-.25,z],[studs[-1]['axis'][0][0]+.5,y-.25,z],1,'A',records=[RID],local_y=[0,1,0])
        for i,stud in enumerate(studs):
            x=stud['axis'][0][0];point=[x,y,z]
            slot(stud,point,[0,1,0],-.875,.875,.75,crc['id'],'A1.75in high x.75in wide mid-height CRC web punch; source stud capacity applicability requires verification')
            c=b.connection(stud['id']+'-MID-BRIDGE','review_mezz_bearing',point,[crc,stud],[RID],
                parameters=dict(purpose='bridge',side=-1 if i==len(studs)-1 else 1),basis='A')
            if i in (0,len(studs)-1):b.endpoint_links.append(dict(member_id=crc['id'],end='start' if i==0 else 'end',connection_id=c['id'],basis='The actual CRC row terminates at its end stud and real web clip; the end stud retains its floor/top-track connections. Adopted restraint strength and stiffness require verification.'))
            aa,dd=[add(q,o)[2] for q,o in zip(stud['axis'],stud['end_offsets'])]
            first,last=aa+1,dd-1;n=math.ceil((last-first)/12);zs=[first+(last-first)*j/n for j in range(n+1)]
            for group in range(0,len(zs),5):
                selected=zs[group:group+5];centre=sum(selected)/len(selected)
                b.connection(stud['id']+'-GYPSUM'+str(group//5),'review_mezz_bearing',[x,y,centre],[stud],[RID],
                    parameters=dict(purpose='gypsum',z_relative=[v-centre for v in selected],negative_panel=panels[-1]['id'],positive_panel=panels[1]['id']),basis='A')
            attach(b,stud,RID,'Exact source600S162-43 on16in grid, aligned with joists, with actual5/8in gypsum each face and located mid-height CRC. CRC/clip/punch and gypsum screws are adopted; original source capacity is not reverified for those details.')
        for track in (bottom,top):attach(b,track,RID,'Actual top/bottom receivers for the source bearing-wall studs and adopted CRC end-stud return path; no new capacity certification.')
    b.note('MEZZ-BEARING-RESTRAINT','S:600S162-43 bearing studs at16in,5/8in gypsum both faces and mid-height bridging. A:1.5x.5in54mil CRC, fitted1.75x.75in web punches,54mil formed clips/two No10 screws per leg, No8 gypsum screws at maximum12in, exact product/set-out and restraint transfer through the row end studs to their actual tracks. The source braced/unsheathed capacity remains evidence; adopted clips, punches, screw product and brace strength/stiffness require verification.')


def draw(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;axes=([1,0,0],[0,1,0],[0,0,1])
    if par['purpose']=='gypsum':
        stud=ctx.ms[0];zs=par['z_relative'];st=p[stud['profile_id']]['dimensions']['t'];extract(ctx,stud,'STUD',axes,max(abs(v) for v in zs)+.5)
        host=next(v for v in ctx.model['panels'] if v['id']==par['positive_panel'])
        x0=max(-12,min(q[0] for q in host['vertices'])-ctx.c['point'][0]);x1=min(12,max(q[0] for q in host['vertices'])-ctx.c['point'][0])
        for side,parameter in ((-1,'negative_panel'),(1,'positive_panel')):
            tag='GYPSUM'+str(side);yy=3 if side>0 else -3-.625
            panel=a.box(tag,[x0,yy,min(zs)-.25],[x1-x0,.625,max(zs)-min(zs)+.5],'S thickness; A context extent','Source5/8in gypsum on actual stud flange',kind='gypsum_panel')
            panel.update(representation_role='context_only',source_panel_parameter=parameter,drawing_style='outline',show_in_section=True)
            a.fastener('GYPSUM-S'+str(side),[[.8125,side*3.625,z] for z in zs],[0,-side,0],.164,.625+st,['STUD',tag],
                'A No8 self-drilling gypsum screws at maximum12in; product/brace strength require verification',basis='A',screw=True)
        a.section_axis=2;a.section_at=zs[len(zs)//2]
        if len(zs)>1:a.dim([.8125,-3.625,zs[0]],[.8125,-3.625,zs[1]],'A pitch, maximum12in',basis='A',offset=-50)
        a.notes.append('Gypsum outlines show the actual attached panels without duplicating them in the BIM assembly. Source thickness is retained; exact screw product and stations are adopted.')
        return
    crc,stud=ctx.ms;extract(ctx,crc,'CRC',axes,8);extract(ctx,stud,'STUD',axes,6)
    st=p[stud['profile_id']]['dimensions']['t'];sg=par['side'];x=sg*st/2;y=-.25+T/2
    a.box('CLIP-STUD',[min(x,x+sg*T),y+T,-.75],[T,1.5-T,1.5],'A','A54mil formed clip at actual stud web')
    a.box('CLIP-CRC',[min(x,x+sg*1.5),y,-.75],[1.5,T,1.5],'A','A54mil return leg at actual CRC web')
    a.fastener('STUD-S',[[x+sg*T,v,0] for v in (.65,1.15)],[-sg,0,0],.19,T+st,['STUD','CLIP-STUD'],'A two No10 screws to actual stud web',basis='A',screw=True)
    a.fastener('CRC-S',[[x+sg*v,y+T,0] for v in (.5,1.15)],[0,-1,0],.19,2*T,['CRC','CLIP-CRC'],'A two No10 screws to actual CRC web',basis='A',screw=True)
    a.weld('FOLD',[x,y+T,-.75],[x,y+T,.75],['CLIP-STUD','CLIP-CRC'],kind='BEND',basis='A',description='A continuous formed clip bend')
    a.front_axes=(0,1);a.front_depth_sign=-1;a.section_axis=2;a.section_at=0
    a.notes.append('Source requires mid-height restraint. CRC section, web punch, clip and screws are explicit adopted selections; brace strength/stiffness and changed stud-punch applicability remain unverified.')
