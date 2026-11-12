"""Physical top-flange extension and a sliding guide for a brace at a cropped transfer chord."""
import math
from .pilots.model import sub,unit,dot

def geometry(ctx):
    detail=ctx.params.get('transfer_chord_bridge')
    if not detail:return None
    r=next(r['data'] for r in ctx.package['design_records'] if r['id'] in ctx.c['design_record_ids'] and 'chord_bridge' in r['data'])
    if detail!=r['chord_bridge']:raise ValueError('Transfer chord extension differs from its design record')
    m=next(m for m in ctx.ms if m['kind']=='transfer_chord')
    i=min(range(2),key=lambda i:math.dist(m['axis'][i],ctx.c['point']))
    axis=unit(sub(m['axis'][1-i],m['axis'][i]))
    cut=dot(m['end_offsets'][i],axis)
    if abs(cut-detail['chord_cut_station_in'])>.001:raise ValueError('Transfer chord end differs from the checked extension')
    return detail

def add_parts(a,spec,face,z):
    width=spec['width_in'];t=spec['thickness_in'];cut=spec['chord_cut_station_in']
    gap=spec['tip_gap_in'];tip=face+gap;guide=spec['guide_reach_in'];gw=spec['guide_width_in'];gt=spec['guide_thickness_in']
    plate=a.box('CHORD-TIP',[tip,-width/2,z-t],[cut-tip,width,t],'S','Sliding extension of transfer-chord top flange')
    plate['selected_material']=spec['material']
    a.weld('TIP-CHORD',[cut,-width/2,z-t/2],[cut,width/2,z-t/2],['CHORD-TIP','BEAM'],0.,kind='CJP',description='Full-width flange-extension butt weld')
    for side in (-1,1):
        y=-width/2 if side<0 else width/2-gw
        for upper in (False,True):
            bottom=z+spec['guide_clearance_in'] if upper else z-t-spec['guide_clearance_in']-gt
            key='GUIDE-'+('UP' if upper else 'LOW')+str(side)
            p=a.box(key,[face,y,bottom],[guide,gw,gt],'S','Column-welded guide for reversible vertical load')
            p['selected_material']=spec['guide_material']
            a.weld(key+'-CJP',[face,y,bottom+gt/2],[face,y+gw,bottom+gt/2],[key,'COLUMN'],0.,
                   kind='CJP',description='Complete-joint-penetration guide to column flange')
            a.interfaces.append(dict(id=key+'-BEARING',kind='sliding_bearing',connects=[key,'CHORD-TIP'],basis='S',
                    description='Machined guide face, longitudinal movement free'))
    a.notes.append('The four guides transfer reversible vertical bearing to the column. The chord extension is free to slide axially at the column.')

def split_weld(a,spec):
    w=next(w for w in a.welds if w['id']=='WGB')
    x=spec['chord_cut_station_in'];p,q=w['a'],w['b']
    if not p[0]<x<q[0]:raise ValueError('The brace support weld must cross the chord-end butt joint')
    joint=[x,p[1],p[2]];length=math.dist(p,q)
    extra=dict(w,id='WGB-CHORD',a=joint,b=q,source_weld_id='WGB',selected_total_length_in=length,segment_index=1,segment_count=2)
    w.update(b=joint,connects=['CHORD-TIP','GUSSET'],source_weld_id='WGB',selected_total_length_in=length,
             segment_index=0,segment_count=2)
    a.welds.append(extra)
