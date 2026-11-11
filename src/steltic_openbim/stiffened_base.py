"""Locate flange-tip stiffeners and the selected adjacent anchor rows."""
import re

from .assembly_templates import NUMBER,number


def selection(text):
    plates=re.search(r'four stiffener plates PL '+NUMBER+r' x '+NUMBER+r' x '+NUMBER+
        r' in (.*?) at the flange tips \(outer faces flush with the tips\), projecting '+
        NUMBER+r' in beyond each flange face, CJP-welded to the flange and to the base plate',text,re.I)
    if not plates:return None
    t,h,length=map(number,plates.groups()[:3])
    if abs(number(plates[5])-length)>1e-5:
        raise ValueError('Flange-tip stiffener projection and plate length differ')
    rows=re.search(r'on each flange side (\d+) rows of two rods, one outside each stiffener '+
        NUMBER+r' in from its face, at ([\d., ]+) in from the flange face',text,re.I)
    if not rows:raise ValueError('The selected flange-tip stiffeners require a located anchor layout')
    stations=[number(value.strip()) for value in rows[3].split(',')]
    if len(stations)!=int(rows[1]):raise ValueError('Stiffened-base anchor row stations differ from the selected count')
    return dict(thickness=t,height=h,projection=length,material=plates[4].strip(),
                outside=number(rows[2]),stations=stations)


def add(assembly,details,depth,flange_width,sole_top):
    thickness=details['thickness'];height=details['height'];length=details['projection']
    for face in (-1,1):
        x=face*depth/2
        for side in (-1,1):
            y=side*flange_width/2
            name=f'FLANGE-STIFFENER-{face}-{side}'
            plate=assembly.box(name,[min(x,x+face*length),min(y,y-side*thickness),sole_top],
                               [length,thickness,height],'S','Selected flange-tip stiffener, outer face flush with flange tip')
            plate['selected_material']=details['material']
            centre=y-side*thickness/2
            assembly.weld(name+'-COLUMN',[x,centre,sole_top],[x,centre,sole_top+height],
                          [name,'M1'],kind='CJP',description='Selected stiffener-to-column-flange CJP')
            assembly.weld(name+'-SOLE',[x,centre,sole_top],[x+face*length,centre,sole_top],
                          [name,'P1'],kind='CJP',description='Selected stiffener-to-base-plate CJP')
