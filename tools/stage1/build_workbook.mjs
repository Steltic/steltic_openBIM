import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const here=path.dirname(fileURLToPath(import.meta.url));
const input=process.argv[3]||path.join(here,'data','workbook_data.json');
const scratch=path.dirname(path.dirname(input));
const data=JSON.parse(await fs.readFile(input,'utf8'));
const output=process.argv[2];
if(!output)throw new Error('Pass the output XLSX path.');
const wb=Workbook.create();
const names=['Overview','Buildings','Missing data','Families','Connections','CFS assemblies'];
const sheets=Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const blue='#23364D',orange='#C46B23',ink='#172B3A',muted='#5C6874';
const safe=v=>typeof v==='string' && /^[=+@-]/.test(v) ? "'"+v : v;
const clip=(v,n=330)=>{const s=String(v??'').replace(/\s+/g,' ').trim();return s.length>n?s.slice(0,n-3)+'...':s;};
const col=n=>{let s='';for(let x=n+1;x;x=Math.floor((x-1)/26))s=String.fromCharCode(65+(x-1)%26)+s;return s;};

function basic(sheet,lastcol,lastrow){
  sheet.showGridLines=false;
  sheet.getRangeByIndexes(0,0,lastrow,lastcol).format.font={name:'Arial',size:10,color:ink};
  sheet.getRangeByIndexes(0,0,lastrow,lastcol).format.verticalAlignment='top';
  sheet.getRangeByIndexes(0,0,lastrow,lastcol).format.rowHeight=22;
  sheet.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:blue};
}
function table(name,title,note,headers,rows,widths,tableName){
  const s=sheets[name]; const last=6+rows.length;
  basic(s,headers.length,last);
  s.getRange('A2').values=[[title]];
  s.getRange('A3').values=[[note]];
  s.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:muted};
  s.getRangeByIndexes(5,0,1,headers.length).values=[headers];
  if(rows.length)s.getRangeByIndexes(6,0,rows.length,headers.length).values=rows.map(r=>r.map(safe));
  widths.forEach((w,i)=>s.getRangeByIndexes(0,i,last,1).format.columnWidth=w);
  const body=s.getRangeByIndexes(6,0,rows.length,headers.length);
  body.format.wrapText=true;
  body.format.verticalAlignment='top';
  rows.forEach((r,i)=>{
    const lines=Math.max(...r.map((v,j)=>String(v??'').split('\n').reduce((n,x)=>n+Math.max(1,Math.ceil(x.length/Math.max(8,widths[j]-2))),0)));
    s.getRangeByIndexes(6+i,0,1,headers.length).format.rowHeight=Math.min(300,Math.max(36,lines*14+8));
  });
  const t=s.tables.add('A6:'+col(headers.length-1)+last,true,tableName);
  t.showFilterButton=true;
  s.getRangeByIndexes(5,0,1,headers.length).format={
    fill:blue,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},
    horizontalAlignment:'center',verticalAlignment:'center',wrapText:true,rowHeight:34,
  };
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(name==='Missing data'?2:1);
  return {s,last,rows};
}

const bdata=data.coverage.map(c=>[
  c.building,c.module,c.geometry_case,c.geometry_readiness,c.profile_readiness,
  c.connection_readiness,c.location_readiness,c.secondary_and_interfaces,c.source_provenance,
  c.connection_records,c.additional_records,c.follow_up_ids.length,c.next_action,c.source_building,c.source_folder,c.follow_up_ids.join(', ')
]);
const bt=table('Buildings','Coverage of all 61 supplied buildings','Counts are design records and schedules, not physical joint quantities.',
  ['Building','Module','Building / geometry','Geometry / layout','Profiles / materials','Connection detail data','Joint assignment','Secondary / interfaces','Source revision checks','Connection records','Supporting records','Follow-up items','Next action','Source building ID','Source folder under drawings','Register item IDs'],
  bdata,[13,10,39,39,37,34,36,39,34,13,13,13,65,65,76,50],'BuildingsTable');
bt.s.getRange('J7:L'+bt.last).setNumberFormat('#,##0');
bt.s.getRange('J7:L'+bt.last).format.horizontalAlignment='right';
bt.s.tabColor=blue;

