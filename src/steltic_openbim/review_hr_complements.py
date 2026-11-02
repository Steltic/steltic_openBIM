"""Source applicability for collectors, boxed corners and multi-variant gussets."""
import math,re
from .assembly_templates import NUMBER,number

def apply(b,levels):
    lookup={m['id']:m for m in b.members};raw={r['id']:r for r in b.raw['connections']}
    def attach(c,short,first=False):
        rid=b.record('connections',short)
        if rid and rid not in c['design_record_ids']:
            c['design_record_ids'].insert(0,rid) if first else c['design_record_ids'].append(rid);b.used_records.add(rid)
    for c in b.connections:
        m=lookup[c['member_ids'][0]];k=m['level'];par=c.setdefault('parameters',{});family=c['detail_ref']['id'];pt=c['point']
        if family in ('review_brace','review_brb') and b.key=='hr10' and par.get('joint')=='apex':
            rid=next((r for r in c['design_record_ids'] if 'brace-apex' in r),None)
            if rid:
                text=b.records[rid]['data']['components'];along=0 if abs(m['axis'][1][0]-m['axis'][0][0])>1 else 1
                grid=chr(65+round(pt[1]/b.config.get('SY',336))) if along==0 else str(1+round(pt[0]/b.config.get('SX',336)))
                level=min(range(len(levels)),key=lambda i:abs(levels[i]-pt[2]))
                hit=re.search(r'level '+str(level)+r' \(Grid '+grid+r', bay \d+\): gussets \('+NUMBER+r' in\) x \('+NUMBER+r' in\), web doubler PL \('+NUMBER+r' in\)',text)
                if hit:t,length,dt=map(number,hit.groups())
                else:
                    t=number(re.search(r'brace-intersection gussets '+NUMBER,text)[1]);length=number(re.search(NUMBER+r' in along the beam',text)[1]);dt=number(re.search(r'web doubler PL '+NUMBER,text)[1])
                par.update(gusset_thickness=t,interface_length=length,doubler_thickness=dt,source_grid=grid,source_level=level)
        if family!='review_beam':continue
        along=0 if abs(m['axis'][1][0]-m['axis'][0][0])>abs(m['axis'][1][1]-m['axis'][0][1]) else 1
        grid=chr(65+round(pt[1]/b.config.get('SY',336))) if along==0 else str(1+round(pt[0]/b.config.get('SX',336)))
        support=next((lookup[i] for i in c['member_ids'][1:] if lookup[i]['kind']=='column'),None)
        if b.key=='hr10' and k==3:
            for rid in raw:
                if rid.startswith('conn-collector-L3-'+grid+'-') and rid.endswith('-'+m['profile_id']):attach(c,rid,True)
        if b.key!='hr12':continue
        diagonal=abs(m['axis'][1][0]-m['axis'][0][0])>1 and abs(m['axis'][1][1]-m['axis'][0][1])>1
        if support and par.get('moment'):
            cp=support['profile_id'];v=[m['axis'][1][i]-m['axis'][0][i] for i in (0,1)]
            opposite=any(mm['id']!=m['id'] and mm['level']==k and mm['kind']=='moment_beam' and any(math.dist(q,pt)<.1 for q in mm['axis']) and abs(v[0]*(mm['axis'][1][1]-mm['axis'][0][1])-v[1]*(mm['axis'][1][0]-mm['axis'][0][0]))<.1 and sum((sum(q[j] for q in mm['axis'])/2-pt[j])*(sum(q[j] for q in m['axis'])/2-pt[j]) for j in (0,1))<0 for mm in b.members)
            typ='int' if opposite else 'end'
            for rid in (f'conn-joint-L{k}-{typ}-{cp}-{"XY"[along]}',f'conn-joint-L{k}-{typ}-{cp}',f'conn-joint-L{k}-above-{cp}'):
                attach(c,rid)
            if k==9:
                above=next((mm for mm in b.members if mm['kind']=='column' and mm['level']==10 and math.dist(mm['axis'][0][:2],pt[:2])<.1),None)
                suffix='above-'+above['profile_id'] if above else 'roof'
                attach(c,f'conn-joint-L9-{typ}-{cp}-{"XY"[along]}-'+suffix)
            if pt[:2]==[168,168]:attach(c,'conn-joint-CH1-L'+str(k))
            xy=[round(pt[0]/336),round(pt[1]/336)]
            if xy in b.config['BOXED'] or k==9 and xy in b.config['BOX9']:
                attach(c,'conn-joint-boxed-biaxial');par['boxing_t']=2.0
                if diagonal:
                    attach(c,'conn-chamfer-corner-2A-1B');c['detail_ref']['id']='review_chamfer';par['joint']='chamfer_corner'
        if par.get('collector'):
            attach(c,'conn-collector-'+('XY'[along])+'-'+('roof' if k==len(levels)-1 else 'floor'),True)
            if k==9:attach(c,'conn-collector-L9-Grid'+grid,True)
            if support and k==9 and pt[:2]==[1344,672]:attach(c,'conn-collector-columns-J10');par['collector_stiffeners']=True
    for c in b.connections:
        m=lookup[c['member_ids'][0]];family=c['detail_ref']['id'];par=c.get('parameters',{})
        if family=='review_beam' and par.get('collector') and not par.get('moment'):
            attach(c,'collector-irregularity-lines');attach(c,'conn-collector-columns-J10');attach(c,'conn-strut-columns-J10');attach(c,'conn-collector-column-webs')
        if b.key=='hr13' and family=='review_beam':
            point=c['point'];on_diagonal=any(mm['kind']=='brace' and math.dist(mm['axis'][0][:2],mm['axis'][1][:2])>200 and any(math.dist(q,point)<.1 for q in mm['axis']) for mm in b.members)
            if on_diagonal:attach(c,'conn-floor-'+m['profile_id']+'-braced-bay',True);par['paired_shear_plates']=True
        if b.key=='hr28' and family=='review_stmf_node':
            if any(lookup[i]['kind']=='truss_web' and math.dist(*[q[:2] for q in lookup[i]['axis']])<.1 for i in c['member_ids']):attach(c,'conn-stmf-vertical-'+par['direction'])
    if b.key=='hr12':
        for m in list(b.members):
            if m['kind']!='column':continue
            x,y=m['axis'][0][:2];xy=[round(x/336),round(y/336)]
            if xy not in b.config['BOXED'] and not (xy in b.config['BOX9'] and m['level'] in (9,10)):continue
            dims=b.profiles[m['profile_id']]['dimensions'];width=dims['d'];t=2.;pid=b.custom('BOXING-'+m['profile_id'],'flat',dict(width=width,thickness=t),basis='A: full-depth side-plate fit; source boxed column and 2 in test thickness')
            plates=[];ly=m['local_y'];normal=[-ly[1],ly[0],0]
            for sign in (-1,1):
                offset=[sign*(dims['bf']+t)/2*q for q in ly];ends=[[q[i]+offset[i] for i in range(3)] for q in m['axis']]
                plates.append(b.member(m['id']+'-BOX'+str(sign),pid,'column_box_plate',*ends,m['level'],'A',local_y=normal))
            b.connection(m['id']+'-BOXING','review_column_box',m['axis'][0],[m]+plates,[b.record('connections','conn-joint-boxed-biaxial')],parameters={'boxing_t':t})
        # Source diaphragm studs are represented as a repeated interface, not counted as a strength result.
        for m in list(b.members):
            if m['level']!=9 or m['kind'] not in ('beam','moment_beam'):continue
            along=0 if abs(m['axis'][1][0]-m['axis'][0][0])>1 else 1
            grid=chr(65+round(m['axis'][0][1]/336)) if along==0 else str(1+round(m['axis'][0][0]/336))
            rid=b.record('connections','diaphragm-studs-L9-Grid'+grid)
            if rid:b.connection(m['id']+'-STUDS','review_deck_studs',[(a+d)/2 for a,d in zip(*m['axis'])],[m],[rid,b.record('connections','diaphragm-chords-L9'),b.record('connections','diaphragm-shear-L9')])
    if b.key=='hr28':
        edge_bars(b,levels)

