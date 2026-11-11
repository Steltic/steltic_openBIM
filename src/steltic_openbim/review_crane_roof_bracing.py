"""Source HR33 roof brace stations and members, with explicit A local fit."""
import copy,math
from .pilots.model import sub,add,mul,unit,cross
from .review_receiver_geometry import extract,point
from .review_crossings import slot
from .review_assemblies import hull

AXES=([1,0,0],[0,1,0],[0,0,1])


def ends(m):return [add(q,o) for q,o in zip(m['axis'],m['end_offsets'])]


def apply(b):
    if b.key!='hr33':return
    rid=b.record('connections','conn-rafter-bracing');source=b.records[rid]['data']['components']
    if '37 in from the column face' not in source or '25-ft bay' not in source:raise ValueError('HR33 source roof-bracing scope changed')
    obsolete={m['id'] for m in b.members if m['id'].startswith(('RBS-BRACE-','RBS-KICKER-'))}
    b.members[:]=[m for m in b.members if m['id'] not in obsolete]
    b.connections[:]=[c for c in b.connections if not any(mid in obsolete for mid in c['member_ids'])]
    columns=[m for m in b.members if m['kind']=='column' and m['profile_id']=='W24X117']
    face=b.depth(columns[0]['profile_id'])/2;first=face+37;last=840-first
    count=math.ceil((last-first)/148.8);stations=[first+i*(last-first)/count for i in range(count+1)]
    rafters={round(m['axis'][0][0],6):m for m in b.members if m['profile_id']=='W30X99' and abs(m['axis'][1][1]-m['axis'][0][1])>800}
    if sorted(rafters)!=list(range(0,3001,300)):raise ValueError('HR33 actual rafter grid is incomplete')
    b.endpoint_links=getattr(b,'endpoint_links',[])
    roof_top=None
    for bay,x in enumerate(range(0,3000,300)):
        left,right=rafters[x],rafters[x+300]
        tops=[ends(m)[0][2]+b.depth(m['profile_id'])/2 for m in (left,right)]
        if abs(tops[0]-tops[1])>.001:raise ValueError('Roof bracing requires level real rafter tops')
        top=tops[0];roof_top=top+6.5
        for row,y in enumerate(stations):
            name=f'RBS-ROOF-{bay}-{row}'
            beam=b.member(name,'HSS6X6X3/8','flange_bracing_beam',[x,y,top+3.5],[x+300,y,top+3.5],1,'S',records=[rid],
                source_station_from_column_face_in=37 if row in (0,len(stations)-1) else None,
                physical_fit_basis='S25 ft bracing beam bears above the real rafter top flange. A1/2 in seat cap and exact equal intermediate stations.')
            kickers=[]
            for index,(rafter,gx,sign) in enumerate(((left,x,1),(right,x+300,-1))):
                dims=b.profiles[rafter['profile_id']]['dimensions'];length=46.5;rise=length/math.sqrt(2)
                foot=[gx+sign*(dims['bf']/2+4),y,top-dims['d']-4]
                head=add(foot,[sign*rise,0,rise])
                k=b.member(name+'-K'+str(index),'HSS4X4X1/4','flange_kicker',foot,head,1,'S',records=[rid],local_y=[0,1,0],
                    physical_fit_basis='S45 deg and46.5 in source workline length. A outboard stiffener tab,4 in head cutback and slotted receiving plate fit; no new local/brace capacity verification.')
                direction=unit(sub(head,foot));k['end_offsets'][1]=mul(direction,-4)
                for q,lo,hi in ((ends(k)[0],0,4.5),(ends(k)[1],-4.5,0)):
                    slot(k,q,[0,1,0],lo,hi,.625,name,'S four4 in slot-edge weld lines; A5/8 in slot clearance and4.5 in rectangular slot envelope')
                kickers.append(k)
            c=b.connection(name+':ASSEMBLY','review_hr_strut_bracing',[x,y,top],[left,right,beam,*kickers],[rid],
                parameters=dict(crane_roof_bracing=True,span_in=300,station_in=y,source_kicker_workline_in=46.5),basis='S members; A receiver fit')
            for m in [beam,*kickers]:
                for end in ('start','end'):b.endpoint_links.append(dict(member_id=m['id'],end=end,connection_id=c['id'],basis='Both actual ends and their source weld groups appear in the complete bracing assembly'))
    # The earlier drawing put these top-bearing braces below the rafters. Use
    # a common roof support datum for the real HSS top and supplier joist top.
    joists=[m for m in b.members if m['id'].startswith('ROOF-JOIST-')]
    highest=max(max(q[2] for q in ends(m))+b.depth(m['profile_id'])/2 for m in joists if '-T' in m['id'])
    shift=roof_top-highest;ids={m['id'] for m in joists}
    for m in joists:
        m['joint_workpoints']=[add(q,[0,0,shift]) for q in m.get('joint_workpoints',m['axis'])]
        for off in m['end_offsets']:off[2]+=shift
        m['roof_datum_basis']='A: supplier joist top aligned to source top-bearing HSS roof bracing; original authored workline retained in axis'
    for c in b.connections:
        if c['member_ids'][0] in ids:c['point'][2]+=shift
    for panel in b.panels:
        if panel['kind']=='floor' and abs(panel['vertices'][0][2]-456)<.001:
            old=copy.deepcopy(panel['vertices'])
            for q in panel['vertices']:q[2]=roof_top
            panel.update(reference_line='bottom of source1.5 in roof deck / top of supporting steel',thickness_direction='positive_global_z')
            b.changes.append(dict(kind='hr33_roof_deck_bearing_datum',panel_id=panel['id'],previous_vertices=old,vertices=copy.deepcopy(panel['vertices']),
                basis='A physical support datum: deck bottom on top of the selected6 in HSS beam plus1/2 in seat above the source rafter TOS. Nominal analysis level retained.'))
    b.changes.append(dict(kind='hr33_source_roof_brace_schedule',stations_in=stations,source_raft_face_in=face,
        maximum_spacing_in=max(b-a for a,b in zip(stations,stations[1:])),roof_steel_top_in=roof_top,supplier_joist_offset_in=shift,
        basis='S sections,25 ft span,RBS station37 in from actual column face,maximum12.4 ft intermediate spacing,45 deg /46.5 in kicker workline. A local tabs,slots,cap thickness,roof datum and supplier geometry.'))
    b.note('ROOF-BRACE-SETOUT','S: HSS6X6X3/8 top-bearing roof bracing beams at37 in from each actual column face and equal intermediate stations no more than12.4 ft apart; HSS4X4X1/4 kickers at45 deg with46.5 in worklines. A1/2 in seat caps, outboard stiffener tabs,5/8 in slots and4 in head cutbacks are explicit fitting proposals. Roof deck and supplier joist tops now meet the top-bearing bracing beams. Local tab,seat,roof-height and supplier load-path/capacity verification remain required; original source analysis is unchanged.')


