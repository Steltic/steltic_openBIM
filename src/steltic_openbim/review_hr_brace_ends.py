"""Carry adopted brace end fits into the physical model, preserving worklines."""
import math,re
from .review_assemblies import *
from .pilots.model import add,sub,mul,unit


CASES={'hr1','hr15','hr23','hr29','hr34a','hr34b'}


def bind(model,package):
    if not model.get('pilot','').startswith('hr'):return
    from .assembly_templates import build_scene
    lookup={m['id']:m for m in model['members']}
    links=model.setdefault('connection_endpoint_links',[]);changes=[];pending_slots={};scenes={};old_spans={}
    for c in model['connections']:
        if c['detail_ref']['id'] not in ('review_brace','review_brb'):continue
        actual=lookup[c['member_ids'][0]]
        if actual['kind']!='brace' or min(math.dist(p,c['point']) for p in actual['axis'])>1e-5:continue
        # A saved drawing scene identifies the exact fitted variant. During
        # initial model construction there is no scene ID yet.
        from .hr_detail_selections import selected_fields,SelectionConflict
        selected=selected_fields(package,c)
        key=(c['assembly_id'],selected.signature(),bool(c.get('parameters',{}).get('common_apex_datum'))) if c.get('assembly_id') else None
        if key is None or key not in scenes:
            try:
                scene=build_scene(model,package,c)
            except SelectionConflict as issue:
                if not c.get('assembly_id'):
                    raise
                issue.record(package,c['id'])
                continue
            if key is not None:scenes[key]=scene
        else:scene=scenes[key]
        actual=lookup[c['member_ids'][0]];end=min(range(2),key=lambda i:math.dist(actual['axis'][i],c['point']))
        receiver=next((p.get('member') for p in scene['parts'] if p['id']=='BRACE'),None)
        if not receiver:continue
        old_spans.setdefault(actual['id'],[add(p,o) for p,o in zip(actual['axis'],actual['end_offsets'])])
        local=receiver['axis'][0]
        if receiver.get('slots'):
            pending_slots.setdefault(actual['id'],{})[end]=(c['id'],receiver['slots'][0])
        distance=math.sqrt(sum(x*x for x in local));ray=unit(sub(actual['axis'][1-end],actual['axis'][end]))
        offset=mul(ray,distance);previous=actual['end_offsets'][end]
        if math.dist(offset,previous)<1e-7:continue
        actual['end_offsets'][end]=offset
        if math.dist(*actual['axis'])<=sum(math.sqrt(sum(x*x for x in q)) for q in actual['end_offsets']):
            raise ValueError('Adopted brace ends consume the physical member: '+actual['id'])
        links[:]=[r for r in links if (r['member_id'],r['end'])!=(actual['id'],'end' if end else 'start')]
        links.append(dict(member_id=actual['id'],end='end' if end else 'start',connection_id=c['id'],
            basis='A finite source-axis cut at the actual continuous gusset/slot or supplier clevis assembly. Source design workpoint remains unchanged.'))
        changes.append(dict(member_id=actual['id'],end=end,connection_id=c['id'],previous_offset=previous,end_offset=offset))
    for mid,ends in pending_slots.items():
        member=lookup[mid]
        start,finish=[add(p,o) for p,o in zip(member['axis'],member['end_offsets'])]
        length=math.dist(start,finish)
        ids={cid for cid,_ in ends.values()}
        previous=old_spans[mid];old_length=math.dist(*previous)
        shift=dot(sub(start,previous[0]),unit(sub(previous[1],previous[0])))
        kept=[]
        for slot in member.get('slots',[]):
            if slot.get('connection_id') in ids:continue
            depth=slot['end_in']-slot['start_in']
            if abs(slot['start_in'])<1e-6:lo=0.
            elif abs(slot['end_in']-old_length)<1e-6:lo=length-depth
            else:lo=slot['start_in']-shift
            kept.append(dict(slot,start_in=lo,end_in=lo+depth))
        for end,(cid,local) in sorted(ends.items()):
            depth=local['end_in']-local['start_in']
            if depth>=length:raise ValueError('Selected gusset slot consumes brace '+mid)
            kept.append(dict(local,connection_id=cid,start_in=length-depth if end else 0.,
                             end_in=length if end else depth))
        member['slots']=kept
    if changes:
        model.setdefault('changes',[]).append(dict(kind='hr_review_brace_end_fit',ends=changes,
            basis='A actual flange-intersection set-out, continuous gussets and finite brace/casing ends; original source designs and analysis axes retained, no capacity recalculation.'))
        aid=model['pilot'].upper()+'-BRACE-END-FIT'
        if not any(a['id']==aid for a in model['assumptions']):
            model['assumptions'].append(dict(id=aid,answer='A: brace/casing ends follow their original source worklines and terminate at the modeled slot or supplier clevis. Apex support strips and stiffeners are centred at the actual flange intersection. Continuous gusset outlines, BRB end caps and clevis geometry are accepted fictional fits; source dimensions and qualification requirements remain separate.'))