const gdata=data.gaps.map(g=>[
  g.id,g.building,g.category,g.requirement,g.remaining,g.action,g.suggested_resolver,g.needed_for,
  g.affected_records.length,clip(g.source,480),g.review_status,g.resolution,g.available,clip(g.evidence,520)
]);
const gt=table('Missing data','Missing data and follow-up register','Verify geometry means check linked sources first. Full affected-record lists are in the accompanying JSON.',
  ['Item ID','Building','Category','Requirement','What remains unresolved','Next action','Suggested resolver','Needed for','Affected records','Source locator','Review status','Resolution / decision','Existing information','Evidence excerpt'],
  gdata,[19,12,24,39,65,70,33,38,12,72,18,65,65,78],'MissingDataTable');
gt.s.getRange('I7:I'+gt.last).setNumberFormat('#,##0');
gt.s.getRange('K7:K'+gt.last).dataValidation={rule:{type:'list',values:['Open','Resolved','Not applicable']}};
gt.s.getRange('K7:L'+gt.last).format.fill='#FFF3D6';
gt.s.getRange('C7:C'+gt.last).conditionalFormats.add('containsText',{text:'Supplement required',format:{fill:'#FCE1DA',font:{color:'#952C1B',bold:true}}});
gt.s.getRange('C7:C'+gt.last).conditionalFormats.add('containsText',{text:'Verify geometry',format:{fill:'#FFF1D2',font:{color:'#80550C'}}});
gt.s.getRange('C7:C'+gt.last).conditionalFormats.add('containsText',{text:'Supplier / delegated',format:{fill:'#F7E7D7',font:{color:'#7B4819'}}});
gt.s.tabColor=orange;

const ft=table('Families','Connection and assembly family coverage','Audit families organize review. Source descriptions remain authoritative; classifications are not template approvals.',
  ['Module','Source table','Audit family','Records','Buildings','Building IDs'],
  data.families.map(f=>[f.module,f.table,f.family,f.records,f.building_count,f.buildings.join(', ')]),
  [12,24,40,13,13,105],'FamiliesTable');
ft.s.getRange('D7:E'+ft.last).setNumberFormat('#,##0');

const rheaders=['Building','Source record ID','Audit family','Source scope','Description','Geometry data form','Location evidence','Numeric geometry fields','Geometry / specification excerpt','Source locator','Stable audit key'];
const rwidths=[12,47,37,25,65,34,65,56,105,73,95];
for(const [name,source] of [['Connections',data.records.filter(r=>r.table==='connections')],['CFS assemblies',data.records.filter(r=>r.table!=='connections')]]){
  table(name,name==='Connections'?'Connection design records':'CFS assembly, attachment and schedule records',
    'Excerpts are shortened for review. The record index JSON/CSV retains longer evidence and source locators.',
    rheaders,source.map(r=>[r.building,r.record_id,r.family,r.scope,clip(r.description,280),r.normalization,clip(r.location_evidence,320),
      clip(r.numeric_geometry_fields.join(', '),260),clip(r.geometry_evidence,650),r.source,r.key]),rwidths,
    name==='Connections'?'ConnectionsTable':'AssembliesTable');
}

