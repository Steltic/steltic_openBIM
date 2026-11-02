"""Read the exported XLSX package and reconcile it with the audit JSON."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('workbook',type=Path)
parser.add_argument('--data',type=Path,default=Path(__file__).parent/'data')
args=parser.parse_args()
read=lambda name:json.loads((args.data/name).read_text(encoding='utf-8'))
coverage=read('coverage_matrix.json');gaps=read('missing_data_register.json')
records=read('record_index.json');families=read('family_coverage.json')
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
errors=[]
def check(ok,message):
    if not ok:errors.append(message)
with ZipFile(args.workbook) as z:
    check(z.testzip() is None,'XLSX ZIP integrity')
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns):
            strings.append(''.join(t.text or '' for t in si.findall('.//m:t',ns)))
    workbook=ET.fromstring(z.read('xl/workbook.xml'))
    names=[s.get('name') for s in workbook.findall('m:sheets/m:sheet',ns)]
    check(names==['Overview','Buildings','Missing data','Families','Connections','CFS assemblies'],'Workbook sheets')
    sheets={name:ET.fromstring(z.read('xl/worksheets/sheet'+str(i+1)+'.xml')) for i,name in enumerate(names)}
    cells={}
    formula_count=0
    for name,sheet in sheets.items():
        cells[name]={}
        for c in sheet.findall('.//m:sheetData/m:row/m:c',ns):
            check(c.get('t')!='e',name+' Excel error at '+c.get('r'))
            value=c.find('m:v',ns)
            if c.get('t')=='s':value=strings[int(value.text)]
            elif c.get('t')=='inlineStr':value=''.join(t.text or '' for t in c.findall('.//m:t',ns))
            else:value=value.text if value is not None else ''
            cells[name][c.get('r')]=value
            if c.find('m:f',ns) is not None:
                formula_count+=1
                check(value!='',name+' empty formula cache '+c.get('r'))
    for address,value in {'B6':36,'B7':25,'B8':61,'C6':1746,'C7':332,'C8':2078,'D6':0,'D7':2785,'D8':2785,'B20':len(gaps)}.items():
        check(float(cells['Overview'][address])==value,'Summary cache '+address)
    for row,g in enumerate(gaps,7):
        check(cells['Missing data']['A'+str(row)]==g['id'],'Register ID row '+str(row))
        check(int(cells['Missing data']['I'+str(row)])==len(g['affected_records']),'Affected count '+g['id'])
        check(cells['Missing data']['K'+str(row)]==g['review_status'],'Initial review status '+g['id'])
    for name,rows in [('Connections',[r for r in records if r['table']=='connections']),('CFS assemblies',[r for r in records if r['table']!='connections'])]:
        for row,r in enumerate(rows,7):
            check(cells[name]['K'+str(row)]==r['key'],name+' stable key '+str(row))
            check(cells[name]['D'+str(row)]==r['scope'],name+' scope '+r['key'])
            check(cells[name]['J'+str(row)]==r['source'],name+' source '+r['key'])
    for row,c in enumerate(coverage,7):
        check(cells['Buildings']['A'+str(row)]==c['building'],'Building identity '+str(row))
        check(int(cells['Buildings']['J'+str(row)])==c['connection_records'],'Building count '+c['building'])
    tables=[ET.fromstring(z.read(name)) for name in z.namelist() if name.startswith('xl/tables/table') and name.endswith('.xml')]
    expected_ranges={'A6:P'+str(6+len(coverage)),'A6:N'+str(6+len(gaps)),'A6:F'+str(6+len(families)),'A6:K2084','A6:K2791'}
    check({t.get('ref') for t in tables}==expected_ranges,'Native table ranges')
    check(all(t.find('m:autoFilter',ns) is not None for t in tables),'Native filters')
    for name in names[1:]:
        pane=sheets[name].find('.//m:pane',ns)
        check(pane is not None and pane.get('ySplit')=='6' and pane.get('xSplit')==('2' if name=='Missing data' else '1'),name+' frozen identifiers/headers')
    dv=sheets['Missing data'].find('m:dataValidations/m:dataValidation',ns)
    check(dv is not None and dv.get('sqref')=='K7:K'+str(6+len(gaps)) and dv.get('type')=='list','Review status dropdown')
    check(len(sheets['Missing data'].findall('m:conditionalFormatting',ns))>0,'Register category highlighting')
result={'status':'PASS' if not errors else 'FAIL','workbook':args.workbook.name,
        'sha256':hashlib.sha256(args.workbook.read_bytes()).hexdigest(),'sheets':names,
        'native_tables':len(tables),'formula_caches_checked':formula_count,
        'building_rows_verified':len(coverage),'register_rows_verified':len(gaps),'record_rows_verified':len(records),
        'checks':['ZIP integrity','Sheet and native table ranges','No Excel error cells','Cached totals','All stable IDs and source locators','Scope boundaries','Frozen headers and IDs','Review status dropdown','Category highlighting'],
        'errors':errors}
(args.data/'workbook_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
raise SystemExit(bool(errors))
