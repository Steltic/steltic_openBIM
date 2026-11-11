import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A1,landscape
from steltic_openbim.pdf_verification import read_ink
from steltic_openbim.pdf_annotation_readback import check_heading,check_legend


@pytest.mark.parametrize("defect",["none","title","sheet","size","basis","shift","clip","missing"])
def test_printed_heading_and_weld_table(tmp_path,defect):
    path=tmp_path/"weld.pdf"
    w,h=landscape(A1)
    c=Canvas(str(path),pagesize=(w,h))
    c.setFont("Helvetica-Bold",17);c.drawString(55,h-70,"STELTIC")
    c.setFont("Helvetica-Bold",27)
    c.drawString(55,h-112,"Other" if defect=="title" else "Brace connection")
    c.drawString(w-390,h-69,"C402" if defect=="sheet" else "C401")
    row=dict(label="W1",basis="S",note=False,lines=["3/4 in fillet to flange"],step=13,gap=6)
    if defect!="missing":
        c.saveState()
        if defect=="clip":
            clip=c.beginPath();clip.rect(0,0,1,1);c.clipPath(clip)
        if defect=="shift":
            c.translate(20,0)
        c.addLiteral("/StelticLegend << /N 0 >> BDC")
        c.setFont("Helvetica-Bold",11);c.drawString(1210,774,"W1")
        c.setFont("Helvetica",10);c.drawString(1274,774,"A" if defect=="basis" else "S")
        c.drawString(1308,774,"1/4 in fillet to flange" if defect=="size" else row["lines"][0])
        c.addLiteral("EMC");c.restoreState()
    c.save()
    page=PdfReader(path).pages[0]
    legend=[]
    read_ink(page,legends=legend)
    heading=check_heading(page,dict(number="C401",title="Brace connection"))
    _,issues=check_legend(page,[row],legend,False)
    assert bool(issues or heading)==(defect!="none"),(issues,heading)