def draw(ctx):
    a,p=ctx.a,ctx.p;left,right,beam,*kickers=ctx.ms;origin=ctx.c['point']
    for label,m,extent in (('LEFT',left,40),('RIGHT',right,40),('BRACING',beam,310)):
        part=extract(ctx,m,label,AXES,extent)
        if label in ('LEFT','RIGHT'):part['drawing_style']='outline'
    for i,(rafter,label,kicker,sign) in enumerate(zip((left,right),('LEFT','RIGHT'),kickers,(1,-1))):
        extract(ctx,kicker,'KICKER'+str(i),AXES,100);rd=p[rafter['profile_id']]['dimensions'];gx=rafter['axis'][0][0]-origin[0]
        top=ends(rafter)[0][2]+rd['d']/2-origin[2];bottom=top-rd['d']
        a.box('CAP'+str(i),[gx-8,-4,top],[16,8,.5],'A','A1/2 in cap at actual rafter top; source two6 in seat weld lines')
        for side in (-1,1):
            a.weld(f'CW{i}-{side}',[gx-3,side*4,top],[gx+3,side*4,top],[label,'CAP'+str(i)],.25,description='S two6 in seat-cap fillets at actual rafter top flange')
            a.weld(f'BW{i}-{side}',[gx,side*3,top+.5],[gx+sign*6,side*3,top+.5],['BRACING','CAP'+str(i)],.25,basis='A',description='A bracing beam foot-to-cap fillet at actual tube side')
        foot,head=[point(q,origin,AXES) for q in ends(kicker)];direction=unit(sub(head,foot));normal=cross([0,1,0],direction)
        # One source1/2 in full-depth stiffener with an A outboard tab. Its
        # lower notch clears the actual bottom flange instead of occupying it.
        coords=[(rd['tw']/2,bottom+rd['tf']),(rd['tw']/2,top-rd['tf']),
                (rd['bf']/2+2,top-rd['tf']),(rd['bf']/2+2,bottom+2),
                (rd['bf']/2+10,bottom+2),(rd['bf']/2+10,bottom-8),
                (rd['bf']/2+.125,bottom-8),(rd['bf']/2+.125,bottom+rd['tf'])]
        a.polygon('STIFFENER'+str(i),[[gx+sign*x,-.25,z] for x,z in coords],.5,normal=[0,1,0],basis='S thickness; A outline',
            description='S1/2 in full-depth stiffener; A notched outboard tab clears the bottom flange and receives the actual slotted kicker')
        for zz in (bottom+rd['tf'],top-rd['tf']):
            a.weld(f'SF{i}-{zz}',[gx+sign*rd['tw']/2,0,zz],[gx+sign*rd['bf']/2,0,zz],[label,'STIFFENER'+str(i)],.25,basis='A',description='A stiffener-to-actual-flange fillet')
        a.weld('SW'+str(i),[gx+sign*rd['tw']/2,0,bottom+rd['tf']],[gx+sign*rd['tw']/2,0,top-rd['tf']],
            [label,'STIFFENER'+str(i)],.25,basis='A',description='A stiffener-to-web fillet')
        points=[]
        for q in (head,add(head,mul(direction,-4))):
            for side in (-1,1):
                # The 4-in attachment is fully inside the 4.5-in slot. An
                # allowance transverse to this run retains weld-edge stock
                # without extending the tab into the closed HSS beyond it.
                v=add(q,mul(normal,side*3));points.append((v[0],v[2]))
        points.extend([(head[0]-4,top+.5),(head[0]+4,top+.5)])
        a.polygon('HEAD'+str(i),[[x,-.25,z] for x,z in hull(points)],.5,normal=[0,1,0],basis='A',description='A slotted kicker head gusset to actual bracing-beam underside')
        a.weld('HW'+str(i),[head[0]-4,0,top+.5],[head[0]+4,0,top+.5],['BRACING','HEAD'+str(i)],.25,basis='A',description='A gusset-to-HSS underside fillet; local wall/capacity unverified')
        for tag,q,travel,host in [('FOOT',foot,direction,'STIFFENER'+str(i)),('HEAD',head,mul(direction,-1),'HEAD'+str(i))]:
            for wall in (-1,1):
                for side in (-1,1):
                    start=add(q,add(mul(normal,wall*2),[0,side*.25,0]))
                    a.weld(f'K{i}{tag}{wall}{side}',start,add(start,mul(travel,4)),['KICKER'+str(i),host],.25,
                        description='S four4 in1/4 in fillet lines at each kicker end; A actual slot fit')
    a.front_axes=(0,2);a.section_axis=1;a.section_at=0
    a.dim([0,0,8],[300,0,8],'S25 ft bracing-beam support span',basis='S')
    a.notes.append('S source members,45 deg kickers,37 in RBS stations and intermediate spacing are physically located. Source1/2 in stiffeners, two6 in1/4 in seat fillets and four4 in1/4 in kicker-end fillets retained. A cap thickness, outboard/notched stiffener profile, gusset and slot geometry; added local capacities and supplier roof coordination remain unverified.')
