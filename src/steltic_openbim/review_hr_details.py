"""Assembled HR variants; explicit physical load paths and source parameters."""
import math,re,copy
from .review_assemblies import *

def bolt_data(text):
    rows,cols,dia,pitch,gauge=4,1,.75,3,3
    explicit=re.search(r'(\d+) x (\d+) = \d+ bolts '+NUMBER+r' in',text)
    if explicit:
        cols,rows,dia=int(explicit[1]),int(explicit[2]),number(explicit[3]);pitch=findnum(r'pitch and gauge '+NUMBER,text,4)
        return rows,cols,dia,pitch,pitch
    hit=re.search(r'(\d+) column\(s\) x (\d+) rows of '+NUMBER+r' in',text,re.I)
    if hit:cols,rows,dia=int(hit[1]),int(hit[2]),number(hit[3])
    else:
        hit=re.search(r'(\d+)\s*x\s*'+NUMBER+r'\s*(?:in\.?|-)\s*(?:ASTM\s+F3125\s+(?:Gr\s*)?)?A(?:325|490)',text,re.I)
        if hit:rows,dia=int(hit[1]),number(hit[2])
    pitch=findnum(NUMBER+r' in(?:\.?\s+|\.?,\s*)pitch',text,findnum(r'bolts at '+NUMBER+r' in',text,3))
    return rows,cols,dia,pitch,gauge

def support(ctx,bp):
    a,p=ctx.a,ctx.p;cp=ctx.select(('column','walkway_post','prop','endwall_post'))
    source=next((m for m in ctx.ms if m['kind'] in ('column','walkway_post','prop')),None)
    beam=ctx.ms[0];bd=effective(p,bp);cd=effective(p,cp);weak=False
    if source:
        axis=unit(sub(*reversed(beam['axis'])));weak=abs(dot(axis,source['local_y']))>.7
    if weak and p[cp]['family']=='i':
        a.member('M1',cp,[0,0,-bd-14],[0,0,14],y=[1,0,0],description='Support column; weak-axis web connection '+cp);face=p[cp]['dimensions']['tw']/2
    elif source or ctx.family in ('review_crane_bracket','review_pin_beam','review_existing_joint'):
        a.member('M1',cp,[0,0,-bd-14],[0,0,14],description='Receiving column '+cp);face=cd/2
    else:
        cp=ctx.select(('girder','beam','moment_beam','walkway_edge_beam','truss_chord'),cp);cd=effective(p,cp)
        a.member('M1',cp,[0,-24,-cd/2],[0,24,-cd/2],y=[1,0,0],description='Receiving girder '+cp);face=p[cp]['dimensions'].get('tw',p[cp]['dimensions'].get('t',.25))/2
    if ctx.params.get('boxing_t'):
        t=ctx.params['boxing_t'];cw=effective(p,cp,'width')
        for j,sg in enumerate((-1,1)):
            offset=sg*(cw+t)/2;name='BOX'+str(j);plate=flat(p,cd,t)
            a.member(name,plate,[offset if weak else 0,0 if weak else offset,-bd-14],[offset if weak else 0,0 if weak else offset,14],y=[0,1,0] if weak else [1,0,0],basis='A',description='Source full-height column boxing; A 2 in fit')
            a.weld('WB'+str(j),[offset if weak else cd/2,cd/2 if weak else offset,-bd-14],[offset if weak else cd/2,cd/2 if weak else offset,14],['M1',name],kind='CJP',description='Source boxing plate to column flange tips')
        if weak:face=cw/2+t
    ctx.weak_axis_support=weak
    return cp,face

