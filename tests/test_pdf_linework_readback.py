from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from steltic_openbim.pdf_linework_readback import DrawingLinework,WireInk
from steltic_openbim.pdf_verification import read_ink


def read_segment(p,q,white=False,clip=False):
    buf=BytesIO()
    c=Canvas(buf,pagesize=(200,200),pageCompression=0)
    if clip:
        path=c.beginPath();path.rect(1,1,4,4);c.clipPath(path,stroke=0)
    c.addLiteral('/StelticFrame BMC')
    c.setStrokeColorRGB(*([1,1,1] if white else [0,0,0]))
    c.line(*p,*q)
    c.addLiteral('EMC')
    c.save()
    wires=[]
    read_ink(PdfReader(buf).pages[0],wires=wires)
    return wires


@pytest.mark.parametrize('change',['none','missing','wrong_slope','wrong_plane','extra','white','clipped','unmarked','ident'])
def test_workline_is_measured_from_real_painted_pdf(change):
    view=dict(sheet='S201',linework='source_axes',member_ids=['brb'],bounds_in=[[0,80],[0,40]],origin_pt=[20,20],axes=[0,2],points_per_inch=2)
    m=dict(id='brb',axis=[[0,16,0],[80,16,40]],kind='brace')
    reader=DrawingLinework(dict(members=[m]),dict(views=[view]),None)
    a,b=(20,20),(180,100)
    if change=='wrong_slope':b=(100,100)
    if change=='wrong_plane':view['axes']=[1,2]
    if change=='ident':view['member_ids']=['unknown']
    wires=read_segment(a,b,white=change=='white',clip=change=='clipped')
    if change=='missing':wires[0].segments=[]
    if change=='unmarked':wires=[]
    if change=='extra':wires[0].segments.append(((20,20),(100,100)))
    n,_,issues=reader.check('S201',wires,(0,0,200,200))
    assert bool(issues)==(change!='none')
    if change=='none':assert n==1


def test_section_cannot_omit_an_applicable_member_from_its_list():
    m=dict(kind='brace',axis=[[0,0,0],[20,0,40]],profile_id='SH')
    v=dict(sheet='S',linework='physical_section',limits_in=[[-1,21],[-1,1],[-1,41]],axes=[0,2],bounds_in=[[0,20],[0,40]],
           origin_pt=[20,20],points_per_inch=2,member_ids=['m1'])
    w=WireInk('/StelticFrame')
    r=DrawingLinework(dict(members=[dict(m,id='m1'),dict(m,id='m2')]),dict(views=[v]),None)
    assert 'cut through the physical model' in str(r.check('S',[w],(0,0,200,200)))


def test_native_gusset_shape_change_with_same_extent_is_visible():
    triangle=[[0,0,0],[10,0,0],[0,0,8]]
    plate=dict(id='gusset',kind='plate',geometry={'type':'mesh','faces':[triangle]})
    physical=dict(members=[],profiles=[],connections=[])
    c=dict(id='joint',parts=[plate])
    n=SimpleNamespace(physical=physical,templates={},connections={'joint':c})
    v=dict(kind='source_connection_assembly',sheet='C001',connection_id='joint',part_ids=['gusset'],
           axes=[0,2],origin_pt=[20,30],points_per_inch=2)
    r=DrawingLinework({},dict(views=[v]),n)
    w=WireInk('/StelticPartWire')
    w.segments=[((20,30),(40,30)),((40,30),(20,46)),((20,46),(20,30))]
    assert r.check('C001',[w],(0,0,200,200))==(0,1,[])
    w.segments[1:2]=[((40,30),(40,46)),((40,46),(20,46))]
    assert r.check('C001',[w],(0,0,200,200))[2]
