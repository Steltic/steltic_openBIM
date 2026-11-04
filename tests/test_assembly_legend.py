from pathlib import Path
from pypdf import PdfReader
from steltic_openbim.design_pdf import DesignSheets
from steltic_openbim.assembly_legend import draw,pages,continuation_jobs


def test_overflow_creates_indexable_pages_with_every_part_and_note(tmp_path):
    scene=dict(id='CD320',sheet='C320',parts=[dict(id=f'P{i:03}',kind='plate',basis='S',description=f'Source plate specification TOKEN{i:03}') for i in range(100)],
               welds=[],notes=['LAST_SOURCE_NOTE '+' '.join(f'NOTEWORD{i:03}' for i in range(500))])
    sh=DesignSheets({},dict(revision=1,source_model_sha256='a'*64),tmp_path,dict(title='Legend test',profiles=[],members=[]))
    assert len(pages(sh,scene))>=3
    jobs=list(continuation_jobs(sh,scene));numbers=[n for n,_,_ in jobs]
    assert len(set(numbers))==len(numbers) and numbers[0]=='C320N01'
    sh.start('C320','Connection');draw(sh,scene)
    for number,title,fn in jobs:sh.start(number,title);fn()
    sh.c.save()
    pdf=PdfReader(tmp_path/'drawings.pdf');text='\n'.join(p.extract_text() for p in pdf.pages)
    assert len(pdf.pages)==1+len(jobs)
    assert all(text.count(f'TOKEN{i:03}')==1 for i in range(100))
    assert all(text.count(f'NOTEWORD{i:03}')==1 for i in range(500)) and 'LAST_SOURCE_NOTE' in text
    assert all(r['number']==n for r,n in zip(sh.rows,['C320']+numbers))