def add_slot_reinforcement(ctx,profile,start,v,slot_end,txt):
    from .hr_detail_selections import reinforcement_weld
    from .hr_brace_fit import reinforcement
    a=ctx.a
    match=re.search(r'(?:two PL|2 PL) '+NUMBER+r' x '+NUMBER+r'(?: x '+NUMBER+r')?',txt)
    selected_reinforcement=[ctx.selected.get(('slot_reinforcement',field)) for field in ('thickness_in','width_in','length_in')]
    if match or all(selected_reinforcement):
        rt=selected_reinforcement[0] or number(match[1])
        rw=selected_reinforcement[1] or number(match[2])
        rl=selected_reinforcement[2] or (number(match[3]) if match[3] else 20)
        half_weld=ctx.selected.get(('reinforcement_fillet','length_each_side_in'))
        line_length=2*half_weld if half_weld is not None else rl
        if line_length>rl+1e-6:
            raise ValueError('Selected reinforcement weld exceeds plate length at '+ctx.c['id'])
        for j,sg in enumerate((-1,1)):
            origin=add(start,mul(v,slot_end-rl/2))
            plate,edges=reinforcement(a,'REINF'+str(j),profile,origin,v,sg,rw,rt,rl)
            grade=ctx.selected.get(('slot_reinforcement','material'))
            if grade:plate['selected_material']=grade
            size=reinforcement_weld(ctx)
            for edge,point in enumerate(edges):
                q=add(point,mul(v,(rl-line_length)/2))
                a.weld('WR'+str(j)+('-B' if edge else ''),q,add(q,mul(v,line_length)),['BRACE','REINF'+str(j)],size if size is not None else .3125,basis='S' if size is not None else 'A',description='Reinforcement longitudinal fillet')


