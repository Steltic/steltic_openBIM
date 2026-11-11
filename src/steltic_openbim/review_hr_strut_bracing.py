"""Located HR30 bracing struts and 45-degree HSS bottom-flange kickers.

The saved selection specifies member sizes, the ten-foot span/stations and
force/stiffness requirements. The end plates, gussets, bolts, welds and local
fit here are accepted fictional proposals; they carry no new capacity check.
"""
import copy,math
from .pilots.model import add,sub,mul,unit,dot
from .review_receiver_geometry import point,extract
from .review_assemblies import hull

AXES=([1,0,0],[0,1,0],[0,0,1])


def ends(m):return [add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]


def apply(b):
    if b.key!='hr30':return
    lookup={m['id']:m for m in b.members};remove=set()
    beams=[m for m in b.members if m['kind'] in ('beam','girder','moment_beam','infill')]
    rid=b.record('connections','conn-strut-bracing-Y')
    if not rid:raise ValueError('HR30 bracing selection is missing')
    for strut in list(b.members):
        if strut['kind']!='lateral_strut' or '-ST' not in strut['id']:continue
        prefix,index=strut['id'].rsplit('-ST',1);beam=lookup[prefix];kicker=lookup[prefix+'-KICK'+index]
        x,y,_=strut['axis'][0];sign=1 if strut['axis'][1][0]>x else -1;farx=x+sign*120
        candidates=[m for m in beams if m['id']!=beam['id'] and m['level']==strut['level']
                    and all(abs(q[0]-farx)<.001 for q in m['axis'])
                    and min(q[1] for q in m['axis'])+4.25<y<max(q[1] for q in m['axis'])-4.25]
        if not candidates:raise ValueError('No actual ten-foot adjacent beam for '+strut['id'])
        support=min(candidates,key=lambda m:(abs(m['axis'][0][2]-beam['axis'][0][2]),m['id']))
        bd=b.profiles[beam['profile_id']]['dimensions'];sd=b.profiles[support['profile_id']]['dimensions']
        top=min(ends(beam)[0][2]+bd['d']/2-bd['tf'],ends(support)[0][2]+sd['d']/2-sd['tf'])
        z=top-2.5  # 4.5 in end plate, 1/4 in clear of the actual top flange.
        start=[x+sign*(bd['tw']/2+.375),y,z]
        end=[farx-sign*(sd['tw']/2+.375),y,z]
        old=copy.deepcopy(strut['end_offsets']);strut['end_offsets']=[sub(q,p) for q,p in zip((start,end),strut['axis'])]
        strut['local_y']=[0,1,0];strut['design_record_ids']=list(dict.fromkeys(strut['design_record_ids']+[rid]))
        lower=ends(beam)[0][2]-bd['d']/2
        foot=[x+sign*(bd['bf']/2+3),y+.5,lower-4]
        headz=z-6
        if headz-foot[2]<8:raise ValueError('Insufficient depth for the selected 45-degree kicker '+kicker['id'])
        head=[foot[0]+sign*(headz-foot[2]),y+.5,headz]
        before=copy.deepcopy(kicker['end_offsets']);kicker['end_offsets']=[sub(q,p) for q,p in zip((foot,head),kicker['axis'])]
        kicker['local_y']=[0,1,0];kicker['design_record_ids']=list(dict.fromkeys(kicker['design_record_ids']+[rid]));b.used_records.add(rid)
        old_connections=[c for c in b.connections if c['member_ids'][0] in (strut['id'],kicker['id'])]
        if len(old_connections)!=4:raise ValueError('Expected two source-defined members with both ends: '+strut['id'])
        remove.update(c['id'] for c in old_connections)
        c=b.connection(prefix+'-LOCATED-BRACING-'+index,'review_hr_strut_bracing',[x,y,beam['axis'][0][2]],
                       [beam,support,strut,kicker],[rid],parameters=dict(sign=sign,plate_in=.375,bolt_diameter_in=.75,bolt_count_each_end=2,
                       source_span_in=120,source_kicker_angle_deg=45),basis='A')
        b.endpoint_links=getattr(b,'endpoint_links',[])
        for m in (strut,kicker):
            for endname in ('start','end'):b.endpoint_links.append(dict(member_id=m['id'],end=endname,connection_id=c['id'],basis='Both actual member ends are detailed in this shared bracing assembly'))
        b.changes.append(dict(kind='hr30_actual_strut_and_kicker_receivers',connection_id=c['id'],member_ids=c['member_ids'],
            source_record_ids=[rid],previous_connections=old_connections,previous_strut_offsets=old,previous_kicker_offsets=before,
            strut_offsets=copy.deepcopy(strut['end_offsets']),kicker_offsets=copy.deepcopy(kicker['end_offsets']),
            basis='S: HSS4X4X1/4 ten-foot bracing strut and HSS3X3X1/4 45-degree kicker; source stiffness/force requirements retained. A: locate below the actual beam top flanges, cut to beam-web end plates, offset the kicker half an inch for an external side gusset and fit both attachments. No new capacity verification.'))
    b.connections[:]=[c for c in b.connections if c['id'] not in remove]