const s=sheets.Overview;
basic(s,5,43);
s.getRange('A2').values=[['Stage 1 drawing-data audit']];
s.getRange('A3').values=[['2 November 2026. Dimensioned design drawings and IFC export.']];
s.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:muted};
for(const [i,w] of [34,15,27,27,55].entries())s.getRangeByIndexes(0,i,43,1).format.columnWidth=w;
s.getRange('A5:D5').values=[['Module','Buildings','Connection records','Supporting records']];
s.getRange('A6:A8').values=[['HR'],['CFS'],['Total']];
for(const row of [6,7]){
 s.getRange('B'+row+':D'+row).formulas=[[
  "=COUNTIFS('Buildings'!$B$7:$B$"+bt.last+',A'+row+')',
  "=SUMIFS('Buildings'!$J$7:$J$"+bt.last+",'Buildings'!$B$7:$B$"+bt.last+',A'+row+')',
  "=SUMIFS('Buildings'!$K$7:$K$"+bt.last+",'Buildings'!$B$7:$B$"+bt.last+',A'+row+')'
 ]];
}
s.getRange('B8:D8').formulas=[['=SUM(B6:B7)','=SUM(C6:C7)','=SUM(D6:D7)']];
s.getRange('B6:D8').setNumberFormat('#,##0');
s.getRange('A8:D8').format.font={name:'Arial',size:10,bold:true,color:ink};
s.getRange('A10').values=[['Follow-up categories']];
s.getRange('A10').format.font={name:'Arial',size:12,bold:true,color:blue};
s.getRange('A11:C11').values=[['Category','Items','Meaning']];
const order=['Supplement required','Supplier / delegated','Verify geometry','Resolve mapping','Extract existing','Scope decision','Verify source','Drawing decision'];
const meanings=[
  'A reviewed dimension or placement decision must be supplied.',
  'Obtain external data or preserve the stated scope boundary.',
  'Check linked sources before declaring information absent.',
  'Associate design records with actual members and joints.',
  'Normalize information that is already in the source.',
  'Choose how excluded or context-only parts are represented.',
  'Confirm provenance before replaying source configuration.',
  'Set sheet, scale, annotation and numbering conventions.'
];
order.forEach((cat,i)=>{
  const row=12+i;
  s.getRange('A'+row).values=[[cat]];
  s.getRange('B'+row).formulas=[["=COUNTIFS('Missing data'!$C$7:$C$"+gt.last+',A'+row+')']];
  s.getRange('C'+row).values=[[meanings[i]]];
});
s.getRange('A20:B20').values=[['Total follow-up items',null]];
s.getRange('B20').formulas=[['=SUM(B12:B19)']];
s.getRange('A20:B20').format.font={name:'Arial',size:10,bold:true,color:ink};
s.getRange('A22').values=[['First decisions']];
s.getRange('A22').format.font={name:'Arial',size:12,bold:true,color:blue};
s.getRange('A23:C23').values=[['Building / scope','Category','Decision']];
s.getRange('A24:C28').values=[
 ['HR-22','Supplement','Roof shear-plate vertical datum and beam-gap reference.'],
 ['CFS-1','Supplement','Roof/header clip dimensions and screw layout.'],
 ['BRB buildings','Supplier','Casing envelope and end-interface geometry.'],
 ['Podiums / existing work','Scope','Supply the external package or retain interface-only scope.'],
 ['CFS wall buildings','Layout','Recover segment positions; Ex8 already has explicit ranges.']
];
s.getRange('A30').values=[['How to read this audit']];
s.getRange('A30').format.font={name:'Arial',size:12,bold:true,color:blue};
const notes=[
 'All 61 recorded consistency results are PASS, and recorded package hashes match the supplied files.',
 'A source PASS is not a drawing-completeness check. Structural calculations were not rerun.',
 'The 2,078 connection records include typical groups and source exclusions, not 2,078 physical joints.',
 'CFS supporting records include walls, studs, materials and schedules; they can overlap physical systems.',
 'Verify geometry is a conservative screen. Missing keywords do not prove package-wide absence.',
 'Use the Buildings sheet for folder mapping, then the register and record index for source pointers.',
 'Review status and resolution cells are editable. Their contents do not change the audit snapshot.',
 'Fabrication details and architectural IFC import remain outside this first-release scope.',
 'Source code/configurations were read only. No job code, solver or design engine was executed.'
];
notes.forEach((n,i)=>s.getRange('A'+(31+i)).values=[[n]]);
s.getRange('A31:A39').format.font={name:'Arial',size:10,color:muted};
for(const rng of ['A5:D5','A11:C11','A23:C23']){
  s.getRange(rng).format={fill:blue,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',rowHeight:28};
}
s.getRange('B12:B20').setNumberFormat('#,##0');
s.getRange('A12:B12').format.fill='#FCE1DA';
s.tabColor=blue;

wb.recalculate();
const inspect=await wb.inspect({kind:'table',range:'Overview!A5:D20',include:'values,formulas',tableMaxRows:17,tableMaxCols:4,maxChars:4500});
console.log(inspect.ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:2000});
console.log(errors.ndjson);
await fs.mkdir(path.dirname(output),{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
console.log('SAVED '+output);
const previews=path.join(scratch,'previews');await fs.mkdir(previews,{recursive:true});
const views=[
 ['Overview','A1:E40'],['Buildings','A1:F10'],['Missing data','A1:F10'],
 ['Families','A1:F13'],['Connections','A1:F10'],['CFS assemblies','A1:F10'],
 ['Missing data','I6:N9']
];
for(let i=0;i<views.length;i++){
  const [sheetName,range]=views[i];
  const blob=await wb.render({sheetName,range,scale:1,format:'png'});
  const target=path.join(previews,String(i)+'-'+sheetName.replaceAll(' ','_')+'.png');
  await fs.writeFile(target,new Uint8Array(await blob.arrayBuffer()));
  console.log('PREVIEW '+target);
}
await fs.writeFile(path.join(scratch,'workbook_verification.txt'),inspect.ndjson+'\n'+errors.ndjson,'utf8');
console.log('COMPLETE');