def draw_brace(ctx):
    from .hr_detail_selections import pin_selection,bolted_brb
    from .hr_brace_fit import bolted_brb_end,fit_brb_rows,fit_detail_slot,bound_base_plate,bind_support_span
    from .hr_brace_fit import column_face_at_gusset,support_selection
    from .connection_cuts import drill_joined_plates
    from .hr_pin_stack import selected_stack,selected_receiver,make_stack
    a,p,pid,txt,par=ctx.a,ctx.p,ctx.pid,ctx.text,ctx.params;kind=par.get('joint','corner');upper=kind in ('apex','link_end');isbrb=ctx.family=='review_brb'
    full_text=txt
    stack=selected_stack(ctx) if isbrb else None
    stack_receiver=selected_receiver(ctx,stack) if stack else {}
    cp=ctx.select(('column',));bp=ctx.select(('beam','moment_beam','girder','transfer_chord'));cd=effective(p,cp);bd=effective(p,bp);bf=effective(p,bp,'width')
    proposal=par.get('unsupported_base_corner')
    if proposal:
        bp=proposal['source_beam_profile'];bd=effective(p,bp);bf=effective(p,bp,'width')
    beam_z=par.get('beam_centroid_z',-bd/2);beam_top=beam_z+bd/2;beam_bottom=beam_z-bd/2
    # The connection datum is the building work point, not the support face.
    # Keep its exact source slope; the rounded display angle is not geometry.
    bm=ctx.ms[0]
    far=max(bm['axis'],key=lambda q:math.dist(q,ctx.c['point']))
    delta=sub(far,ctx.c['point']);horizontal=math.hypot(delta[0],delta[1])
    v=unit([horizontal,0,delta[2]]);sign=1 if v[2]>=0 else -1
    actual_base=bound_base_plate(ctx) if kind=='base' else None
    from .brace_base_attachment import base_attachment,collar
    base_spec=base_attachment(ctx,cp) if kind=='base' else None
    base_kind=base_spec['kind'] if base_spec else None
    interface_z=(beam_bottom if sign<0 else beam_top) if kind!='base' else actual_base[0][2][1] if actual_base else 0
    if base_kind in ('free','collar'):interface_z=base_spec.get('clearance',0.)
    # Top-of-steel is the analysis workpoint. On a downward brace the actual
    # flange intersection is farther into the bay; centre its support strip
    # and stiffeners there, while retaining the exact source brace workline.
    interface_station=interface_z/v[2] if abs(v[2])>1e-8 else 0
    beam_x=v[0]*interface_station if upper else 0
    if par.get('common_apex_datum'):beam_x=0.
    # End-specific source text can prescribe different UFM edges at the two ends.
    if par.get('upper_end') and 'upper end:' in txt and not par.get('interface_length'):
        txt=txt.split('upper end:',1)[1];ctx.text=txt
    t=par.get('gusset_thickness',ctx.n(r'(?:corner|apex|base) gusset '+NUMBER+r' in',ctx.n(r'slotted for a '+NUMBER+r' in',.75)));lx=ctx.n(r'(?:beam-edge weld length|beam edge|base-plate weld length|upper-end beam-edge weld) '+NUMBER+r' in',24);lz=ctx.n(r'(?:column-edge weld length|column edge|upper-end column-edge weld) '+NUMBER+r' in',24)
    t=ctx.selected.get(('gusset','thickness_in')) or t
    horizontal_role='gusset_base_weld' if kind=='base' and ('gusset_base_weld','length_in') in ctx.selected else 'gusset_beam_weld'
    if base_spec:
        lz=base_spec['column_length']
        if base_kind!='free':lx=base_spec['horizontal_length']
    else:
        lx=support_selection(ctx,horizontal_role,'length_in','WGB',lx)
        lz=support_selection(ctx,'gusset_column_weld','length_in','WGC',lz)
    if stack_receiver:
        lx=stack_receiver['horizontal_edge']['length_in']
        lz=stack_receiver['column_edge']['length_in']
    if upper:
        length=ctx.n(r'(?:both sides x|flange over) '+NUMBER+r' in',ctx.n(r'apex gusset '+NUMBER+r' in along',36))
        if kind=='link_end':length=ctx.n(r'flange over '+NUMBER+r' in',length)
        length=par.get('interface_length',length)
        length=support_selection(ctx,'gusset_beam_weld','length_in','WGB',length)
        a.member('BEAM',bp,[beam_x-length/2-10,0,beam_z],[beam_x+length/2+10,0,beam_z]);lx=length;lz=max(24,length*.65)
        vertices=[[beam_x+x,-t/2,z] for x,z in ((-length/2,interface_z),(length/2,interface_z),(length/2-3,interface_z+sign*lz*.4),(3,interface_z+sign*lz),(-length/2+3,interface_z+sign*lz*.4))]
        a.polygon('GUSSET',vertices,t,basis='A',description=f'Source gusset t={t:g}, beam interface L={length:g}; A free-edge outline')
        w=support_selection(ctx,'gusset_beam_weld','size_in','WGB',ctx.n(r'\('+NUMBER+r'-in fillets both sides x',.5))
        a.weld('WGB',[beam_x-length/2,0,interface_z],[beam_x+length/2,0,interface_z],['BEAM','GUSSET'],w,description='Source apex/link-end interface weld, both sides; A centre at actual brace/flange intersection')
        # Source web stiffeners at both brace work lines and ends.
        tw=p[bp]['dimensions'].get('tw',.4);tf=p[bp]['dimensions'].get('tf',.6)
        if par.get('doubler_thickness'):
            dt=par['doubler_thickness'];a.box('DOUBLER',[beam_x-length/2-2,tw/2,beam_bottom+tf+.0625],[length+4,dt,bd-2*tf-.125],'S','Source apex beam web doubler; A corner clipping envelope')
            a.weld('WD',[beam_x-length/2-2,tw/2,beam_bottom+tf],[beam_x+length/2+2,tw/2,beam_bottom+tf],['BEAM','DOUBLER'],max(.125,dt-.125),kind='PJP',description='Source doubler-to-flange PJP; both flanges, matching source record')
        for i,x in enumerate((-length/2+2,0,length/2-2)):
            x+=beam_x
            for j,sg in enumerate((-1,1)):
                yy=tw/2 if sg>0 else -bf/2+.25;label=f'ST{i}{j}'
                a.box(label,[x-.25,yy,beam_bottom+tf],[.5,bf/2-tw/2-.25,bd-2*tf],'A','Source-required stiffener, A thickness/station where unspecified');a.weld('W'+label,[x,sg*tw/2,beam_bottom+tf],[x,sg*tw/2,beam_top-tf],['BEAM',label],.25,basis='A')
    else:
        weak=par.get('weak_axis_gusset',False);column_face=column_face_at_gusset(p,cp,weak)
        column_lo=-18 if proposal else -(base_spec or {}).get('thickness',0.) if kind=='base' else -bd-lz-24
        a.member('COLUMN',cp,[0,0,column_lo],[0,0,lz+12 if proposal else lz+24],y=[1,0,0] if weak else [0,1,0])
        if kind=='base':
            if base_kind=='collar':
                plate=collar(a,base_spec,column_face,effective(p,cp,'width'),interface_z)
                plate['selected_material']=ctx.selected.get(('gusset','material'))
                host='COLLAR'
            elif base_kind=='free':
                a.notes.append(f"S: lower gusset edge stays {base_spec['clearance']:g} in clear of the cap with no foundation attachment.")
                host=None
            elif actual_base:
                stock,connection,part=actual_base
                base=a.box('BASE',[pair[0] for pair in stock],[hi-lo for lo,hi in stock],'S',
                           'Located view of the separately selected column base plate')
                base['parameters']={'referenced_connection_id':connection,'referenced_part_id':part}
                host='BASE'
            else:
                a.box('BASE',[-cd-4,-bf/2-6,-1.5],[cd+column_face+lx+4,bf+12,1.5],'A','Local base support envelope including the complete selected gusset edge')
                host='BASE'
            if base_kind not in ('free','collar'):
                a.box('CONC',[-cd-8,-bf/2-10,-12],[cd+lx+12,bf+20,10.5],'A','Foundation context',kind='concrete')
        elif proposal:
            seat=proposal['seat_thickness_in'];width=proposal['seat_width_in']
            st=proposal['stiffener_thickness_in'];height=proposal['stiffener_depth_in']
            a.box('SEAT',[column_face,-width/2,-seat],[lx,width,seat],'A',
                  'A stiffened seat replaces absent same-side beam; source base-corner condition does not match this continuous column')
            for side in (-1,1):
                name='SEAT-STIFF'+str(side);yy=side*(width/2-2)-st/2
                a.polygon(name,[[column_face,yy,-seat],[column_face+lx,yy,-seat],
                                [column_face,yy,-seat-height]],st,basis='A',
                          description='A 1/2 in triangular seat stiffener; capacity unverified')
                a.weld(name+'-C',[column_face,yy+st/2,-seat-height],
                       [column_face,yy+st/2,-seat],['COLUMN',name],.375,basis='A',
                       description='A stiffener-to-column fillet, both sides; new load path unverified')
                a.weld(name+'-S',[column_face,yy+st/2,-seat],
                       [column_face+lx,yy+st/2,-seat],['SEAT',name],.375,basis='A',
                       description='A stiffener-to-seat fillet, both sides')
            a.weld('SEAT-C',[column_face,-width/2,-seat/2],
                   [column_face,width/2,-seat/2],['COLUMN','SEAT'],.375,basis='A',
                   description='A seat-to-column fillet, top/bottom; capacity unverified')
            a.notes.append(proposal['basis']);host='SEAT'
        else:a.member('BEAM',bp,[column_face,0,beam_z],[column_face+lx+24,0,beam_z]);host='BEAM'
        clearance=column_face+(2*t if par.get('beam_only_gusset') else 0)
        vertices=[[clearance,-t/2,interface_z],[lx+clearance,-t/2,interface_z],[max(lx,18)+clearance,-t/2,interface_z+sign*lz*.65],[clearance,-t/2,interface_z+sign*lz]]
        a.polygon('GUSSET',vertices,t,basis='A',description=f'Source gusset t={t:g}; A fitted perimeter, source UFM edges')
        weld=ctx.n(NUMBER+r'-in E70 fillets both sides',.375)
        if not par.get('beam_only_gusset'):
            kind_gc=base_spec['column_kind'] if base_spec else ctx.selected.get(('gusset_column_weld','kind')) or 'fillet'
            weld_gc=(base_spec or {}).get('fillet') or support_selection(ctx,'gusset_column_weld','size_in','WGC',weld)
            a.weld('WGC',[column_face,0,interface_z],[column_face,0,interface_z+sign*lz],['COLUMN','GUSSET'],weld_gc,
                   kind=kind_gc,description='Source column-edge weld, both sides')
        else:a.notes.append('S: beam-only gusset; no gusset-to-column weld. A 2t clear gap is drawn at the column face. Source free-edge and rotation-clearance requirements remain.')
        if host:
            weld_gb=(base_spec or {}).get('fillet') or support_selection(ctx,horizontal_role,'size_in','WGB',weld)
            a.weld('WGB',[clearance,0,interface_z],[lx+clearance,0,interface_z],[host,'GUSSET'],weld_gb,
                   kind=ctx.selected.get((horizontal_role,'kind')) or 'fillet',description='Source horizontal gusset attachment')
    ctx.text=full_text
    station=max(8,min(lx,lz)*.55,abs(interface_z/v[2])+4 if abs(v[2])>1e-8 else 0,
                (clearance+2)/v[0] if not upper and v[0]>1e-8 else 0)
    if stack:
        make_stack(ctx,stack,v,station,effective(p,pid),effective(p,pid,'width'))
        if upper:bind_support_span(ctx,'BEAM',0)
        else:bind_support_span(ctx,'COLUMN',2)
        return
    wl=ctx.selected.get(('brace_slot_weld','length_in')) or ctx.n(r'welds? x '+NUMBER+r' in',12)
    fold_ratio=ctx.selected.get(('brace_end_clearance','depths')) if not isbrb else None
    if fold_ratio is not None:
        from .brace_linear_clearance import restraint_station
        if fold_ratio<=0:raise ValueError('Invalid selected brace-end clearance')
        fold,restrained_edges=restraint_station(a.welds,v)
        station=max(station,fold+fold_ratio*t)
    if not isbrb:
        from .slotted_gusset_outline import fitted_outline,width_station
        effective_width=ctx.selected.get(('gusset','whitmore_effective_width_in'))
        fit_limits=[(1,sign,interface_z)]
        if not upper:fit_limits.append((0,1,clearance))
        station=max(station,width_station(v,effective_width,fit_limits))
    selected_bolts=bolted_brb(ctx) if isbrb else None
    bolt_contour=[];bolt_groups=[]
    if selected_bolts:
        # A long selected support weld does not require a proportionally long
        # offset before the first bolt. Place the complete selected bolt group
        # clear of the actual support and retain usable casing between both ends.
        station,layout=fit_brb_rows(selected_bolts,v,interface_station,None if upper else clearance)
        start,bolt_contour,bolt_groups=bolted_brb_end(a,selected_bolts,v,station,t,interface_station,layout,effective(p,pid))
        end=add(start,mul(v,24))
        a.member('BRACE',pid,start,end,description='Source BRB casing with bolted supplier core extension')
        a.interfaces.append(dict(id='CORE-TO-CASING',kind='supplier_interface',connects=['BRACE','CORE-END'],
            basis='A',description='Source supplier core end meets its casing at the adopted station'))
    elif isbrb:
        dia,pin_material,hole_clearance=pin_selection(ctx)
        cheek=ctx.selected.get(('cheek_plate','thickness_in')) or ctx.n(r'two '+NUMBER+r' in cheek plates',.875)
        plate=t+2*cheek
        breadth=ctx.selected.get(('gusset','width_at_hole_in')) or ctx.n(r'width '+NUMBER+r' in',19)
        # The entire pin-bearing cheek clears the support, not just its axis.
        pin_station=max(station+7,interface_station+(breadth/2+2)/abs(v[2]))
        if not upper:pin_station=max(pin_station,(clearance+breadth/2+2)/v[0])
        pin=mul(v,pin_station);start=add(pin,mul(v,13));end=add(start,mul(v,24))
        a.member('BRACE',pid,start,end,description='Source BRB core; A supplier casing ends at its adopted end cap')
        normal=[-v[2],0,v[0]];depth=effective(p,pid);width=effective(p,pid,'width')
        cap=add(pin,mul(v,12))
        a.polygon('END-CAP',[add(cap,add(mul(normal,ss*depth/2),[0,yy*width/2,0])) for ss,yy in ((-1,-1),(-1,1),(1,1),(1,-1))],1,normal=v,basis='A',description='A 1in supplier casing end cap; local capacity and BRB qualification remain delegated')
        for side in (-1,1):
            aa=add(start,add(mul(normal,side*depth/2),[0,-width/2,0]));bb=add(aa,[0,width,0])
            a.weld('CAP-W'+str(side),aa,bb,['BRACE','END-CAP'],.375,basis='A',description='A supplier casing/end-cap fillet; not a source-tested connection')
        for j,sg in enumerate((-1,1)):
            yy=t/2 if sg>0 else -t/2-cheek
            a.box('CHEEK'+str(j),[pin[0]-breadth/2,yy,pin[2]-breadth/2],[breadth,cheek,breadth],'A','Source cheek thickness/width; A perimeter and pin position')
            a.weld('WCH'+str(j),[pin[0]-breadth/2,sg*t/2,pin[2]-breadth/2],[pin[0]+breadth/2,sg*t/2,pin[2]-breadth/2],['GUSSET','CHEEK'+str(j)],.375,basis='A')
            yy=plate/2+.125 if sg>0 else -plate/2-.125-1.25
            a.polygon('CLEVIS'+str(j),[add(pin,add(mul(v,ss),add(mul(normal,nn),[0,yy,0]))) for ss,nn in ((-6,-6),(12,-6),(12,6),(-6,6))],1.25,normal=[0,1,0],basis='A',description='A supplier clevis follows the actual brace slope and meets its end cap')
            a.weld('WC'+str(j),add(cap,add(mul(normal,-min(6,depth/2)),[0,yy,0])),add(cap,add(mul(normal,min(6,depth/2)),[0,yy,0])),['END-CAP','CLEVIS'+str(j)],.375,basis='A')
        pin_group=a.fastener('PIN',[[pin[0],-plate/2-.125-1.25,pin[2]]],[0,1,0],dia,plate+.25+2.5,['GUSSET','CHEEK0','CHEEK1','CLEVIS0','CLEVIS1'],f'{dia:g} in {pin_material} pin; A supplier retaining envelope')
        pin_group.update(functional_kind='pin',selected_material=pin_material)
        a.notes.append('BRB core area retained; casing/clevis and pin-position fit are A supplier assumptions. Source cheek plates, free-edge stiffening and qualification requirements remain in the specification.')
    else:
        station=max(station,interface_station+(effective(p,pid)/2*abs(v[0])+2*t)/abs(v[2]))
        if not upper:station=max(station,(clearance+effective(p,pid)/2*abs(v[2])+t)/v[0])
        start=mul(v,station);end=add(start,mul(v,wl+24))
        a.member('BRACE',pid,start,end,description='Source slotted brace section '+pid+'; A finite end cut on its original workline')
        weld=ctx.selected.get(('brace_slot_weld','size_in')) or ctx.n(r'(?:four |\(four lines\) )'+NUMBER+r' in E70',ctx.n(NUMBER+r'-in \(four lines\)',.375));th=effective(p,pid)/2
        for side in (-1,1):
            for edge in (-1,1):
                # Four distinct slot-edge lines, two at each HSS wall.
                off=[-v[2]*th*side,edge*t/2,v[0]*th*side];aa=add(start,off);a.weld(f'WB{side}{edge}',aa,add(aa,mul(v,wl)),['BRACE','GUSSET'],weld,description=f'Source slot weld L={wl:g}; four lines')
    # Free edges are authored fit geometry. Enclose the actual brace slot welds
    # while retaining the source support-edge lengths and plate thickness.
    gusset=next(q for q in a.parts if q['id']=='GUSSET')
    outline=[(q[0],q[2]) for q in gusset['polygon']]
    if selected_bolts:
        outline.extend(bolt_contour)
    elif isbrb:
        # Cheeks and pin must be on the same continuous gusset that reaches
        # the beam/column. Previously only slotted-HSS welds extended it.
        outline.extend((pin[0]+sx*(breadth/2+t),pin[2]+sz*(breadth/2+t)) for sx in (-1,1) for sz in (-1,1))
    else:
        fixed=[q for w in a.welds if w['id'] in ('WGB','WGC') for q in (w['a'],w['b'])]
        transfers=[(w['a'],w['b']) for w in a.welds if w['id'].startswith('WB')]
        outline=fitted_outline(fixed,transfers,start,v,t,effective_width,fit_limits)
    a.parts.remove(gusset)
    finished=a.polygon('GUSSET',[[x,-t/2,z] for x,z in hull(outline)],t,basis='A',description=gusset['description'])
    if not isbrb:
        finished.setdefault('parameters',{})['free_contour_rule']='slotted_attachment_hull'
        if effective_width:
            transverse=[-v[2],0.,v[0]]
            a.dim(add(start,mul(transverse,-effective_width/2)),add(start,mul(transverse,effective_width/2)),
                  'Selected Whitmore effective width at the transfer section',basis='S',offset=30)
        if upper or not any(w['id']=='WGC' for w in a.welds):
            lz=max(sign*(z-interface_z) for _,z in outline)
    if selected_bolts:
        for group in bolt_groups:drill_joined_plates(a,group,selected_bolts['diameter']+.0625,'A 1/16 in diametral fit allowance')
    elif isbrb:
        drill_joined_plates(a,pin_group,dia+(hole_clearance if hole_clearance is not None else .0625),
                            'S selected pin-hole clearance' if hole_clearance is not None else 'A 1/16 in diametral fit allowance')
    else:
        width=ctx.selected.get(('slot','width_in'))
        slot_clearance=ctx.selected.get(('slot','clearance_in'))
        if width is None and slot_clearance is not None:width=t+slot_clearance
        fit_detail_slot(a,width)
        brace=next(q for q in a.parts if q['id']=='BRACE')
        slot=brace['member'].get('slots',[])
        if slot:add_slot_reinforcement(ctx,p[pid],start,v,slot[0]['end_in'],txt)
        if fold_ratio is not None:
            from .brace_linear_clearance import dimension
            dimension(a,v,fold_ratio,fold,dot(start,v),restrained_edges)
    a.section_at=pin[0] if isbrb and not selected_bolts else start[0]+6
    edge_start=beam_x-lx/2 if upper else clearance
    if base_kind!='free':
        a.dim([edge_start,0,interface_z],[edge_start+lx,0,interface_z],
              'Source support-edge weld' if proposal else f'{lx:g} in source interface length',
              basis='S',offset=-48 if proposal else 24)
    elif isbrb:
        a.dim([edge_start,0,interface_z],[edge_start+lx,0,interface_z],
              'Adopted lower free-edge extent',basis='A',offset=24)
    a.dim([beam_x,0,interface_z],[beam_x,0,interface_z+sign*lz],basis='S' if proposal else 'A',offset=65 if proposal else 40)
    if upper:a.notes.append('A: support weld, doubler and stiffeners centre on the actual brace/flange intersection. Continuous gusset to the attachment; original source checks remain separate.')
    if upper:bind_support_span(ctx,'BEAM',0)
    if not upper:bind_support_span(ctx,'COLUMN',2)
    from .gusset_support_welds import place_faces
    place_faces(a,ctx.selected,horizontal_role)
    a.notes.append('Separate source end condition: '+kind+'. Member slot, gusset clearance and free-edge trim follow the attached source record; drawings show the assembled load path. A geometry remains subject to the unchanged design verification requirements.')