def draw(ctx):
    if ctx.params.get('crane_eave_bracing'):
        from .review_crane_eave_bracing import draw as crane_eave
        return crane_eave(ctx)
    if ctx.params.get('crane_roof_bracing'):
        from .review_crane_roof_bracing import draw as crane_roof
        return crane_roof(ctx)
    a,p=ctx.a,ctx.p;beam,support,strut,kicker=ctx.ms;origin=ctx.c['point'];sign=ctx.params['sign'];plate=.375
    from .connection_cuts import drill_receivers
    for label,m,extent in (('BEAM',beam,30),('ADJACENT',support,30),('STRUT',strut,150),('KICKER',kicker,90)):
        part=extract(ctx,m,label,AXES,extent)
        if label in ('BEAM','ADJACENT'):part['drawing_style']='outline'
    line=[point(q,origin,AXES) for q in ends(strut)];z=line[0][2]
    for i,(host,label,normal,q) in enumerate(((beam,'BEAM',sign,line[0]),(support,'ADJACENT',-sign,line[1]))):
        d=p[host['profile_id']]['dimensions'];webface=q[0]-normal*plate;name='ENDPLATE'+str(i)
        a.box(name,[min(webface,q[0]),-4.25,z-2.25],[plate,8.5,4.5],'A','A fitted 3/8 in HSS end plate bolted to actual beam web')
        fastener=a.fastener('EB'+str(i),[[q[0],v,z] for v in (-2.75,2.75)],[-normal,0,0],.75,plate+d['tw'],[label,name],
                   'A two 3/4 in A325 bolts through end plate and beam web; 5.5 in gauge; capacity unverified',basis='A')
        drill_receivers(a,fastener,.8125)
        for side in (-1,1):
            a.weld(f'EW{i}H{side}',[q[0],-2,z+side*2],[q[0],2,z+side*2],['STRUT',name],.1875,basis='A',description='A 3/16 in continuous HSS end-to-plate fillet')
            a.weld(f'EW{i}V{side}',[q[0],side*2,z-2],[q[0],side*2,z+2],['STRUT',name],.1875,basis='A',description='A 3/16 in continuous HSS end-to-plate fillet')
    foot,head=[point(q,origin,AXES) for q in ends(kicker)];travel=unit(sub(head,foot));bd=p[beam['profile_id']]['dimensions']
    lower=ends(beam)[0][2]-bd['d']/2-origin[2];y=2
    seams=[([sign*(bd['bf']/2-3),y,lower],[sign*bd['bf']/2,y,lower]),
           ([head[0]-4,y,z],[head[0]+4,y,z])]
    for i,(end,stations,host) in enumerate(((foot,(1.5,4.5),'BEAM'),(head,(-4.5,-1.5),'STRUT'))):
        centres=[add(end,mul(travel,s)) for s in stations]
        pts=[(q[0]+dx,q[2]+dz) for q in centres for dx,dz in ((-1.5,-1.5),(-1.5,1.5),(1.5,-1.5),(1.5,1.5))]
        pts.extend((q[0],q[2]) for q in seams[i]);name='GUSSET'+str(i)
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        from .pilots.geometry import strips
        from .pilots.model import cross
        outline=Polygon(hull(pts))
        for steel in (beam,support):
            ends_local=[point(q,origin,AXES) for q in ends(steel)]
            axis=unit(sub(ends_local[1],ends_local[0]))
            if abs(axis[1])<.99999:raise ValueError('Kicker needs a located transverse receiver web')
            if not min(q[1] for q in ends_local)-plate<y<max(q[1] for q in ends_local)+plate:continue
            near=ends_local[0];wy=steel['local_y'];wz=cross(axis,wy)
            sections=[Polygon([(near[0]+u*wy[0]+v*wz[0],near[2]+u*wy[2]+v*wz[2]) for u,v in ring])
                      for ring in strips(p[steel['profile_id']],p)]
            outline=outline.difference(unary_union(sections))
        if outline.geom_type!='Polygon' or outline.interiors:
            raise ValueError('The retained kicker gusset cannot fit around both receiving sections')
        a.polygon(name,[[x,y,zz] for x,zz in list(outline.exterior.coords)[:-1]],plate,basis='A',
                  description='External kicker side gusset coped to the actual receiving sections')
        fastener=a.fastener('KB'+str(i),[[q[0],y+plate,q[2]] for q in centres],[0,-1,0],.75,3+plate,['KICKER',name],
                   'A two 3/4 in A325 through-bolts through both HSS walls and external gusset; local HSS wall/bolt design unverified',basis='A')
        drill_receivers(a,fastener,.8125)
        a.weld('KW'+str(i),*seams[i],[host,name],.25,basis='A',description='A 1/4 in gusset fillets at actual '+('beam bottom flange' if i==0 else 'HSS strut side wall'))
    a.dim([0,0,z+7],[sign*120,0,z+7],'S 10 ft support worklines',basis='S');a.dim(foot,head,'S 45 deg / A end fit',basis='A')
    a.front_axes=(0,2);a.section_axis=0;a.section_at=line[0][0]
    a.notes.append('Source HSS sizes, ten-foot support spacing/stations and 45-degree kicker are preserved. Source Prb = 3.6 kip and required stiffness = 32 kip/in remain attached. All local end plates, gussets, bolts, welds, clearances and HSS wall checks are accepted fictional fit proposals without a new capacity verification.')
