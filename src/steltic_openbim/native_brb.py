"""Build a source-selected BRB connection at a fresh job's actual end workpoint."""
import math

from .bim_assemblies import transformed
from .drawing_workflow import fingerprint
from .hr_detail_selections import selected_fields
from .pilots.model import add,sub,mul,dot,cross,unit
from .review_assemblies import Context
from .review_hr_brace_ends import draw_brace
from .saved_assemblies import native_parts,receivers
from .stmf_fit import local


def build_brb_end(package,c,brace,supports,profiles,catalogue,joint):
    p=package['physical'];point=joint['point'];selected=selected_fields(package,c)
    variant=selected.get(('connection','variant'))
    if variant not in ('brb_pinned','brb_bolted'):raise ValueError('BRB attachment topology is unspecified')
    t=selected.get(('gusset','thickness_in'));grade=selected.get(('gusset','material'))
    if not t or not grade:raise ValueError('BRB connection requires selected gusset thickness and material')
    cols=[m for m in supports if m['kind'] in ('column','col','post')]
    beams=[m for m in supports if m['kind'] in ('beam','girder','moment_beam','transfer_chord')]
    if len(cols)>1 or len(beams)>1 or not (cols or beams):
        raise ValueError('BRB end requires an unambiguous source-selected column and/or beam')
    end=min(range(2),key=lambda i:math.dist(point,brace['axis'][i]))
    if math.dist(point,brace['axis'][end])>1e-4:raise ValueError('BRB workpoint is outside its located end')
    away=unit(sub(brace['axis'][1-end],point));x=unit([away[0],away[1],0.]);y=cross([0.,0.,1.],x)
    frame=dict(origin=point,x_axis=x,y_axis=y,bindings={'BRACE':brace['id']})
    kind='corner' if cols and beams else 'apex' if beams else 'base'
    par=dict(c.get('parameters',{}),joint=kind,upper_end=away[2]<0)
    if cols:
        col=cols[0];ca=unit(sub(col['axis'][1],col['axis'][0]))
        if abs(ca[2])<1.-1e-7:raise ValueError('Inclined column requires a source-compatible oblique BRB attachment')
        frame['bindings']['COLUMN']=col['id'];cy=local(col['local_y'],frame)
        if max(map(abs,cy[:2]))<1.-1e-6:raise ValueError('Rotated column requires an oblique gusset support face')
        par['weak_axis_gusset']=abs(cy[0])>.9
    if beams:
        beam=beams[0];ends=[add(q,o) for q,o in zip(beam['axis'],beam['end_offsets'])]
        if abs(dot(unit(sub(ends[1],ends[0])),x))<1.-1e-7:
            raise ValueError('Located beam is outside the selected BRB plane')
        frame['bindings']['BEAM']=beam['id'];par['beam_centroid_z']=ends[0][2]-point[2]
    if kind=='base':
        existing=any(q.get('detail_ref',{}).get('legacy_family') in ('review_base','review_wall_base') and
                     cols[0]['id'] in q.get('member_ids',[]) and math.dist(q.get('point',point),point)<.01 and
                     q.get('assembly_instance') for q in p['connections'])
        if not existing:raise ValueError('Located BRB base needs its selected column base plate extent and placement')
    rows=[brace,*cols,*beams]
    context=dict(pilot='hr_native',members=rows,profiles=list(profiles.values()),panels=p['panels'])
    target=dict(c,point=point,member_ids=[m['id'] for m in rows],parameters=par,detail_ref={'id':'review_brb'})
    original=c.get('assembly_instance');c['assembly_instance']=frame
    try:
        ctx=Context(context,package,target);draw_brace(ctx)
    finally:
        if original is None:c.pop('assembly_instance',None)
        else:c['assembly_instance']=original
    scene=ctx.a.result();scene['source_record_ids']=c['design_record_ids']
    # These are physical geometry decisions. Retain each specifically named
    # constituent grade; use the selected connection steel for its fitted plies.
    welds=[m['specification'] for m in catalogue.values() if 'weld' in m.get('source_item','').lower()]
    for part in scene['parts']:
        if part['kind']=='plate' and not part.get('selected_material'):
            part['selected_material']=grade
        if part['kind']=='concrete':
            concrete=[m['specification'] for m in catalogue.values() if 'concrete' in m.get('source_item','').lower()]
            if len(set(concrete))==1:part['selected_material']=concrete[0]
            else:part['representation_role']='context_only'
    for weld in scene['welds']:
        weld.setdefault('selected_material',welds[0] if len(set(welds))==1 else 'Weld consumable grade unspecified in HR handoff')
    local_brace=next(part['member'] for part in scene['parts'] if part['id']=='BRACE')
    offset=sub(transformed(local_brace['axis'][0],frame),brace['axis'][end])
    old=brace['end_offsets'][end]
    if math.dist(old,[0,0,0])>1e-6 and math.dist(offset,old)>1e-4:
        raise ValueError('Source-specified brace end and selected connection set-out disagree')
    offsets=[*brace['end_offsets']];offsets[end]=offset
    if dot(sub(add(brace['axis'][1],offsets[1]),add(brace['axis'][0],offsets[0])),unit(sub(brace['axis'][1],brace['axis'][0])))<=0:
        raise ValueError('BRB terminal selections consume the source casing')
    members={m['id']:dict(m,end_offsets=offsets) if m['id']==brace['id'] else m for m in rows}
    native=native_parts(scene,{'parts':[]},catalogue)
    rr,bindings=receivers(scene,{'receivers':[]},frame,members,target)
    tid='openbim-brb-'+fingerprint([c['id'],native,rr])[:16]
    template=dict(id=tid,basis='Selected HR brace connection; finite openBIM fit to located native receivers',
                  source_record_ids=c['design_record_ids'],parts=native,receivers=rr,source_interfaces=scene['interfaces'])
    template['revision']=fingerprint(template)
    frame.update(template_id=tid,revision=template['revision'],bindings=bindings)
    return template,frame,offsets,list(brace.get('slots',[]))
