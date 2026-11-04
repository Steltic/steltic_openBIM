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
 function report(checks){return el('ul',{},...(checks.length?checks:[{title:'No listed model-data findings',count:0}]).map(f=>el('li',{},(f.title||f.message||f.code)+(f.count==null?'':': '+f.count))))}
 function importGuard(){return {revision:state.imported.revision,source_sha256:state.imported.source_sha256}}
 async function renderImport(){
   box.append(el('h2',{},'IFC import'),el('p',{},'Upload an IFC, review the questions, then build a 3D model for geometry and model-data checking. The original file is retained. This step does not run structural analysis.'));
   const file=el('input',{type:'file',accept:'.ifc','aria-label':'IFC file'}),upload=el('button',{class:'primary',onclick:()=>run(upload,async()=>{if(!file.files[0])throw Error('Choose an IFC file');const data=new FormData();data.append('file',file.files[0]);if(state.imported)data.append('revision',state.imported.revision);await api(base+'/import',{method:'POST',body:data})})},state.imported?'Import a new IFC revision':'Inspect IFC');
   box.append(card(el('h3',{},'1. Choose a model'),el('p',{class:'ifc-note'},'IFC2X3, IFC4 or IFC4X3 · uncompressed .ifc · up to 100 MB and 100,000 products. From Revit, use File → Export → IFC.'),el('div',{class:'ifc-row'},file,upload)));
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
     const target=el('select',{'aria-label':'Design module'},el('option',{value:'HR'},'HR Steel'),el('option',{value:'CFS'},'CFS Steel'));target.value=state.target_module||'HR';
     const brief=el('textarea',{'aria-label':'Design job brief',rows:'10'});brief.value=state.design_brief||state.hr_brief||'';
     const next=el('p',{class:'ifc-note'}),prepare=el('button',{class:'primary',onclick:()=>run(prepare,()=>post('/handoff',{...importGuard(),target_module:target.value,brief:brief.value}))});
     const updateTarget=()=>{prepare.textContent='Prepare '+target.value+' design brief';brief.placeholder='Building use, loads, seismic and wind criteria, structural system, support assumptions and project requirements. '+target.value+' will size and check the structure.';next.textContent='Download the prepared brief and load it into '+target.value+' Steel → Design using the same project name. Run '+target.value+', then use IFC export for the return model. Steltic import can generate drawings when needed.'};target.onchange=updateTarget;updateTarget();
     box.append(card(el('h3',{},'4. Continue to structural design'),el('p',{},'Choose HR or CFS and add your engineering brief. The handoff includes IFC grids, storeys, floor/roof surfaces, wall geometry and opening locations with source references. It does not infer a structural design.'),el('label',{},'Design module',target),brief,prepare,next));
     for(const h of state.handoffs||[]){const url=base+'/handoff/'+h.key,t=h.target_module||'HR';box.append(card(el('h4',{},t+' handoff · IFC revision '+h.import_revision),el('a',{href:url+'/'+(h.brief_filename||'hr_brief.txt'),class:'ifc-download'},'Download '+t+' design brief'),el('a',{href:url+'/architectural_geometry.json'},'Download architectural geometry'),h.import_revision!==s.revision?el('p',{},'Prepared from an earlier IFC review revision. Prepare a new brief if the source or answers changed.'):null,el('ul',{},h.warnings.map(w=>el('li',{},w)))))}
   }
   box.append(el('details',{},el('summary',{},'IFC import history'),el('ul',{},state.history.map(r=>el('li',{},`Revision ${r.revision} · ${r.filename} · ${r.status}`)))));
 }
 function renderExport(){
   box.append(el('h2',{},'IFC export'),el('p',{},'Export an HR/CFS job directly, use a drawing revision, or retain an imported IFC with review information. Revit can open or link the IFC; it is not a native Revit family library.'));
   const jobs=state.sources||[];
   if(jobs.length){
     const select=el('select',{'aria-label':'HR/CFS job for IFC export'},...jobs.map((s,i)=>el('option',{value:i},s.module+' / '+s.job)));
     const selected=jobs.findIndex(s=>s.job===(state.structural?.source_job||project)&&(!state.structural||s.module===state.structural.source_module));if(selected>=0)select.value=selected;
     const load=el('button',{class:'primary',onclick:()=>run(load,()=>post('/structural/import',{...jobs[Number(select.value)],revision:state.structural?.revision}))},'Load job for IFC export');
     box.append(card(el('h3',{},'HR/CFS physical source'),el('p',{},'Load the job’s current physical export. This saves a source snapshot without generating drawings. Reload after HR/CFS updates the job; earlier exports are retained.'),el('div',{class:'ifc-row'},select,load)));
   }
   if(state.structural){const s=state.structural,requests=s.requests||[];box.append(card(el('h3',{},'Source completeness · '+s.source_module+' / '+s.source_job),
     el('p',{},s.source_readiness==='ready'?'No missing data reported by the current package checks. Architectural agreement and design approval are separate checks.':'Physical information is still required. You can export the supplied geometry provisionally; unresolved information remains in the IFC.'),
     s.source_evidence?.source_freshness_checked?el('p',{class:'ifc-note'},s.source_evidence.tracked_files+' recorded source files verified when this revision was loaded.'):el('p',{class:'ifc-note'},'Source-file freshness was not verified for this saved revision. Reload the job to check its recorded files.'),
     requests.length?el('details',{},el('summary',{},requests.length+' information requests'),el('ul',{},requests.map(r=>el('li',{},el('strong',{},r.question||r.id),el('p',{},r.proposal))))):null));}
   const source=el('select',{'aria-label':'IFC export source'});
   if(state.structural)source.append(el('option',{value:'structural'},`${state.structural.source_module} / ${state.structural.source_job} · physical revision ${state.structural.revision}`));
   if(state.drawing)source.append(el('option',{value:'steltic'},`Steltic drawing model · revision ${state.drawing.revision}`));
   if(['built','reviewed'].includes(state.imported?.status))source.append(el('option',{value:'ifc_import'},`Imported IFC · revision ${state.imported.revision}`));
   const selectedState=()=>source.value==='structural'?state.structural:source.value==='steltic'?state.drawing:state.imported;
   if(source.options.length){const info=el('p'),update=()=>{const s=selectedState();info.textContent=source.value==='ifc_import'?'Retains every original IFC object, including those outside the preview selection. Adds review notes and applies an explicitly selected length-unit interpretation.':s.representation==='captured_source_worklines'?'This source contains captured reference axes. The IFC identifies them as axes; physical member set-out and connection parts remain TBD.':'Exports supplied member surfaces, panel surfaces and located connection parts. Unlocated assemblies remain metadata. Valid coplanar openings cut their explicitly declared host panels; opening boundaries are also retained as references. Members are not cut.'};source.onchange=update;update();
     const generate=el('button',{class:'primary',onclick:()=>run(generate,()=>{const s=selectedState();return post('/export',{source:source.value,revision:s.revision,source_sha256:s.source_sha256})})},'Generate IFC');box.append(card(el('h3',{},'Export source'),source,info,generate));
   }else box.append(card('Load an HR/CFS job above, import a Steltic drawing package, or build an IFC review model first.'));
   for(const r of state.exports){const url=base+'/export/'+r.key;box.append(card(el('h3',{},r.source==='structural'?r.source_module+' / '+r.source_job+' physical export':r.source==='steltic'?'Steltic model export':'Imported IFC with review information'),el('p',{},`${r.schema} · source revision ${r.physical_revision||r.drawing_revision||r.import_revision} · ${r.schema_errors.length?'Schema findings: '+r.schema_errors.length:'Schema validation passed'}`),
     el('p',{},Object.entries(r.counts).map(([k,v])=>k.replaceAll('_',' ')+': '+v.toLocaleString()).join(' · ')),
     el('div',{class:'ifc-row'},el('a',{href:url+'/model.ifc',class:'ifc-download'},'Download IFC'),el('a',{href:url+'/report.json',target:'_blank'},'Export report')),
     r.source_validation?el('div',{},el('h4',{},'Source completeness'),el('p',{},r.source_validation.status==='ready'?'No missing data reported by the current package checks.':'Information required: this IFC is provisional even though its file schema is valid.'),report(r.source_validation.findings)):null,
     r.physical_checks?el('div',{},el('h4',{},'Physical source checks'),el('p',{},r.physical_checks.findings.length?'Source-model review required. The IFC retains the supplied geometry.':'No findings in the limited source screens. This does not establish architectural agreement or design approval.'),el('ul',{},r.physical_checks.findings.map(f=>el('li',{},`${f.title}: ${f.count}`)))):null,
     el('ul',{},r.limits.map(t=>el('li',{},t))),r.warnings.length?el('p',{},`${r.warnings.length} geometry warnings — see export report.`):null));}
 }
 try{await refresh()}catch(e){error(e)}
}};
