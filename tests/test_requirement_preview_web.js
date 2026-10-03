'use strict';
// Synthetic DOM regression checks only: no browser, account, network or runtime DATA.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let document;
const walk=node=>[node,...node.children.flatMap(walk)];
function matches(node,selector){
  const className=selector.match(/\.([\w-]+)/)?.[1];
  if(className&&!String(node.className||'').split(' ').includes(className))return false;
  const tag=selector.match(/^[a-z]+/)?.[0];
  if(tag&&node.tag!==tag)return false;
  const attr=selector.match(/\[([^\]]+)\]/)?.[1];
  return !attr||node.getAttribute(attr)!=null;
}
class Node {
  constructor(tag='div'){
    this.tag=tag;this.tagName=tag.toUpperCase();this.dataset={};this.children=[];this.attrs={};this.listeners={};this.value='';this.scrollTop=0;this.top=0;this.height=20;
    this.style={setProperty(){}};this.classes=new Set();this.classList={toggle:(k,on)=>{if(on===undefined)on=!this.classes.has(k);if(on)this.classes.add(k);else this.classes.delete(k);},remove:k=>this.classes.delete(k),add:k=>this.classes.add(k),contains:k=>this.classes.has(k)};
  }
  append(...items){for(const node of items){node.parentElement=this;this.children.push(node);}}
  replaceChildren(...items){for(const child of this.children)child.parentElement=null;this.children=[];this.append(...items);}
  replaceWith(node){const parent=this.parentElement;if(parent){parent.children[parent.children.indexOf(this)]=node;node.parentElement=parent;this.parentElement=null;}}
  setAttribute(key,value){this.attrs[key]=value;if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())]=value;}
  getAttribute(key){if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())];return this.attrs[key];}
  removeAttribute(key){delete this.attrs[key];}
  addEventListener(key,handler){this.listeners[key]=handler;}
  focus(){document.activeElement=this;}
  contains(node){return walk(this).includes(node);}
  querySelectorAll(selector){return walk(this).slice(1).filter(node=>matches(node,selector));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){for(let node=this;node;node=node.parentElement)if(matches(node,selector))return node;return null;}
  getBoundingClientRect(){return {top:this.top,bottom:this.top+this.height};}
  get options(){return this.children;}
  get firstChild(){return this.children[0];}
  get lastElementChild(){return this.children.at(-1);}
}
require('./dom_patch_fixture.js')(Node,()=>document);
const ids=new Map();
for(const match of fs.readFileSync('web/index.html','utf8').matchAll(/\bid="([^"]+)"/g)){const node=new Node();node.id=match[1];ids.set(match[1],node);}
document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){assert(ids.has(id),'Real HTML ID required: '+id);return ids.get(id);},createElement:tag=>new Node(tag),createTextNode:text=>Object.assign(new Node('#text'),{textContent:text}),querySelectorAll(selector){return [...ids.values()].flatMap(walk).filter(node=>matches(node,selector));}};
const window={scrollY:420,addEventListener(){},scrollTo(options,y){this.scrollY=typeof options==='object'?options.top:y;}};
const pending=[];
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:'#conversations'},window,setInterval(){},AbortSignal:{timeout(){}},fetch:(url)=>new Promise((resolve,reject)=>pending.push({url,resolve,reject})),URL,console,assert};
vm.createContext(context);
for(const file of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);

context.pending=pending;context.walk=walk;
const run=script=>vm.runInContext(script,context);
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve();};

run(`
const q={id:'q',task_id:'goal',summary:'Preview original requirement',status:'received',observed_at:2,owner:{status:'assignment_unconfirmed'},history:[],status_history:[]};
const base={metrics:{sampled_at:2},tasks:[{id:'goal',name:'Goal',created:1}],runs:[{id:'r',task_id:'goal',status:'running',started:1}],activity:[{id:1,task_id:'goal',created:1,stage:'implementation',message:'History remains mounted'}],events:[],requirements:[q],requirement_counters:{receipt:1},agents:[],schedules:[],software:[],rules:{groups:[]},about:{doctor:{}},artifacts:[]};
$('task-filter').value='goal';location.hash='#conversations';render(base);$('detail-scroll').scrollTop=145;
const originalCanvas=$('detail-scroll'),originalChildren=[...$('project-activity').children],originalFilter=$('task-filter').value,bookmark=$('requirement-bookmarks').children[0];bookmark.focus();
const beforeFetches=pending.length;openRequirement('q');
assert.equal(pending.length,beforeFetches,'Bookmark preview needs no extra HTTP page navigation');assert.equal($('requirement-preview').hidden,false);assert.equal($('detail-scroll'),originalCanvas);assert.equal(originalCanvas.scrollTop,145);assert.equal($('task-filter').value,originalFilter);assert.deepEqual([...$('project-activity').children],originalChildren);
assert(walk($('requirement-preview-content')).some(n=>n.textContent===q.summary));
const previewCard=$('requirement-preview-content').children[0],history=previewCard.children.find(n=>n.tag==='details');history.open=true;history.listeners.toggle();
render({...base,requirements:[{...q,status:'in_progress',current_step:'Verified current work'}],requirement_counters:{receipt:1,state:2}},true);
assert.equal($('requirement-preview-content').children[0],previewCard);assert.equal(history.open,true);assert(walk(previewCard).some(n=>String(n.textContent).includes('Verified current work')));assert.equal(originalCanvas.scrollTop,145);
$('requirement-preview-close').listeners.click();assert.equal($('requirement-preview').hidden,true);assert.equal(document.activeElement,bookmark);assert.equal(originalCanvas.scrollTop,145);
openRequirement('q');$('requirement-preview').listeners.keydown({key:'Escape',preventDefault(){},stopPropagation(){}});assert.equal($('requirement-preview').hidden,true);assert.equal($('task-filter').value,'goal');
const oldQ={...q,id:'older-q',task_id:'outside-overview',summary:'Task outside the 500 overview window'};
const oldTask={id:'outside-overview',name:'Old precise task',created:0};
const overview={...base,requirements:[oldQ]};render(overview);
const precise={...overview,tasks:[...base.tasks,oldTask]};
globalThis.precisionPromise=openRequirement('older-q',{preserveView:false});
assert.equal(stateNavigationPending,true);assert(pending.at(-1).url==='/api/state?task_id=outside-overview');
`);
(async()=>{
 const exact=pending.findLast(item=>item.url==='/api/state?task_id=outside-overview');
 // The initial overview poll began before explicit navigation and must not overwrite it.
 const oldPoll=pending.find(item=>item.url==='/api/state');oldPoll.resolve({ok:true,json:async()=>run('base')});await flush();
 exact.resolve({ok:true,json:async()=>run('precise')});await context.precisionPromise;await flush();
 run(`assert.equal($('task-filter').value,'outside-overview');assert.equal($('requirement-preview').hidden,false);assert.equal(requirementPreview.id,'older-q');assert(walk($('requirement-preview-content')).some(n=>n.textContent==='Task outside the 500 overview window'));assert.equal(stateNavigationPending,false);`);
 console.log('Requirement preview: no task/scroll navigation, retained facts/history/focus, precise old-task load and stale overview-response suppression passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
