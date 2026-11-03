window.StelticIFC={async mount(root,project,mode){
 'use strict';root._ifcViewer?.dispose();const token={};root._ifcToken=token;
 const base=`/api/project/${encodeURIComponent(project)}/ifc`;let state=null;
 const el=(tag,attrs={},...kids)=>{const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k.startsWith('on'))n[k]=v;else n.setAttribute(k,v)}for(const k of kids.flat())if(k!=null)n.append(k.nodeType?k:document.createTextNode(String(k)));return n};
 const box=el('div',{class:'ifc-ui'}),message=el('p',{'aria-live':'polite',class:'ifc-status'});root.replaceChildren(box,message);
 async function api(path,options={}){const r=await fetch(path,options);let data;try{data=await r.json()}catch(e){throw Error('The module did not return a readable response')}if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'The request could not be processed');return data}
 const post=(path,body)=>api(base+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 function error(e){message.textContent=e.message;message.className='ifc-status ifc-error'}
 async function run(button,work){button.disabled=true;message.className='ifc-status';message.textContent='Processing IFC… Large models may take a few minutes.';try{await work();await refresh();message.textContent='Saved.'}catch(e){error(e)}finally{button.disabled=false}}
 async function refresh(){state=await api(base);if(root._ifcToken!==token)return;root._ifcViewer?.dispose();box.replaceChildren();if(mode==='import')await renderImport();else renderExport()}
 function card(...children){return el('section',{class:'ifc-card'},...children)}
 function report(checks){return el('ul',{},...(checks.length?checks:[{title:'No listed model-data findings',count:0}]).map(f=>el('li',{},`${f.title}: ${f.count}`)))}
 function importGuard(){return {revision:state.imported.revision,source_sha256:state.imported.source_sha256}}
 async function renderImport(){
   box.append(el('h2',{},'IFC import'),el('p',{},'Upload an IFC, review the questions, then build a 3D model for geometry and model-data checking. The original file is retained. This step does not run structural analysis.'));
   const file=el('input',{type:'file',accept:'.ifc','aria-label':'IFC file'}),upload=el('button',{class:'primary',onclick:()=>run(upload,async()=>{if(!file.files[0])throw Error('Choose an IFC file');const data=new FormData();data.append('file',file.files[0]);if(state.imported)data.append('revision',state.imported.revision);await api(base+'/import',{method:'POST',body:data})})},state.imported?'Import a new IFC revision':'Inspect IFC');
   box.append(card(el('h3',{},'1. Choose a model'),el('p',{class:'ifc-note'},'IFC2X3, IFC4 or IFC4X3 · uncompressed .ifc · up to 100 MB and 20,000 products. From Revit, use File → Export → IFC.'),el('div',{class:'ifc-row'},file,upload)));
   const s=state.imported;if(!s)return;const meta=s.inspection;
   const scope=el('select',{'aria-label':'Review scope'},el('option',{value:'all'},'All objects, including architectural context'),el('option',{value:'structural'},'Structural IFC classes only'));scope.value=s.options.scope||'all';
   const unit=el('select',{'aria-label':'Review length units'});if(!meta.units.known)unit.append(el('option',{value:''},'Choose units — not declared in this IFC'));for(const[v,label]of [['auto','Use IFC units: '+meta.units.name],['m','Interpret coordinates as metres'],['mm','Interpret coordinates as millimetres'],['ft','Interpret coordinates as feet'],['in','Interpret coordinates as inches']])unit.append(el('option',{value:v},label));unit.value=s.options.units||(meta.units.known?'auto':'');
   const note=el('textarea',{'aria-label':'IFC review information',placeholder:'Scope, missing data, source or coordination notes'});note.value=s.options.note||'';
   const build=el('button',{class:'primary',onclick:()=>run(build,()=>post('/build',{...importGuard(),options:{scope:scope.value,units:unit.value,note:note.value}}))},'Save answers and build review model');
   box.append(card(el('h3',{},'2. Review the questions'),el('p',{},`${s.filename} · ${meta.schema} · revision ${s.revision} · ${meta.counts.products.toLocaleString()} products · ${meta.storeys.length} storeys`),
     el('label',{},'Which objects should the review include?',scope),el('label',{},'Which units should the review use?',unit),el('p',{class:'ifc-note'},'Default proposals retain all objects and the IFC units. A unit override reinterprets the source numbers; it does not move or repair georeferencing.'),
     el('h4',{},'Missing information proposal'),el('p',{},'Keep supplied geometry and show unknown materials, sections and connection behaviour as TBD. No design values are invented.'),note,report(meta.findings),build));
   if(s.status==='built'||s.status==='reviewed'){
     const model=await api(base+'/import/file/model.json?revision='+s.directory);if(root._ifcToken!==token)return;
     const view=el('div'),counts=model.counts;
     box.append(card(el('h3',{},'3. Check the model'),el('p',{},`${counts.displayed.toLocaleString()} of ${counts.selected.toLocaleString()} selected objects displayed · ${counts.unrendered} could not be displayed · ${counts.excluded_by_scope} outside selected scope`),
       el('p',{class:'ifc-note'},model.coordinate_basis),view,el('h4',{},'Source data and geometry findings'),report(model.checks),
       model.unrendered.length?el('details',{},el('summary',{},'Objects that could not be displayed'),el('ul',{},model.unrendered.map(o=>el('li',{},`${o.name||o.guid}: ${o.reason}`)))):null,
       el('a',{href:base+'/import/file/model.json?revision='+s.directory,target:'_blank'},'Download review model and findings')));
     root._ifcViewer=window.StelticIFCViewer(view,model);
     const reviewNote=el('textarea',{'aria-label':'Model review conclusion',placeholder:'Record your model-review notes'});reviewNote.value=s.review_note||'';
     const check=el('input',{type:'checkbox','aria-label':'Confirm geometry and data review'}),confirm=el('button',{onclick:()=>run(confirm,async()=>{if(!check.checked)throw Error('Confirm you reviewed the geometry and data findings');await post('/review',{...importGuard(),confirm:true,note:reviewNote.value})})},'Record model review');
     box.append(card(el('h3',{},s.status==='reviewed'?'Model review recorded':'Record your review'),reviewNote,el('label',{},check,' I have reviewed the geometry and data findings. This is not a structural design approval.'),confirm));
   }
   box.append(el('details',{},el('summary',{},'IFC import history'),el('ul',{},state.history.map(r=>el('li',{},`Revision ${r.revision} · ${r.filename} · ${r.status}`)))));
 }
 function renderExport(){
   box.append(el('h2',{},'IFC export'),el('p',{},'Generate an IFC from the current Steltic drawing model, or retain an imported IFC with your recorded review information. Revit can open or link the IFC; it is not a native Revit family library.'));
   const source=el('select',{'aria-label':'IFC export source'});if(state.drawing)source.append(el('option',{value:'steltic'},`Steltic drawing model · revision ${state.drawing.revision}`));if(['built','reviewed'].includes(state.imported?.status))source.append(el('option',{value:'ifc_import'},`Imported IFC · revision ${state.imported.revision}`));
   if(source.options.length){const info=el('p'),update=()=>{info.textContent=source.value==='steltic'?(state.drawing.representation==='captured_source_worklines'?`This drawing model contains ${state.drawing.counts.drawn_occurrences||''} captured reference axes. The IFC will identify them as axes; missing physical member set-out and connection parts remain TBD.`:'Exports the geometry held in the drawing revision: member surfaces, panel surfaces and located connection parts. Unlocated assemblies remain metadata. Unconfirmed openings are not cut into the IFC.'):'Retains every original IFC object, including those outside the preview selection. Adds review notes and applies an explicitly selected length-unit interpretation.'};source.onchange=update;update();
     const generate=el('button',{class:'primary',onclick:()=>run(generate,()=>{const s=source.value==='steltic'?state.drawing:state.imported;return post('/export',{source:source.value,revision:s.revision,source_sha256:s.source_sha256})})},'Generate IFC');box.append(card(el('h3',{},'Export source'),source,info,generate));
   }else box.append(card('Import a Steltic package or build an IFC review model first.'));
   for(const r of state.exports){const url=base+'/export/'+r.key;box.append(card(el('h3',{},r.source==='steltic'?'Steltic model export':'Imported IFC with review information'),el('p',{},`${r.schema} · source revision ${r.drawing_revision||r.import_revision} · ${r.schema_errors.length?'Schema findings: '+r.schema_errors.length:'Schema validation passed'}`),
     el('p',{},Object.entries(r.counts).map(([k,v])=>k.replaceAll('_',' ')+': '+v.toLocaleString()).join(' · ')),
     el('div',{class:'ifc-row'},el('a',{href:url+'/model.ifc',class:'ifc-download'},'Download IFC'),el('a',{href:url+'/report.json',target:'_blank'},'Export report')),
     el('ul',{},r.limits.map(t=>el('li',{},t))),r.warnings.length?el('p',{},`${r.warnings.length} geometry warnings — see export report.`):null));}
 }
 try{await refresh()}catch(e){error(e)}
}};
