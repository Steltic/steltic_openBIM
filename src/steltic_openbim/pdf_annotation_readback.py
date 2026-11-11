"""Read the published sheet title, component table, weld sizes and notes."""
import math
import re

from pypdf.generic import ContentStream, DecodedStreamObject
from reportlab.pdfbase.pdfmetrics import stringWidth

from .assembly_legend import number, pages
from .drawing_pdf import Sheets, ascii_text
from .pdf_verification import compose, IDENTITY, inside, POINT_TOL, transform


def expected_legends(scenes,omitted):
    result={}
    wrapping=Sheets.__new__(Sheets)
    for scene in scenes:
        if scene["reference"] in omitted:
            continue
        for i,rows in enumerate(pages(wrapping,scene)):
            key=number(scene,i) if i else scene["sheet"]
            if key in result:
                raise ValueError("two assembly legends share drawing sheet "+key)
            result[key]=(rows,bool(i))
    return result


def check_heading(page,registered):
    stream=page.get_contents()
    if stream is None:
        return ["sheet has no painted title block"]
    data=stream.get_data()
    # The producer places the title and sheet number in the opening text blocks.
    # Parse the complete PDF operands at the head without decoding a second whole page.
    ends=[m.end() for m in re.finditer(rb"(?<!\S)ET(?=\s|$)",data[:16000])]
    if not ends:
        return ["sheet has no readable title block"]
    prefix=DecodedStreamObject()
    prefix.set_data(data[:ends[min(11,len(ends)-1)]])
    matrix=IDENTITY
    text_matrix=IDENTITY
    clipped=False
    text_mode=0
    colour=(0.,)
    stack=[]
    seen=[]
    for args,op in ContentStream(prefix,page.pdf).operations:
        if op==b"q":
            stack.append((matrix,text_mode,clipped,colour))
        elif op==b"Q":
            matrix,text_mode,clipped,colour=stack.pop()
        elif op==b"cm":
            matrix=compose(matrix,map(float,args))
        elif op==b"BT":
            text_matrix=IDENTITY
        elif op==b"Tm":
            text_matrix=tuple(map(float,args))
        elif op==b"Tr":
            text_mode=int(args[0])
        elif op in (b"W",b"W*",b"gs"):
            clipped=True
        elif op in (b"rg",b"g",b"k"):
            colour=tuple(map(float,args))
        elif op==b"Tj" and not clipped and not text_mode and not (len(colour)<=3 and min(colour)>.96):
            full=compose(matrix,text_matrix)
            seen.append((str(args[0]),full))
    w,h=map(float,(page.mediabox.width,page.mediabox.height))
    expected=[(ascii_text(registered["title"]),(55,h-112)),(str(registered["number"]),(w-390,h-69))]
    if any(not any(s==label and math.dist(m[4:],point)<=POINT_TOL and
                   all(abs(a-b)<.0001 for a,b in zip(m[:4],IDENTITY[:4])) and inside(point,page.cropbox) for s,m in seen)
           for label,point in expected):
        return ["printed title, sheet number or title-block placement differs from register"]
    return []


def check_legend(page,expected,groups,continuation):
    issues=[]
    if len(groups)!=len(expected):
        issues.append((None,"number of painted legend rows differs from source parts, welds and notes"))
    h=float(page.mediabox.height)
    x,y=(80,h-195) if continuation else (1210,774)
    for i,row in enumerate(expected):
        items=[]
        if not row["note"]:
            label=ascii_text(row["label"])
            size=min(11,11*56/max(1,stringWidth(row["label"],"Helvetica-Bold",11)))
            items.extend([(label,x,y,size,"Helvetica-Bold"),(ascii_text(row["basis"]),x+64,y,10,"Helvetica")])
        for line in row["lines"]:
            items.append((line,x+(0 if row["note"] else 98),y,10,"Helvetica"))
            y-=row["step"]
        y-=row["gap"]
        if i>=len(groups):
            continue
        g=groups[i]
        if g["id"]!=i or g["errors"] or g["lines"] or len(items)!=len(g["text"]):
            issues.append((i,"incomplete, hidden, misplaced or duplicated legend row"))
            continue
        for (label,tx,ty,size,font),(actual,m,printed_size,printed_font) in zip(items,g["text"]):
            if (label!=actual or printed_font!="/"+font or abs(printed_size-size)>.01
                    or math.dist((tx,ty),m[4:])>POINT_TOL or max(abs(a-b) for a,b in zip(m[:4],IDENTITY[:4]))>.0001):
                issues.append((i,"printed part, weld, basis or note differs from expected text or position"))
                break
            width=stringWidth(actual,font,printed_size)
            if any(not inside(transform(m,p),page.cropbox) for p in [(0,-.22*size),(width,.73*size)]):
                issues.append((i,"part or weld note lies outside printed crop"))
                break
    return min(len(expected),len(groups)),issues
