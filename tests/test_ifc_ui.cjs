// Render the actual export screen with both contract and preview finding shapes.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
 constructor(tag,text=''){this.tag=tag;this.nodeType=tag==='#text'?3:1;this.children=[];this.attributes={};this.text=text;}
 setAttribute(key,value){this.attributes[key]=value;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 get options(){return this.children.filter(n=>n.tag==='option');}
 set value(value){this.selected=value;}
 get value(){return this.selected??this.options[0]?.attributes.value;}
 get textContent(){return this.text+this.children.map(n=>n.textContent??String(n)).join(' ');}
 set textContent(value){this.text=value;this.children=[];}
}
test('provisional export displays contract messages, proposals and freshness evidence',async()=>{
 const state={sources:[],structural:{source_module:'HR',source_job:'Example',revision:1,source_readiness:'needs_input',source_evidence:{source_freshness_checked:true,tracked_files:4},requests:[{id:'missing_bolts',question:'Resolve the bolt quantity',proposal:'Retain the available assembly; bolt quantity TBD.'}]},exports:[{
  source:'structural',source_module:'HR',source_job:'Example',schema:'IFC4',physical_revision:1,key:'e-example',schema_errors:[],counts:{members:2},
  source_validation:{status:'needs_input',findings:[{code:'connection_fastener_quantity',message:'The selected connection needs four bolts',entity_ids:['C1']}]},
  physical_checks:{findings:[{title:'Overlapping parts',count:2}]},limits:[],warnings:[]
 }]};
 const context={window:{},document:{createElement:tag=>new Element(tag),createTextNode:text=>new Element('#text',text)},fetch:async()=>({ok:true,json:async()=>state})};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/steltic_openbim/ifc_ui.js'),'utf8'),context);
 const root=new Element('div');await context.window.StelticIFC.mount(root,'Example','export');
 const text=root.textContent;
 for(const expected of ['The selected connection needs four bolts','Overlapping parts: 2','bolt quantity TBD','4 recorded source files verified','this IFC is provisional'])assert.ok(text.includes(expected),expected);
 assert.ok(!text.includes('undefined'));
});

test('storey selection is sent to review build and its handoff scope is explicit',async()=>{
 const state={imported:{revision:1,source_sha256:'fixture',filename:'large.ifc',status:'questions',options:{},inspection:{schema:'IFC4',units:{known:true,name:'METRE'},counts:{products:3},storeys:[{id:'LEVEL-1',name:'Level 1'}],products:[{storey:'LEVEL-1'},{storey:'LEVEL-1'},{storey:null}],review_group_size:1,findings:[]}},history:[]};
 let submitted;
 const context={window:{},document:{createElement:tag=>new Element(tag),createTextNode:text=>new Element('#text',text)},fetch:async(url,options)=>{if(url.endsWith('/build'))submitted=JSON.parse(options.body);return {ok:true,json:async()=>state}}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/steltic_openbim/ifc_ui.js'),'utf8'),context);
 const root=new Element('div');await context.window.StelticIFC.mount(root,'Example','import');
 const nodes=[];function visit(node){nodes.push(node);for(const child of node.children||[])visit(child)}visit(root);
 const select=nodes.find(n=>n.attributes?.['aria-label']==='Review storey');
 assert.deepEqual(select.options.map(n=>n.attributes.value),['all','LEVEL-1','unassigned']);select.value='LEVEL-1';select.onchange();
 const group=nodes.find(n=>n.attributes?.['aria-label']==='Review group');assert.deepEqual(group.options.map(n=>n.attributes.value),['all','1','2']);group.value='2';
 assert.ok(root.textContent.includes('an HR/CFS design handoff uses the current review selection'));
 const button=nodes.find(n=>n.tag==='button'&&n.textContent==='Save answers and build review model');await button.onclick();
 assert.equal(submitted.options.storey,'LEVEL-1');assert.equal(submitted.options.group,2);assert.equal(submitted.revision,1);
});
