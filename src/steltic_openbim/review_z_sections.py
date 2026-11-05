"""Explicit adopted folded-Z fit for the fictional retrofit model.

The gold calculations used point-symmetric nominal Z sections. Unequal flange
widths are a geometry proposal, not an equivalent section or capacity claim.
"""
import copy, math


def folded(b, source_id, flange_difference=.25):
    source=b.profiles[source_id]
    if source['family']!='z':raise ValueError('Nested Z fit needs its original Z section')
    pid='A-NEST-FIT-'+source_id
    if pid in b.profiles:return pid
    d=source['dimensions'];h,w,t,lip=(d[k] for k in ('d','b','t','lip'))
    components=[]
    def strip(label, start, end):
        delta=[end[i]-start[i] for i in (0,1)]
        child=b.custom(pid+'-'+label,'flat',dict(width=math.hypot(*delta),thickness=t),basis='A geometric strip of one folded Z, not a separate plate')
        components.append(dict(profile_id=child,rotation_deg=math.degrees(math.atan2(delta[1],delta[0])),offset=[(start[i]+end[i])/2 for i in (0,1)]))
    strip('WEB',[0,-h/2+t],[0,h/2-t])
    for sign in (-1,1):
        width=w+sign*flange_difference
        start=[-sign*t/2,sign*(h/2-t/2)];end=[sign*(width-t/2),start[1]]
        strip('FLANGE'+str(sign),start,end)
        angle=math.radians(source.get('lip_angle_deg',50))
        tip=[end[0]-sign*math.cos(angle)*lip,end[1]-sign*math.sin(angle)*lip]
        if lip:strip('LIP'+str(sign),end,tip)
    return b.custom(pid,'built_up',copy.deepcopy(d),components=components,
        source_profile_id=source_id,source_dimensions=copy.deepcopy(d),basis='A unequal-flange physical nesting proposal; source depth and thickness retained',
        fabrication_form='one folded Z section, represented by joined strips',
        fit_proposal=f'A upper/lower flange widths {w+flange_difference:g}/{w-flange_difference:g}in. Gold used nominal point-symmetric {w:g}in flanges; original capacity is not assigned to this changed shape. Supplier section and bend details require verification.')
