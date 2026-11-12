"""Select the stated paired-plate variant for the actual column face."""
import re
from .assembly_templates import NUMBER,number

PAIR = r'(?:two plates PL|two plates,.*?each: plate) '+NUMBER+r' x '+NUMBER+r' in'


def paired(text, *, weak=False, column=None):
    line=next((line for line in text.splitlines() if re.search(PAIR,line,re.I)),None)
    if line is None:return text,None
    if 'web-side ends on the ' in line:
        common=line.split('; fit-up:',1)[-1] if '; fit-up:' in line else ''
        if weak:
            match=re.search(r'web-side ends on the '+re.escape(column or '')+r'\b.*?(?=; web-side ends on the |; fit-up:|$)',line,re.I)
            if match is None:raise ValueError('No source paired-plate web-side selection for '+str(column))
            line=match[0]+'; fit-up: '+common
        else:line=line.split('; web-side ends on the ',1)[0]+'; fit-up: '+common
    return line,re.search(PAIR,line,re.I)


def add_web_reinforcement(assembly,stock,text,start,centre_z,web_t):
    thickness,height,length=map(number,stock.groups())
    clause=text[stock.end():].split(';',1)[0]
    grade=re.search(r'\bA(?:36|572\s+Gr(?:ade)?\.?\s*\d+)\b',clause,re.I)
    fillet=re.search(NUMBER+r'\s*in\.?\s+fillets?\s+all\s+(?:a?round)',clause,re.I)
    size=number(fillet[1]) if fillet else .3125
    edges=[(start,centre_z-height/2),(start+length,centre_z-height/2),
           (start+length,centre_z+height/2),(start,centre_z+height/2)]
    ids=[]
    for i,side in enumerate((-1,1)):
        label='RP'+str(i)
        contact=side*web_t/2
        y=contact-thickness if side<0 else contact
        plate=assembly.box(label,[start,y,centre_z-height/2],[length,thickness,height],'S','Source beam-web reinforcement')
        if grade:plate['selected_material']=grade[0]
        for j,((x,z),(xx,zz)) in enumerate(zip(edges,edges[1:]+edges[:1]),1):
            assembly.weld(f'{label}-W{j}',[x,contact,z],[xx,contact,zz],['M2',label],size,
                          basis='S' if fillet else 'A',description=f'{size:g} in perimeter fillet to beam web')
        ids.append(label)
    return ids
