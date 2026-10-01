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
    this.style={setProperty(){}};this.classList={toggle(){},remove(){},add(){},contains(){return false;}};
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
const ids=new Map();
for(const match of fs.readFileSync('web/index.html','utf8').matchAll(/\bid="([^"]+)"/g)){const node=new Node();node.id=match[1];ids.set(match[1],node);}
document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){assert(ids.has(id),'Real HTML ID required: '+id);return ids.get(id);},createElement:tag=>new Node(tag),createTextNode:text=>Object.assign(new Node('#text'),{textContent:text}),querySelectorAll(selector){return [...ids.values()].flatMap(walk).filter(node=>matches(node,selector));}};
const window={scrollY:420,addEventListener(){},scrollTo(options,y){this.scrollY=typeof options==='object'?options.top:y;}};
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:'#conversations'},window,setInterval(){},AbortSignal:{timeout(){}},fetch:async()=>{throw Error('Synthetic offline');},URL,console,assert};
vm.createContext(context);
for(const file of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);
vm.runInContext(`
const flatten=node=>[node,...node.children.flatMap(flatten)],textOf=node=>flatten(node).map(n=>n.textContent||'').join(' ');
const task={id:'example',name:'Synthetic task',project:'Fixture',created:10};
const run={id:'run',task_id:task.id,status:'running',started:10,updated:50,note:'Original scope'};
const state={metrics:{sampled_at:1000,os:'Fixture',scope:'Fixture'},tasks:[task],runs:[run],latest_runs:[run],activity:[{id:1,task_id:task.id,created:40,stage:'implementation',state:'in_progress',message:'A checked milestone'}],events:[{id:1,run_id:'run',created:45,message:'Test started'}],artifacts:[],agents:[],agent_assignments:[],schedules:[],software:[],rules:{groups:[{id:'files',title:{en:'Files',zh:'文件'},items:[]}]},about:{doctor:{checks:[]}}};
render(state);$('task-filter').value=task.id;render(state);
$('detail-scroll').scrollTop=77;window.scrollY=420;render({...state,metrics:{...state.metrics,sampled_at:1005},runs:[{...run,updated:1005}]});
assert.equal($('detail-scroll').scrollTop,77);assert.equal(window.scrollY,420);assert.equal(detailTab,'timeline');
assert.equal($('project-activity').children.length,3,'Stage, run event and start note share one timeline');
const before=textOf($('task-list'));
render({...state,runs:[{...run,updated:2000}]});
assert.equal(textOf($('task-list')),before,'Heartbeat timestamp does not pretend work progressed');
for(const id of ['rules-content','about-doctor']){
  const details=flatten($(id)).find(n=>n.tag==='details');details.open=true;details.listeners.toggle();
}
const ruleSummary=flatten($('rules-content')).find(n=>n.tag==='summary');ruleSummary.focus();render(state);
assert(flatten($('rules-content')).find(n=>n.tag==='details').open);
assert(flatten($('about-doctor')).find(n=>n.tag==='details').open);
assert.equal(document.activeElement,flatten($('rules-content')).find(n=>n.tag==='summary'),'Expanded disclosure keeps keyboard focus on refresh');
const overview=$('page-overview'),activities=$('page-conversations');overview.dataset.page='overview';activities.dataset.page='conversations';overview.append($('active-work'));activities.append($('task-list'));
const activeButton=flatten($('task-list')).find(n=>n.dataset.focusKey==='task-details:example');activeButton.focus();render(state);
assert.equal(document.activeElement.closest('[data-page]').dataset.page,'conversations','Duplicate card actions retain focus within the visible page');
const selected=$('task-filter'),options=selected.children;selected.focus();render({...state,tasks:[{...task,name:'Changed title'}]});assert.equal(selected.children,options,'Focused select is not rebuilt during polling');
const measured={...state,progress_updates:[{id:'measured',run_id:'run',created:46,current_step:'Check six cases',result:'Case inventory verified',next_step:'Finish checks',evidence:'Six synthetic assertions',completed:0,total:6,unit:'checks'}]};
render(measured);assert(textOf($('task-list')).includes('Check six cases'));assert(textOf($('task-list')).includes('0 / 6 checks'));assert(textOf($('task-list')).includes('Next: Finish checks'));
const progress=flatten($('task-list')).find(n=>n.tag==='progress');assert.equal(progress.value,0);assert.equal(progress.max,6);
const steps=flatten($('task-list')).find(n=>n.className==='task-steps');let stopped=false;steps.listeners.click({stopPropagation(){stopped=true;}});assert(stopped,'Expanding step evidence does not navigate away');
// Restore the same visible item when newer records are inserted above it.
const scroller=$('detail-scroll'),anchor=element('div','Anchor','event');anchor.dataset.timelineKey='stable';anchor.top=96;anchor.height=30;scroller.top=100;scroller.replaceChildren(anchor);scroller.scrollTop=180;
const view=captureView(task.id);anchor.top=156;scroller.scrollTop=0;window.scrollY=0;restoreView(view,task.id);
assert.equal(scroller.scrollTop,240,'Visible timeline anchor survives insertion above viewport');assert.equal(window.scrollY,420);
const next=captureView('different');assert.equal(next.detail,0,'A new task starts at its own top');
const other={id:'different',name:'Another task',project:'Fixture',created:50};
lastState={...state,tasks:[task,other]};detailTab='files';$('task-filter').value=task.id;$('detail-scroll').scrollTop=90;selectTask(other);setDetailTab('files');assert.equal($('detail-scroll').scrollTop,0,'New task does not inherit the previous file-tab offset');
// Card, status filters and detail header use one current-run selection.
const ui={...run,id:'ui',status:'running',note:'UI implementation',started:10};
const decision={...run,id:'decision',status:'waiting_user',lifecycle_reason:'Scope confirmation',note:'Approve the scope',started:20};
const backup={...run,id:'backup',status:'succeeded',note:'Backup completed',started:30};
const parallelState={...state,runs:[backup],latest_runs:[backup],current_runs:[ui],open_runs:[ui,decision],agents:[{id:'active',name:'Current contributor',status:'running',observed_at:Date.now()/1000-1}],agent_run_assignments:[{agent_id:'active',run_id:'ui'}],progress_updates:[{id:'ui-step',run_id:'ui',created:40,current_step:'Review the interface',result:'Checked',next_step:'Finish review',evidence:'Test fixture',completed:2,total:4,unit:'checks'}],activity:[{id:60,task_id:task.id,created:60,stage:'state_changed',message:'Backup is complete'}],events:[{id:60,run_id:'backup',created:60,message:'Backup is complete'}]};
$('task-filter').value=task.id;render(parallelState);
assert.equal($('detail-status').textContent,'Running');
let card=$('task-list').children[0];assert.equal(card.className,'task-card running');assert(textOf(card).includes('Review the interface'));assert(!textOf(card).includes('Backup is complete'));assert(textOf(card).includes('Unfinished runs · 2'));assert(textOf(card).includes('Approve the scope'),'Other waiting run remains inspectable');
assert($('activity-tabs').children[1].textContent.includes('1'),'Unfinished filter agrees with the card');
const noExecution={...parallelState,agents:[],agent_run_assignments:[]};render(noExecution);card=$('task-list').children[0];assert.equal(card.className,'task-card waiting_user');assert.equal($('detail-status').textContent,'Waiting for user');assert(textOf(card).includes('Scope confirmation'));assert(!flatten(card).some(node=>node.tag==='progress'),'Waiting cards do not inherit running measurements');
const taskNote={...parallelState,activity:[{id:70,task_id:task.id,created:70,stage:'review',message:'Task-wide observation'}]};render(taskNote);card=$('task-list').children[0];assert(textOf(card).includes('Latest task update'));assert(textOf(card).includes('Task-wide observation'));assert(!flatten(card).some(node=>node.tag==='progress'));
language='en';
const scheduled=rule=>({platform_observation:{enabled:true,timezone:'Asia/Shanghai',schedule:rule,observed_at:100}});
assert(schedulePlatformView(scheduled('RRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=30')).compact.startsWith('Daily 08:30'));
for(const rule of ['RRULE:FREQ=DAILY;BYHOUR=8;BYDAY=MO,TU','RRULE:FREQ=DAILY;BYHOUR=28','RRULE:FREQ=DAILY;BYHOUR=8;COUNT=2'])assert(schedulePlatformView(scheduled(rule)).compact.startsWith('Recorded schedule;'),'Constrained recurrences never get a misleading daily label');
assert(schedulePlatformView(scheduled('RRULE:FREQ=HOURLY;BYMINUTE=30')).compact.includes('minute 30'));
const css=${JSON.stringify(fs.readFileSync('web/style.css','utf8'))};
assert(css.includes('.activity-toolbar{display:grid;grid-template-columns:minmax(0,1fr) minmax(132px,220px)'));
assert(css.includes('#detail-scroll{scrollbar-gutter:stable;overscroll-behavior:contain;overflow-anchor:none;min-height:0'));
assert(!css.includes('animation:')||!css.includes('infinite'),'No perpetual fake activity animation');
`,context);
console.log('Eight-tab refresh refinements: measured progress, heartbeat distinction, preserved scroll/anchor/disclosures/focus, stable select, responsive toolbar and safe step expansion passed');