def boxed(ctx):
    a,p=ctx.a,ctx.p;chamfer=ctx.family=='review_chamfer';cp=ctx.select(('column',),ctx.pid);d=effective(p,cp);w=effective(p,cp,'width');t=ctx.params.get('boxing_t',2)
    height=ctx.params.get('full_height_in');z0,z1=(-height/2,height/2) if height else (-42,24)
    plate_width=ctx.params.get('boxing_width_in',d)
    a.member('COLUMN',cp,[0,0,z0],[0,0,z1]);ids=['COLUMN']
    for i,sg in enumerate((-1,1)):
        yy=w/2 if sg>0 else -w/2-t;name='BOX'+str(i);ids.append(name);plate=flat(p,plate_width,t);a.member(name,plate,[0,yy+t/2,z0],[0,yy+t/2,z1],y=[1,0,0],basis='S',description='Source full-tier boxing; actual physical piece')
        for j,x in enumerate((-plate_width/2,plate_width/2)):
            for k,region in enumerate(ctx.params.get('boxing_weld_regions',[dict(z0=z0,z1=z1,kind='CJP')])):
                a.weld(name+'W'+str(j)+'-'+str(k),[x,yy,region['z0']],[x,yy,region['z1']],['COLUMN',name],.25,kind=region['kind'],basis='S joint zones/type; A fillet size',description='Source boxing weld classification; A 1/4 in continuous fillet where the source leaves size unstated')
    if chamfer:
        # Beam local X points away from the 45-degree face of the boxed column.
        column=next(m for m in ctx.ms if m['kind']=='column');beam=ctx.ms[0];origin=ctx.c['point'];far=max(beam['axis'],key=lambda q:math.dist(q,origin));ray=unit(sub(far,origin))
        cy=column['local_y'];cx=cross(cy,[0,0,1]);v=unit([dot(ray,cx),dot(ray,cy),0]);normal=cross([0,0,1],v)
        face=(d/2+w/2+t)/math.sqrt(2)-min(d,w)*.25;width=max(d,w)/math.sqrt(2)+2;bd=effective(p,ctx.pid);bf=effective(p,ctx.pid,'width');start=mul(v,face+1)
        for part in a.parts:clip_part(part,mul(v,-1),-face+1)
        origin=add(mul(v,face-1),mul(normal,-width/2));origin[2]=-bd-4
        a.box('FACE',origin,[2,width,bd+8],'S','Source 2 in face plate across boxed corner',x=v,y=normal)
        a.member('BEAM',ctx.pid,add(start,[0,0,-bd/2]),add(start,[v[0]*42,v[1]*42,-bd/2]),y=normal)
        for i,z in enumerate((0,-bd)):
            a.box('DIA'+str(i),[-d/2,-w/2-t,z-.875],[d,w+2*t,1.75],'S','1-3/4 in source through diaphragm / box continuity')
            # Projecting tongue meets the beam flange and passes through the face plate.
            q=add(mul(v,face-6),mul(normal,-bf/2));q[2]=z-.875
            a.box('TONGUE'+str(i),q,[7,bf,1.75],'S','Source projecting diaphragm tongue',x=v,y=normal)
            a.weld('FLANGE'+str(i),add(start,add(mul(normal,-bf/2),[0,0,z])),add(start,add(mul(normal,bf/2),[0,0,z])),['BEAM','TONGUE'+str(i)],kind='CJP',description='Source beam flange to projecting diaphragm CJP')
        a.weld('WEB',add(start,[0,0,-bd+2]),add(start,[0,0,-2]),['BEAM','FACE'],kind='CJP');a.notes.append('Source 45-degree corner geometry and through diaphragms. Local column-corner trim, face-plate width and tongue overlap are A fits; source cyclic qualification remains a verification requirement.')
    a.section_axis=2;a.section_at=-6;a.dim([-d/2,0,0],[d/2,0,0],f'{d:g} in column depth',view='section')


