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


def test_repeated_weld_leader_matches_legend_without_losing_any_weld_geometry(tmp_path):
    import copy
    from steltic_openbim.assembly_legend import entries
    a=Assembly('Full-width stud welds',{})
    a.box('EMBED',[0,0,0],[336,1,12],'S')
    a.box('STUD-CONTEXT',[0,1,0],[336,5,12],'A')
    a.box('MAT',[0,0,-12],[336,12,24],'A',kind='concrete')
    for i in range(112):
        x=1.5+3*i
        a.weld('WS'+str(i),[x-.4375,1,6],[x+.4375,1,6],['EMBED','STUD-CONTEXT'],kind='STUD_WELD')
    scene=a.result();scene.update(id='QA',family='render_fixture',reference='1/QA')
    before=copy.deepcopy(scene);labels=[];strokes=[]
    sh=DesignSheets({}, {},tmp_path,dict(title='Weld labels',members=[],profiles=[]));sh.current='QA'
    original_label=sh.label;original_line=sh.line
    def label(x,y,t,size=10,color='#000000'):
        labels.append((x,y,t,stringWidth(t,'Helvetica',size)));original_label(x,y,t,size,color)
    def line(a,b,color='#000000',width=1,*args,**kwargs):
        if color=='#ae4742':strokes.append((a,b))
        return original_line(a,b,color,width,*args,**kwargs)
    sh.label=label;sh.line=line;rect=(70,855,1090,620)
    draw_view(sh,scene,'front',rect,'Full-width anchorage');sh.c.save()
    assert scene==before and len(strokes)==112
    rows=[r for r in entries(scene) if r['label'].startswith('WS')]
    assert len(rows)==1 and rows[0]['label']=='WS0..WS111' and '112 weld lines' in rows[0]['text']
    assert [t for x,y,t,w in labels if t.startswith('WS')]==['WS0..WS111']
    for x,y,t,w in labels:
        if t=='A-A':continue
        assert rect[0]+10<=x and x+w<=rect[0]+rect[2]-10
        assert rect[1]<y<rect[1]+rect[3]