def draw(ctx):
    a,p,pid,txt,par,f=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params,ctx.family
    if f in ('review_beam','review_existing_joint','review_crane_bracket'):
        bp=pid;bd=effective(p,bp);bf=effective(p,bp,'width');cp,face=support(ctx,bp);moment=par.get('moment',False) or f=='review_crane_bracket';gap=0 if moment else 1.25
        rbs={};hit=re.search(r'RBS\s*\(?a = '+NUMBER+r'(?: in)?, b = '+NUMBER+r'(?: in)?, c = '+NUMBER,txt,re.I)
        if hit:rbs=dict(a_in=number(hit[1]),b_in=number(hit[2]),c_in=number(hit[3]));moment=True;gap=0
        m=a.member('M2',bp,[face+gap,0,-bd/2],[face+gap+max(42,rbs.get('a_in',0)+rbs.get('b_in',0)+8),0,-bd/2],**({'rbs':rbs} if rbs else {}))
        if not moment and not any(mm['kind'] in ('column','walkway_post','prop') for mm in ctx.ms):
            support_width=effective(p,cp,'width');cope=max(0,support_width/2+.25-face-gap)
            if cope:
                m['member']['cope']={'length_in':cope,'depth_in':p[cp]['dimensions'].get('tf',.5)+.5,'ends':[0]}
                from .pilots.geometry import member_faces
                m['faces']=member_faces(m['member'],p)
                from .assembly_scene import bounds
                m['bounds']=bounds(m['faces'])
        rows,cols,dia,pitch,gauge=bolt_data(txt);t=ctx.n(r'(?:single plate|erection tab|web single plate)\s*(?:PL\s*)?'+NUMBER,.375)
        if not txt:rows=max(2,min(4,int((bd-3)/3)+1))
        if moment and 'erection tab' in txt:rows,cols,dia,pitch=4,1,.75,3
        if f=='review_crane_bracket':
            a.weld('WF1',[face,-bf/2,0],[face,bf/2,0],['M1','M2'],kind='CJP',description='Source CJP bracket flange; Category C; reinforcement left')
            a.weld('WF2',[face,-bf/2,-bd],[face,bf/2,-bd],['M1','M2'],kind='CJP');a.weld('WW',[face,0,-bd+1],[face,0,-1],['M1','M2'],.375,description='3/8 in web fillets both sides');a.section_at=face+6;return
        if f=='review_existing_joint':
            # Bolted hypothetical survey answer, with no weld to unverified 1968 steel.
            moment=False;rows,cols,dia,pitch=4,1,.875,3;t=.5
            a.notes.append('A: fictional existing joint survey answer: paired bolted web angles and flange cover/seat plates. No welding to existing A36 steel is shown; source survey and weldability requirements remain.')
        ph=(rows-1)*pitch+2*max(dia*1.5,1.5);edge=(ph-(rows-1)*pitch)/2
        if ph>bd-2:
            # Preserve the source pattern; a mismatched source profile is an error.
            ph=bd-1.5;edge=(ph-(rows-1)*pitch)/2
            if edge<dia*.8:raise ValueError('Source bolt group does not fit '+ctx.model['pilot']+' '+pid+' '+str((rows,cols,dia,pitch)))
        width=ctx.n(r'bolt line '+NUMBER+r' in from the weld',3)+(cols-1)*gauge+max(2*dia,1.5);tw=p[bp]['dimensions'].get('tw',.375);z=-bd/2-ph/2
        pattern_basis='S' if re.search(r'\b(?:bolts|erection tab|column\(s\))\b',txt,re.I) else 'A'
        a.box('P1',[face,tw/2,z],[width,t,ph],pattern_basis,'Shear plate / erection tab; A fitted width where unprovided')
        paired=par.get('paired_shear_plates',False);joins=['M2','P1']
        if paired:a.box('P2',[face,-tw/2-t,z],[width,t,ph],'S','Source second shear plate / double-shear joint');joins.append('P2')
        a.fastener('F1',grid(rows*cols,cols,pitch,gauge,(face+width-max(2*dia,1.5)-(cols-1)*gauge,-tw/2-(t if paired else 0),z+edge)),[0,1,0],dia,tw+t*(2 if paired else 1),joins,f'{rows} rows x {cols}; {dia:g} in '+('A490' if 'A490' in txt else 'A325')+'; source pretension/faying-surface requirements',pattern_basis)
        weld=ctx.n(r'\('+NUMBER+r' in fillets both sides',.25)
        a.weld('W1',[face,tw/2,z],[face,tw/2,z+ph],['M1','P1'],weld,description=f'{weld:g} in fillet both sides to support')
        if paired:a.weld('W2',[face,-tw/2,z],[face,-tw/2,z+ph],['M1','P2'],weld,description='Source second shear-plate support weld')
        if moment:
            for i,zz in enumerate((0,-bd)):a.weld('WF'+str(i),[face,-bf/2,zz],[face,bf/2,zz],['M1','M2'],kind='CJP',description='Source flange CJP; demand-critical / access-hole requirements retained')
            if 'web CJP' in txt or 'welded web' in txt:a.weld('WW',[face,0,-bd+1.5],[face,0,-1.5],['M1','M2'],kind='CJP')
        # Actual source joint schedule supplies column reinforcement, never every column by default.
        cd=effective(p,cp);cw=effective(p,cp,'width');ct=p[cp]['dimensions'].get('tw',.375);tf=p[cp]['dimensions'].get('tf',.5)
        weak=getattr(ctx,'weak_axis_support',False)
        def column_point(q):return [-q[1],q[0],q[2]] if weak else q
        column_axes=dict(x=[0,1,0],y=[-1,0,0]) if weak else {}
        match=re.search(r'continuity plates\s*(?:2 x PL\s*)?'+NUMBER+r' in',txt,re.I)
        if match and 'no continuity plates' not in txt:
            thick=number(match[1]);j=0
            for zz in (-bd,0):
                for sign in (-1,1):
                    yy=ct/2 if sign>0 else -cw/2+.25;j+=1
                    a.box(f'CP{j}',column_point([-cd/2+tf,yy,zz-thick/2]),[cd-2*tf,cw/2-ct/2-.25,thick],'S','Column continuity plate',**column_axes)
                    a.weld(f'WC{j}',column_point([-cd/2+tf,yy,zz]),column_point([cd/2-tf,yy,zz]),['M1',f'CP{j}'],max(.1875,min(.75,thick*.75)),description='Continuity weld; full source flange/web weld specification in source register')
        match=re.search(r'(?<!no )doubler plate\s*(?:PL\s*)?'+NUMBER+r' in',txt,re.I)
        if match:
            thick=number(match[1]);a.box('DP',column_point([-cd/2+tf,ct/2,-bd-6]),[cd-2*tf,thick,bd+12],'S','Column web doubler; source extension 6 in',**column_axes);a.weld('WD',column_point([-cd/2+tf,ct/2,-bd-6]),column_point([-cd/2+tf,ct/2,6]),['M1','DP'],.375,kind='PJP',description='Source doubler groove/fillet weld system; see attached record')
        reinforcing=re.search(r'beam web reinforcing plates PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER,txt,re.I)
        if reinforcing:
            rt,rh,rl=map(number,reinforcing.groups())
            for j,sg in enumerate((-1,1)):
                yy=tw/2 if sg>0 else -tw/2-rt;a.box('RP'+str(j),[face+gap,yy,-bd/2-rh/2],[rl,rt,rh],'S','Source beam-web reinforcement');a.weld('WR'+str(j),[face+gap,yy,-bd/2-rh/2],[face+gap+rl,yy,-bd/2-rh/2],['M2','RP'+str(j)],.3125,description='5/16 in fillet all around reinforcement')
        a.section_at=face+width-2;a.dim([face,0,z],[face+width,0,z],basis='A');a.dim([face+width,0,z+edge],[face+width,0,z+edge+(rows-1)*pitch],f'{rows-1} @ {pitch:g} in',offset=40)
        if rbs:a.dim([face+rbs['a_in'],0,1],[face+rbs['a_in']+rbs['b_in'],0,1],f'RBS b={rbs["b_in"]:g}; c={rbs["c_in"]:g} in',offset=30)
    elif f=='review_pin_beam':pin_beam(ctx)
    elif f in ('review_base','review_wall_base'):base(ctx)
    elif f in ('review_splice','review_column_continuity'):splice(ctx)
    elif f in ('review_brace','review_brb','review_rocker','review_core_base','review_plate_base','review_chamfer','review_column_box','review_deck_studs','review_edge_bars'):
        from .review_hr_special import draw
        draw(ctx)
    elif f in ('review_plate_wall','review_core_wall','review_coupling'):wall(ctx)
    elif f in ('review_stmf_node','review_stmf_end'):stmf(ctx)
    elif f=='review_ebf_link':
        d=effective(p,pid);bf=effective(p,pid,'width');tw=p[pid]['dimensions'].get('tw',.375);tf=p[pid]['dimensions'].get('tf',.5)
        a.member('M1',pid,[-30,0,0],[30,0,0]);a.member('M2',pid,[30,0,0],[42,0,0],description='Same continuous source beam beyond protected link')
        t=ctx.n(r'stiffeners?\s*(?:PL\s*)?'+NUMBER,.5)
        for j,x in enumerate((-18,-9,0,9,18)):
            for side in (-1,1):
                label=f'S{j}{side}';yy=tw/2 if side>0 else -bf/2+.25;a.box(label,[x-t/2,yy,-d/2+tf],[t,bf/2-tw/2-.25,d-2*tf],'A','Link full-depth web stiffener; adopted station')
                a.weld('W'+label,[x,yy,-d/2+tf],[x,yy,d/2-tf],['M1',label],.25,basis='A')
        a.dim([-18,0,-d/2],[18,0,-d/2],'36 in protected shear link',basis='S');a.section_at=0
    elif f.startswith('review_retrofit_'):retrofit(ctx)
    elif f in ('review_crane_seat','review_crane_tie','review_rail_clip','review_sliding_post','review_joist_seat'):industrial(ctx)
    else:raise ValueError(f)

def pin_beam(ctx):
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text;d=effective(p,pid);bf=effective(p,pid,'width');tf=p[pid]['dimensions']['tf'];tw=p[pid]['dimensions']['tw'];cp,face=support(ctx,pid)
    stub=ctx.n(r'beam stub '+NUMBER+r' in',22);pin=ctx.n(r'pin '+NUMBER+r' in dia',3);kt=ctx.n(r'knife plate '+NUMBER+r' in',2);ct=ctx.n(r'two clevis plates '+NUMBER+r' in',1.5);lk=ctx.n(r'Lk = '+NUMBER+r' in',10);lc=ctx.n(r'Lc = '+NUMBER+r' in',10)
    h=d-2*tf-.125;px=face+stub+.5;insertion=face+stub-lk;gap=.0625
    # End webs are absent over the inserted knife/clevis plates; source full profiles resume outside this zone.
    a.member('M2',pid,[face,0,-d/2],[insertion,0,-d/2],description='Source beam stub, intact web')
    a.member('M3',pid,[face+stub+1+lc,0,-d/2],[face+stub+1+lc+15,0,-d/2],description='Connected beam, intact web')
    for tag,x,length in [('STUB',insertion,lk),('BEAM',face+stub+1,lc)]:
        for j,z in enumerate((-d,-tf)):a.box(tag+str(j),[x,-bf/2,z],[length,bf,tf],'S','Actual flange over source web cut-back')
    a.box('KNIFE',[insertion,-kt/2,-d/2-h/2],[lk+7,kt,h],'S','Source inserted knife plate')
    for j,sign in enumerate((-1,1)):
        yy=kt/2+gap if sign>0 else -kt/2-gap-ct
        a.box('CLEVIS'+str(j),[px-5.5,yy,-d/2-h/2],[lc+6,ct,h],'S','Source clevis plate')
        a.weld('WC'+str(j),[face+stub+1,yy,-tf],[face+stub+1+lc,yy,-tf],['CLEVIS'+str(j),'BEAM1'],.6875,description='Source outer-face clevis-to-flange fillet; both flange levels')
    a.box('TRANS',[face+stub+1+lc-.5,-bf/2,-d+tf],[.5,bf,d-2*tf],'S','Web-to-clevis transverse plate')
    a.fastener('PIN',[[px,-kt/2-gap-ct,-d/2]],[0,1,0],pin,kt+2*gap+2*ct,['KNIFE','CLEVIS0','CLEVIS1'],f'{pin:g} in AISI 4140 Q&T pin, double shear; A retaining washers')
    a.weld('WK',[insertion,0,-d+tf],[insertion,0,-tf],['KNIFE','M2'],kind='CJP',description='Source knife to cut stub web CJP')
    a.weld('WS',[face,-bf/2,0],[face,bf/2,0],['M1','M2'],kind='CJP',description='Stub flange/web CJP to column')
    a.weld('WT',[face+stub+1+lc,-bf/2,-d/2],[face+stub+1+lc,bf/2,-d/2],['TRANS','M3'],.1875,description='Transverse plate fillet to web and clevis ends')
    a.section_at=px;a.dim([face,0,2],[px,0,2],f'{stub+.5:g} in column face to pin');a.dim([insertion,0,-d],[face+stub,0,-d],f'Lk {lk:g} in')
    a.notes.append('Source knife/clevis insertions, 1 in flange gap and web cut-backs are shown. Plate end shapes are A rectangular fit envelopes; source narrowed tip dimensions and weld-access exclusions govern the joint.')

def base(ctx):
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text;d=effective(p,pid);w=effective(p,pid,'width');existing=ctx.params.get('existing_grillage')
    if existing:
        gp=ctx.default_w();a.member('M1',pid,[0,0,-24],[0,0,24]);a.member('M2',gp,[-30,0,-30],[30,0,-30],basis='A',description='A existing encased grillage assumption');a.box('CONC',[-36,-30,-48],[72,60,48],'A','Existing concrete context',kind='concrete');a.box('BEARING',[-d/2-3,-w/2-3,-24],[d+6,w+6,1],'A','A retained bearing plate');a.weld('W1',[-d/2,-w/2,-23],[d/2,-w/2,-23],['M1','BEARING'],.25,basis='A',description='A historic connection depiction; existing metallurgy and weld condition not verified');a.section_axis=2;a.section_at=-25;a.notes.append('No designed anchor rods in source. Existing grillage and its connections are fictional survey assumptions, not an assessed foundation.');return
    embedded='embedded' in txt
    if embedded:
        le=ctx.n(r'Le = '+NUMBER+r' in',0) or ctx.n(r'embedded '+NUMBER+r' ft',6)*12
        match=re.search(r'end (?:bearing )?plate\s*(?:PL\s*)?'+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',txt,re.I)
        t,bx,by=2,d+10,w+10
        if match:
            vals=list(map(number,match.groups()));t,bx,by=(vals if 'PL' in match[0] else [vals[2],vals[0],vals[1]])
        reinforce=ctx.n(r'box built of PL '+NUMBER+r' in plates',0)
        if reinforce and p[pid]['family']=='rhs':
            ep=pid+'-EMBED';p[ep]=copy.deepcopy(p[pid]);p[ep]['id']=ep;p[ep]['dimensions']['t']=reinforce
            a.member('M1',ep,[0,0,-le],[0,0,12]);a.member('COLUMN',pid,[0,0,12],[0,0,32]);a.weld('TRANSITION',[-d/2,-w/2,12],[d/2,-w/2,12],['M1','COLUMN'],kind='CJP',description='Source 12 in above-foundation transition; taper thicker inside plate 1:2.5')
        else:a.member('M1',pid,[0,0,-le],[0,0,max(24,ctx.n(r'to '+NUMBER+r' in above',0)+12)])
        a.box('P1',[-bx/2,-by/2,-le-t],[bx,by,t],'S','Embedded end bearing/anchor plate');a.box('CONC',[-bx/2-12,-by/2-12,-le-t-12],[bx+24,by+24,le+t+12],'A','Mat/pile-cap context, source embedment',kind='concrete')
        a.weld('W1',[-d/2,-w/2,-le],[d/2,-w/2,-le],['M1','P1'],kind='CJP',description='Column-end-plate CJP / source heavy-plate CVN and UT requirements')
        # Side plates close source W columns only where specified.
        side=ctx.n(r'side plates PL '+NUMBER,0)
        if side and p[pid]['family']=='i':
            tf=p[pid]['dimensions']['tf']
            for j,yy in enumerate((-w/2,w/2-side)):
                a.box('SIDE'+str(j),[-d/2+tf,yy,-le],[d-2*tf,side,le],'S','Source boxing side plate');a.weld('WS'+str(j),[-d/2+tf,yy,-le],[-d/2+tf,yy,0],['M1','SIDE'+str(j)],kind='CJP')
        reinforcing=re.search(r'8 PL '+NUMBER+r' x '+NUMBER+r' in',txt)
        if reinforcing:
            rt,rw=map(number,reinforcing.groups());height=ctx.n(r'to '+NUMBER+r' in above',50);clear=ctx.n(r'\('+NUMBER+r' in apart',8.25);ri=0
            for face in range(4):
                axis=[1 if face==0 else -1 if face==1 else 0,1 if face==2 else -1 if face==3 else 0,0];along=[axis[1],-axis[0],0];facehalf=d/2 if face<2 else w/2
                for sg in (-1,1):
                    ri+=1;q=add(mul(axis,facehalf),mul(along,sg*(clear/2+rw/2)));q[2]=-le;origin=add(q,mul(along,-rw/2))
                    a.box('REINF'+str(ri),origin,[rw,rt,le+height],'S','Source embedded box reinforcement',x=along,y=axis)
                    for edge in (-1,1):
                        at=add(q,mul(along,edge*rw/2));a.weld(f'WR{ri}{edge}',at,add(at,[0,0,le+height]),['M1','REINF'+str(ri)],.75 if rt==1 else 1,description='Source double fillets; stop 1 in clear of gusset collar')
        count=int(ctx.n(r'(\d+) x 7/8 in headed studs',ctx.n(r'(\d+) headed studs 7/8',0)));dia=.875
        if not count and 'two rows of 14 headed studs' in txt:count=28
        if count:
            # Every source stud is represented; stations are A where the source gives only counts.
            per=math.ceil(count/4);specified=re.search(r'(\d+) rows '+NUMBER+r' in apart from '+NUMBER+r' in below',txt)
            nlevels=int(specified[1]) if specified else max(1,int((le-12)/6));rows=math.ceil(per/nlevels);pitch=number(specified[2]) if specified else (le-12)/max(1,nlevels-1);first=number(specified[3]) if specified else 6;placed=0
            bottom_zone=re.search(r'(\d+) rows of \d+ at 6 in.*?from 6 in above the end plate',txt)
            if bottom_zone:nlevels=int(bottom_zone[1]);rows=math.ceil(per/nlevels);first=le-6;pitch=-6
            for face in range(4):
                normal=[1 if face==0 else -1 if face==1 else 0,1 if face==2 else -1 if face==3 else 0,0];origin=[normal[0]*d/2,normal[1]*w/2,0];along=[0,1,0] if face<2 else [1,0,0];half=(w if face<2 else d)/2
                points=[]
                for j in range(min(per,count-placed)):
                    across=ctx.n(NUMBER+r' in across the faces',min(6,2*(half-2)/max(1,rows-1)));shift=(j%rows-(rows-1)/2)*across;z=-first-(j//rows)*pitch;pt=add(origin,add(mul(along,shift),[0,0,z]));points.append(pt);placed+=1
                if points:a.fastener('STUDS'+str(face),points,normal,dia,5,['M1','CONC'],'Source 7/8 x 5 in headed stud group; A stations / illustrative head envelope')
            a.notes.append(f'S: all {count} headed studs represented. '+('Source row count, vertical and transverse spacing retained.' if specified else 'A stations within the source embedment; exact distribution requires reconciliation.'))
        a.section_axis=2;a.section_at=-le/2;a.dim([bx/2,0,-le],[bx/2,0,0],f'Embedment {le:g} in');return
    match=re.search(r'(?:base plate\s*(?:PL)?|moment base:\s*PL)\s*'+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',txt,re.I)
    t,bx,by=list(map(number,match.groups())) if match else (1,d+8,w+8)
    n=int(ctx.n(r'(\d+) x '+NUMBER+r' in (?:ASTM )?F1554',4));dia=ctx.n(r'\d+ x '+NUMBER+r' in (?:ASTM )?F1554',.75);embed=ctx.n(r'embedment\s*(?:hef = )?'+NUMBER,18);grout=ctx.n(r'on '+NUMBER+r' in (?:non-shrink )?grout',2)
    a.box('CONC',[-bx/2-8,-by/2-8,-embed-6],[bx+16,by+16,embed+6],'A','Foundation context',kind='concrete');a.box('GROUT',[-bx/2,-by/2,0],[bx,by,grout],'S','Source grout');a.box('P1',[-bx/2,-by/2,grout],[bx,by,t],'S' if match else 'A','Base plate')
    a.member('M1',pid,[0,0,grout+t],[0,0,grout+t+32]);edge=ctx.n(r'rods '+NUMBER+r' in from the plate edges',max(1.5,1.5*dia));rows=max(2,math.ceil(n/2));points=[]
    for i in range(n):points.append([(-1 if i%2==0 else 1)*(bx/2-edge),-by/2+edge+(i//2)*(by-2*edge)/(rows-1),-embed])
    a.fastener('ANCH',points,[0,0,1],dia,embed+grout+t,['CONC','P1'],f'{n} x {dia:g} in source F1554 rods; A embedment where source delegates it')
    a.weld('W1',[-d/2,-w/2,grout+t],[d/2,-w/2,grout+t],['M1','P1'],kind='CJP' if 'CJP' in txt else 'fillet',description='Column-to-plate weld per source flange/web specification')
    if 'lug' in txt:
        lt=ctx.n(r'PL '+NUMBER+r' x \d+ in.*?(?:embedded|CJP)',.75);lw=min(d,16)
        a.box('LUGX',[-lw/2,-lt/2,-4],[lw,lt,grout+4],'A','Source cruciform shear lug, A fit envelope');a.box('LUGY',[-lt/2,-lw/2,-4],[lt,lw,grout+4],'A','Crossing lug plate');a.weld('WL',[-lw/2,0,grout],[lw/2,0,grout],['LUGX','P1'],kind='CJP')
    a.section_axis=2;a.section_at=grout+t/2;a.dim([-bx/2,0,grout],[bx/2,0,grout],f'{bx:g} in plate');a.dim([points[0][0],0,grout+t+5],[points[1][0],0,grout+t+5],basis='A',offset=30)

def splice(ctx):
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text;lower=ctx.ms[1]['profile_id'] if len(ctx.ms)>1 else pid;d=effective(p,pid);ld=effective(p,lower);w=effective(p,pid,'width')
    a.member('M1',lower,[0,0,-30],[0,0,0]);a.member('M2',pid,[0,0,.0625],[0,0,30])
    if ctx.family=='review_column_continuity':
        a.weld('CONT',[0,-w/2,0],[0,w/2,0],['M1','M2'],kind='CONTINUOUS',basis='S',description='Continuous physical column across analysis storey split; NO field joint or weld at this datum');a.section_axis=2;a.section_at=0;return
    if 'CJP' in txt and 'bolted' not in txt[:100]:
        a.weld('SPLICE',[-d/2,-w/2,0],[d/2,w/2,0],['M1','M2'],kind='CJP',description='Source all-around column splice CJP; thickness transitions and demand-critical requirements retained')
        a.section_axis=2;a.section_at=0;a.dim([d/2,0,0],[d/2,0,12],'Splice 48 in above source floor',basis='S');return
    dia=ctx.n(NUMBER+r' in (?:ASTM F3125 )?A325',.875);t=ctx.n(r'flange (?:plates?|plate splice)\s*(?:PL)?\s*'+NUMBER,.75);width=w
    match=re.search(r'PL '+NUMBER+r' x '+NUMBER+r' in outside each flange with (\d+) x',txt)
    flange_count=8 if ctx.model['pilot']=='hr32' else 4
    if match:t,width,flange_count=number(match[1]),number(match[2]),int(match[3])
    for j,sg in enumerate((-1,1)):
        xx=max(d,ld)/2 if sg>0 else -max(d,ld)/2-t;label='FP'+str(j);a.box(label,[xx,-width/2,-15],[t,width,30],'A','Source flange splice plate; A fitted length')
        for end,zz in enumerate((-6,6)):
            nrows=math.ceil(flange_count/2);pts=[[xx+t if sg>0 else xx,y,zz+(r-(nrows-1)/2)*3] for r in range(nrows) for y in (-width/4,width/4)][:flange_count]
            shape=pid if end else lower;filler=(max(d,ld)-effective(p,shape))/2
            if filler>.01:
                fill=f'FILL{j}{end}';start=max(d,ld)/2-filler if sg>0 else -max(d,ld)/2;a.box(fill,[start,-width/2,-14 if end==0 else .1],[filler,width,13.9],'A','A milled filler to actual flange face')
            a.fastener(f'F{j}{end}',pts,[-sg,0,0],dia,t+filler+p[shape]['dimensions'].get('tf',.5),[label,'M2' if end else 'M1']+([fill] if filler>.01 else []),f'{flange_count} bolts each side per flange; source grade / A set-out','A')
    tw=p[pid]['dimensions'].get('tw',.5)
    for j,sg in enumerate((-1,1)):
        yy=tw/2 if sg>0 else -tw/2-.375;a.box('WP'+str(j),[-3.5,yy,-10],[7,.375,20],'A','Web splice cover')
    for end,z in enumerate((-1,1)):
        pts=[[0,-tw/2-.375,z*(3+j*3)] for j in range(3)] if ctx.model['pilot']=='hr32' else [[x,-tw/2-.375,z*5] for x in (-1.5,1.5)]
        a.fastener('FW'+str(end),pts,[0,1,0],dia,tw+.75,['WP0','WP1','M2' if end else 'M1'],'Web splice bolts; source grade/count / A positions','A')
    a.section_axis=2;a.section_at=6;a.dim([0,0,-15],[0,0,15],'30 in fitted cover length (A)',basis='A')


def wall(ctx):
    a,p,pid,txt,par=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params
    if ctx.family=='review_plate_wall':
        cp=ctx.select(('column',));bp=ctx.select(('beam','moment_beam'));cd=effective(p,cp);bd=effective(p,bp);t=par['thickness'];wp=flat(p,32,t)
        a.member('M1',cp,[-cd/2,0,-bd],[ -cd/2,0,40]);a.member('M2',bp,[0,0,-bd/2],[42,0,-bd/2]);a.member('WALL',wp,[18,.28125,2],[18,.28125,34],y=[1,0,0],basis='S',description='Physical 3/16 in wall plate / corner extract')
        a.box('FISH-H',[0,-.1875,0],[36,.375,4],'S','3/8 x 4 in horizontal fishplate');a.box('FISH-V',[0,-.1875,0],[4,.375,36],'S','3/8 x 4 in vertical fishplate')
        for tag,ends,host in [('H',([0,0,0],[36,0,0]),'M2'),('V',([0,0,0],[0,0,36]),'M1')]:
            a.weld('WF'+tag,*ends,[host,'FISH-'+tag],.25,description='Two 1/4 in shop fillets');a.weld('WW'+tag,*([2,.375,2],[34,.375,2]) if tag=='H' else ([2,.375,2],[2,.375,34]),['WALL','FISH-'+tag],.1875,description='3/16 in field fillets, both lap edges')
        a.section_axis=2;a.section_at=3;a.dim([0,0,0],[4,0,0],'4 in fishplate');a.notes.append('Perforated panel: 6 in holes at 10.75 in diagonal pitch.' if par.get('perforated') else 'Solid source panel; corner cut-out and 2 in boundary overlap are A fit dimensions.');return
    if ctx.family=='review_core_wall':
        t=par['plate_thickness'];overall=18;wp=flat(p,36,t)
        for j,sg in enumerate((-1,1)):a.member('FACE'+str(j),wp,[0,sg*(overall-t)/2,-18],[0,sg*(overall-t)/2,18],y=[1,0,0],description='Source composite wall faceplate')
        a.box('CONC',[-18,-9+t,-18],[36,18-2*t,36],'S','Concrete between steel faceplates',kind='concrete')
        dia=ctx.n(NUMBER+r' in.*?tie',.75);dia=min(dia,2);wt=ctx.n(NUMBER+r' in fillet weld all around',.625)
        for i,(x,z) in enumerate(((-6,-6),(6,-6),(-6,6),(6,6))):
            a.fastener('TIE'+str(i),[[x,-9,z]],[0,1,0],dia,18,['FACE0','FACE1'],'Through-wall tie bar; A 12 in stations',basis='A')
            for face,sg in enumerate((-1,1)):a.weld('WT'+str(i)+str(face),[x-.5,sg*9,z],[x+.5,sg*9,z],['FACE'+str(face),'TIE'+str(i)],wt,description=f'{wt:g} in source all-around tie-bar weld at each outside face')
        dp=ctx.default_w();a.member('DIAPH',dp,[0,-30,-6],[0,-9,-6],y=[1,0,0],basis='A',description='A representative diaphragm collector');a.box('LEDGER',[-8,-9-.5,-12],[16,.5,12],'A','Diaphragm transfer plate');a.weld('WD',[-8,-9,-12],[8,-9,-12],['LEDGER','FACE0'],.375,basis='A');a.weld('WC',[0,-9.5,-12],[0,-9.5,0],['DIAPH','LEDGER'],.25,basis='A')
        a.section_axis=0;a.section_at=6;a.dim([18,-9,0],[18,9,0],'18 in wall',view='section');a.notes.append('Tie spacing, local collector embed and wall splice fit are A. Source ties, diaphragms, concrete grade and faceplate plate groups remain authoritative.');return
    # Embedded coupling beam continues into both faceplates at the opening.
    t=ctx.n(r'faceplates? '+NUMBER+r' in',.75);d=effective(p,pid);a.member('M1',pid,[-30,0,0],[30,0,0]);wp=flat(p,30,t)
    for j,sg in enumerate((-1,1)):
        a.member('WALL'+str(j),wp,[-15,sg*(18-t)/2,-30],[-15,sg*(18-t)/2,30],y=[1,0,0],basis='A');a.weld('W'+str(j),[-30,sg*9,-d/2],[0,sg*9,-d/2],['M1','WALL'+str(j)],.5,kind='CJP',description='Source coupling flange/faceplate development; A local embed envelope')
    a.box('CONC',[-30,-9+t,-30],[30,18-2*t,60],'A','Wall concrete context',kind='concrete');a.dim([-30,0,d/2],[0,0,d/2],'30 in adopted embedment',basis='A');a.section_at=-15

def stmf(ctx):
    a,p,txt=ctx.a,ctx.p,ctx.text;point=ctx.c['point'];horizontal=0 if ctx.params.get('direction')=='X' else 1;normal=1-horizontal;ends=[]
    for i,m in enumerate(ctx.ms):
        if m['kind']=='column':continue
        far=max(m['axis'],key=lambda q:math.dist(q,point));v=unit([far[horizontal]-point[horizontal],far[normal]-point[normal],far[2]-point[2]])
        ly=m['local_y'];local=[ly[horizontal],ly[normal],ly[2]];part=a.member('M'+str(i),m['profile_id'],mul(v,.01 if ctx.family=='review_stmf_end' else 2),mul(v,30),y=local,basis='A');ends.append((part,v,m))
    if ctx.family=='review_stmf_end':
        cp=ctx.select(('column',));cd=effective(p,cp);xc=-cd/2 if sum(v[0] for _,v,_ in ends)>0 else cd/2;a.member('COLUMN',cp,[xc,0,-20],[xc,0,20]);
        for i,(part,v,m) in enumerate(ends):a.weld('END'+str(i),[0,-4,-4],[0,4,4],[part['id'],'COLUMN'],kind='CJP',description='Source chord CJP / diagonal gusset interface at column')
    else:
        t=.75;coords=[(-4,-4),(4,4)]
        for part,v,m in ends:coords.extend([(v[0]*18-4,v[2]*18-4),(v[0]*18+4,v[2]*18+4)])
        poly=hull(coords);a.polygon('GUSSET',[[x,-t/2,z] for x,z in poly],t,basis='A',description='Source 3/4 in node gusset; A outline')
        for i,(part,v,m) in enumerate(ends):a.weld('W'+str(i),mul(v,3),mul(v,16),[part['id'],'GUSSET'],.3125,description='Slotted HSS / welded flat-bar source interface; A fit extent')
    a.section_at=6;a.notes.append('Chord webs are horizontal. The 90 in special segment and its source flat bars remain distinct from outside HSS diagonals; no attachments are introduced in the protected segment except specified node connections.')

def retrofit(ctx):
    a,p,pid,par=ctx.a,ctx.p,ctx.pid,ctx.params;t=par['plate_thickness'];width=par['plate_width'];d=effective(p,pid)
    if 'column' in ctx.family:
        a.member('M1',pid,[0,0,-30],[0,0,30],description='Existing A36 column');a.member('M2',pid,[0,0,30],[0,0,42],description='Continuation of existing column')
        for j,sg in enumerate((-1,1)):
            xx=d/2 if sg>0 else -d/2-t;a.box('P'+str(j),[xx,-width/2,-24],[t,width,48],'A','A bolted column reinforcement');a.fastener('F'+str(j),[[xx,y,z] for y in (-width/4,width/4) for z in (-18,-6,6,18)],[1,0,0],.875,t+p[pid]['dimensions']['tf'],['M1','P'+str(j)],'A: eight 7/8 in bolts per face; existing steel drilled',basis='A')
    else:
        a.member('M1',pid,[-36,0,0],[36,0,0],description='Existing beam');a.member('M2',pid,[36,0,0],[48,0,0],description='Continuous existing beam');a.box('P1',[-30,-width/2,-d/2-t],[60,width,t],'A','A bottom cover plate; shown central extract')
        a.fastener('F1',[[x,y,-d/2-t] for x in (-24,-12,0,12,24) for y in (-width/4,width/4)],[0,0,1],.75,t+p[pid]['dimensions']['tf'],['M1','P1'],'A bolted reinforcement; no weld to unverified existing steel',basis='A');a.notes.append('Plate extends over middle 60% of the actual beam workline. End rows 6 in from plate ends; intermediate pitch 12 in maximum, dimensioned as fictional retrofit input.')
    a.section_axis=0 if 'beam' in ctx.family else 2;a.section_at=0

def industrial(ctx):
    a,p,pid,f=ctx.a,ctx.p,ctx.pid,ctx.family
    if f=='review_sliding_post':
        from .review_cfs_details import endpost
        endpost(ctx,base=ctx.c['point'][2]<1);return
    run=ctx.params.get('runway_profile',ctx.select(('runway_beam','beam','girder')));d=effective(p,run);w=effective(p,run,'width')
    if f=='review_rail_clip':
        a.member('M1',run,[-24,0,-d/2],[24,0,-d/2]);a.member('M2',pid,[-24,0,effective(p,pid)/2],[24,0,effective(p,pid)/2],basis='A',description='A rail envelope')
        for j,sg in enumerate((-1,1)):
            yy=sg*effective(p,pid,'width')/2;a.box('CLIP'+str(j),[-2,yy-.75,.5],[4,1.5,.5],'A','A adjustable rail clip');a.fastener('F'+str(j),[[0,yy,-.5]],[0,0,1],.625,1.5,['M1','CLIP'+str(j)],'A rail clip bolt',basis='A')
        a.section_at=0;return
    supportpid=ctx.select(('crane_bracket','beam','girder','rafter'))
    sd=effective(p,supportpid);a.member('M1',supportpid,[0,-22,-sd/2],[0,22,-sd/2],y=[1,0,0]);a.member('M2',run,[-24,0,d/2+.125],[24,0,d/2+.125]);a.box('SEAT',[-6,-w/2,0],[12,w,.125],'S','1/8 in steel bearing plate')
    a.fastener('F1',[[x,y,-p[supportpid]['dimensions'].get('tf',.5)] for x in (-4,4) for y in (-w/4,w/4)],[0,0,1],.875,p[supportpid]['dimensions'].get('tf',.5)+.125+p[run]['dimensions'].get('tf',.5),['M1','SEAT','M2'],'Four 7/8 in A325-SC, Class A, source seat bolts')
    if f=='review_crane_tie':
        tp=flat(p,4,.375);a.member('TIE',tp,[0,w/2,d],[0,w/2+18,d],y=[1,0,0],basis='A');a.fastener('FT',[[x,w/2+2,d-.1875] for x in (-1,1)],[0,0,1],.625,.75,['M2','TIE'],'A flexible tie-back attachment',basis='A');a.notes.append('Source flexible runway tie-back; local support fit A. Do not splice simple-span runway girders across their 1/2 in support gap.')
    a.section_at=4;a.dim([-4,0,0],[4,0,0],'8 in bolt pitch (A)',basis='A')
