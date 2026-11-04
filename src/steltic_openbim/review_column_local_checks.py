"""Located source J10 stiffener schedules, separate from beam-end hardware."""
import math,re
from .assembly_templates import NUMBER,number
from .pilots.model import unit,sub,dot,cross


def schedule(text):
    rows=[]
    pattern=r'(W\d+X\d+)\s+\(PL '+NUMBER+r' x '+NUMBER+r' in, '+NUMBER+r' in fillets to the flanges, '+NUMBER+r' in to the web\):\s*(.*?)(?=\s*\|\s*W|; J10|$)'
    for match in re.finditer(pattern,text,re.I):
        section,t,w,fw,ww,locations=match.groups()
        for level,places in re.findall(r'level (\d+) at ([^;]+)',locations,re.I):
            for x,y in re.findall(r'Grid (\d+)/([A-Z])',places):rows.append(dict(section=section,level=int(level),grid_x=int(x)-1,grid_y=ord(y)-65,t=number(t),width=number(w),flange_weld=number(fw),web_weld=number(ww),flange_weld_kind='fillet'))
    pattern=r'grid (\d+)-([A-Z]), level (\d+)(?: \(roof\))? \((W\d+X\d+)\): pair of PL '+NUMBER+r' x '+NUMBER+r' in'
    for match in re.finditer(pattern,text,re.I):
        x,y,level,section,t,w=match.groups()
        rows.append(dict(section=section,level=int(level),grid_x=int(x)-1,grid_y=ord(y.upper())-65,t=number(t),width=number(w),flange_weld=0,web_weld=number(re.search(NUMBER+r' in fillets to the web',text,re.I)[1]),flange_weld_kind='CJP'))
    return rows


def apply(b):
    if not b.key.startswith('hr'):return
    members={m['id']:m for m in b.members};existing=list(b.connections)
    xs=b.config.get('XS') or b.config.get('G',{}).get('xs') or [i*b.config.get('SX',336) for i in range(b.config.get('NX',0)+1)]
    ys=b.config.get('YS') or b.config.get('G',{}).get('ys') or [i*b.config.get('SY',336) for i in range(b.config.get('NY',0)+1)]
    for rid,record in b.records.items():
        if record['table']!='connections' or not any(s in rid for s in ('column-webs','columns-J10')):continue
        text=str(record['data'].get('components',''));rows=schedule(text)
        for index,row in enumerate(rows):
            if row['grid_x']>=len(xs) or row['grid_y']>=len(ys):raise ValueError('Source J10 grid outside building: '+rid)
            xy=[xs[row['grid_x']],ys[row['grid_y']]];options=[]
            for c in existing:
                if c['detail_ref']['id']!='review_beam' or math.dist(c['point'][:2],xy)>.01:continue
                beam=members[c['member_ids'][0]]
                if beam['level']!=row['level']:continue
                col=next((members[mid] for mid in c['member_ids'][1:] if members[mid]['kind']=='column' and members[mid]['profile_id']==row['section']),None)
                if not col:continue
                normal=cross(unit(sub(col['axis'][1],col['axis'][0])),col['local_y'])
                if abs(dot(unit(sub(beam['axis'][1],beam['axis'][0])),normal))<.99:continue
                options.append((abs(float(beam.get('source_forces',{}).get('collector_axial_kip') or 0)),c['id'],c,col,beam))
            if not options:
                b.changes.append(dict(kind='source_j10_location_unresolved',record_id=rid,source_selection=row,reason='No matching physical beam-to-column flange joint; retain as an unresolved source schedule'))
                continue
            _,_,c,col,beam=max(options,key=lambda q:(q[0],q[1]));par=dict(row,centre_z_in=-b.depth(beam['profile_id'])/2)
            b.connection('J10-'+rid.split('/')[-1]+'-'+str(index),'review_column_local_stiffeners',c['point'],[col,beam],[rid],parameters=par,basis='S')
            b.changes.append(dict(kind='source_j10_stiffener_location',record_id=rid,source_selection=row,column_id=col['id'],beam_id=beam['id'],connection_point=c['point']))


def draw(ctx):
    from .review_receiver_geometry import extract
    a,p,par=ctx.a,ctx.p,ctx.params;col=ctx.ms[0];u=unit(sub(col['axis'][1],col['axis'][0]));y=col['local_y'];x=cross(y,u);axes=(x,y,u)
    extract(ctx,col,'COLUMN',axes,40);extract(ctx,ctx.ms[1],'BEAM',axes,32)
    dim=p[col['profile_id']]['dimensions'];half=dim['d']/2-dim['tf'];web=dim['tw']/2;t=par['t'];w=par['width'];z=par['centre_z_in'];clip=.75
    for sign in (-1,1):
        inner=web;outer=web+w
        poly=[[-half+clip,inner], [half-clip,inner], [half,inner+clip], [half,outer-clip], [half-clip,outer],[-half+clip,outer],[-half,outer-clip],[-half,inner+clip]]
        name='STIFF'+str(sign);a.polygon(name,[[px,sign*py,z-t/2] for px,py in poly],t,normal=[0,0,1],basis='S',description=f'Source PL {t:g} x {w:g}, full depth, 3/4 in corner clips')
        for end in (-1,1):
            a.weld('FLANGE'+str(sign)+str(end),[end*half,sign*(inner+clip),z],[end*half,sign*(outer-clip),z],['COLUMN',name],par['flange_weld'],kind=par['flange_weld_kind'],description='Source stiffener flange weld; fitted bearing')
        for face in (-1,1):a.weld('WEB'+str(sign)+str(face),[-half+clip,sign*web,z+face*t/2],[half-clip,sign*web,z+face*t/2],['COLUMN',name],par['web_weld'],description='Source web fillet both faces')
    a.section_axis=2;a.section_at=z;a.dim([0,web,z],[0,web+w,z],f'{w:g} in source width',view='section')
    a.notes.append('This is the source-scheduled transverse stiffener pair at the specified column/grid/level. It is recorded once for this column joint; adjacent beam shear plates remain separate assemblies. No stiffness or capacity calculation is rerun.')
