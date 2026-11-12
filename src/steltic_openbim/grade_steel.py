"""Source-selected steel at a brace workpoint and its grade-slab interface."""
import math

def add_nut(a,index,point,level,diameter,hardware):
    from .connection_cuts import drill_plate
    x,y=point[:2];radius=hardware['nut_across_flats_in']/math.sqrt(3)
    ring=[[x+radius*math.cos(i*math.pi/3),y+radius*math.sin(i*math.pi/3),level] for i in range(6)]
    nut=a.polygon('NUT-TOP-'+str(index),ring,hardware['nut_height_in'],normal=[0,0,1],
                  basis='S',description='Machined hex anchor nut seated on the plate washer')
    nut.update(selected_material=hardware['nut_material'],parameters={'source_role':'top_anchor_nut'})
    drill_plate(nut,[point],[0,0,1],diameter,'Nominal thread envelope')

def selection(records,connection):
    selected=[(rid,records[rid]['grade_steel']) for rid in connection.get('design_record_ids',[])
              if rid in records and records[rid].get('grade_steel')]
    if len(selected)>1:raise ValueError('Multiple grade receivers at '+connection['id'])
    if not selected:return None
    rid,stock=selected[0]
    if stock['kind']!='grade_rail':return None
    if connection.get('parameters',{}).get('joint')!='base':
        raise ValueError('Grade receiver attached above its selected base: '+connection['id'])
    return dict(stock,record_id=rid)

def add_rail(a,stock,face):
    length=stock['horizontal_length']+stock['end_margin_in'];width=stock['width_in']
    lower=stock['bottom_plate_in'];upper=stock['top_plate_in'];height=stock['web_height_in']
    web=stock['web_thickness_in'];gauge=stock['web_gauge_in']
    if min(length,width,lower,upper,height,web,gauge)<=0 or gauge+web>width or web>=gauge:
        raise ValueError('Grade rail component dimensions do not fit')
    z=lower+height
    def plate(key,label,y,base,breadth,thickness):
        part=a.box(key,[face,y,base],[length,breadth,thickness],'S',label)
        part.update(selected_material=stock['material'],parameters={'grade_receiver_role':key,
                    'source_record_id':stock['record_id']})
    plate('BASE','Grade receiver top plate',-width/2,z,width,upper)
    plate('GRADE-SOLE','Grade interface plate, underside at slab datum',-width/2,0,width,lower)
    for i,side in enumerate((-1,1)):
        y=side*gauge/2;key='GRADE-WEB'+str(i)
        plate(key,'Longitudinal grade receiver web',y-web/2,lower,web,height)
        for level,host in ((lower,'GRADE-SOLE'),(z,'BASE')):
            a.weld(key+'-'+host,[face,y,level],[face+length,y,level],[key,host],0,kind='CJP',basis='S',
                   description='Continuous complete-joint-penetration web-to-plate groove')
            a.welds[-1]['selected_material']=stock['weld_material']
    a.dim([face,width/2,0],[face,width/2,z+upper],'Grade to top of receiver',basis='S')
    a.notes.append(stock['interface_note'])
