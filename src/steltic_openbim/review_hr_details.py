"""Assembled HR variants; explicit physical load paths and source parameters."""
import math,re,copy
from .review_assemblies import *

def bolt_data(text):
    rows,cols,dia,pitch,gauge=4,1,.75,3,3
    matrix=re.search(r'(\d+)\s*x\s*(\d+)\s*x\s*'+NUMBER+r'\s*in\.?\s*(?:A325|A490|ASTM)',text,re.I)
    if matrix:return int(matrix[1]),int(matrix[2]),number(matrix[3]),3,3
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
    a,p=ctx.a,ctx.p;cp=ctx.select(('column','walkway_post','prop','endwall_post','rocking_post','transfer_vertical'))
    core=ctx.params.get('core_face_attachment')
    if core:
        from .review_receiver_geometry import horizontal_frame,extract
        beam,wall=ctx.ms[:2];origin=ctx.c['point'];far=max(beam['axis'],key=lambda q:math.dist(q,origin))
        axes=horizontal_frame(sub(far,origin));part=extract(ctx,wall,'M1',axes,36)
        half=core['wall_half_thickness_in'];thickness=core['embed_thickness_in'];width=core['embed_width_in'];height=core['embed_height_in']
        bd=effective(p,bp)
        yy=[dot(sub(q,origin),axes[1]) for q in wall['axis']]
        wall_width=effective(p,wall['profile_id'],'width');centre=yy[0]
        # Keep most of the patch over steel at a wall/opening edge. Its small
        # outstand accommodates the source single plate on the beam-web face.
        y0=max(centre-wall_width/2,min(-width/2,centre+wall_width/2-width+2))
        a.box('EMBED',[half,y0,-height],[thickness,width,height],'A',core['basis'])
        left=max(y0,centre-wall_width/2);right=min(y0+width,centre+wall_width/2)
        paths=[([half,left,z],[half,right,z]) for z in (-height,0)]
        paths += [([half,y,-height],[half,y,0]) for y in (y0,y0+width) if centre-wall_width/2<=y<=centre+wall_width/2]
        for i,(start,end) in enumerate(paths):a.weld('WE'+str(i),start,end,['M1','EMBED'],.25,basis='A',description='A face-patch fillet only over actual wall steel; edge outstand and wall local capacity require verification')
        ctx.support_attachment='EMBED';ctx.weak_axis_support=False
        a.notes.append(core['basis'])
        return wall['profile_id'],half+thickness
    source=next((m for m in ctx.ms if m['kind'] in ('column','walkway_post','prop','rocking_post','transfer_vertical')),None)
    beam=ctx.ms[0];bd=effective(p,bp);cd=effective(p,cp);weak=False
    if source:
        axis=unit(sub(*reversed(beam['axis'])));weak=abs(dot(axis,source['local_y']))>.7
    if weak and p[cp]['family']=='i':
        a.member('M1',cp,[0,0,-bd-14],[0,0,14],y=[1,0,0],description='Support column; weak-axis web connection '+cp);face=p[cp]['dimensions']['tw']/2
    elif source or ctx.family in ('review_crane_bracket','review_pin_beam','review_existing_joint'):
        a.member('M1',cp,[0,0,-bd-14],[0,0,14],description='Receiving column '+cp);face=cd/2
    else:
        receiver=next((m for m in ctx.ms[1:] if m['kind'] in ('girder','beam','moment_beam','walkway_edge_beam','truss_chord','transfer_chord')),None)
        if receiver:
            point=ctx.c['point'];far=max(beam['axis'],key=lambda q:math.dist(q,point));x=unit([far[0]-point[0],far[1]-point[1],0]);y=cross([0,0,1],x);axes=(x,y,[0,0,1])
            local=lambda q:[dot(sub(q,point),v) for v in axes]
            ends=[add(q,o) for q,o in zip(receiver['axis'],receiver['end_offsets'])];u=unit(sub(ends[1],ends[0]));length=math.dist(*ends);station=max(0,min(length,dot(sub(point,ends[0]),u)))
            selected=[add(ends[0],mul(u,t)) for t in (max(0,station-24),min(length,station+24))]
            cp=receiver['profile_id'];cd=effective(p,cp);width_axis=[dot(receiver['local_y'],v) for v in axes]
            part=a.member('M1',cp,*[local(q) for q in selected],y=width_axis,description='Actual receiving girder '+cp)
            normal=width_axis;half=p[cp]['dimensions'].get('tw',p[cp]['dimensions'].get('t',.25))/2
            if abs(normal[0])<.01:
                normal=cross(unit(sub(*reversed(part['member']['axis']))),normal);half=cd/2
            if abs(normal[0])<.01:raise ValueError('A parallel beam end needs an explicit splice/continuity selection: '+ctx.c['id']+' -> '+receiver['id'])
            centre=part['member']['axis'][0]
            face=(dot(normal,centre)+math.copysign(half,normal[0])+normal[2]*bd/2)/normal[0]
            ctx.support_surface=dict(normal=normal,offset=dot(normal,centre)+math.copysign(half,normal[0]))
        else:
            cp=ctx.select(('girder','beam','moment_beam','walkway_edge_beam','truss_chord'),cp);cd=effective(p,cp)
            a.member('M1',cp,[0,-24,-cd/2],[0,24,-cd/2],y=[1,0,0],description='Receiving girder '+cp);face=p[cp]['dimensions'].get('tw',p[cp]['dimensions'].get('t',.25))/2
    if ctx.params.get('boxing_t'):
        t=ctx.params['boxing_t'];cw=effective(p,cp,'width')
        length=ctx.params.get('boxing_length_in',bd+28);zlo=-bd/2-length/2;zhi=-bd/2+length/2
        for j,sg in enumerate((-1,1)):
            offset=sg*(cw+t)/2;name='BOX'+str(j);plate=flat(p,ctx.params.get('boxing_width_in',cd),t)
            a.member(name,plate,[offset if weak else 0,0 if weak else offset,zlo],[offset if weak else 0,0 if weak else offset,zhi],y=[0,1,0] if weak else [1,0,0],basis='A',representation_role='assembly_component' if 'boxing_length_in' in ctx.params else None,description=f'Source {str(length)+" in local" if "boxing_length_in" in ctx.params else "full-height"} column boxing; {t:g} in plate; A local edge fit')
            edge=ctx.params.get('boxing_width_in',cd)/2
            for sg_edge in (-1,1):
                a.weld('WB'+str(j)+str(sg_edge),[offset if weak else sg_edge*edge,sg_edge*edge if weak else offset,zlo],[offset if weak else sg_edge*edge,sg_edge*edge if weak else offset,zhi],['M1',name],kind='CJP',description='Source boxing plate to column flange tips')
        if weak:face=cw/2+t
    ctx.weak_axis_support=weak
    return cp,face

