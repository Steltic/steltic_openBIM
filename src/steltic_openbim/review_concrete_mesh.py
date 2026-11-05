"""Source welded-wire design mat, with explicit adopted location and voids.

This is design reinforcement geometry, not a fabrication sheet/lap schedule.
The complete diaphragm record stays unmapped until its other components exist.
"""
import math


def clear_runs(start,end,voids,margin):
    runs=[(start,end)]
    for lo,hi in sorted(voids):
        result=[]
        lo-=margin;hi+=margin
        for a,b in runs:
            if hi<=a or lo>=b:result.append((a,b));continue
            if lo>a:result.append((a,lo))
            if hi<b:result.append((hi,b))
        runs=result
    return [(a,b) for a,b in runs if b-a>.01]


def apply(b):
    if b.key!='cfs4':return
    rid='diaphragms/diaphragm-floors';record=b.records[rid]
    if '6x6-W2.9xW2.9 WWR' not in record['data']['selection']:
        raise ValueError('Unrecognized source floor mesh selection')
    # WRI nominal-size table: W2.9 has 0.029 in2 area and 0.192 in diameter.
    diameter=.192;spacing=6.;margin=2.
    profile=b.custom('WWR-W2.9','round',dict(d=diameter),nominal_area_in2=.029,
        basis='S: W2.9 plain wire; WRI nominal size table, https://wirereinforcementinstitute.org/application/files/3316/0588/6872/WWR400-R-03.pdf')
    b.material_selections.append(dict(id='CFS4-WWR',basis='S product designation; A manufacturing standard',
        specification='6x6-W2.9xW2.9 plain welded-wire reinforcement; A ASTM A1064 product. Strength and factory listing remain supplier confirmation; no new capacity calculation.'))
    openings={o['id']:o for o in b.openings}
    for panel in (p for p in b.panels if p['kind']=='floor'):
        vertices=panel['vertices'];low=[min(q[i] for q in vertices) for i in (0,1)]
        high=[max(q[i] for q in vertices) for i in (0,1)]
        if len(vertices)!=4 or any(q[0] not in (low[0],high[0]) or q[1] not in (low[1],high[1]) for q in vertices):
            raise ValueError('This mesh layout requires its actual rectangular floor boundary')
        if panel.get('material_id')!='CFS4-LWC' or panel['thickness_in']!=2.5:
            raise ValueError('Mesh must use the actual topping, excluding deck depth')
        top=vertices[0][2];level=panel['level'];axes=[[],[]]
        for along in (0,1):
            normal=1-along
            stations=[low[normal]+3+i*spacing for i in range(math.floor((high[normal]-low[normal]-6)/spacing)+1)]
            for row,station in enumerate(stations):
                voids=[]
                for oid in panel.get('openings',[]):
                    opening=openings[oid]
                    if opening['plane']!='xy':raise ValueError('Mesh opening must have its actual floor-plane geometry')
                    lo=[opening['x_ft']*12,opening['y_ft']*12]
                    hi=[lo[0]+opening['width_ft']*12,lo[1]+opening['height_ft']*12]
                    if lo[normal]-diameter/2 < station < hi[normal]+diameter/2:
                        voids.append((lo[along],hi[along]))
                runs=clear_runs(low[along]+margin,high[along]-margin,voids,margin)
                for piece,(start,end) in enumerate(runs):
                    z=top-.5-along*diameter
                    a=[start,station,z] if along==0 else [station,start,z]
                    d=[end,station,z] if along==0 else [station,end,z]
                    mid=f'WWR-L{level}-{"XY"[along]}-{row+1}-{piece+1}'
                    member=b.member(mid,profile,'reinforcement_bar',a,d,level,'S product; A set-out',
                        host_panel_id=panel['id'],source_context_record_ids=[rid],
                        source_selection=record['data']['selection'],mesh_id=f'WWR-L{level}',
                        engineering_status='not_verified',top_cover_in=.5+along*diameter-diameter/2,
                        fabrication_status='Continuous design mat; supplier sheet extents, laps and opening-edge anchorage remain explicit requirements')
                    member['material_id']='CFS4-WWR';axes[along].append(member)
                    cid=mid+':BOND'
                    b.connection(cid,'review_collector_bond',[(x+y)/2 for x,y in zip(a,d)],[member],
                        parameters=dict(host_panel_id=panel['id'],slab_top_in=top,topping_in=2.5,
                            reinforcement_label='W2.9 welded-wire design mat',
                            reinforcement_note='S: 6x6-W2.9xW2.9 mesh, nominal wire diameter 0.192 in. A: grid origin, cover, two touching wire layers and opening trims. Sheet panelization/laps, edge development and factory weld certification remain supplier/engineer requirements.'),
                        title='SOURCE WELDED-WIRE MAT / A HOST SET-OUT')
                    for end_name in ('start','end'):
                        b.endpoint_links.append(dict(member_id=mid,end=end_name,connection_id=cid,
                            basis='This design-mat wire end is in its actual concrete host, trimmed clear of the edge/void. Bond geometry is explicit; development and fabrication sheet laps are unverified.'))
        crossings=0
        for x in axes[0]:
            for y in axes[1]:
                if (x['axis'][0][0]<=y['axis'][0][0]<=x['axis'][1][0] and
                    y['axis'][0][1]<=x['axis'][0][1]<=y['axis'][1][1]):crossings+=1
        panel['reinforcement_design_mat']=dict(id=f'WWR-L{level}',source_context_record_id=rid,
            source_selection=record['data']['selection'],spacing_in=[spacing,spacing],
            nominal_wire_area_in2=.029,nominal_wire_diameter_in=diameter,
            x_wire_ids=[m['id'] for m in axes[0]],y_wire_ids=[m['id'] for m in axes[1]],
            factory_crossing_count=crossings,
            factory_crossing_rule='All actual orthogonal wire intersections have touching surfaces and belong to the source welded mesh; factory weld shape and strength are not fabricated here.',
            fabrication_requirements=['Supplier sheet/roll panelization and laps','Opening-edge anchorage/development','Wire strength and factory weld certification'],
            engineering_status='not_verified')
        b.changes.append(dict(kind='source_welded_wire_design_mat',host_panel_id=panel['id'],
            source_context_record_id=rid,wire_count=sum(map(len,axes)),factory_crossing_count=crossings,
            basis='S spacing and W2.9 size. A three-inch grid origin, two-inch end/void margins and centres0.5/0.692 in below topping top. Design mat only; fabrication and development remain explicit requirements.'))
    b.note('FLOOR-WWR','S: 6x6-W2.9xW2.9 plain welded-wire reinforcement is represented by actual individual wires, with a located factory-crossing rule and cuts around each accepted stair void. A: grid origin, vertical placement and edge margins. This design mat is not a fabrication sheet/lap schedule. Supplier panelization, laps, anchorage and certification remain explicit requirements. The floor diaphragm schedule stays unmapped until perimeter chord continuity and deck attachments are complete.')
