"""Read explicit base selections; distinguish shafts, rods and shear lugs.

This fixture reader does not size any component. Its numeric values come from
the retained design text; absent fit dimensions remain labelled proposals.
"""
import re
from .assembly_templates import NUMBER,number


def embedment(text):
    # The section can precede the verb: "BOX24X4 embedded 10.0 ft".
    # Requiring the embedded object to be a shaft prevents anchor-end washers
    # and shear-lug embedment from changing the selected foundation type.
    hit=re.search(r'\b(?:(?:BOX|HSS|W)[\dX./-]+|(?:steel\s+)?column|shaft)\s+(?:is\s+)?embedded\s*'+NUMBER+r'\s*(ft|in)\b',text,re.I)
    if hit:return number(hit[1])*(12 if hit[2].lower()=='ft' else 1)
    if not re.search(r'\bembedded\s+(?:(?:steel\s+)?(?:column|shaft|box|W\d|HSS)|base)|\bLe\s*=\s*\d',text,re.I):
        return None
    hit=re.search(r'\bLe\s*=\s*'+NUMBER+r'\s*in',text,re.I)
    if hit:return number(hit[1])
    hit=re.search(r'\bembedded\s*'+NUMBER+r'\s*ft',text,re.I)
    return 12*number(hit[1]) if hit else None


def rods(text):
    grade=r'((?:ASTM\s+)?(?:F1554(?:[- ](?:Grade\s*)?\d+)?|A193\s+(?:Grade\s+)?B7))'
    for pattern in (r'(\d+)\s*x\s*'+NUMBER+r'\s*in\s*'+grade,
                    r'(\d+)\s+anchor rods\s*'+NUMBER+r'\s*in\s*'+grade):
        hit=re.search(pattern,text,re.I)
        if hit:return int(hit[1]),number(hit[2]),hit[3]
    return None


def erection_rods(text):
    """Keep selected rod size/grade and edge minimum; label missing lengths A."""
    hit=re.search(r'\b(\d+|four) erection anchor rods\b',text,re.I)
    if not hit:return None
    count=4 if hit[1].lower()=='four' else int(hit[1])
    tail=text[hit.end():]
    selected=re.match(r'\s*'+NUMBER+r'\s*in\s*((?:ASTM\s+)?F1554(?:[- ](?:Grade\s*)?\d+)?)',tail,re.I)
    edge=re.search(r'at '+NUMBER+r' in or more from the plate edges',tail,re.I)
    return dict(count=count,diameter=number(selected[1]) if selected else .75,
        grade=selected[2] if selected else 'F1554 Grade 36',
        selected_size=bool(selected),edge_min=number(edge[1]) if edge else 2)


def flange_rows(text,flange_width=None):
    """(rows per flange, rods per row, row pitch, flange gap, rod pitch)."""
    hit=re.search(r'rods in two rows, (\d+) per row, '+NUMBER+r' in from the flange faces',text,re.I)
    edge=re.search(r'rods '+NUMBER+r' in from the plate edges',text,re.I)
    if hit and edge and flange_width is not None:
        count=int(hit[1]);usable=flange_width-2*number(edge[1])
        if count<2 or usable<=0:raise ValueError('Selected anchor row does not fit the flange-parallel stock')
        return 1,count,0,number(hit[2]),usable/(count-1)
    selected=re.search(r'(\d+) per flange side in one row outside the flanges at '+NUMBER+r' in, '+NUMBER+r' in from the flange face',text,re.I)
    if selected:
        return 1,int(selected[1]),0,number(selected[3]),number(selected[2])
    hit=re.search(r'rod layout: (\d+) rods outside each flange in (?:(\d+) rows '+NUMBER+r' in apart of (\d+)|one row of (\d+)).*?a1 = '+NUMBER+r' in.*?rods '+NUMBER+r' in apart',text,re.I)
    if hit:
        _,rows,pitch,cols,one,gap,spacing=hit.groups()
        return int(rows or 1),int(cols or one),number(pitch) if pitch else 0,number(gap),number(spacing)
    hit=re.search(r'rod layout: \d+ rods, one row of (\d+) outside each flange,.*?first row '+NUMBER+r' in from the flange face, rods at '+NUMBER+r' in centres',text,re.I)
    if hit:return 1,int(hit[1]),0,number(hit[2]),number(hit[3])
    hit=re.search(r'rod layout: on each tension side (\d+) row of (\d+) rods at '+NUMBER+r' in, the first row '+NUMBER+r' in from the flange face',text,re.I)
    if hit:return int(hit[1]),int(hit[2]),0,number(hit[4]),number(hit[3])
    hit=re.search(r'two outside each flange '+NUMBER+r' in from the flange face at '+NUMBER+r' in',text,re.I)
    if hit:return 1,2,0,number(hit[1]),number(hit[2])
    return None


def lug_arms(text):
    """Return explicit (thickness, width, embedment) for both crossing arms."""
    main=re.search(r'shear lug:\s*(?:ASTM\s+\w+\s+)?PL '+NUMBER+r' x '+NUMBER+r' in, '+NUMBER+r' in embedded',text,re.I)
    other=re.search(r'second arm PL '+NUMBER+r' x '+NUMBER+r' in',text,re.I)
    if main:
        t,w,e=map(number,main.groups());rt,rw=map(number,other.groups()) if other else (t,w)
        return (t,w,e),(rt,rw,e)
    pairs=re.findall(r'(?:strong-axis arm \(bearing along the web\)|weak-axis arm \(bearing along the flanges\)|in-plane arm|out-of-plane arm|arm bearing in [XY]) PL '+NUMBER+r' x '+NUMBER+r' in',text,re.I)
    height=re.search(r'crossing plates, '+NUMBER+r' in embedded',text,re.I)
    if len(pairs)==2 and height:
        e=number(height[1]);return tuple((*map(number,pair),e) for pair in pairs)
    same=re.search(r'cruciform shear lug.*?PL '+NUMBER+r' x '+NUMBER+r' in.*?'+NUMBER+r' in (?:embedded|below the)',text,re.I)
    if same:
        t,w,e=map(number,same.groups());return (t,w,e),(t,w,e)
    same=re.search(r'cruciform shear lug PL '+NUMBER+r' in \(legs '+NUMBER+r' in wide, '+NUMBER+r' in below',text,re.I)
    if same:
        t,w,e=map(number,same.groups());return (t,w,e),(t,w,e)
    return None