def draw(ctx):
    a,p,pid,txt,par,f=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params,ctx.family
    if par.get('actual_composite_core'):
        from .review_composite_core import draw as core
        return core(ctx)
    if par.get('actual_crane_joint'):
        from .review_crane_receivers import draw as actual_crane
        return actual_crane(ctx)
    if f in ('review_beam','review_existing_joint','review_crane_bracket'):
        # A member-specific V-beam end selection can accompany a generic
        # collector force check. Do not mix one record's bolt group with the
        # other record's setback or weld. Full source evidence stays in ctx.text.
        from .review_shear_selection import paired as paired_selection
        bp=pid;bd=effective(p,bp);bf=effective(p,bp,'width');cp,face=support(ctx,bp)
        typed_shear=f=='review_beam' and ctx.selected.get(('shear_plate','thickness_in')) is not None
        collector=None
        if typed_shear:
            from .hr_detail_selections import selected_shear_text,located_collector_fit
            txt=selected_shear_text(ctx)
            collector=located_collector_fit(ctx,txt)
        txt,twin=paired_selection(txt,weak=getattr(ctx,'weak_axis_support',False),column=cp)
        n=lambda pattern,default:findnum(pattern,txt,default)
        moment=par.get('moment',False) or f=='review_crane_bracket';gap=0 if moment else n(r'beam end set back (?:\(web side\) )?'+NUMBER+r' in',1) if twin else 1.25
        if collector:gap=collector['gap']
        rbs={};hit=re.search(r'RBS\s*\(?a = '+NUMBER+r'(?: in)?, b = '+NUMBER+r'(?: in)?, c = '+NUMBER,txt,re.I)
        if hit:rbs=dict(a_in=number(hit[1]),b_in=number(hit[2]),c_in=number(hit[3]),ends=[0]);moment=True;gap=0
        m=a.member('M2',bp,[face+gap,0,-bd/2],[face+gap+max(42,rbs.get('a_in',0)+rbs.get('b_in',0)+8),0,-bd/2],**({'rbs':rbs} if rbs else {}))
        if not moment and not par.get('core_face_attachment') and not any(mm['kind'] in ('column','walkway_post','prop','rocking_post','transfer_vertical') for mm in ctx.ms):
            support_width=effective(p,cp,'width');cope=max(0,support_width/2+.25-face-gap)
            if cope:
                m['member']['cope']={'length_in':cope,'depth_in':p[cp]['dimensions'].get('tf',.5)+.5,'ends':[0]}
                from .pilots.geometry import member_faces
                m['faces']=member_faces(m['member'],p)
                from .assembly_scene import bounds
                m['bounds']=bounds(m['faces'])
        rows,cols,dia,pitch,gauge=bolt_data(txt);t=ctx.n(r'(?:single plate|erection tab|web single plate)\s*(?:PL\s*)?'+NUMBER,.375)
        if typed_shear:
            t=ctx.selected.get(('shear_plate','thickness_in')) or t
            count=ctx.selected.get(('bolt','count')) or rows*cols
            dia=ctx.selected.get(('bolt','diameter_in')) or dia
            pitch=ctx.selected.get(('bolt','pitch_in')) or pitch
            cols=ctx.selected.get(('bolt','columns')) or cols
            gauge=ctx.selected.get(('bolt','gauge_in')) or gauge
            if count%cols:raise ValueError('Selected shear bolt count does not fit its columns at '+ctx.c['id'])
            rows=int(count//cols)
        if not txt and not typed_shear:rows=max(2,min(4,int((bd-3)/3)+1))
        if moment and 'erection tab' in txt:rows,cols,dia,pitch=4,1,.75,3
        if f=='review_crane_bracket':
            a.weld('WF1',[face,-bf/2,0],[face,bf/2,0],['M1','M2'],kind='CJP',description='Source CJP bracket flange; Category C; reinforcement left')
            a.weld('WF2',[face,-bf/2,-bd],[face,bf/2,-bd],['M1','M2'],kind='CJP');a.weld('WW',[face,0,-bd+1],[face,0,-1],['M1','M2'],.375,description='3/8 in web fillets both sides');a.section_at=face+6;return
        if f=='review_existing_joint':
            # Bolted hypothetical survey answer, with no weld to unverified 1968 steel.
            moment=False;rows,cols,dia,pitch=4,1,.875,3;t=.5
            a.notes.append('A: fictional existing joint survey answer: paired bolted web angles and flange cover/seat plates. No welding to existing A36 steel is shown; source survey and weldability requirements remain.')
        ph=(rows-1)*pitch+2*max(dia*1.5,1.5);edge=(ph-(rows-1)*pitch)/2
        if twin:t,ph=map(number,twin.groups());edge=(ph-(rows-1)*pitch)/2
        if typed_shear and ctx.selected.get(('shear_plate','depth_in')) is not None:
            ph=ctx.selected[('shear_plate','depth_in')];edge=(ph-(rows-1)*pitch)/2
            if edge<dia/2:raise ValueError('Selected bolt group and plate depth conflict')
        elif ph>bd-2:
            # Preserve the source pattern; a mismatched source profile is an error.
            ph=bd-1.5;edge=(ph-(rows-1)*pitch)/2
            if edge<dia*.8:raise ValueError('Source bolt group does not fit '+ctx.model['pilot']+' '+pid+' '+str((rows,cols,dia,pitch)))
        width=n(r'bolt line '+NUMBER+r' in from the weld',3)+(cols-1)*gauge+max(2*dia,1.5);tw=p[bp]['dimensions'].get('tw',.375);z=-bd/2-ph/2
        plate_edge=max(2*dia,1.5)
        if collector:
            plate_edge=collector['plate_edge'];width=collector['line']+plate_edge
            if abs(edge-collector['vertical'])>1e-5:raise ValueError('Collector end distance disagrees with its bolt pitch and plate depth')
        if twin:
            plate_edge=n(NUMBER+r' in beam-end and plate-edge distances',2.25)
            width=gap+plate_edge+(cols-1)*gauge+plate_edge
        pattern_basis='S' if re.search(r'\b(?:bolts|erection tab|column\(s\))\b',txt,re.I) else 'A'
        shim=.0625 if twin else 0
        plate=a.box('P1',[face,tw/2+shim,z],[width,t,ph],pattern_basis,'Shear plate / erection tab; A fitted width where unprovided')
        if typed_shear:
            plate['thickness']=t
            grade=ctx.selected.get(('shear_plate','material'))
            if grade:plate['selected_material']=grade
        paired=bool(twin) or par.get('paired_shear_plates',False)
        if typed_shear:
            if ctx.selected.get(('shear_plate','count')) is not None:
                paired=ctx.selected[('shear_plate','count')]==2
            elif ('connection','variant') not in ctx.selected.conflicts:
                variant=ctx.selected.get(('connection','variant'))
                if variant in ('double_plate_shear','single_plate_shear'):
                    paired=variant=='double_plate_shear'
        joins=['M2','P1']
        if paired:
            second=a.box('P2',[face,-tw/2-t,z],[width,t,ph],'S','Source second shear plate / double-shear joint')
            if typed_shear:
                second['thickness']=t
                if plate.get('selected_material'):second['selected_material']=plate['selected_material']
            joins.append('P2')
        if shim:a.box('SHIM',[face+gap,tw/2,z],[width-gap,shim,ph],'S','Source 1/16 in finger shim against beam web');joins.append('SHIM')
        bolt=a.fastener('F1',grid(rows*cols,cols,pitch,gauge,(face+width-plate_edge-(cols-1)*gauge,-tw/2-(t if paired else 0),z+edge)),[0,1,0],dia,tw+shim+t*(2 if paired else 1),joins,f'{rows} rows x {cols}; {dia:g} in '+('A490' if 'A490' in txt else 'A325')+'; source pretension/faying-surface requirements',pattern_basis)
        if typed_shear:
            bolt['functional_kind']='bolt'
            material=ctx.selected.get(('bolt','material'))
            if material:bolt['selected_material']=material
        weld=n(r'\('+NUMBER+r' in fillets both sides',.25)
        if twin:weld=n(r'(?:with one|\(one) '+NUMBER+r' in (?:E70 )?fillet',.5)
        a.weld('W1',[face,tw/2,z],[face,tw/2,z+ph],[getattr(ctx,'support_attachment','M1'),'P1'],weld,description=f'{weld:g} in fillet both sides to support')
        if paired:a.weld('W2',[face,-tw/2,z],[face,-tw/2,z+ph],['M1','P2'],weld,description='Source second shear-plate support weld')
        surface=getattr(ctx,'support_surface',None)
        if surface:
            normal=surface['normal'];offset=surface['offset'];sign=1 if normal[0]>0 else -1
            x_at=lambda y,z:(offset-normal[1]*y-normal[2]*z)/normal[0]
            for label in ('P1','P2'):
                part=next((q for q in a.parts if q['id']==label),None)
                if part is None:continue
                _,yy,zz=part['geometry']['origin'];_,thick,high=part['geometry']['size']
                start=min(x_at(y,z) for y in (yy,yy+thick) for z in (zz,zz+high))
                outer=face+width;a.parts.remove(part)
                made=a.box(label,[start,yy,zz],[outer-start,thick,high],part['basis'],part['description']+'; A skew support-edge cut')
                clip_part(made,mul(normal,sign),offset*sign)
            for w in a.welds:
                if w['id'] in ('W1','W2'):
                    for endpoint in ('a','b'):q=w[endpoint];q[0]=x_at(q[1],q[2])
        if twin:
            for w in a.welds:
                if w['id'] not in ('W1','W2'):continue
                for q in (w['a'],w['b']):q[1]=tw/2+shim+t if w['id']=='W1' else -tw/2-t
                w['description']='Source one fillet on the outer face only; inner face not welded'
            a.notes.append('S: paired shear plates spaced t_w + 1/16 in, source finger shim fitted at one web face before pretensioning. One-sided outer fillets only; bolted beam web restrains plate rotation.')
        if collector:
            from .connection_cuts import drill_receivers
            drill_receivers(a,bolt,collector['hole'])
            if not paired and 'fillets both sides' in txt:
                seam=next(w for w in a.welds if w['id']=='W1')
                outer=[add(q,[0,t,0]) for q in (seam['a'],seam['b'])]
                if surface:
                    for q in outer:q[0]=x_at(q[1],q[2])
                a.weld('W1-OUTER',*outer,seam['connects'],weld,description='Selected outer-face collector plate fillet')
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
        length=par.get('link_length',36)
        d=effective(p,pid);bf=effective(p,pid,'width');tw=p[pid]['dimensions'].get('tw',.375);tf=p[pid]['dimensions'].get('tf',.5)
        a.member('M1',pid,[-30,0,0],[30,0,0]);a.member('M2',pid,[30,0,0],[42,0,0],description='Same continuous source beam beyond protected link')
        t=ctx.n(r'stiffeners?\s*(?:PL\s*)?'+NUMBER,.5)
        for j,x in enumerate((-length/2,-length/4,0,length/4,length/2)):
            for side in (-1,1):
                label=f'S{j}{side}';yy=tw/2 if side>0 else -bf/2+.25;a.box(label,[x-t/2,yy,-d/2+tf],[t,bf/2-tw/2-.25,d-2*tf],'A','Link full-depth web stiffener; adopted station')
                a.weld('W'+label,[x,yy,-d/2+tf],[x,yy,d/2-tf],['M1',label],.25,basis='A')
        a.dim([-length/2,0,-d/2],[length/2,0,-d/2],f'{length:g} in protected shear link',basis='S');a.section_at=0
        a.translate([0,0,-d/2]) # Source joint point is top of steel, not centroid.
    elif f.startswith('review_retrofit_'):retrofit(ctx)
    elif f in ('review_crane_seat','review_crane_tie','review_rail_clip','review_sliding_post','review_joist_seat'):industrial(ctx)
    else:raise ValueError(f)

def pin_beam(ctx):
    from .hr_detail_selections import pin_selection,outer_clevis_weld
    from .connection_cuts import drill_joined_plates
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text;d=effective(p,pid);bf=effective(p,pid,'width');tf=p[pid]['dimensions']['tf'];tw=p[pid]['dimensions']['tw'];cp,face=support(ctx,pid)
    from .selected_beam_hinge import draw as selected_beam_pin
    if selected_beam_pin(ctx,face):return
    pin,pin_material,hole_clearance=pin_selection(ctx)
    stub=ctx.n(r'beam stub '+NUMBER+r' in',ctx.n(NUMBER+r' in beam stub',22));kt=ctx.n(r'knife plate (?:PL )?'+NUMBER+r' in',2);ct=ctx.n(r'two clevis plates (?:PL )?'+NUMBER+r' in',1.5);lk=ctx.n(r'Lk = '+NUMBER+r' in',ctx.n(r'inserted '+NUMBER+r' in between the stub flanges',10));lc=ctx.n(r'Lc = '+NUMBER+r' in',ctx.n(r'inserted '+NUMBER+r' in between the beam flanges',10))
    outer_size=outer_clevis_weld(ctx)
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
        a.weld('WC'+str(j),[face+stub+1,yy,-tf],[face+stub+1+lc,yy,-tf],['CLEVIS'+str(j),'BEAM1'],outer_size if outer_size is not None else .6875,basis='S' if outer_size is not None else 'A',description='Outer-face clevis-to-flange fillet; both flange levels')
    a.box('TRANS',[face+stub+1+lc-.5,-bf/2,-d+tf],[.5,bf,d-2*tf],'S','Web-to-clevis transverse plate')
    group=a.fastener('PIN',[[px,-kt/2-gap-ct,-d/2]],[0,1,0],pin,kt+2*gap+2*ct,['KNIFE','CLEVIS0','CLEVIS1'],f'{pin:g} in {pin_material} pin, double shear; A retaining washers')
    group.update(functional_kind='pin',selected_material=pin_material)
    drill_joined_plates(a,group,pin+(hole_clearance if hole_clearance is not None else .0625),'S selected pin-hole clearance' if hole_clearance is not None else 'A 1/16 in diametral fit allowance')
    a.weld('WK',[insertion,0,-d+tf],[insertion,0,-tf],['KNIFE','M2'],kind='CJP',description='Source knife to cut stub web CJP')
    a.weld('WS',[face,-bf/2,0],[face,bf/2,0],['M1','M2'],kind='CJP',description='Stub flange/web CJP to column')
    a.weld('WT',[face+stub+1+lc,-bf/2,-d/2],[face+stub+1+lc,bf/2,-d/2],['TRANS','M3'],.1875,description='Transverse plate fillet to web and clevis ends')
    a.section_at=px;a.dim([face,0,2],[px,0,2],f'{stub+.5:g} in column face to pin');a.dim([insertion,0,-d],[face+stub,0,-d],f'Lk {lk:g} in')
    a.notes.append('Source knife/clevis insertions, 1 in flange gap and web cut-backs are shown. Plate end shapes are A rectangular fit envelopes; source narrowed tip dimensions and weld-access exclusions govern the joint.')

def base(ctx):
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text;d=effective(p,pid);w=effective(p,pid,'width');existing=ctx.params.get('existing_grillage')
    if existing:
        gp=ctx.default_w();a.member('M1',pid,[0,0,-24],[0,0,24]);a.member('M2',gp,[-30,0,-30],[30,0,-30],basis='A',representation_role='assembly_component',description='A existing encased grillage assumption');a.box('CONC',[-36,-30,-48],[72,60,48],'A','Existing concrete context',kind='concrete');a.box('BEARING',[-d/2-3,-w/2-3,-24],[d+6,w+6,1],'A','A retained bearing plate');a.weld('W1',[-d/2,-w/2,-23],[d/2,-w/2,-23],['M1','BEARING'],.25,basis='A',description='A historic connection depiction; existing metallurgy and weld condition not verified');a.section_axis=2;a.section_at=-25;a.notes.append('No designed anchor rods in source. Existing grillage and its connections are fictional survey assumptions, not an assessed foundation.');return
    # An embedded anchor end or shear lug does not make the column embedded.
    from .review_base_selection import embedment,rods,flange_rows,lug_arms
    le=embedment(txt)
    delegated=re.search(r'anchor reinforcement.*?(?:foundation engineer|foundation designer)',txt,re.I)
    if delegated:a.notes.append('S: '+delegated[0]+'. This is delegated concrete reinforcement, not a steel box around the column.')
    if le is not None:
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
        face_match=re.search(r'face bearing plates PL '+NUMBER+r' x '+NUMBER+r' in',txt,re.I)
        face_thickness=0
        if face_match:
            face_thickness,face_width=map(number,face_match.groups())
            for j,sg in enumerate((-1,1)):
                xx=d/2 if sg>0 else -d/2-face_thickness;tag='FACE'+str(j)
                a.box(tag,[xx,-face_width/2,-le],[face_thickness,face_width,le],'S','Source outer-flange bearing plate; full embedment')
                a.weld('WF'+str(j),[sg*d/2,-face_width/2,-le],[sg*d/2,-face_width/2,0],['M1',tag],.5,basis='A',description='Source all-round fillet; A 1/2 in size where unquantified')
        reinforcing=re.search(r'8 PL '+NUMBER+r' x '+NUMBER+r' in',txt)
        if reinforcing:
            rt,rw=map(number,reinforcing.groups());height=ctx.n(r'to '+NUMBER+r' in above',50);clear=ctx.n(r'\('+NUMBER+r' in apart',8.25);ri=0
            selected_weld=re.search(r'double fillets \('+NUMBER+r' in\)',txt[reinforcing.end():],re.I)
            weld_size=number(selected_weld[1]) if selected_weld else .25
            for face in range(4):
                axis=[1 if face==0 else -1 if face==1 else 0,1 if face==2 else -1 if face==3 else 0,0];along=[axis[1],-axis[0],0];facehalf=d/2 if face<2 else w/2
                for sg in (-1,1):
                    ri+=1;q=add(mul(axis,facehalf),mul(along,sg*(clear/2+rw/2)));q[2]=-le;origin=add(q,mul(along,-rw/2))
                    a.box('REINF'+str(ri),origin,[rw,rt,le+height],'S','Source embedded box reinforcement',x=along,y=axis)
                    for edge in (-1,1):
                        at=add(q,mul(along,edge*rw/2));a.weld(f'WR{ri}{edge}',at,add(at,[0,0,le+height]),['M1','REINF'+str(ri)],weld_size,basis='S' if selected_weld else 'A',description='Source double fillets; stop 1 in clear of gusset collar' if selected_weld else 'A 1/4 in fillet proposal; source size not quantified')
        count=int(ctx.n(r'(\d+) x 7/8 in headed studs',ctx.n(r'(\d+) headed studs 7/8',0)));dia=.875
        if not count and 'two rows of 14 headed studs' in txt:count=28
        if count:
            # Every source stud is represented; stations are A where the source gives only counts.
            per=math.ceil(count/4);specified=re.search(r'(\d+) rows '+NUMBER+r' in apart from '+NUMBER+r' in below',txt)
            nlevels=int(specified[1]) if specified else max(1,int((le-12)/6));rows=math.ceil(per/nlevels);pitch=number(specified[2]) if specified else (le-12)/max(1,nlevels-1);first=number(specified[3]) if specified else 6;placed=0
            bottom_zone=re.search(r'(\d+) rows of \d+ at 6 in.*?from 6 in above the end plate',txt)
            if bottom_zone:nlevels=int(bottom_zone[1]);rows=math.ceil(per/nlevels);first=le-6;pitch=-6
            for face in range(4):
                normal=[1 if face==0 else -1 if face==1 else 0,1 if face==2 else -1 if face==3 else 0,0];origin=[normal[0]*(d/2+face_thickness),normal[1]*w/2,0];along=[0,1,0] if face<2 else [1,0,0];half=(w if face<2 else d)/2
                points=[]
                for j in range(min(per,count-placed)):
                    across=ctx.n(NUMBER+r' in across the faces',min(6,2*(half-2)/max(1,rows-1)));shift=(j%rows-(rows-1)/2)*across;z=-first-(j//rows)*pitch;pt=add(origin,add(mul(along,shift),[0,0,z]));points.append(pt);placed+=1
                if points:a.fastener('STUDS'+str(face),points,normal,dia,5,['M1','CONC'],'Source 7/8 x 5 in headed stud group; A stations / illustrative head envelope')
            a.notes.append(f'S: all {count} headed studs represented. '+('Source row count, vertical and transverse spacing retained.' if specified else 'A stations within the source embedment; exact distribution requires reconciliation.'))
        from .review_base_selection import erection_rods
        erection=erection_rods(txt)
        if erection:
            n=erection['count'];edge=erection['edge_min'];dia=erection['diameter'];grade=erection['grade']
            points=[[sx*(bx/2-edge),sy*(by/2-edge),-le-t-12] for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1))]
            if n!=4:raise ValueError('An explicit erection-rod layout is required for this source count')
            selected='S' if erection['selected_size'] else 'A'
            a.fastener('ERECTION-ANCHORS',points,[0,0,1],dia,12+t,['P1','CONC'],f'S {n} erection anchor rods; {selected} {dia:g} in {grade}; A 12 in embedment and symmetric stations at edge minimum {edge:g} in; erection only',basis=f'S count; {selected} diameter/grade; A length and set-out')
        a.section_axis=2;a.section_at=-le/2;a.dim([bx/2,0,-le],[bx/2,0,0],f'Embedment {le:g} in');return
    match=re.search(r'(?:base plate\s*(?:PL)?|moment base:\s*PL)\s*'+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',txt,re.I)
    t,bx,by=list(map(number,match.groups())) if match else (1,d+8,w+8)
    layout=flange_rows(txt,bx if match else None,by if match else None,d)
    from . import stiffened_base
    flange_stiffeners=stiffened_base.selection(txt)
    if (layout or flange_stiffeners) and match:
        # The source uses DG1 B (parallel to flange) x N (depth direction).
        # Local X is the column depth direction, not the first printed size.
        t,by,bx=list(map(number,match.groups()))
    selected_rods=rods(txt);n,dia,grade=selected_rods or (4,.75,'F1554 Grade 36 (A)');embed=ctx.n(r'embedment\s*(?:hef = )?'+NUMBER,18);grout=ctx.n(r'on '+NUMBER+r' in (?:non-shrink )?grout',2)
    a.box('CONC',[-bx/2-8,-by/2-8,-embed-6],[bx+16,by+16,embed+6],'A','Foundation context',kind='concrete')
    a.box('GROUT',[-bx/2,-by/2,0],[bx,by,grout],'S','Source grout',kind='grout')
    tongues=ctx.params.get('integral_gusset_tongues')
    if tongues:
        from .base_plate_extensions import add as add_stock
        add_stock(a,bx,by,grout,t,tongues)
    else:
        a.box('P1',[-bx/2,-by/2,grout],[bx,by,t],'S' if match else 'A','Base plate')
    context_height=max(32,flange_stiffeners['height']+4) if flange_stiffeners else 32
    a.member('M1',pid,[0,0,grout+t],[0,0,grout+t+context_height]);edge=ctx.n(r'rods '+NUMBER+r' in from the plate edges',max(1.5,1.5*dia));rows=max(2,math.ceil(n/2));points=[]
    if flange_stiffeners:
        stiffened_base.add(a,flange_stiffeners,d,w,grout+t)
        gap=ctx.selected.get(('anchor_pattern','stiffener_offset_in')) or flange_stiffeners['outside']
        points=[[sg*(d/2+station),side*(w/2+gap),-embed] for sg in (-1,1)
                for station in flange_stiffeners['stations'] for side in (-1,1)]
        if len(points)!=n:raise ValueError('Stiffened-base row stations do not account for every selected rod')
    elif layout:
        nrows,ncols,spacing,a1,pitch=layout
        a1=ctx.selected.get(('anchor_pattern','flange_offset_in')) or a1
        pitch=ctx.selected.get(('anchor_pattern','spacing_in')) or pitch
        if 2*nrows*ncols!=n:raise ValueError('Source anchor count and flange layout disagree')
        for sg in (-1,1):
            for r in range(nrows):
                for col in range(ncols):points.append([sg*(d/2+a1+r*spacing),(col-(ncols-1)/2)*pitch,-embed])
        if any(abs(q[0])+dia/2>bx/2 or abs(q[1])+dia/2>by/2 for q in points):raise ValueError('Source anchor layout falls outside base plate')
    else:
        for i in range(n):points.append([(-1 if i%2==0 else 1)*(bx/2-edge),-by/2+edge+(i//2)*(by-2*edge)/(rows-1),-embed])
    top_washer=re.search(r'top plate washers PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in',txt,re.I)
    washer_dimensions=list(map(number,top_washer.groups())) if top_washer else None
    if not washer_dimensions:
        alt=re.search(r'plate washers '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in over the rod holes',txt,re.I)
        if alt:
            wx,wy,wt=map(number,alt.groups());washer_dimensions=[wt,wx,wy]
        else:
            alt=re.search(r'(?:with )?PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+r' in plate washers on the base plate',txt,re.I)
            if alt:washer_dimensions=list(map(number,alt.groups()))
    washer_grip=washer_dimensions[0] if washer_dimensions and ctx.params.get('bearing_at_workpoint') else 0.
    anchors=a.fastener('ANCH',points,[0,0,1],dia,embed+grout+t+washer_grip,['CONC','P1'],f'{n} x {dia:g} in {grade} anchor rods; A embedment where source delegates it',basis='S count/diameter/grade; A embedment' if selected_rods else 'A')
    from .connection_cuts import drill_plate
    diameter=ctx.selected.get(('anchor_hole','diameter_in'))
    if diameter is None:
        hole=re.search(NUMBER+r'[- ]in(?:ch)?(?: diameter| dia\.?)? (?:rod |anchor )?holes?\s*\(AISC Manual Table 14-2',txt,re.I)
        if not hole:hole=re.search(r'\brod holes '+NUMBER+r' in\b',txt,re.I)
        if hole:diameter=number(hole[1])
    if diameter is not None:
        if diameter<dia:raise ValueError('Selected base plate hole is smaller than the anchor diameter')
        drill_plate(next(part for part in a.parts if part['id']=='P1'),points,[0,0,1],diameter,'S selected anchor hole diameter')
    if selected_rods:
        anchors.update(functional_kind='anchor',selected_material=ctx.selected.get(('anchor','material')) or grade)
    directional={field:ctx.selected.get(('anchor_pattern',field)) for field in
                 ('edge_flange_normal_in','edge_along_flange_in','minimum_edge_in','flange_offset_in','spacing_in')}
    if directional['edge_flange_normal_in'] is not None or directional['edge_along_flange_in'] is not None:
        anchors['parameters']={'source_anchor_pattern':{k:v for k,v in directional.items() if v is not None},
                               'flange_normal_axis_local':[1,0,0],'flange_row_axis_local':[0,1,0]}
    bottom_washer=re.search(NUMBER+r' in square plate washers at the embedded end',txt,re.I)
    for j,q in enumerate(points):
        if washer_dimensions:
            wt,wx,wy=washer_dimensions;wid='WASHER-TOP-'+str(j)
            washer=a.box(wid,[q[0]-wx/2,q[1]-wy/2,grout+t],[wx,wy,wt],'S','Source top plate washer at the actual anchor')
            washer_hole=ctx.selected.get(('washer_hole','diameter_in')) or dia+.0625
            drill_plate(washer,[q],[0,0,1],washer_hole,'S selected washer hole' if ctx.selected.get(('washer_hole','diameter_in')) else 'A 1/16 in diametral washer clearance')
            size=ctx.n(r'welded to the base plate with '+NUMBER+r' in fillets',.25)
            corners=[[q[0]+sx*wx/2,q[1]+sy*wy/2,grout+t] for sx,sy in ((-1,-1),(1,-1),(1,1),(-1,1))]
            if re.search(r'washer.*?welded to the base plate',txt,re.I):
                for k in range(4):a.weld(wid+'-W'+str(k),corners[k],corners[(k+1)%4],[wid,'P1'],size,description='Source washer all-round fillet')
        if bottom_washer:
            size=number(bottom_washer[1]);washer=a.box('WASHER-END-'+str(j),[q[0]-size/2,q[1]-size/2,-embed],[size,size,.5],'S plan size; A thickness','Source embedded-end square washer, A 1/2 in thickness')
            drill_plate(washer,[q],[0,0,1],dia+.0625,'A 1/16 in diametral embedded washer clearance')
    if re.search(r'column flanges and web CJP-welded to the base plate|column welded to the plate with CJP groove welds at the flanges and the web',txt,re.I) and p[pid]['family']=='i':
        tf=p[pid]['dimensions']['tf'];z=grout+t
        for side in (-1,1):
            x=side*(d-tf)/2
            a.weld('COLUMN-FLANGE-'+str(side),[x,-w/2,z],[x,w/2,z],['M1','P1'],kind='CJP',
                   description='Selected column flange CJP at the base plate')
        a.weld('COLUMN-WEB',[-d/2+tf,0,z],[d/2-tf,0,z],['M1','P1'],kind='CJP',description='Selected column web CJP at the base plate')
    else:
        a.weld('W1',[-d/2,-w/2,grout+t],[d/2,-w/2,grout+t],['M1','P1'],kind='CJP' if 'CJP' in txt else 'fillet',description='Column-to-plate weld per source flange/web specification')
    if 'lug' in txt:
        primary=re.search(r'shear lug:?\s+(.*?)\bPL '+NUMBER+r' x '+NUMBER+r' in, '+NUMBER+r' in embedded',txt,re.I)
        secondary=re.search(r'second arm PL '+NUMBER+r' x '+NUMBER+r' in',txt,re.I)
        arms=lug_arms(txt)
        (lt,lw,le),(rt,rw,_)=arms or ((.75,min(d,16),4),(.75,min(d,16),4))
        if primary:lt,lw,le=map(number,primary.groups()[1:])
        lt=ctx.selected.get(('shear_lug','thickness_in')) or lt
        lw=ctx.selected.get(('shear_lug','width_in')) or lw
        le=ctx.selected.get(('shear_lug','embedment_in')) or le
        width_axis=[1.,0.,0.];normal=[0.,1.,0.]
        if re.search(r'\(continuous\) across the shear in the brace plane \(column strong axis\)',txt,re.I):
            width_axis=[0.,-1.,0.];normal=[1.,0.,0.]
        world=ctx.selected.get(('shear_lug','face_normal'))
        written=re.search(r'shear lug has a face normal along world ([XY])\b',txt,re.I)
        if world is None and written:world=[1.,0.,0.] if written[1].upper()=='X' else [0.,1.,0.]
        if world is not None:
            instance=next((c.get('assembly_instance') for c in ctx.package['physical']['connections'] if c['id']==ctx.c['id']),None)
            if not instance:raise ValueError('Selected shear lug direction needs a located base')
            normal=unit([dot(world,instance['x_axis']),dot(world,instance['y_axis']),0.])
            width_axis=[normal[1],-normal[0],0.]
        start=add(add(mul(width_axis,-lw/2),mul(normal,-lt/2)),[0,0,-le])
        lug=a.box('LUGX',start,[lw,lt,grout+le],'S' if arms or primary else 'A','Main shear lug centered below the base',
                  x=width_axis,y=normal)
        lug['parameters']=dict(source_role='shear_lug',thickness_in=lt,width_in=lw,embedment_in=le)
        material=ctx.selected.get(('shear_lug','material')) or (primary[1].strip() if primary else None)
        if material:lug['selected_material']=material
        # The crossing arm is split at the main plate, avoiding duplicate steel.
        for sg in ((-1,1) if arms or secondary or not primary else ()):
            start=lt/2 if sg>0 else -rw/2;span=(rw-lt)/2
            if span<=0:raise ValueError('Crossing shear-lug arm cannot fit around main plate')
            corner=add(mul(width_axis,-rt/2),mul(normal,start))
            label='LUGY'+str(sg);a.box(label,add(corner,[0,0,-le]),[rt,span,grout+le],'S' if arms else 'A',
                'Source crossing lug arm, fitted to main plate',x=width_axis,y=normal)
            weld_start=add(corner,[0,0,grout])
            a.weld('WL'+str(sg),weld_start,add(weld_start,mul(normal,span)),[label,'P1'],kind='CJP')
            if 'in two arms CJP-welded to both faces of the main plate' in txt:
                end_face=mul(normal,sg*lt/2)
                a.weld('LUG-CROSS'+str(sg),add(end_face,[0,0,-le]),add(end_face,[0,0,grout]),
                       [label,'LUGX'],kind='CJP',description='Crossing arm CJP to continuous shear lug')
        a.weld('WL',add(mul(width_axis,-lw/2),[0,0,grout]),add(mul(width_axis,lw/2),[0,0,grout]),['LUGX','P1'],kind='CJP')
    a.section_axis=2;a.section_at=grout+t/2;a.dim([-bx/2,0,grout],[bx/2,0,grout],f'{bx:g} in plate');a.dim([points[0][0],0,grout+t+5],[points[1][0],0,grout+t+5],basis='A',offset=30)
    if ctx.params.get('bearing_at_workpoint'):
        for extension in tongues or []:
            i=extension['axis'];sign=extension['sign'];length=extension['length_in']
            other=1-i;edge=[0.,0.,grout+t];edge[i]=sign*(bx,by)[i]/2;edge[other]=(bx,by)[other]/2
            tip=edge[:];tip[i]+=sign*length
            a.dim(edge,tip,f'{length:g} in brace-side extension',view='section',basis='S')
            a.notes.append(f"S: base plate {(bx,by)[i]+length:g} in overall; {length:g} in extension toward brace. Anchor group on nominal stock.")
        a.translate([0,0,-grout-t])
        a.notes.append('Plate top and column bearing at brace workpoint. Grout below plate.')

def splice(ctx):
    from .selected_column_splice import selected,cjp_paths
    if ctx.family=='review_splice' and selected(ctx):return
    a,p,pid,txt=ctx.a,ctx.p,ctx.pid,ctx.text;lower=ctx.ms[1]['profile_id'] if len(ctx.ms)>1 else pid;d=effective(p,pid);ld=effective(p,lower);w=effective(p,pid,'width')
    a.member('M1',lower,[0,0,-30],[0,0,0]);a.member('M2',pid,[0,0,.0625],[0,0,30])
    if ctx.family=='review_column_continuity':
        a.weld('CONT',[0,-w/2,0],[0,w/2,0],['M1','M2'],kind='CONTINUOUS',basis='S',description='Continuous physical column across analysis storey split; NO field joint or weld at this datum');a.section_axis=2;a.section_at=0;return
    if 'CJP' in txt and 'bolted' not in txt[:100]:
        a.weld('SPLICE',[-d/2,-w/2,0],[d/2,w/2,0],['M1','M2'],kind='CJP',description='Source all-around column splice CJP; thickness transitions and demand-critical requirements retained')
        boxing=ctx.params.get('boxing_t') or ctx.ms[0].get('boxing_thickness_in')
        if boxing:
            for j,sg in enumerate((-1,1)):
                names=[]
                for index,(shape,z0,z1) in enumerate(((lower,-30,0),(pid,.0625,30))):
                    actual=ctx.ms[0 if index else 1]
                    if not actual.get('boxing_thickness_in'):continue
                    cw=effective(p,shape,'width');cd=effective(p,shape);name=f'BOX{j}{index}';names.append(name);offset=sg*(cw+boxing)/2
                    pw=actual.get('boxing_width_in',cd)
                    a.member(name,flat(p,pw,boxing),[0,offset,z0],[0,offset,z1],y=[1,0,0],basis='A',description=f'Source {boxing:g} in full-height side plate; A local edge fit')
                    for edge in (-1,1):a.weld(f'WB{j}{index}{edge}',[edge*pw/2,offset,z0],[edge*pw/2,offset,z1],['M1' if index==0 else 'M2',name],kind='CJP',description='Boxing side plate to column flange tips')
                if len(names)==2:a.weld(f'BOX-SPLICE{j}',[-pw/2,sg*(w+boxing)/2,0],[pw/2,sg*(w+boxing)/2,0],names,kind='CJP',basis='S' if 'side plates spliced' in txt else 'A',description='Side-plate splice at the shaft splice datum')
        from .review_splice_parts import transition,erection
        transition(ctx,lower);erection(ctx,lower);cjp_paths(ctx)
        a.section_axis=2;a.section_at=-12 if any(q['id']=='DIVISION' for q in a.parts) else 4;a.dim([-d/2,0,15],[d/2,0,15],'Upper shaft depth',basis='S',offset=-30)
        a.notes.append('Splice world elevation and source floor offset are in the occurrence index. Source CJP requirements remain authoritative; temporary erection fit and installation sequence shown as A.')
        return
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
    if ctx.family=='review_plate_wall' and par.get('actual_plate_boundary'):
        from .review_plate_boundaries import draw
        return draw(ctx)
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
    sign=1 if horizontal==0 else -1
    local=lambda q:[q[horizontal]-point[horizontal],sign*(q[normal]-point[normal]),q[2]-point[2]]
    vector=lambda q:[q[horizontal],sign*q[normal],q[2]]
    for i,m in enumerate(ctx.ms):
        if m['kind']=='column':continue
        physical=[add(q,o) for q,o in zip(m['axis'],m.get('end_offsets',[[0,0,0],[0,0,0]]))]
        near,far=sorted(physical,key=lambda q:math.dist(q,point));v=unit(vector(sub(far,near)));origin=local(near);length=math.dist(near,far)
        part=a.member('M'+str(i),m['profile_id'],add(origin,mul(v,min(2,length/4))),add(origin,mul(v,min(30,length))),y=vector(m['local_y']),basis='S axis/profile; A end cutback');ends.append((part,v,m))
    if ctx.family=='review_stmf_end':
        column=next(m for m in ctx.ms if m['kind']=='column');cp=column['profile_id'];q=local(column['axis'][0]);a.member('COLUMN',cp,[q[0],q[1],-20],[q[0],q[1],20],y=vector(column['local_y']))
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
    if 'beam' in ctx.family:a.translate([0,0,-d/2])
    a.section_axis=0 if 'beam' in ctx.family else 2;a.section_at=0

def industrial(ctx):
    a,p,pid,f=ctx.a,ctx.p,ctx.pid,ctx.family
    if f=='review_sliding_post':
        if ctx.params.get('actual_endwall_head') or ctx.params.get('actual_endwall_base'):
            from .review_endwall_posts import head,base
            return head(ctx) if ctx.params.get('actual_endwall_head') else base(ctx)
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
