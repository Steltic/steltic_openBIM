import json

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DecodedStreamObject
from reportlab.pdfgen.canvas import Canvas

from steltic_openbim.design_pdf import DesignSheets
from steltic_openbim.pdf_verification import verify_dimensions


def make_revision(path):
    sh=DesignSheets.__new__(DesignSheets)
    sh.c=Canvas(str(path/'drawings.pdf'),pagesize=(400,400),invariant=1)
    sh.current='S001'
    sh.page=1
    sh.dimensions=[]
    projection=dict(sheet='S001',axes=[0,1],scale=72,origin_pt=[50,100],bounds_in=[[0,100],[0,100]])
    sh.dim((50,100),(150,100),25,value=100,ref='Grid A-B',source=dict(kind='grid',axis=0,names=['A','B']),projection=projection)
    sh.dim((50,100),(150,100),65,value=100,ref='Overall grid dimension',source=dict(kind='grid',axis=0,names=['A','B']),projection=projection)
    sh.c.showPage()
    sh.c.save()
    manifest=dict(sheets=[dict(number='S001')],dimensions=sh.dimensions,
                  views=[dict(sheet='S001',axes=[0,1],points_per_inch=1,grid_axes=True,bounds_in=projection['bounds_in'])])
    model=dict(grids=dict(x=[['A',0],['B',100]],y=[]),openings=[],levels=[])
    for name,data in [('drawing_manifest',manifest),('design_model',model),('connection_assemblies',{'assemblies':[]})]:
        (path/(name+'.json')).write_text(json.dumps(data))


def alter_pdf(path,change):
    pdf=PdfReader(path)
    writer=PdfWriter()
    page=writer.add_page(pdf.pages[0])
    stream=DecodedStreamObject()
    data=page.get_contents().get_data()
    changed=change(data)
    assert changed!=data
    stream.set_data(changed)
    page[NameObject('/Contents')]=writer._add_object(stream)
    with path.open('wb') as out:
        writer.write(out)


@pytest.mark.parametrize('defect', ['none','line','value','shift','crop','missing','source','grid_omission'])
def test_readback_detects_dimension_defects(tmp_path,defect):
    make_revision(tmp_path)
    pdf=tmp_path/'drawings.pdf'
    if defect=='line':
        alter_pdf(pdf,lambda b:b.replace(b'50 125 m 150 125 l',b'50 125 m 144 125 l',1))
    if defect=='value':
        alter_pdf(pdf,lambda b:b.replace(b'8\'-4"',b'8\'-7"',1))
    if defect=='shift':
        alter_pdf(pdf,lambda b:b'q 1 0 0 1 8 0 cm\n'+b+b'\nQ')
    if defect=='crop':
        alter_pdf(pdf,lambda b:b'q 0 0 10 10 re W n\n'+b+b'\nQ')
    if defect in ('missing','grid_omission'):
        def drop(b):
            start=b.index(b'/StelticDim')
            end=b.index(b'EMC',start)+3
            return b[:start]+b[end:]
        alter_pdf(pdf,drop)
        if defect=='grid_omission':
            m=tmp_path/'drawing_manifest.json'
            data=json.loads(m.read_bytes())
            data['dimensions'].pop(0)
            m.write_text(json.dumps(data))
    if defect=='source':
        m=tmp_path/'design_model.json'
        data=json.loads(m.read_bytes())
        data['grids']['x'][1][1]=94
        m.write_text(json.dumps(data))
    result=verify_dimensions(tmp_path)
    assert result['passed']==(defect=='none'),result
    assert result['pages_checked']==1
