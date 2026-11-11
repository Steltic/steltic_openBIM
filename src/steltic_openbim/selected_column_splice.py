"""Draw the selected milled W-column splice, with its plate stock and auditable bolt stations."""
import math
import re
from .assembly_templates import NUMBER, number
from .connection_cuts import drill_joined_plates


def selected(ctx):
    text=ctx.text
    web=re.search(r'web plates 2 PL '+NUMBER+r' x '+NUMBER+r' in \((A572 Gr 50)\) with (\d+) x '+NUMBER+r' in (A(?:325|490)-[NX]) bolts per side in one vertical line at '+NUMBER+r' in',text,re.I)
    flange=re.search(r'flange plates PL '+NUMBER+r' x '+NUMBER+r' in \((A572 Gr 50)\) with (\d+) bolts per flange per side in two lines at g = '+NUMBER+r' in',text,re.I)
    bore=re.search(r'standard holes '+NUMBER+r' in',text,re.I);edge=re.search(r'edge distances at least '+NUMBER+r' in',text,re.I)
    if not (web and flange and bore and edge):return False
    upper,lower=(ctx.p[m['profile_id']]['dimensions'] for m in ctx.ms[:2]);a=ctx.a
    wt,ww,wn,dia,pitch=[number(web[i]) for i in (1,2,4,5,7)];ft,fw,fn,gauge=[number(flange[i]) for i in (1,2,4,5)]
    edge=number(edge[1]);hole=number(bore[1]);wn=int(wn);fn=int(fn)
    if fn%2 or min(wn,fn,edge,dia,pitch,gauge)<=0 or hole<=dia:raise ValueError('Incomplete selected bolted column-splice set-out')
    wz=edge+(wn-1)*pitch+edge;fz=edge+(fn//2-1)*pitch+edge
    if min(x['d']-2*x['tf'] for x in (upper,lower))+1e-6<ww or (fw-gauge)/2+1e-6<edge:
        raise ValueError('Selected splice stock cannot fit its section opening or flange gauge')
    a.member('M1',ctx.ms[1]['profile_id'],[0,0,-max(30,wz+3,fz+3)],[0,0,0]);a.member('M2',ctx.ms[0]['profile_id'],[0,0,0],[0,0,max(30,wz+3,fz+3)])
    height=max(x['d'] for x in (upper,lower));web_th=max(x['tw'] for x in (upper,lower))
    for j,sign in enumerate((-1,1)):
        x=height/2 if sign>0 else -height/2-ft;y=web_th/2 if sign>0 else -web_th/2-wt
        a.box('FP'+str(j),[x,-fw/2,-fz],[ft,fw,2*fz],'S','Selected A572 Gr 50 flange cover, two vertical bolt lines').update(selected_material=flange[3],thickness=ft)
        a.box('WP'+str(j),[-ww/2,y,-wz],[ww,wt,2*wz],'S','Selected A572 Gr 50 web cover, one centred vertical bolt line').update(selected_material=web[3],thickness=wt)
    receiver_holes={}
    def bolts(name,points,axis,grip,joins,member):
        group=a.fastener(name,points,axis,dia,grip,joins,f'{dia:g} in {web[6]} splice bolts, {hole:g} in selected holes');group.update(functional_kind='bolt',selected_material='ASTM F3125 '+web[6])
        drill_joined_plates(a,group,hole,'S selected standard splice holes')
        receiver_holes.setdefault(member,[]).extend(dict(point=list(pt),axis=list(axis),diameter_in=hole,fastener=name) for pt in points)
    for end,(section,vertical,member) in enumerate(((lower,-1,'M1'),(upper,1,'M2'))):
        stations=lambda count:[vertical*(edge+i*pitch) for i in range(count)]
        for j,sign in enumerate((-1,1)):
            label='FP'+str(j);joins=[label,member];fill=(height-section['d'])/2
            if fill>1e-6:
                key=f'FLANGE-FILL-{end}-{j}';x=section['d']/2 if sign>0 else -height/2
                a.box(key,[x,-fw/2,min(0,vertical*fz)],[fill,fw,fz],'A','Fitted packing from selected cover to narrower flange').update(selected_material=flange[3]);joins.append(key)
            x=sign*(height/2+ft);points=[[x,y,z] for z in stations(fn//2) for y in (-gauge/2,gauge/2)]
            bolts(f'F{j}{end}',points,[-sign,0,0],ft+fill+section['tf'],joins,member)
        joins=['WP0','WP1',member];fill=(web_th-section['tw'])/2
        if fill>1e-6:
            for j,sign in enumerate((-1,1)):
                y=section['tw']/2 if sign>0 else -web_th/2;key=f'WEB-FILL-{end}-{j}'
                a.box(key,[-ww/2,y,min(0,vertical*wz)],[ww,fill,wz],'A','Fitted packing to thinner web').update(selected_material=web[3]);joins.append(key)
        bolts('FW'+str(end),[[0,-web_th/2-wt,z] for z in stations(wn)],[0,1,0],web_th+2*wt,joins,member)
    from .pilots.geometry import member_faces
    from .assembly_scene import bounds
    for part in a.parts:
        holes=receiver_holes.get(part['id'])
        if holes:
            part['member']['through_bores']=holes;part['faces']=member_faces(part['member'],ctx.p);part['bounds']=bounds(part['faces'])
    a.section_axis=2;a.section_at=edge
    a.dim([0,0,edge],[0,0,edge+pitch],'Selected vertical bolt pitch',basis='S')
    a.dim([height/2,-gauge/2,edge],[height/2,gauge/2,edge],'Selected flange bolt gauge',basis='S',view='section')
    return True


def cjp_paths(ctx):
    """Place the three CJP paths on actual upper steel at a selected flange-and-web splice."""
    if not re.search(r'CJP groove welds of both flanges and the web',ctx.text,re.I):return
    a=ctx.a;profile=ctx.p[ctx.pid]
    if profile['family']!='i':return
    weld=next((w for w in a.welds if w['id']=='SPLICE'),None)
    if not weld:return
    d=profile['dimensions'];h,b,tf=d['d'],d['bf'],d['tf']
    weld.update(a=[-h/2+tf,0,0],b=[h/2-tf,0,0],description='Selected CJP of the column web at the milled-end splice')
    for label,sign in (('SPLICE-FLANGE-1',-1),('SPLICE-FLANGE-2',1)):
        x=sign*(h-tf)/2;a.weld(label,[x,-b/2,0],[x,b/2,0],weld['connects'],kind='CJP',description='Selected CJP of this column flange at the milled-end splice')
    if 'milled ends' in ctx.text.lower():
        from .pilots.geometry import member_faces
        from .assembly_scene import bounds
        part=next(q for q in a.parts if q['id']=='M2');part['member']['axis'][0][2]=0
        part['faces']=member_faces(part['member'],ctx.p);part['bounds']=bounds(part['faces'])
