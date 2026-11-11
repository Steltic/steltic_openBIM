"""Recover the terminal of a sized, individually located HR supplier-core occurrence."""
import math


def selected_end(spec,member,connection_id,end):
    issued=spec.get('terminal',{}).get('physical_occurrences')
    if issued is None:return None
    located=[row for row in issued if row['member_id']==member['id']]
    if len(located)!=1:raise ValueError('The HR core needs one checked physical occurrence for '+member['id'])
    row=located[0];length=math.dist(*member['axis'])
    if (abs(row['workpoint_length_in']-length)>1e-4 or
            abs(row['yielding_length_in']-length*spec['yielding_length_workpoint_ratio'])>1e-4):
        raise ValueError('The length of the HR core does not match its located workpoints: '+member['id'])
    ends=row['end_locations']
    if len(ends)!=2 or {r['end_index'] for r in ends}!={0,1}:raise ValueError('Incomplete located HR core end set at '+member['id'])
    required=next(r for r in ends if r['end_index']==end)
    if (required['connection_id']!=connection_id or required['head_front_station_in']<=required['pin_station_in'] or
            required['head_back_station_in']<=required['head_front_station_in'] or
            abs(required['casing_face_station_in']-required['head_back_station_in']-required['head_to_casing_clearance_in'])>1e-4 or
            required['head_to_casing_clearance_in']<required['full_travel_in']-1e-4 or required['full_travel_in']<=0):
        raise ValueError('Contradictory located core terminal set-out at '+connection_id)
    return required


def head_fit(row):
    return dict(front_in=row['head_front_station_in'],thickness_in=row['head_back_station_in']-row['head_front_station_in'],
                required_travel_in=row['full_travel_in'],casing_gap_in=row['head_to_casing_clearance_in'])
