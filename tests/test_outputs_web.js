'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(tag='div'){this.tag=tag;this.dataset={};this.children=[];this.attrs={};this.listeners={};this.value='';this.style={setProperty(){}};this.classList={toggle(){},remove(){},add(){},contains(){return false;}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attrs[k]=v;}
 getAttribute(k){return this.attrs[k];}
 removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,v){this.listeners[k]=v;}
 focus(){this.focused=true;document.activeElement=this;}
 contains(node){return this===node||this.children.some(child=>child.contains?.(node));}
 get options(){return this.children;}
 get lastElementChild(){return this.children.at(-1);}
 get firstChild(){return this.children[0];}
}
const ids=new Map();
const document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){if(!ids.has(id))throw Error('Missing real HTML id: '+id);return ids.get(id);},createElement(tag){return new Node(tag);},createTextNode(text){const n=new Node();n.textContent=text;return n;},querySelectorAll(){return [];}};
for(const match of fs.readFileSync('web/index.html','utf8').matchAll(/\bid="([^"]+)"/g))ids.set(match[1],new Node());
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:''},window:{addEventListener(){}},setInterval(){},AbortSignal:{timeout(){}},fetch:async()=>{throw Error('offline');},URL,console};
vm.createContext(context);
for(const f of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+f,'utf8'),context);


context.assert=assert;
vm.runInContext(`
const main={id:'artifact',title:'<script>title.mp4</script>',filename:'registered.mp4',kind:'video',designation:'draft',delivery:[]};
const state={tasks:[{id:'task',name:'Task',project:'Synthetic'}],runs:[],activity:[],agents:[],agent_assignments:[],output_summaries:{task:{count:1200,kinds:[{kind:'video',count:1200}],main}},artifacts:[{id:'artifact',task_id:'task'}]};
for(const lang of ['zh','en']){
 language=lang;const text=outputCountText(outputSummary(state,'task'));assert(text.includes('1200'));assert(!outputMainText(state.output_summaries.task).includes(lang==='en'?'Acceptance':'验收'));
 const card=taskCard(state.tasks[0],null,state);assert.equal(card.tag,'article');
 const actions=card.children.find(node=>node.className==='task-card-actions');assert.equal(actions.children.length,2);assert(actions.children.every(node=>node.tag==='button'));
 let selected=[],tabs=[];selectTask=task=>selected.push(task.id);setDetailTab=tab=>tabs.push(tab);
 let stopped=false;actions.children[1].listeners.click({stopPropagation(){stopped=true;}});assert(stopped);assert.deepEqual(selected,['task']);assert.deepEqual(tabs,['files']);assert.equal(document.activeElement,$('tab-files'));
 renderOutputBar(state,'task');const button=$('output-summary-files');button.focus();renderOutputBar(state,'task');assert.equal(document.activeElement,button);assert($('output-summary-count').textContent.includes('1200'));assert.equal($('output-summary-main').title,'registered.mp4');
 assert($('output-summary-note').textContent.includes(lang==='en'?'native cloud desktop':'云桌面原生'));
 renderOutputBar({output_summaries:{}},'task');assert($('output-summary-count').textContent.includes(lang==='en'?'No registered':'尚无'));assert.equal($('output-summary-main').textContent,'');
 const empty=taskCard(state.tasks[0],null,{...state,output_summaries:{}});assert.equal(empty.children.find(node=>node.className==='task-card-actions').children.length,1);
}
`,context);
const source=fs.readFileSync('web/app.js','utf8'),html=fs.readFileSync('web/index.html','utf8'),css=fs.readFileSync('web/style.css','utf8');
assert(html.includes('id="output-summary-files" type="button"'));
assert(css.includes('.output-summary-bar{grid-template-columns:minmax(0,1fr)}'));
assert(!source.includes('file://'));
console.log('Outputs UI: full counts, draft/delivery distinction, independent semantic buttons, exact Files jump, stable refresh focus, literal titles, cloud-only folder note, zero outputs and narrow wrapping passed');
