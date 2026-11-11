import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from steltic_openbim.pdf_part_verification import check_parts
from steltic_openbim.pdf_verification import read_ink


@pytest.mark.parametrize("defect",["none","missing","shift","short","blocked_hole","white","clipped","unbound"])
def test_actual_plate_ink_matches_holed_gusset(tmp_path,defect):
    rectangles=[(-10,-6,10,-2),(-10,2,10,6),(-10,-2,-2,2),(2,-2,10,2)]
    faces=[[(x0,y0,0),(x1,y0,0),(x1,y1,0),(x0,y1,0)] for x0,y0,x1,y1 in rectangles]
    scene=dict(id="joint",front_axes=[0,1],parts=[dict(id="gusset",kind="plate",faces=faces)])
    view=dict(rect_pt=[0,0,220,200],scale_denominator=72)
    pdf=tmp_path/"plate.pdf"
    c=Canvas(str(pdf),pagesize=(220,200))
    c.drawString(10,10,"gusset 20 x 12 x 1/2")
    c.saveState()
    if defect=="shift":
        c.translate(5,1)
    if defect=="clipped":
        clip=c.beginPath()
        clip.rect(0,0,5,5)
        c.clipPath(clip)
    for i,face in enumerate(faces):
        if defect=="missing":
            continue
        c.addLiteral(f'/StelticPart << /N {1 if defect=="unbound" else 0} >> BDC')
        c.setFillGray(1 if defect=="white" else .5)
        if defect=="blocked_hole" and i==2:
            face=[(-10,-2,0),(2,-2,0),(2,2,0),(-10,2,0)]
        p=c.beginPath()
        for j,(x,y,z) in enumerate(face):
            (p.moveTo if j==0 else p.lineTo)(110+(x/2 if defect=="short" else x),90+y)
        p.close()
        c.drawPath(p,fill=1,stroke=0)
        c.addLiteral("EMC")
    c.restoreState()
    c.save()
    page=PdfReader(pdf).pages[0]
    ink=[]
    read_ink(page,ink)
    count,issues=check_parts(scene,view,ink,page.cropbox)
    assert count==1
    assert bool(issues)==(defect!="none"),issues
