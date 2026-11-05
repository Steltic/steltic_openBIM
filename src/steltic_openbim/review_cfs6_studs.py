"""Actual L-plan wall lines select the final CFS6 gravity-stud tiers.

The analysis coordinates are tributary fitted. They must not be used as the
physical room or corridor locations when applying these source selections.
"""
import copy,re


def selection(axis,x,y,k):
    x/=12;y/=12
    at=lambda a,b:abs(a-b)<.001
    if axis==0:
        if at(y,152):name='ext-bar-XN-L1-L3' if k<=3 else 'ext-bar-L3-L5'
        elif at(y,90) and x>62:name='ext-bar-X90-L1-L2' if k<=2 else 'ext-bar-L3-L5'
        elif any(at(y,n) for n in (118,124)):name='corr-bar-L1-L3' if k<=3 else 'corr-bar-L4-L5'
        elif any(at(y,n) for n in (104,138)):name='mid-bar-L1-L2' if k<=2 else 'mid-bar-L3-L5'
        elif at(y,0):name='endwall-L1-L5'
        elif any(at(y,n) for n in (30,60)):name='party-68-L1-L3' if k<=2 else 'party-54-L1-L5'
        elif at(y,90):name='party-54-L1-L5'
        else:raise ValueError('Unselected physical CFS6 X wall '+str((x,y,k)))
    else:
        if y<90-.001:
            if any(at(x,n) for n in (0,62)):name='ext-leg-L1-L5'
            elif any(at(x,n) for n in (28,34)):name='corr-leg-L1-L5'
            elif any(at(x,n) for n in (14,48)):name='mid-leg-L1' if k==1 else 'mid-leg-L2-L3' if k<=3 else 'mid-leg-L4-L5'
            else:raise ValueError('Unselected physical CFS6 leg wall '+str((x,y,k)))
        elif any(at(x,n) for n in (0,180)):name='endwall-L1-L5'
        elif any(at(x,n) for n in (30,60,90,120,150)):name='party-68-L1-L3' if k<=3 else 'party-54-L1-L5'
        elif at(x,62):name='party-54-L1-L5'
        else:raise ValueError('Unselected physical CFS6 bar wall '+str((x,y,k)))
    return 'stud-'+name


def named(b,d,name,k,props):
    # Only the source braced runs use named lines. Their physical position is
    # in line_plan_pos_ft; the node-fitting coordinates are intentionally ignored.
    line=next(l for l in b.cfg['lines_x' if d=='X' else 'lines_y'] if l['name']==name)
    position=b.cfg.get('line_plan_pos_ft',{}).get(d+'-'+name,line['pos'])*12
    axis=0 if d=='X' else 1
    other=120*12 if d=='Y' and name.startswith('P') else 45*12 if d=='Y' else 100*12 if name=='X90' else 30*12
    x,y=(other,position) if axis==0 else (position,other)
    row=copy.deepcopy(next(r for r in b.raw['studs'] if r['id']==selection(axis,x,y,k)))
    minimum=int(round(props.get('t_stud_in',.054)*1000));selected=int(row['section'].rsplit('-',1)[1])
    if minimum>selected:row['section']='600S162-'+str(minimum)
    row['spacing_in']=16
    return row


def ordinary(b):
    if b.key!='cfs6':return
    rows={r['id']:r for r in b.raw['studs']};changed=[]
    for m in b.members:
        if m['kind']!='stud' or not m['id'].startswith('ORD-'):continue
        axis=int(m['id'].split('-')[1]);x,y=m['axis'][0][:2]
        short=selection(axis,x,y,m['level']);source=rows[short];rid=b.record('studs',short)
        old=m['profile_id'];m['profile_id']=b.profile(source['section'])
        m['design_record_ids']=[r for r in m['design_record_ids'] if not r.startswith('studs/stud-')]+[rid]
        if short=='stud-ext-bar-XN-L1-L3':
            typical=b.record('studs','stud-typ-bearing');m['design_record_ids'].append(typical);b.used_records.add(typical)
        b.used_records.add(rid);m['source_bridging_spacing_in']=source['bridging_in']
        m['source_stud_spacing_in']=source['spacing_in']
        m['physical_fit_basis']='S exact final ordinary-stud tier on the actual wall line. A retained16 in fictional set-out where the source party-wall maximum is24 in; no reduced source thickness or omitted bridging is implied.'
        changed.append(dict(member_id=m['id'],previous_profile_id=old,profile_id=m['profile_id'],record_id=rid,bridging_in=source['bridging_in']))
    b.changes.append(dict(kind='cfs6_source_ordinary_stud_tiers',members=changed,basis='Final saved gravity tiers applied to actual L-plan coordinates; analysis and checked designs unchanged.'))
    b.note('ORDINARY-STUD-TIERS','S: exterior, corridor, mid-unit, party and end-wall ordinary studs follow the exact final source tier, including32/24 in bridging where specified. A: retained16 in ordinary-stud set-out is closer than the source24 in party-wall maximum. Full source bracing forces, web-punch, clip and anchor requirements remain attached.')
