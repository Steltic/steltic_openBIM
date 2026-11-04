from reportlab.pdfbase.pdfmetrics import stringWidth
from steltic_openbim.assembly_pdf import draw_view
from steltic_openbim.assembly_scene import Assembly
from steltic_openbim.design_pdf import DesignSheets


def test_long_component_names_stay_inside_their_view_and_are_not_truncated(tmp_path):
    names=['RIM-PACKTRUSS-1--1-P1LOW','PAR-END-0--1-FOOT','SOURCE-RECEIVER-FLOOR-BEARING-LEFT','R4']
    a=Assembly('Long named parts',{'C':dict(id='C',family='channel',dimensions=dict(d=2,b=1,t=.1,lip=0))})
    for i,name in enumerate(names):a.member(name,'C',[i*3,0,i],[i*3+2,0,i],basis='A')
    a.interfaces.append(dict(id='FIT',kind='review_fit',connects=names,basis='A',description='Rendering fixture'))
    scene=a.result();scene.update(id='QA',family='render_fixture',reference='1/QA')
    sheets=DesignSheets({}, {},tmp_path,dict(title='Labels',members=[],profiles=[]));sheets.current='QA'
    labels=[];original=sheets.label
    def capture(x,y,t,size=10,color='#000000'):
        labels.append((x,y,t,stringWidth(t,'Helvetica',size)))
        original(x,y,t,size,color)
    sheets.label=capture
    rect=(70,155,1090,675)
    for mode in ('front','iso'):draw_view(sheets,scene,mode,rect,'Parts')
    sheets.c.save()
    assert {t for x,y,t,w in labels}==set(names)|{'A-A'}
    labels=[item for item in labels if item[2] in names]
    assert len(labels)==2*len(names)
    for x,y,t,w in labels:
        assert rect[0]+10<=x and x+w<=rect[0]+rect[2]-10,t
        assert rect[1]<y<rect[1]+rect[3],t