def edge_bars(b,levels):
    """Physical source slab-edge reinforcement; laps stay outside special zones."""
    rid=b.record('connections','conn-edge-chord-bars');pid=b.custom('REBAR5','round',dict(d=.625),basis='S: #5 Grade 60 diaphragm chord bars')
    from .review_hr import nearest
    for k,z in enumerate(levels[1:],1):
        pts=[p for panel in b.panels if panel['level']==k for p in panel['vertices']]
        if not pts:continue
        low=[min(p[i] for p in pts) for i in (0,1)];high=[max(p[i] for p in pts) for i in (0,1)]
        for along in (0,1):
            normal=1-along;n=6 if along==0 else 3
            for side in (0,1):
                station=(low if side==0 else high)[normal];bars=[]
                for j in range(n):
                    aa=[0.,0.,z+4.5];bb=list(aa);aa[along]=low[along]+2;bb[along]=high[along]-2
                    aa[normal]=bb[normal]=station+(1 if side==0 else -1)*(2+j*1.5)
                    bars.append(b.member(f'CHORD-L{k}-{along}-{side}-{j}',pid,'diaphragm_chord_bar',aa,bb,k,'A',records=[rid],setout_basis='S count/diameter/12 in band; A bar centres and slab cover; source 66 in lap outside protected zones'))
                at=list(bars[0]['axis'][0]);at[along]+=90;support=nearest(b,at,('beam','moment_beam','infill','truss_chord'))
                b.connection(f'CHORD-L{k}-{along}-{side}','review_edge_bars',at,bars+([support] if support else []),[rid],parameters={'bar_count':n,'lap_in':66,'cover_in':2,'pitch_in':1.5})
    b.note('EDGE-CHORDS','S: #5 Grade 60 slab-edge bars, 6 at Grids A/C and 3 at Grids 1/4, within 12 in of the edge; 66 in Class B laps outside all STMF protected zones. A: 1.5 in bar centres, 2 in edge cover and local corner/lap fit. Reinforcement is shown independently of the steel members.')