def deck_studs(ctx):
    a,p,pid=ctx.a,ctx.p,ctx.pid;d=effective(p,pid);pitch=ctx.n(r' at '+NUMBER+r' in',12);diameter=.75
    a.member('BEAM',pid,[-30,0,-d/2],[30,0,-d/2]);a.box('SLAB',[-30,-18,0],[60,36,6.25],'A','Floor/deck context',kind='concrete')
    xs=[-24+i*pitch for i in range(int(48/pitch)+1)];a.fastener('STUD',[[x,0,0] for x in xs],[0,0,1],diameter,4.5,['BEAM','SLAB'],'Source 3/4 in headed studs; A height envelope / longitudinal datum')
    for j,x in enumerate(xs):a.weld('W'+str(j),[x-.375,0,0],[x+.375,0,0],['BEAM','STUD'],kind='STUD',description='Automatic headed-stud weld per source')
    a.dim([xs[0],0,0],[xs[1],0,0],f'{pitch:g} in source spacing');a.section_axis=0;a.section_at=xs[0];a.notes.append('Keep studs outside source RBS protected zones. Extract shows repeated interface; source chord/diaphragm forces and local exclusions govern the full run.')


def plate_base(ctx):
    from .review_wall_bases import plate
    plate(ctx)


def core_base(ctx):
    a,p,par=ctx.a,ctx.p,ctx.params;t=par['plate_thickness'];pid=flat(p,36,t)
    for j,sg in enumerate((-1,1)):a.member('FACE'+str(j),pid,[0,sg*(18-t)/2,-72],[0,sg*(18-t)/2,24],y=[1,0,0])
    a.box('MAT',[-30,-24,-84],[60,48,84],'A','Mat context / reinforcement delegated',kind='concrete');a.box('BASE',[-20,-11,-74],[40,22,2],'A','A base bearing plate thickness/footprint')
    for j,sg in enumerate((-1,1)):
        pts=[[x,sg*9,z] for x in (-15,-9,-3,3,9,15) for z in range(-3,-72,-6)]
        a.fastener('STUDS'+str(j),pts,[0,sg,0],.875,5,['FACE'+str(j),'MAT'],'Source 7/8 x 5 in headed studs at 6 x 6 in; A 3 in extract margins')
        a.weld('WB'+str(j),[-18,sg*9,-72],[18,sg*9,-72],['FACE'+str(j),'BASE'],kind='CJP',basis='A',description='A plate development weld fit; source mat design handoff retained')
    a.section_axis=2;a.section_at=-36;a.dim([24,0,-72],[24,0,0],'72 in source wall embedment')

